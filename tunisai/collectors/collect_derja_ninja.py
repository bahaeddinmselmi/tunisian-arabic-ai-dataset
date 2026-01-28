import re
import json
import time
import argparse
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TunisAI/0.1; +https://example.com/bot)"}
DOMAINS = {"derja.ninja", "www.derja.ninja"}
SKIP_PATH_PREFIXES = ("/about", "/contact", "/privacy", "/terms")

EN_STOP = {
    "the","and","for","are","you","your","with","this","that","have","has","from","was","were",
    "not","but","can","all","any","our","out","about","more","will","just","over","into","how",
    "what","when","where","who","why","use","used","using","on","in","at","by","of","to","as",
}

# Load .env from project root (if present)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


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
        # Skip some obvious non-content paths
        if any(p.path.startswith(sp) for sp in SKIP_PATH_PREFIXES):
            return None
        return abs_url
    except Exception:
        return None


essential_selectors = ["main", "article", "#content", ".site-content"]

def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "noscript", "svg", "form", "iframe"]):
        tag.decompose()
    container = None
    for sel in essential_selectors:
        container = soup.select_one(sel)
        if container:
            break
    if container is None:
        container = soup.body or soup
    parts = []
    for el in container.find_all(["h1", "h2", "h3", "p", "li", "blockquote"], recursive=True):
        txt = el.get_text(" ", strip=True)
        if txt:
            parts.append(txt)
    text = "\n".join(parts)
    text = re.sub(r"\s+", " ", text).strip()
    # Reintroduce newlines between major blocks for card detection
    text = text.replace(" . ", ".\n")
    return text


def split_sentences(text: str) -> list[str]:
    s = re.split(r"(?<=[.!؟\?؛])\s+", text)
    return [t.strip() for t in s if t.strip()]


def is_roman_tunisian_token(tok: str) -> bool:
    if len(tok) < 3:
        return False
    if tok.lower() in EN_STOP:
        return False
    if tok.isdigit():
        return False
    if re.search(r"[2395678]", tok):
        return True
    return any(p in tok.lower() for p in ["barcha", "barsha", "toun", "touns", "tunsi", "3lech", "9", "7", "kh", "gh", "ch", "sh"]) 


def extract_tokens(text: str) -> tuple[list[str], list[str]]:
    ar = re.findall(r"[\u0600-\u06FF]{2,}", text)
    roman_all = [t.lower() for t in re.findall(r"[A-Za-z0-9]{3,}", text)]
    roman = [t for t in roman_all if is_roman_tunisian_token(t)]
    return ar, roman


def extract_cards_from_text(text: str, url: str) -> list[dict]:
    cards = []
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for i in range(len(lines) - 2):
        en = lines[i]
        ar = lines[i + 1]
        ro = lines[i + 2]
        if re.search(r"[\u0600-\u06FF]", ar) and re.fullmatch(r"[A-Za-z0-9 '\-]+", ro) and re.search(r"[2395678]", ro):
            if len(en) >= 5 and len(ar) >= 2:
                cards.append({
                    "source": "derja.ninja",
                    "url": url,
                    "english": en,
                    "arabic": ar,
                    "roman": ro
                })
    # Also try to capture explicit "Word of the day:" blocks
    m = re.search(r"Word of the day:\s*(.*?)\s+([\u0600-\u06FF].*?)\s+([A-Za-z0-9 '\-]+)", text)
    if m:
        en, ar, ro = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        if re.search(r"[2395678]", ro):
            cards.append({"source": "derja.ninja", "url": url, "english": en, "arabic": ar, "roman": ro})
    return cards


def crawl_and_extract(max_pages: int, delay: float = 0.15):
    start = "https://derja.ninja/"
    rp = setup_robots()
    q = [start]
    seen = set()

    freq = {}
    samples = {}
    raw_pages = []
    cards = []

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
                # tokens
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
                # flashcards
                cards.extend(extract_cards_from_text(text, url))

            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                nxt = normalize_url(url, a['href'])
                if nxt and nxt not in seen:
                    q.append(nxt)
            time.sleep(delay)
        except Exception:
            continue

    return freq, samples, raw_pages, cards


def setup_robots() -> RobotFileParser | None:
    try:
        rp = RobotFileParser()
        rp.set_url("https://derja.ninja/robots.txt")
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


def save_outputs(freq: dict, samples: dict, raw_pages: list, cards: list, out_vocab: Path, out_raw: Path, out_cards: Path):
    out_vocab.parent.mkdir(parents=True, exist_ok=True)
    out_raw.parent.mkdir(parents=True, exist_ok=True)
    out_cards.parent.mkdir(parents=True, exist_ok=True)

    vocab = []
    for w, c in sorted(freq.items(), key=lambda x: x[1], reverse=True):
        s = samples.get(w, {})
        vocab.append({"word": w, "count": c, "script": s.get("script"), "examples": s.get("examples", [])})
    with open(out_vocab, "w", encoding="utf-8") as f:
        json.dump({"site": "derja.ninja", "total_words": len(vocab), "vocab": vocab}, f, ensure_ascii=False, indent=2)

    with open(out_raw, "w", encoding="utf-8") as f:
        for p in raw_pages:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    with open(out_cards, "w", encoding="utf-8") as f:
        for c in cards:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max_pages", type=int, default=150)
    ap.add_argument("--out_vocab", type=str, default=str(Path("tunisai")/"data"/"processed"/"derja_ninja_words.json"))
    ap.add_argument("--out_raw", type=str, default=str(Path("tunisai")/"data"/"raw"/"derja_ninja_pages.jsonl"))
    ap.add_argument("--out_cards", type=str, default=str(Path("tunisai")/"data"/"raw"/"derja_ninja_cards.jsonl"))
    args = ap.parse_args()

    freq, samples, raw_pages, cards = crawl_and_extract(max_pages=args.max_pages)
    save_outputs(freq, samples, raw_pages, cards, Path(args.out_vocab), Path(args.out_raw), Path(args.out_cards))
