import re
import json
import time
import argparse
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser

import requests
import warnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from dotenv import load_dotenv

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TunisAI/0.1; +https://example.com/bot)"}
DOMAINS = {"tunisia-sat.com", "www.tunisia-sat.com"}
SKIP_PATH_PREFIXES = (
    "/login", "/logout", "/register", "/members", "/account", "/whats-new",
    "/help", "/search", "/tags", "/resources", "/media"
)

EN_STOP = {
    "the","and","for","are","you","your","with","this","that","have","has","from","was","were",
    "not","but","can","all","any","our","out","about","more","will","just","over","into","how",
    "what","when","where","who","why","use","used","using","on","in","at","by","of","to","as",
}

# Load .env from project root (if present)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

def normalize_url(base: str, href: str) -> str | None:
    if not href:
        return None
    if href.startswith("javascript:") or href.startswith("mailto:"):
        return None
    try:
        abs_url = urljoin(base, href)
        abs_url, _ = urldefrag(abs_url)
        p = urlparse(abs_url)
        if p.scheme not in ("http", "https"):
            return None
        if p.netloc not in DOMAINS:
            return None
        return abs_url
    except Exception:
        return None


def setup_robots() -> RobotFileParser | None:
    try:
        rp = RobotFileParser()
        rp.set_url("https://www.tunisia-sat.com/robots.txt")
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
    for tag in soup(["script", "style", "nav", "footer", "noscript", "svg", "form", "iframe"]):
        tag.decompose()
    container = soup.find(["article", "main"]) or soup.body or soup
    parts = []
    for el in container.find_all(["h1", "h2", "h3", "p", "li", "blockquote"], recursive=True):
        txt = el.get_text(" ", strip=True)
        if txt:
            parts.append(txt)
    text = "\n".join(parts)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_sentences(text: str) -> list[str]:
    s = re.split(r"(?<=[.!؟\?؛])\s+", text)
    return [t.strip() for t in s if t.strip()]


def is_thread_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return "/threads/" in p.path
    except Exception:
        return False


def parse_thread_posts(html: str, url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    for art in soup.select("article.message"):
        try:
            pid = art.get("data-content") or art.get("id") or ""
            content = art.select_one("div.bbWrapper") or art
            text = content.get_text(" ", strip=True)
            author_el = art.select_one(".message-name a, a.username")
            author = author_el.get_text(strip=True) if author_el else None
            t = art.select_one("time")
            dt = t.get("datetime") if t else None
            if text and len(text) > 20:
                posts.append({
                    "source": "tunisia-sat",
                    "thread_url": url,
                    "post_id": pid,
                    "author": author,
                    "datetime": dt,
                    "text": text,
                })
        except Exception:
            continue
    # Also try to enqueue explicit next-page link discovery by returning nothing here (handled in crawl)
    return posts


def is_roman_tunisian_token(tok: str) -> bool:
    if len(tok) < 4:
        return False
    if tok in EN_STOP:
        return False
    if tok.isdigit():
        return False
    # arabizi often mixes digits 2/3/5/6/7/8/9, but also pure letters like 'barcha'
    if re.search(r"[2395678]", tok):
        return True
    return any(p in tok for p in ["barcha", "barsha", "toun", "touns", "tunsi", "3lech", "9a", "7keya", "9leb", "9rit", "9al", "7aja", "khater", "ma3lich"]) 


def extract_tokens(text: str) -> tuple[list[str], list[str]]:
    ar = re.findall(r"[\u0600-\u06FF]{2,}", text)
    roman_all = [t.lower() for t in re.findall(r"[A-Za-z0-9]{3,}", text)]
    roman = [t for t in roman_all if is_roman_tunisian_token(t)]
    return ar, roman


def crawl_and_extract(max_pages: int, delay: float = 0.15):
    start = "https://www.tunisia-sat.com/"
    rp = setup_robots()
    q = [start]
    seen = set()

    freq = {}
    samples = {}
    raw_pages = []
    posts = []

    while q and len(seen) < max_pages:
        url = q.pop(0)
        if url in seen:
            continue
        seen.add(url)
        if not allowed(rp, url):
            continue
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200 or not r.text:
                continue
            # If it's a thread page, extract structured posts/comments
            if is_thread_url(url):
                p = parse_thread_posts(r.text, url)
                if p:
                    posts.extend(p)
                    # Count tokens from posts to enrich vocab with actual comments
                    def add_token_with_sents(tkn, script, sents_local):
                        freq[tkn] = freq.get(tkn, 0) + 1
                        if tkn not in samples:
                            ss = []
                            for s in sents_local:
                                if tkn in s:
                                    ss.append(s)
                                if len(ss) >= 3:
                                    break
                            samples[tkn] = {"script": script, "examples": ss}
                    for po in p:
                        psents = split_sentences(po.get("text", ""))
                        if not psents:
                            continue
                        par, prom = extract_tokens(po.get("text", ""))
                        for t in par:
                            add_token_with_sents(t, "arabic", psents)
                        for t in prom:
                            add_token_with_sents(t, "roman", psents)
            text = extract_text(r.text)
            if text:
                raw_pages.append({"url": url, "text": text})
                ar, roman = extract_tokens(text)
                sents = split_sentences(text)
                def add_token(tkn, script):
                    freq[tkn] = freq.get(tkn, 0) + 1
                    if tkn not in samples:
                        ss = []
                        for s in sents:
                            if tkn in s:
                                ss.append(s)
                            if len(ss) >= 3:
                                break
                        samples[tkn] = {"script": script, "examples": ss}
                for t in ar:
                    add_token(t, "arabic")
                for t in roman:
                    add_token(t, "roman")

            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                nxt = normalize_url(url, a['href'])
                if not nxt or nxt in seen:
                    continue
                # Skip noise paths (auth/help/search/etc.)
                try:
                    p = urlparse(nxt)
                    if any(p.path.startswith(sp) for sp in SKIP_PATH_PREFIXES):
                        continue
                except Exception:
                    pass
                # Prioritize threads for richer content
                if is_thread_url(nxt):
                    q.insert(0, nxt)
                else:
                    q.append(nxt)
            # Prefer explicit next-page links on threads
            if is_thread_url(url):
                nxt = soup.select_one('a[rel="next"], .pageNav-page--next a')
                if nxt:
                    nurl = normalize_url(url, nxt.get('href'))
                    if nurl and nurl not in seen:
                        q.insert(0, nurl)
            time.sleep(delay)
        except Exception:
            continue

    return freq, samples, raw_pages, posts


def save_outputs(freq: dict, samples: dict, raw_pages: list, posts: list, out_vocab: Path, out_raw: Path, out_posts: Path):
    out_vocab.parent.mkdir(parents=True, exist_ok=True)
    out_raw.parent.mkdir(parents=True, exist_ok=True)
    out_posts.parent.mkdir(parents=True, exist_ok=True)

    vocab = []
    for w, c in sorted(freq.items(), key=lambda x: x[1], reverse=True):
        s = samples.get(w, {})
        vocab.append({"word": w, "count": c, "script": s.get("script"), "examples": s.get("examples", [])})
    with open(out_vocab, "w", encoding="utf-8") as f:
        json.dump({"site": "tunisia-sat.com", "total_words": len(vocab), "vocab": vocab}, f, ensure_ascii=False, indent=2)

    with open(out_raw, "w", encoding="utf-8") as f:
        for p in raw_pages:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    with open(out_posts, "w", encoding="utf-8") as f:
        for p in posts:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max_pages", type=int, default=200)
    ap.add_argument("--out_vocab", type=str, default=str(Path("tunisai")/"data"/"processed"/"tunisia_sat_words.json"))
    ap.add_argument("--out_raw", type=str, default=str(Path("tunisai")/"data"/"raw"/"tunisia_sat_pages.jsonl"))
    ap.add_argument("--out_posts", type=str, default=str(Path("tunisai")/"data"/"raw"/"tunisia_sat_posts.jsonl"))
    args = ap.parse_args()

    freq, samples, raw_pages, posts = crawl_and_extract(max_pages=args.max_pages)
    save_outputs(freq, samples, raw_pages, posts, Path(args.out_vocab), Path(args.out_raw), Path(args.out_posts))
