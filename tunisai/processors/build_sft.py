import os
import json
import random
import argparse

SYSTEM_PROMPT = "انت معاون ذكي تحكي بالدّارجة التونسية وببساطة."


def build_sft(in_path: str, out_path: str, max_samples: int = 200000):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as out:
        with open(in_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= max_samples:
                    break
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                user_uttr = o["arabic_norm"] if random.random() < 0.7 else o["roman_norm"]
                instruction = f"فسّرلي النص التالي باللهجة التونسية وخرّج أفكار رئيسية:\n{user_uttr}"
                sample = {
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": instruction},
                        {"role": "assistant", "content": "هات نوضّحلك باختصار بالنقّاط..."},
                    ],
                    "meta": {"source": o.get("source")},
                }
                out.write(json.dumps(sample, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="inp", type=str, default="data/processed/dedup.jsonl")
    parser.add_argument("--out", type=str, default="data/processed/sft.jsonl")
    parser.add_argument("--max", type=int, default=200000)
    args = parser.parse_args()
    build_sft(args.inp, args.out, args.max)
