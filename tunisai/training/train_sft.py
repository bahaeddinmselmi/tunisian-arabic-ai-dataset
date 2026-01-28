import os
import argparse
import torch
import json
from pathlib import Path
from datasets import load_dataset, Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer
from transformers import TrainingArguments
from transformers.trainer_utils import get_last_checkpoint

try:
    from transformers import BitsAndBytesConfig  # optional; only used if qlora
except Exception:
    BitsAndBytesConfig = None  # type: ignore


def apply_chat_template(tokenizer, sample):
    return tokenizer.apply_chat_template(sample["messages"], tokenize=False, add_generation_prompt=False)


def load_model_tokenizer(base_model: str, qlora: bool):
    use_bnb = qlora and BitsAndBytesConfig is not None and torch.cuda.is_available()
    tokenizer = AutoTokenizer.from_pretrained(base_model, use_fast=True)
    if use_bnb:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float16,
            bnb_4bit_quant_type="nf4",
        )
        model = AutoModelForCausalLM.from_pretrained(
            base_model, quantization_config=bnb_config, device_map="auto"
        )
    else:
        model = AutoModelForCausalLM.from_pretrained(base_model, torch_dtype=torch.float16 if torch.cuda.is_available() else None)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    return model, tokenizer


def main():
    ap = argparse.ArgumentParser()
    root_dir = Path(__file__).resolve().parents[1]
    splits_dir = root_dir / "data" / "splits"
    ap.add_argument("--base_model", type=str, default=os.getenv("BASE_MODEL", "Qwen/Qwen2.5-1.5B-Instruct"))
    ap.add_argument("--train_file", type=str, default=str(splits_dir / "combined_train.jsonl"))
    ap.add_argument("--val_file", type=str, default=str(splits_dir / "combined_val.jsonl"))
    ap.add_argument("--output_dir", type=str, default="out-sft")
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--per_device_train_batch_size", type=int, default=1)
    ap.add_argument("--gradient_accumulation_steps", type=int, default=16)
    ap.add_argument("--lr", type=float, default=5e-5)
    ap.add_argument("--max_seq_length", type=int, default=512)
    ap.add_argument("--qlora", action="store_true")
    ap.add_argument("--lora", action="store_true")
    ap.add_argument("--max_steps", type=int, default=-1)
    ap.add_argument("--packing", action="store_true")
    ap.add_argument("--save_steps", type=int, default=200)
    ap.add_argument("--eval_steps", type=int, default=200)
    ap.add_argument("--resume_from_checkpoint", type=str, default=None)
    args = ap.parse_args()

    model, tokenizer = load_model_tokenizer(args.base_model, args.qlora)
    if torch.cuda.is_available():
        try:
            model.config.use_cache = False
        except Exception:
            pass
        try:
            model.gradient_checkpointing_enable()
        except Exception:
            pass
        try:
            model.enable_input_require_grads()
        except Exception:
            pass

    def read_jsonl(path):
        items = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                    if "messages" in o:
                        items.append(o)
                except Exception:
                    continue
        return items

    train_items = read_jsonl(args.train_file)
    val_items = read_jsonl(args.val_file)
    ds_train = Dataset.from_list(train_items)
    ds_val = Dataset.from_list(val_items)

    ds_train = ds_train.map(lambda s: {"text": apply_chat_template(tokenizer, s)})
    ds_val = ds_val.map(lambda s: {"text": apply_chat_template(tokenizer, s)})

    can_bf16 = torch.cuda.is_available() and torch.cuda.get_device_capability()[0] >= 8
    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.lr,
        max_steps=args.max_steps,
        bf16=bool(can_bf16),
        fp16=bool(torch.cuda.is_available() and not can_bf16),
        gradient_checkpointing=True,
        logging_steps=10,
        save_steps=args.save_steps,
        save_strategy="steps",
        evaluation_strategy="steps",
        eval_steps=args.eval_steps,
        save_total_limit=3,
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        max_grad_norm=1.0,
        weight_decay=0.01,
        report_to="none",
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
    )

    lora_cfg = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )

    trainer = SFTTrainer(
        model=model,
        peft_config=lora_cfg if (args.lora or args.qlora) else None,
        tokenizer=tokenizer,
        train_dataset=ds_train,
        eval_dataset=ds_val,
        args=training_args,
        packing=bool(args.packing),
        max_seq_length=args.max_seq_length,
        dataset_text_field="text",
    )

    last_checkpoint = None
    if os.path.isdir(args.output_dir):
        try:
            last_checkpoint = get_last_checkpoint(args.output_dir)
        except Exception:
            last_checkpoint = None
    resume_from = args.resume_from_checkpoint or last_checkpoint

    trainer.train(resume_from_checkpoint=resume_from)
    os.makedirs(args.output_dir, exist_ok=True)
    if args.lora or args.qlora:
        try:
            trainer.model.save_pretrained(os.path.join(args.output_dir, "lora"))
        except Exception:
            pass
    tokenizer.save_pretrained(os.path.join(args.output_dir, "tokenizer"))


if __name__ == "__main__":
    main()
