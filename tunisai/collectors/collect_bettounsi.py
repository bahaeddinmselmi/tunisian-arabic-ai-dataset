import re
import json
import time
import argparse
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TunisAI/0.1; +https://example.com/bot)"}
DOMAINS = {"bettounsi.com", "www.bettounsi.com"}

EN_STOP = {
    "the","and","for","are","you","your","with","this","that","have","has","from","was","were",
    "not","but","can","all","any","our","out","about","more","will","just","over","into","how",
    "what","when","where","who","why","use","used","using","on","in","at","by","of","to","as",
}


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
        rp.set_url("https://www.bettounsi.com/robots.txt")
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
    for el in container.find_all(["h1", "h2", "h3", "p", "li"], recursive=True):
        txt = el.get_text(" ", strip=True)
        if txt:
            parts.append(txt)
    text = "\n".join(parts)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_sentences(text: str) -> list[str]:
    s = re.split(r"(?<=[.!؟\?؛])\s+", text)
    return [t.strip() for t in s if t.strip()]


def is_roman_tunisian_token(tok: str) -> bool:
    if len(tok) < 4:
        return False
    if tok in EN_STOP:
        return False
    # arabizi often mixes digits 2/3/5/6/7/8/9, but also pure letters like 'barcha'
    if re.search(r"[2395678]", tok):
        return True
    # heuristic: contains at least one of common tunisian letter sequences
    return any(p in tok for p in ["barcha", "barsha", "toun", "touns", "tunsi", "3lech", "9a", "7keya", "9leb", "9rit"])


def extract_tokens(text: str) -> tuple[list[str], list[str]]:
    # Arabic tokens
    ar = re.findall(r"[\u0600-\u06FF]{2,}", text)
    # Romanized (arabizi/latin)
    roman_all = [t.lower() for t in re.findall(r"[A-Za-z0-9]{3,}", text)]
    roman = [t for t in roman_all if is_roman_tunisian_token(t)]
    return ar, roman


def crawl_and_extract(max_pages: int, delay: float = 0.2):
    start = "https://www.bettounsi.com/"
    rp = setup_robots()
    q = [start]
    seen = set()

    freq = {}
    samples = {}

    raw_pages = []

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
            text = extract_text(r.text)
            if text:
                raw_pages.append({"url": url, "text": text})
                ar, roman = extract_tokens(text)
                # Count and sample contexts
                sents = split_sentences(text)
                def add_token(tkn, script):
                    freq[tkn] = freq.get(tkn, 0) + 1
                    if tkn not in samples:
                        # collect up to 3 sentences containing token
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

            # enqueue same-domain links
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                nxt = normalize_url(url, a['href'])
                if nxt and nxt not in seen:
                    q.append(nxt)
            time.sleep(delay)
        except Exception:
            continue

    return freq, samples, raw_pages


def save_outputs(freq: dict, samples: dict, raw_pages: list, out_vocab: Path, out_raw: Path):
    out_vocab.parent.mkdir(parents=True, exist_ok=True)
    out_raw.parent.mkdir(parents=True, exist_ok=True)

    vocab = []
    for w, c in sorted(freq.items(), key=lambda x: x[1], reverse=True):
        s = samples.get(w, {})
        vocab.append({"word": w, "count": c, "script": s.get("script"), "examples": s.get("examples", [])})
    with open(out_vocab, "w", encoding="utf-8") as f:
        json.dump({"site": "bettounsi.com", "total_words": len(vocab), "vocab": vocab}, f, ensure_ascii=False, indent=2)

    with open(out_raw, "w", encoding="utf-8") as f:
        for p in raw_pages:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max_pages", type=int, default=120)
    ap.add_argument("--out_vocab", type=str, default=str(Path("tunisai")/"data"/"processed"/"bettounsi_words.json"))
    ap.add_argument("--out_raw", type=str, default=str(Path("tunisai")/"data"/"raw"/"bettounsi_pages.jsonl"))
    args = ap.parse_args()

    freq, samples, raw_pages = crawl_and_extract(max_pages=args.max_pages)
    save_outputs(freq, samples, raw_pages, Path(args.out_vocab), Path(args.out_raw))
