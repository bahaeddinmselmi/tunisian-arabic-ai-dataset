import os
import json
import time
import argparse
import requests
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

API_KEY = os.getenv("GOOGLE_API_KEY")
CX = os.getenv("GOOGLE_CX")

robots_cache = {}

def robots_allowed(url: str) -> bool:
    try:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in robots_cache:
            r = RobotFileParser()
            r.set_url(base + "/robots.txt")
            try:
                r.read()
            except Exception:
                robots_cache[base] = None
            else:
                robots_cache[base] = r
        r = robots_cache.get(base)
        if r is None:
            return True
        return r.can_fetch("*", url)
    except Exception:
        return False


def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    texts = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    return "\n".join([t for t in texts if t])


def cse_search(query: str, num: int):
    url = "https://www.googleapis.com/customsearch/v1"
    start = 1
    fetched = 0
    while fetched < num:
        params = {
            "key": API_KEY,
            "cx": CX,
            "q": query,
            "start": start,
        }
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            raise SystemExit(f"CSE error {resp.status_code}: {resp.text}")
        data = resp.json()
        items = data.get("items", [])
        if not items:
            break
        for it in items:
            yield it
            fetched += 1
            if fetched >= num:
                break
        start += 10
        time.sleep(0.2)


def collect(query: str, out_path: str, num: int, site: list[str] | None):
    os.makedirs(Path(out_path).parent, exist_ok=True)
    if site:
        parts = [f"site:{s}" for s in site]
        query = f"{query} {' OR '.join(parts)}"
    with open(out_path, "w", encoding="utf-8") as f:
        for it in cse_search(query, num):
            link = it.get("link")
            title = it.get("title")
            snippet = it.get("snippet")
            if not link or not robots_allowed(link):
                continue
            try:
                r = requests.get(link, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code != 200 or not r.text:
                    continue
                text = extract_text(r.text)
            except Exception:
                continue
            obj = {"source": "google_cse", "query": query, "title": title, "link": link, "snippet": snippet, "text": text}
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", type=str, required=True)
    parser.add_argument("--num", type=int, default=30)
    parser.add_argument("--site", type=str, help="Comma-separated domains to restrict, e.g., gov.tn,*.tn")
    parser.add_argument("--out", type=str, default="data/raw/google_cse.jsonl")
    args = parser.parse_args()

    if not (API_KEY and CX):
        raise SystemExit("Missing GOOGLE_API_KEY or GOOGLE_CX in environment.")
    site = [s.strip() for s in args.site.split(",")] if args.site else None
    collect(args.query, args.out, args.num, site)
