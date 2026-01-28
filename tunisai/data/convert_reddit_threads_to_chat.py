import os
import re
import json
import argparse
import random
from pathlib import Path
from typing import Dict, List, Tuple

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


def clean_text(t: str) -> str:
    t = (t or "").replace("\r", "").strip()
    # remove obvious placeholders
    if t in ("[deleted]", "[removed]"):
        return ""
    # collapse whitespace
    t = re.sub(r"\s+", " ", t)
    # collapse excessive punctuation (keep two max)
    t = re.sub(r"([!?.،])\1{2,}", r"\1\1", t)
    return t.strip()


def build_pairs(posts_path: str, comments_path: str, min_len: int, min_score: int) -> List[Tuple[dict, dict]]:
    posts_by_url: Dict[str, dict] = {}
    for p in read_jsonl(posts_path):
        url = p.get("url") or p.get("comments_url") or p.get("post_url")
        if not url:
            continue
        title = clean_text(p.get("title", ""))
        selftext = clean_text(p.get("selftext", ""))
        if not title and not selftext:
            continue
        posts_by_url[url] = {
            "title": title,
            "selftext": selftext,
            "subreddit": p.get("subreddit"),
            "created_utc": p.get("created_utc"),
            "url": url,
        }

    grouped: Dict[str, List[dict]] = {}
    for c in read_jsonl(comments_path):
        url = c.get("post_url")
        if not url or url not in posts_by_url:
            continue
        body = clean_text(c.get("body", ""))
        if len(body) < min_len:
            continue
        score = int(c.get("score") or 0)
        if score < min_score:
            continue
        if body.lower() in ("[deleted]", "[removed]"):
            continue
        (grouped.setdefault(url, [])).append({
            "body": body,
            "score": score,
            "comment_id": c.get("comment_id"),
            "parent_id": c.get("parent_id"),
            "author": c.get("author"),
            "created_utc": c.get("created_utc"),
        })

    pairs: List[Tuple[dict, dict]] = []
    for url, clist in grouped.items():
        if not clist:
            continue
        # choose best comment by score then length
        clist.sort(key=lambda x: (x["score"], len(x["body"])), reverse=True)
        best = clist[0]
        pairs.append((posts_by_url[url], best))
    return pairs


def to_chat(samples: List[Tuple[dict, dict]], out_path: str):
    with open(out_path, "w", encoding="utf-8") as w:
        for post, com in samples:
            title = post.get("title", "")
            selftext = post.get("selftext", "")
            if selftext:
                user = f"اقرأ المشاركة التالية وردّ بالدّارجة التونسية باختصار ووضوح:\n{title}\n\n{selftext}"
            else:
                user = f"اقرأ العنوان التالي وردّ بالدّارجة التونسية باختصار ووضوح:\n{title}"
            obj = {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": com["body"]},
                ],
                "meta": {
                    "subreddit": post.get("subreddit"),
                    "post_url": post.get("url"),
                    "created_utc": post.get("created_utc"),
                    "comment_id": com.get("comment_id"),
                    "score": com.get("score"),
                },
            }
            w.write(json.dumps(obj, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--posts", type=str, required=True)
    ap.add_argument("--comments", type=str, required=True)
    ap.add_argument("--out_dir", type=str, default=str(Path("tunisai")/"data"/"splits"))
    ap.add_argument("--val_ratio", type=float, default=0.05)
    ap.add_argument("--min_len", type=int, default=24)
    ap.add_argument("--min_score", type=int, default=0)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    pairs = build_pairs(args.posts, args.comments, args.min_len, args.min_score)
    if not pairs:
        raise SystemExit("No (post,comment) pairs built - check inputs")

    random.seed(42)
    random.shuffle(pairs)
    n = len(pairs)
    n_val = max(1, int(n * args.val_ratio))
    val = pairs[:n_val]
    train = pairs[n_val:]

    train_out = str(Path(args.out_dir)/"reddit_train.jsonl")
    val_out = str(Path(args.out_dir)/"reddit_val.jsonl")

    to_chat(train, train_out)
    to_chat(val, val_out)
    print(f"Wrote train: {len(train)} -> {train_out}")
    print(f"Wrote val:   {len(val)} -> {val_out}")


if __name__ == "__main__":
    main()
