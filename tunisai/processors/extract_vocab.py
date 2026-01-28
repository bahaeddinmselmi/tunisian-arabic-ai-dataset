import re
import json
import argparse
from pathlib import Path


def split_sentences(text: str) -> list[str]:
    s = re.split(r"(?<=[.!؟\?؛])\s+", text)
    return [t.strip() for t in s if t.strip()]


def is_roman_tunisian_token(tok: str) -> bool:
    if len(tok) < 3:
        return False
    if tok.isdigit():
        return False
    if re.search(r"[2395678]", tok):
        return True
    return any(p in tok.lower() for p in [
        "barcha", "barsha", "toun", "touns", "tunsi", "3lech", "9", "7",
        "kh", "gh", "ch", "sh", "s7i7", "mouch", "tawa", "bech", "nheb",
    ])


def extract_tokens(text: str):
    ar = re.findall(r"[\u0600-\u06FF]{2,}", text)
    roman_all = [t.lower() for t in re.findall(r"[A-Za-z0-9]{3,}", text)]
    roman = [t for t in roman_all if is_roman_tunisian_token(t)]
    return ar, roman


def extract_cards_like(text: str, url: str) -> list[dict]:
    cards = []
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for i in range(len(lines) - 2):
        en = lines[i]
        ar = lines[i + 1]
        ro = lines[i + 2]
        if re.search(r"[\u0600-\u06FF]", ar) and re.search(r"[2395678]", ro):
            if len(en) >= 5 and len(ar) >= 2:
                cards.append({
                    "source": "raw",
                    "url": url,
                    "english": en,
                    "arabic": ar,
                    "roman": ro
                })
    return cards


def build_vocab_from_raw(in_path: Path, out_vocab: Path, out_cards: Path | None, site_name: str | None):
    freq: dict[str, int] = {}
    samples: dict[str, dict] = {}
    cards: list[dict] = []

    with open(in_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            text = obj.get("text") or obj.get("body") or obj.get("content") or ""
            url = obj.get("url") or obj.get("link") or ""
            if not text:
                continue
            ar, roman = extract_tokens(text)
            sents = split_sentences(text)
            def add_token(tkn: str, script: str):
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
            # Try card-like triples
            if out_cards is not None:
                cards.extend(extract_cards_like(text, url))

    vocab = []
    for w, c in sorted(freq.items(), key=lambda x: x[1], reverse=True):
        s = samples.get(w, {})
        vocab.append({"word": w, "count": c, "script": s.get("script"), "examples": s.get("examples", [])})

    out_vocab.parent.mkdir(parents=True, exist_ok=True)
    with open(out_vocab, "w", encoding="utf-8") as f:
        json.dump({"site": site_name or "raw", "total_words": len(vocab), "vocab": vocab}, f, ensure_ascii=False, indent=2)

    if out_cards is not None:
        out_cards.parent.mkdir(parents=True, exist_ok=True)
        with open(out_cards, "w", encoding="utf-8") as f:
            for c in cards:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", type=str, required=True, help="Input raw JSONL with a 'text' field")
    ap.add_argument("--out_vocab", type=str, required=True)
    ap.add_argument("--out_cards", type=str, default="")
    ap.add_argument("--site", type=str, default="raw")
    args = ap.parse_args()

    in_path = Path(args.in_path)
    out_vocab = Path(args.out_vocab)
    out_cards = Path(args.out_cards) if args.out_cards else None

    build_vocab_from_raw(in_path, out_vocab, out_cards, args.site)
