import os
import json
import argparse
try:
    from datasketch import MinHash, MinHashLSH
    HAS_DATASKETCH = True
except Exception:
    HAS_DATASKETCH = False


def dedup_minhash(in_path: str, out_path: str, threshold: float = 0.9):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    uniq = []
    if HAS_DATASKETCH:
        lsh = MinHashLSH(threshold=threshold, num_perm=64)
        with open(in_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                text = obj.get("arabic_norm") or obj.get("clean") or ""
                shingles = set(text.split())
                m = MinHash(num_perm=64)
                for s in shingles:
                    m.update(s.encode("utf-8"))
                if not lsh.query(m):
                    lsh.insert(f"doc{i}", m)
                    uniq.append(obj)
    else:
        # Fallback: exact text dedup
        seen = set()
        with open(in_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                text = obj.get("arabic_norm") or obj.get("clean") or ""
                if text not in seen:
                    seen.add(text)
                    uniq.append(obj)
    with open(out_path, "w", encoding="utf-8") as fo:
        for u in uniq:
            fo.write(json.dumps(u, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="inp", type=str, default="data/processed/cleaned.jsonl")
    parser.add_argument("--out", type=str, default="data/processed/dedup.jsonl")
    parser.add_argument("--threshold", type=float, default=0.9)
    args = parser.parse_args()
    dedup_minhash(args.inp, args.out, args.threshold)
