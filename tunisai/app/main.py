import os
import re
import math
import json
import glob
from pathlib import Path
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

# Load .env from project root (one level up from this file's directory)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

MODEL_PATH = os.getenv("MODEL_PATH", "bm25")
USE_LLM = os.getenv("USE_LLM", "0") == "1"
GEN_KW_DEFAULT = dict(max_new_tokens=256, temperature=0.7, top_p=0.9, do_sample=True)

app = FastAPI(title="TunisAI API", version="0.1.0")

# -----------------------------
# Optional LLM mode (guarded)
# -----------------------------
enable_bnb = False
has_cuda = False
has_mps = False
if USE_LLM:
    try:  # import torch only if needed
        import torch  # type: ignore
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig  # type: ignore
        try:
            import bitsandbytes  # noqa: F401
            enable_bnb = True
        except Exception:
            enable_bnb = False
        has_cuda = torch.cuda.is_available()
        has_mps = getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()
    except Exception:
        USE_LLM = False  # fallback to retrieval-only if torch/transformers unavailable

class ChatRequest(BaseModel):
    prompt: str
    history: list[dict] | None = None
    max_new_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None

tokenizer = None
model = None

# -----------------------------
# Retrieval-only (BM25) backend
# -----------------------------
BM25_K1 = 1.5
BM25_B = 0.75
bm25_docs: list[dict] = []
bm25_tokens: list[list[str]] = []
bm25_df: dict[str, int] = {}
bm25_avgdl: float = 0.0


def _norm_text(s: str) -> str:
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _tok(s: str) -> list[str]:
    # Keep Arabic letters and digits, split on anything else
    s = s.lower()
    s = re.sub(r"[^\w\u0600-\u06FF]+", " ", s)
    return [t for t in s.split() if t]


def build_bm25_index():
    global bm25_docs, bm25_tokens, bm25_df, bm25_avgdl
    sources = []
    for fp in glob.glob(str(PROJECT_ROOT / "data" / "raw" / "*.jsonl")):
        try:
            sources.append(fp)
        except Exception:
            continue
    docs = []
    for fp in sources:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        o = json.loads(line)
                    except Exception:
                        continue
                    text = o.get("text") or o.get("transcript") or o.get("selftext") or ""
                    title = o.get("title") or ""
                    link = o.get("link") or o.get("url") or ""
                    txt = (title + "\n" + text).strip()
                    if not txt:
                        continue
                    # Chunk long docs to improve retrieval granularity
                    for i in range(0, len(txt), 800):
                        chunk = _norm_text(txt[i : i + 800])
                        if len(chunk) < 80:
                            continue
                        docs.append({"text": chunk, "link": link, "source": fp})
        except Exception:
            continue
    bm25_docs = docs
    bm25_tokens = [_tok(d["text"]) for d in bm25_docs]
    bm25_df = {}
    for toks in bm25_tokens:
        seen = set()
        for t in toks:
            if t not in seen:
                bm25_df[t] = bm25_df.get(t, 0) + 1
                seen.add(t)
    avg = sum(len(t) for t in bm25_tokens) / max(1, len(bm25_tokens))
    bm25_avgdl = float(avg)


def bm25_score(query: str) -> list[tuple[int, float]]:
    q = _tok(query)
    N = len(bm25_tokens)
    scores = [0.0] * N
    for i, toks in enumerate(bm25_tokens):
        dl = len(toks)
        score = 0.0
        for term in q:
            n = bm25_df.get(term, 0)
            if n == 0:
                continue
            # IDF (BM25)
            idf = math.log((N - n + 0.5) / (n + 0.5) + 1)
            tf = toks.count(term)
            denom = tf + BM25_K1 * (1 - BM25_B + BM25_B * (dl / (bm25_avgdl or 1.0)))
            score += idf * (tf * (BM25_K1 + 1)) / (denom or 1.0)
        scores[i] = score
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    return ranked

def render_chat(tokenizer, messages: list[dict]) -> str:
    # Use model's chat template if available; otherwise fall back to a simple tagged prompt
    try:
        if getattr(tokenizer, "chat_template", None) is not None:
            return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    except Exception:
        pass
    sys_lines = []
    convo = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            sys_lines.append(content)
        elif role == "user":
            convo.append(f"[user]: {content}")
        elif role == "assistant":
            convo.append(f"[assistant]: {content}")
    sys_block = ("[system]: " + " \n".join(sys_lines) + "\n") if sys_lines else ""
    return sys_block + "\n".join(convo) + "\n[assistant]:"

def load_backend():
    global tokenizer, model
    if USE_LLM:
        # Lazy import inside branch
        import torch  # type: ignore
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig  # type: ignore
        if os.path.isdir(MODEL_PATH) or "/" in MODEL_PATH or "-" in MODEL_PATH:
            tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, use_fast=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
            if enable_bnb and has_cuda:
                bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16, bnb_4bit_quant_type="nf4")
                model = AutoModelForCausalLM.from_pretrained(MODEL_PATH, device_map="auto", quantization_config=bnb)
            else:
                dtype = torch.float16 if (has_cuda or has_mps) else torch.float32
                device_map = "auto" if (has_cuda or has_mps) else {"": "cpu"}
                model = AutoModelForCausalLM.from_pretrained(MODEL_PATH, device_map=device_map, torch_dtype=dtype)
    else:
        build_bm25_index()


@app.on_event("startup")
def _startup():
    load_backend()


@app.post("/tunisai")
def tunisai(req: ChatRequest):
    if USE_LLM and model is not None and tokenizer is not None:
        # LLM path
        import torch  # type: ignore
        messages = [
            {"role": "system", "content": "انت معاون ذكي تحكي بالدّارجة التونسية وباحترام وباختصار مفيد."}
        ]
        if req.history:
            messages.extend(req.history[:8])
        messages.append({"role": "user", "content": req.prompt})

        text = render_chat(tokenizer, messages)
        device = next(model.parameters()).device
        inputs = tokenizer(text, return_tensors="pt").to(device)

        kw = GEN_KW_DEFAULT.copy()
        if req.max_new_tokens is not None:
            kw["max_new_tokens"] = req.max_new_tokens
        if req.temperature is not None:
            kw["temperature"] = req.temperature
        if req.top_p is not None:
            kw["top_p"] = req.top_p

        with torch.no_grad():
            out = model.generate(**inputs, **kw)
        gen = tokenizer.decode(out[0], skip_special_tokens=True)
        reply = gen[len(text):].strip()
        return {"assistant": reply}
    else:
        # Retrieval-only path
        ranked = bm25_score(req.prompt)[:5]
        snippets = []
        sources = []
        for idx, sc in ranked:
            d = bm25_docs[idx]
            snippets.append(d["text"])
            if d.get("link"):
                sources.append(d["link"])
        reply = "\n\n".join(snippets[:3]) if snippets else "ما لقيتش معلومات كافية توّا. جرّب سؤال آخر."  # simple concat
        return {"assistant": reply, "sources": sources[:5]}
