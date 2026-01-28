import os
import re
import json
import argparse
import random
from pathlib import Path
from typing import List, Dict

SYSTEM_PROMPT = "انت معاون ذكي تحكي بالدّارجة التونسية وببساطة."


def read_jsonl(path: str):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def normalize_text(s: str) -> str:
    s = (s or "").replace("\r", " ")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"([!?.،])\1{2,}", r"\1\1", s)
    return s.strip()


def build_transcript_text(segments: List[Dict]) -> str:
    parts = []
    for seg in segments:
        t = seg.get("text")
        if not t or t in ("[Music]", "[Applause]"):
            continue
        parts.append(t)
    return normalize_text(" ".join(parts))


def split_sentences(text: str) -> List[str]:
    # Lightweight sentence split for mixed Arabic/French/English
    sents = re.split(r"(?<=[.!؟\?])\s+", text)
    sents = [normalize_text(s) for s in sents if len(normalize_text(s)) > 0]
    return sents


def top_k_sentences(text: str, k: int = 5, min_len: int = 24) -> List[str]:
    sents = split_sentences(text)
    if not sents:
        return []
    # Scoring: length-normalized frequency of non-stopword terms (very simple)
    # Build term freq
    freq: Dict[str, int] = {}
    for s in sents:
        for tok in re.findall(r"[\w\u0600-\u06FF]+", s.lower()):
            if len(tok) <= 2:
                continue
            freq[tok] = freq.get(tok, 0) + 1
    scored = []
    for s in sents:
        if len(s) < min_len:
            continue
        score = 0.0
        for tok in re.findall(r"[\w\u0600-\u06FF]+", s.lower()):
            if len(tok) <= 2:
                continue
            score += freq.get(tok, 0)
        score = score / max(1, len(s))
        scored.append((score, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = [s for _, s in scored[:k]]
    # Ensure unique and preserve original order
    uniq = []
    seen = set()
    for s in sents:
        if s in out and s not in seen:
            uniq.append(s)
            seen.add(s)
            if len(uniq) >= len(out):
                break
    return uniq


def to_chat(samples: List[dict], out_path: str):
    with open(out_path, "w", encoding="utf-8") as w:
        for obj in samples:
            w.write(json.dumps(obj, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_file", type=str, default=str(Path("tunisai")/"data"/"raw"/"youtube_transcripts.jsonl"))
    ap.add_argument("--out_dir", type=str, default=str(Path("tunisai")/"data"/"splits"))
    ap.add_argument("--val_ratio", type=float, default=0.1)
    ap.add_argument("--min_transcript_chars", type=int, default=400)
    ap.add_argument("--bullets_k", type=int, default=5)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    items = list(read_jsonl(args.in_file))
    pairs: List[dict] = []

    for it in items:
        segs = it.get("segments") or []
        text = build_transcript_text(segs)
        if len(text) < args.min_transcript_chars:
            continue
        title = normalize_text(it.get("title") or "")
        bullets = top_k_sentences(text, k=args.bullets_k)
        if not bullets:
            continue
        # Sample 1: bullet summary in Derja
        user_1 = (
            "لخّصلي الفيديو هذا بالنّقاط وبالدّارجة التونسية.\n"
            "النّص:\n" + text
        )
        assistant_1 = "\n".join([f"- {b}" for b in bullets])
        pairs.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_1},
                {"role": "assistant", "content": assistant_1},
            ],
            "meta": {"source": it.get("url"), "video_id": it.get("video_id"), "task": "bullets"},
        })
        # Sample 2: title-style summary if we have a title
        if title:
            user_2 = (
                "أعطيني عنوان مختصر يعبّر على محتوى الفيديو هذا بالدّارجة التونسية.\n"
                "النّص:\n" + text
            )
            # Use provided title as pseudo-gold (can be in any language)
            pairs.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_2},
                    {"role": "assistant", "content": title},
                ],
                "meta": {"source": it.get("url"), "video_id": it.get("video_id"), "task": "title"},
            })

    if not pairs:
        raise SystemExit("No pairs built from transcripts")

    random.seed(42)
    random.shuffle(pairs)
    n = len(pairs)
    n_val = max(1, int(n * args.val_ratio))
    val = pairs[:n_val]
    train = pairs[n_val:]

    train_out = str(Path(args.out_dir)/"yt_train.jsonl")
    val_out = str(Path(args.out_dir)/"yt_val.jsonl")
    to_chat(train, train_out)
    to_chat(val, val_out)
    print(f"Wrote train: {len(train)} -> {train_out}")
    print(f"Wrote val:   {len(val)} -> {val_out}")


if __name__ == "__main__":
    main()
