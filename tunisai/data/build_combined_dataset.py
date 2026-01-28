import json
from pathlib import Path
import argparse

SPLITS_DIR = Path(__file__).resolve().parents[0] / "splits"


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def write_jsonl(objs, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as w:
        for obj in objs:
            w.write(json.dumps(obj, ensure_ascii=False) + "\n")


def is_placeholder_assistant(msg: str) -> bool:
    if not msg:
        return True
    m = msg.strip()
    # Old bad template from train.jsonl
    if m.startswith("هات نوضّحلك باختصار بالنقّاط"):
        return True
    return False


def load_and_filter(path: Path, tag: str):
    """Load a chat JSONL file and filter obvious garbage.

    We currently just drop entries with empty/placeholder assistant replies.
    """
    out = []
    for obj in read_jsonl(path):
        msgs = obj.get("messages") or []
        if not msgs or not isinstance(msgs, list):
            continue
        # find assistant msg
        assistant_msg = None
        for m in msgs:
            if isinstance(m, dict) and m.get("role") == "assistant":
                assistant_msg = m.get("content") or ""
                break
        if is_placeholder_assistant(assistant_msg or ""):
            continue
        # tag source dataset
        meta = obj.get("meta") or {}
        if not isinstance(meta, dict):
            meta = {}
        if "dataset" not in meta:
            meta["dataset"] = tag
        obj["meta"] = meta
        out.append(obj)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out_train", type=str, default=str(SPLITS_DIR / "combined_train.jsonl"))
    ap.add_argument("--out_val", type=str, default=str(SPLITS_DIR / "combined_val.jsonl"))
    args = ap.parse_args()

    # Known good per-task splits
    train_files = [
        (SPLITS_DIR / "tunizi_train.jsonl", "tunizi"),
        (SPLITS_DIR / "reddit_train.jsonl", "reddit"),
        (SPLITS_DIR / "yt_train.jsonl", "youtube"),
    ]
    val_files = [
        (SPLITS_DIR / "tunizi_val.jsonl", "tunizi"),
        (SPLITS_DIR / "reddit_val.jsonl", "reddit"),
        (SPLITS_DIR / "yt_val.jsonl", "youtube"),
    ]

    train_data = []
    val_data = []

    for path, tag in train_files:
        if path.exists():
            train_data.extend(load_and_filter(path, tag))
    for path, tag in val_files:
        if path.exists():
            val_data.extend(load_and_filter(path, tag))

    if not train_data:
        raise SystemExit("No training data found; check that split files exist.")
    if not val_data:
        raise SystemExit("No validation data found; check that split files exist.")

    write_jsonl(train_data, Path(args.out_train))
    write_jsonl(val_data, Path(args.out_val))
    print(f"Wrote train: {len(train_data)} -> {args.out_train}")
    print(f"Wrote val:   {len(val_data)} -> {args.out_val}")


if __name__ == "__main__":
    main()
