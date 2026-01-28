import os
import json
import random
import argparse


def split_jsonl(path: str, out_dir: str = "data/splits", ratios=(0.9, 0.05, 0.05)):
    os.makedirs(out_dir, exist_ok=True)
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    random.shuffle(lines)
    n = len(lines)
    n_train = int(n * ratios[0])
    n_val = int(n * ratios[1])
    open(os.path.join(out_dir, "train.jsonl"), "w", encoding="utf-8").write("\n".join(lines[:n_train]))
    open(os.path.join(out_dir, "val.jsonl"), "w", encoding="utf-8").write("\n".join(lines[n_train : n_train + n_val]))
    open(os.path.join(out_dir, "test.jsonl"), "w", encoding="utf-8").write("\n".join(lines[n_train + n_val :]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="inp", type=str, default="data/processed/sft.jsonl")
    parser.add_argument("--out_dir", type=str, default="data/splits")
    args = parser.parse_args()
    split_jsonl(args.inp, args.out_dir)
