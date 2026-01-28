import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

sys.path.append(str(DATA_DIR))
from derja_detector import score_derja

try:
    from collect_derja_ninja import extract_text as _extract_text, split_sentences as _split_sentences
except Exception:
    _extract_text = None
    _split_sentences = None


def extract_text(html: str) -> str:
    if _extract_text is not None:
        return _extract_text(html)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "noscript", "svg", "form", "iframe"]):
        tag.decompose()
    container = soup.body or soup
    parts = []
    for el in container.find_all(["h1", "h2", "h3", "p", "li", "blockquote"], recursive=True):
        txt = el.get_text(" ", strip=True)
        if txt:
            parts.append(txt)
    text = " ".join(parts)
    return text


def split_sentences(text: str) -> list[str]:
    if _split_sentences is not None:
        return _split_sentences(text)
    s = re.split(r"(?<=[.!؟\?؛])\s+", text)
    return [t.strip() for t in s if t.strip()]


def serpapi_search(query: str, api_key: str, max_results: int) -> list[str]:
    params = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "num": max_results,
    }
    try:
        r = requests.get("https://serpapi.com/search.json", params=params, timeout=30)
    except Exception:
        return []
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except Exception:
        return []
    urls: list[str] = []
    for item in data.get("organic_results", []):
        link = item.get("link")
        if link:
            urls.append(link)
    return urls


def fetch_html(url: str, timeout: float = 30.0) -> str | None:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TunisAI/0.1; +https://example.com/bot)"}
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
    except Exception:
        return None
    if r.status_code != 200 or not r.text:
        return None
    return r.text


def mine_from_url(
    url: str,
    query: str,
    min_score: float,
    max_segments: int,
    source_tag: str,
    out_f,
) -> int:
    html = fetch_html(url)
    if not html:
        return 0
    text = extract_text(html)
    if not text:
        return 0
    sents = split_sentences(text)
    if not sents:
        return 0
    domain = urlparse(url).netloc
    written = 0
    for s in sents:
        sc = score_derja(s)
        if sc["score"] < min_score:
            continue
        rec = {
            "text": s,
            "role": None,
            "source": source_tag,
            "orig_file": url,
            "score": float(sc["score"]),
            "tokens": float(sc["tokens"]),
            "meta": {"url": url, "query": query, "domain": domain},
        }
        out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        written += 1
        if written >= max_segments:
            break
    return written


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", type=str, nargs="*", default=[])
    ap.add_argument("--max_results_per_query", type=int, default=10)
    ap.add_argument("--min_score", type=float, default=0.12)
    ap.add_argument("--max_segments", type=int, default=50000)
    ap.add_argument("--out_file", type=str, default=str(DATA_DIR / "derja_segments_raw.jsonl"))
    ap.add_argument("--serpapi_api_key", type=str, default="")
    args = ap.parse_args()

    api_key = args.serpapi_api_key or os.getenv("SERPAPI_API_KEY") or ""
    if not api_key:
        raise SystemExit("SERPAPI_API_KEY is not set. Provide --serpapi_api_key or set the environment variable.")

    queries = args.queries
    if not queries:
        queries = [
            "تونسية بالدارجة",
            "اللهجة التونسية الدارجة",
            "كلام تونسي بالدارجة",
            "derja tounsi",
            "darija tounsi",
        ]

    out_path = Path(args.out_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total_written = 0
    with out_path.open("a", encoding="utf-8") as f:
        for q in queries:
            if total_written >= args.max_segments:
                break
            urls = serpapi_search(q, api_key, args.max_results_per_query)
            for url in urls:
                if total_written >= args.max_segments:
                    break
                remaining = args.max_segments - total_written
                n = mine_from_url(
                    url=url,
                    query=q,
                    min_score=args.min_score,
                    max_segments=remaining,
                    source_tag="web_search",
                    out_f=f,
                )
                total_written += n

    print(f"Wrote {total_written} segments to {out_path}")


if __name__ == "__main__":
    main()
