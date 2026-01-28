import os
import re
import json
from pathlib import Path

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
try:
    from peft import PeftModel  # optional: only used if GEN_LORA_DIR is set
except Exception:
    PeftModel = None  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GEN_MODEL_DIR = os.getenv("GEN_MODEL_DIR", str(PROJECT_ROOT / "models" / "qwen2.5-1_5b-tunisai-merged"))

gen_model = None
gen_tokenizer = None


def _load_model():
    global gen_model, gen_tokenizer
    if gen_model is not None:
        return True
    # If local path exists, load from disk; else treat as model ID
    model_dir = Path(GEN_MODEL_DIR)
    src = GEN_MODEL_DIR if not model_dir.exists() else model_dir
    try:
        gen_tokenizer = AutoTokenizer.from_pretrained(src, use_fast=True)
        if gen_tokenizer.pad_token is None:
            gen_tokenizer.pad_token = gen_tokenizer.eos_token
        env_dev = os.getenv("GEN_DEVICE", "cpu")
        device = "cuda" if (env_dev == "cuda" and torch.cuda.is_available()) else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        # If a LoRA directory is provided, load base then apply adapter instead of merged weights
        lora_dir = os.getenv("GEN_LORA_DIR", "").strip()
        if lora_dir and Path(lora_dir).exists() and PeftModel is not None:
            base_model = AutoModelForCausalLM.from_pretrained(src, torch_dtype=dtype)
            gen_model = PeftModel.from_pretrained(base_model, lora_dir)
        else:
            gen_model = AutoModelForCausalLM.from_pretrained(src, torch_dtype=dtype)
        gen_model.to(device)
        # ensure generation config has proper special tokens
        try:
            gen_model.generation_config.pad_token_id = gen_tokenizer.eos_token_id
            gen_model.generation_config.eos_token_id = gen_tokenizer.eos_token_id
        except Exception:
            pass
        gen_model.eval()
    except Exception:
        return False
    return True


async def app(scope, receive, send):
    if scope["type"] != "http":
        return
    method = scope.get("method")
    path = scope.get("path")

    if method == "GET" and path == "/":
        html = (
            """
            <!doctype html><html><head><meta charset='utf-8'><title>TunisAI - Gen</title>
            <style>body{font-family:system-ui,Arial;margin:24px;max-width:860px} textarea{width:100%;height:140px} input,textarea,button{font-size:16px;padding:8px}</style>
            </head><body>
            <h1>TunisAI (Generation)</h1>
            <p>Health: <a href="/health">/health</a></p>
            <textarea id="prompt" placeholder="اكتب سؤالك هنا..."></textarea><br/>
            <button id="btn" onclick="gen()">Generate</button>
            <pre id="out"></pre>
            <script>
            async function gen(){
              const btn = document.getElementById('btn');
              const out = document.getElementById('out');
              const p = document.getElementById('prompt').value;
              btn.disabled = true;
              out.textContent = 'Generating on CPU... this may take 30-90s for longer replies.';
              try {
                const r = await fetch('/generate',{
                  method:'POST',
                  headers:{'Content-Type':'application/json'},
                  body: JSON.stringify({prompt:p, max_tokens: 128})
                });
                const text = await r.text();
                try { const j = JSON.parse(text); out.textContent = JSON.stringify(j,null,2); }
                catch(e) { out.textContent = `HTTP ${r.status}: ${text}`; }
              } catch(err){
                out.textContent = 'Error: ' + err;
              } finally {
                btn.disabled = false;
              }
            }
            </script>
            </body></html>
            """
        ).encode("utf-8")
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/html; charset=utf-8")]})
        await send({"type": "http.response.body", "body": html})
        return

    if method == "GET" and path == "/health":
        body = b"{\"status\":\"ok\"}"
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})
        return

    if method == "POST" and path == "/generate":
        body = b""
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.request":
                body += message.get("body", b"")
                more_body = message.get("more_body", False)
            else:
                more_body = False
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            payload = {}
        prompt = (payload.get("prompt") or "").strip()
        # optional max tokens from client
        try:
            max_tokens = int(payload.get("max_tokens") or 256)
        except Exception:
            max_tokens = 256
        if max_tokens < 1:
            max_tokens = 1
        if max_tokens > 512:
            max_tokens = 512
        if not prompt:
            await send({"type": "http.response.start", "status": 400, "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b"{\"error\":\"prompt required\"}"})
            return
        if not _load_model():
            await send({"type": "http.response.start", "status": 500, "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b"{\"error\":\"model not found\"}"})
            return
        msgs = [
            {"role": "system", "content": "انت معاون ذكي تحكي بالدّارجة التونسية وببساطة."},
            {"role": "user", "content": prompt},
        ]
        text = gen_tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inputs = gen_tokenizer(text, return_tensors="pt")
        device = next(gen_model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}
        input_ids = inputs["input_ids"]
        with torch.inference_mode():
            out_ids = gen_model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                do_sample=False,
                num_beams=1,
                no_repeat_ngram_size=4,
                pad_token_id=gen_tokenizer.eos_token_id,
                eos_token_id=gen_tokenizer.eos_token_id,
            )
        gen_ids = out_ids[0, input_ids.shape[-1]:].cpu()
        reply = gen_tokenizer.decode(gen_ids, skip_special_tokens=True).strip()
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json; charset=utf-8")]})
        await send({"type": "http.response.body", "body": json.dumps({"assistant": reply}, ensure_ascii=False).encode("utf-8")})
        return

    await send({"type": "http.response.start", "status": 404, "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": b"{\"error\":\"not found\"}"})
