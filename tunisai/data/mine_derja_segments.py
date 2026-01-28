import argparse
import json
from pathlib import Path
from typing import Dict, Iterable

from derja_detector import score_derja, is_likely_derja


DATA_DIR = Path(__file__).resolve().parent


def read_jsonl(path: Path) -> Iterable[Dict]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def split_sentences(text: str):
    # Lightweight split that works OK for mixed Arabic/Latin
    import re

    sents = re.split(r"(?<=[.!؟\?؛])\s+", text)
    return [s.strip() for s in sents if s and len(s.strip()) >= 5]


def mine_from_chat_file(path: Path, min_score: float, tag: str):
    for obj in read_jsonl(path):
        msgs = obj.get("messages") or []
        if not isinstance(msgs, list):
            continue
        meta = obj.get("meta") or {}
        for m in msgs:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            content = (m.get("content") or "").strip()
            if not content or len(content) < 5:
                continue
            sc = score_derja(content)
            if sc["score"] < min_score:
                continue
            yield {
                "text": content,
                "role": role,
                "source": tag,
                "orig_file": str(path),
                "score": sc["score"],
                "tokens": sc["tokens"],
                "meta": meta,
            }


def mine_from_text_file(path: Path, text_key: str, min_score: float, tag: str):
    for obj in read_jsonl(path):
        text = (obj.get(text_key) or "").strip()
        if not text:
            continue
        meta = {k: v for k, v in obj.items() if k not in {text_key}}
        for sent in split_sentences(text):
            sc = score_derja(sent)
            if sc["score"] < min_score:
                continue
            yield {
                "text": sent,
                "role": None,
                "source": tag,
                "orig_file": str(path),
                "score": sc["score"],
                "tokens": sc["tokens"],
                "meta": meta,
            }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out_file", type=str, default=str(DATA_DIR / "derja_segments_raw.jsonl"))
    ap.add_argument("--min_score", type=float, default=0.12, help="Minimum Derja score to keep a segment")
    ap.add_argument("--max_segments", type=int, default=100000, help="Hard cap on number of mined segments")
    ap.add_argument("--include_reddit", action="store_true")
    ap.add_argument("--include_youtube", action="store_true")
    ap.add_argument("--include_tunizi", action="store_true")
    ap.add_argument("--include_sites", action="store_true", help="Use sites_tunisiya_derja + derja_ninja_pages")
    ap.add_argument("--extra_jsonl", type=str, nargs="*", default=[], help="Additional JSONL chat files to scan")
    args = ap.parse_args()

    out_path = Path(args.out_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    sources = []
    splits = DATA_DIR / "splits"

    if args.include_tunizi:
        sources.append((splits / "tunizi_train.jsonl", "chat" , "tunizi"))
        sources.append((splits / "tunizi_val.jsonl", "chat" , "tunizi"))
    if args.include_reddit:
        sources.append((splits / "reddit_train.jsonl", "chat" , "reddit"))
        sources.append((splits / "reddit_val.jsonl", "chat" , "reddit"))
    if args.include_youtube:
        sources.append((splits / "yt_train.jsonl", "chat" , "youtube"))
        sources.append((splits / "yt_val.jsonl", "chat" , "youtube"))
    if args.include_sites:
        sources.append((DATA_DIR / "raw" / "sites_tunisiya_derja.jsonl", "text", "sites"))
        sources.append((DATA_DIR / "raw" / "derja_ninja_pages.jsonl", "text", "derja_ninja"))

    for p_str in args.extra_jsonl:
        p = Path(p_str)
        sources.append((p, "chat", p.name))

    n_written = 0
    with out_path.open("w", encoding="utf-8") as w:
        for path, kind, tag in sources:
            if not path.exists():
                continue
            if kind == "chat":
                gen = mine_from_chat_file(path, args.min_score, tag)
            else:
                gen = mine_from_text_file(path, "text", args.min_score, tag)
            for rec in gen:
                w.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n_written += 1
                if n_written >= args.max_segments:
                    print(f"Reached max_segments={args.max_segments}, stopping.")
                    print(f"Wrote {n_written} segments -> {out_path}")
                    return

    print(f"Wrote {n_written} segments -> {out_path}")


if __name__ == "__main__":
    main()
