import os
import argparse
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel


def merge_and_save(base_model: str, lora_path: str, out_path: str):
    tokenizer = AutoTokenizer.from_pretrained(base_model)
    base = AutoModelForCausalLM.from_pretrained(base_model, device_map="cpu")
    peft = PeftModel.from_pretrained(base, lora_path)
    merged = peft.merge_and_unload()
    os.makedirs(out_path, exist_ok=True)
    merged.save_pretrained(out_path, safe_serialization=True)
    tokenizer.save_pretrained(out_path)
    print(f"Merged model saved to {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base_model", type=str, default=os.getenv("BASE_MODEL", "Qwen/Qwen2.5-1.5B-Instruct"))
    ap.add_argument("--lora_dir", type=str, default=os.getenv("LORA_PATH", "out-sft/lora"))
    ap.add_argument("--out_dir", type=str, default=os.getenv("OUT_PATH", "out-merged"))
    args = ap.parse_args()
    merge_and_save(args.base_model, args.lora_dir, args.out_dir)
