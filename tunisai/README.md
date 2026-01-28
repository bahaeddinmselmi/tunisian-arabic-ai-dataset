# TunisAI — Tunisian Darija Assistant

A production-ready blueprint to build and serve a Tunisian AI assistant that understands Derja (Tunisian Arabic), romanized Derja, and code-switching with French/English.

## Quick Start

- Requirements: Python 3.10+, Git, optional CUDA GPU.
- Create env and install deps:
  - Windows PowerShell
    - `python -m venv .venv`
    - `.\.venv\Scripts\Activate.ps1`
    - `pip install -r requirements.txt`
  - Copy `.env.example` to `.env` and fill API keys.

### Data Collection
- Twitter/X:
  - `python collectors/collect_x.py --limit 2000 --out data/raw/x_tn.jsonl`
- Reddit:
  - `python collectors/collect_reddit.py --sub Tunisia --limit 2000 --out data/raw/reddit_tn.jsonl`
- YouTube (provide channel id):
  - `python collectors/collect_youtube.py --channel UCxxxx --out data/raw/youtube_tn.jsonl`

### Preprocessing
- Clean and normalize:
  - `python processors/clean.py --raw_dir data/raw --out data/processed/cleaned.jsonl`
- Deduplicate:
  - `python processors/dedup.py --in data/processed/cleaned.jsonl --out data/processed/dedup.jsonl`
- Build SFT dataset and split:
  - `python processors/build_sft.py --in data/processed/dedup.jsonl --out data/processed/sft.jsonl`
  - `python processors/split.py --in data/processed/sft.jsonl --out_dir data/splits`

### Training (QLoRA SFT)
- Set base model (default Qwen/Qwen2.5-7B-Instruct):
  - PowerShell: `$env:BASE_MODEL='Qwen/Qwen2.5-7B-Instruct'`
- Train:
  - `python training/train_sft.py`
- Merge LoRA (optional for serving):
  - `python training/merge_lora.py`

### API
- Set model path (merged or base):
  - PowerShell: `$env:MODEL_PATH='out-merged'`
- Run API:
  - `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Test:
  - `curl -X POST http://localhost:8000/tunisai -H "Content-Type: application/json" -d '{"prompt":"شنوّا الإجراءات لتجديد الباسبور؟"}'`

### Docker (GPU)
- `docker build -t tunisai .`
- `docker run --gpus all -p 8000:8000 -e MODEL_PATH=/models/tunisai -v %CD%\out-merged:/models/tunisai tunisai`

## Structure
- `collectors/` API scrapers for X, Reddit, YouTube.
- `processors/` cleaning, dedup, SFT build, split.
- `training/` QLoRA SFT training and LoRA merge.
- `app/` FastAPI serving `/tunisai`.
- `data/` raw, processed, splits, rag.

## Notes
- Respect each platform's ToS and robots.txt.
- Remove PII by default. See `processors/clean.py`.
- For production, consider vLLM/TGI backends and add auth/rate limiting.
