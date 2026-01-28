import os
import re
import csv
import json
import random
import argparse
from pathlib import Path

SYSTEM_PROMPT = "انت معاون ذكي تحكي بالدّارجة التونسية وببساطة."
USER_INSTR = (
    "قيّم المشاعر في النصّ التالي باللهجة التونسية.\n"
    "جاوب بكلمة وحدة: إيجابي أو سلبي.\n\n"
    "النص: {text}"
)

LABEL_MAP = {"0": "سلبي", "1": "إيجابي", 0: "سلبي", 1: "إيجابي"}


def read_tunizi_csv(csv_path: str):
    items = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            # Support rows with commas in text: label is the last column
            if len(row) < 2:
                continue
            label_raw = row[-1].strip()
            text = ",".join(row[:-1]).strip()
            # Remove leading numeric IDs like "99935," or "12345 "
            text = re.sub(r"^\s*\d+\s*[,;:\-]?\s*", "", text)
            # Collapse excessive repeated punctuation (e.g., hhhhhh stays as is, but !!!!! -> !!)
            text = re.sub(r"([!?.،])\1{2,}", r"\1\1", text)
            if not text:
                continue
            if label_raw not in ("0", "1"):
                # Skip malformed labels
                continue
            label = LABEL_MAP[label_raw]
            items.append((text, label))
    return items


def to_chat_jsonl(samples, out_path: str):
    with open(out_path, "w", encoding="utf-8") as w:
        for text, label in samples:
            obj = {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": USER_INSTR.format(text=text)},
                    {"role": "assistant", "content": label},
                ]
            }
            w.write(json.dumps(obj, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=str, required=True, help="Path to TuniziDataset.csv")
    ap.add_argument("--out_dir", type=str, default=str(Path("tunisai") / "data" / "splits"))
    ap.add_argument("--val_ratio", type=float, default=0.05)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    items = read_tunizi_csv(args.csv)
    if not items:
        raise SystemExit("No rows loaded from CSV")

    # Basic filtering: drop very short texts and deduplicate
    items = [(t, l) for (t, l) in items if len(t) >= 3]
    seen = set()
    uniq = []
    for t, l in items:
        k = (t, l)
        if k in seen:
            continue
        seen.add(k)
        uniq.append((t, l))
    items = uniq

    random.seed(42)
    random.shuffle(items)
    n = len(items)
    n_val = max(1, int(n * args.val_ratio))
    val = items[:n_val]
    train = items[n_val:]

    train_out = str(Path(args.out_dir) / "tunizi_train.jsonl")
    val_out = str(Path(args.out_dir) / "tunizi_val.jsonl")

    to_chat_jsonl(train, train_out)
    to_chat_jsonl(val, val_out)

    print(f"Wrote train: {len(train)} -> {train_out}")
    print(f"Wrote val:   {len(val)} -> {val_out}")


if __name__ == "__main__":
    main()
