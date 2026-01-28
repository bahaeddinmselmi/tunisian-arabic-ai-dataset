import os
import re
import json
import time
import queue
import argparse
from pathlib import Path
from urllib.parse import urlparse, urljoin, urldefrag
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TunisAI/0.1; +https://example.com/bot)"}


def normalize_url(base: str, href: str) -> str | None:
    if not href:
        return None
    try:
        if href.startswith("javascript:") or href.startswith("mailto:"):
            return None
        abs_url = urljoin(base, href)
        abs_url, _ = urldefrag(abs_url)
        p = urlparse(abs_url)
        if p.scheme not in ("http", "https"):
            return None
        return abs_url
    except Exception:
        return None


def setup_robots(domain: str) -> RobotFileParser | None:
    try:
        rp = RobotFileParser()
        rp.set_url(f"https://{domain}/robots.txt")
        rp.read()
        return rp
    except Exception:
        return None


def allowed(rp: RobotFileParser | None, url: str) -> bool:
    if rp is None:
        return True
    try:
        return rp.can_fetch("*", url)
    except Exception:
        return False


def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Remove script/style/nav/footer
    for tag in soup(["script", "style", "nav", "footer", "noscript"]):
        tag.decompose()
    # Prefer article/main; fallback to body
    container = soup.find(["article", "main"]) or soup.body or soup
    # Grab paragraphs and list items
    parts = []
    for el in container.find_all(["h1", "h2", "h3", "p", "li"], recursive=True):
        txt = el.get_text(" ", strip=True)
        if txt:
            parts.append(txt)
    text = "\n".join(parts)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def crawl(start_urls: list[str], domains: list[str], max_pages: int, out_path: str, delay: float = 0.2):
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    domain_set = set(domains) if domains else set(urlparse(u).netloc for u in start_urls)
    robots_map: dict[str, RobotFileParser | None] = {d: setup_robots(d) for d in domain_set}

    seen: set[str] = set()
    q: queue.Queue[str] = queue.Queue()
    for u in start_urls:
        q.put(u)

    written = 0
    with open(out_path, "w", encoding="utf-8") as f:
        while not q.empty() and written < max_pages:
            url = q.get()
            if url in seen:
                continue
            seen.add(url)
            dom = urlparse(url).netloc
            if not any(dom.endswith(d) for d in domain_set):
                continue
            rp = None
            for d in domain_set:
                if dom.endswith(d):
                    rp = robots_map.get(d)
                    break
            if not allowed(rp, url):
                continue
            try:
                r = requests.get(url, headers=HEADERS, timeout=30)
                if r.status_code != 200 or not r.text:
                    continue
                text = extract_text(r.text)
                if text:
                    title = None
                    try:
                        title = BeautifulSoup(r.text, "html.parser").title
                        title = title.get_text(strip=True) if title else None
                    except Exception:
                        title = None
                    f.write(json.dumps({
                        "source": "site",
                        "domain": dom,
                        "url": url,
                        "title": title,
                        "text": text
                    }, ensure_ascii=False) + "\n")
                    written += 1
                # enqueue links
                if written < max_pages:
                    soup = BeautifulSoup(r.text, "html.parser")
                    for a in soup.find_all("a", href=True):
                        nxt = normalize_url(url, a['href'])
                        if nxt and nxt not in seen:
                            nxt_dom = urlparse(nxt).netloc
                            if any(nxt_dom.endswith(d) for d in domain_set) and allowed(rp, nxt):
                                q.put(nxt)
                time.sleep(delay)
            except Exception:
                continue


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start_urls", type=str, required=True, help="Comma-separated seed URLs")
    ap.add_argument("--domains", type=str, help="Comma-separated domains to keep (optional)")
    ap.add_argument("--max_pages", type=int, default=100)
    ap.add_argument("--out", type=str, default="data/raw/sites.jsonl")
    args = ap.parse_args()

    starts = [s.strip() for s in args.start_urls.split(",") if s.strip()]
    domains = [d.strip() for d in args.domains.split(",")] if args.domains else []
    crawl(starts, domains, args.max_pages, args.out)
