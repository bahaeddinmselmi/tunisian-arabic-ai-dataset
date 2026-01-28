import os
import csv
import json
import argparse
from pathlib import Path


def import_csv(csv_path: str, out_jsonl: str, text_col: str = "InputText", label_col: str = "SentimentLabel"):
    in_path = Path(csv_path)
    out_path = Path(out_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with open(in_path, "r", encoding="utf-8") as fin, open(out_path, "w", encoding="utf-8") as fout:
        reader = csv.DictReader(fin)
        for row in reader:
            text = (row.get(text_col) or "").strip()
            if not text:
                continue
            lab_raw = (row.get(label_col) or "").strip()
            try:
                label = int(lab_raw)
            except Exception:
                # try to map strings
                m = {"positive": 1, "pos": 1, "1": 1, "neutral": 0, "neu": 0, "0": 0, "negative": -1, "neg": -1, "-1": -1}
                label = m.get(lab_raw.lower(), 0)
            label_str = {1: "positive", 0: "neutral", -1: "negative"}.get(label, "neutral")
            rec = {
                "source": str(in_path),
                "task": "sentiment",
                "text": text,
                "label": label,
                "label_str": label_str,
            }
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            total += 1
    print(f"wrote {total} rows -> {out_path}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True, help="Path to sentiment CSV")
    p.add_argument("--out", required=True, help="Output JSONL path under data/raw")
    p.add_argument("--text_col", default="InputText")
    p.add_argument("--label_col", default="SentimentLabel")
    args = p.parse_args()
    import_csv(args.csv, args.out, args.text_col, args.label_col)
