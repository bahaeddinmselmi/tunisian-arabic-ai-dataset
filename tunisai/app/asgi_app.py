import os
import re
import math
import json
import glob
from pathlib import Path
import requests

# Build a simple BM25 index over data/raw/*.jsonl at startup
PROJECT_ROOT = Path(__file__).resolve().parents[1]

BM25_K1 = 1.5
BM25_B = 0.75
bm25_docs = []  # list[dict]
bm25_tokens = []  # list[list[str]]
bm25_df = {}  # dict[str, int]
bm25_avgdl = 0.0


def _norm_text(s: str) -> str:
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _tok(s: str) -> list[str]:
    s = s.lower()
    s = re.sub(r"[^\w\u0600-\u06FF]+", " ", s)
    return [t for t in s.split() if t]


def build_bm25_index():
    global bm25_docs, bm25_tokens, bm25_df, bm25_avgdl
    sources = []
    for fp in glob.glob(str(PROJECT_ROOT / "data" / "raw" / "*.jsonl")):
        sources.append(fp)
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
            idf = math.log((N - n + 0.5) / (n + 0.5) + 1)
            tf = toks.count(term)
            denom = tf + BM25_K1 * (1 - BM25_B + BM25_B * (dl / (bm25_avgdl or 1.0)))
            score += idf * (tf * (BM25_K1 + 1)) / (denom or 1.0)
        scores[i] = score
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    return ranked


build_bm25_index()


async def app(scope, receive, send):
    if scope["type"] != "http":
        return
    method = scope.get("method")
    path = scope.get("path")

    if method == "GET" and path == "/":
        html = (
            """
            <!doctype html><html><head><meta charset='utf-8'><title>TunisAI</title>
            <style>body{font-family:system-ui,Arial;margin:24px;max-width:860px} input,textarea,button{font-size:16px;padding:8px} textarea{width:100%;height:120px}</style>
            </head><body>
            <h1>TunisAI</h1>
            <p>Health: <a href="/health">/health</a></p>
            <h2>Ask</h2>
            <textarea id="prompt" placeholder="اكتب سؤالك هنا..."></textarea><br/>
            <button onclick="ask()">Send</button>
            <pre id="out"></pre>
            <h2>Learn from a URL</h2>
            <input id="url" placeholder="https://example.com/article" size="60" />
            <button onclick="ingest()">Ingest URL</button>
            <pre id="ing"></pre>
            <script>
            async function ask(){
              const r = await fetch('/tunisai',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:document.getElementById('prompt').value})});
              const j = await r.json();
              document.getElementById('out').textContent = JSON.stringify(j,null,2);
            }
            async function ingest(){
              const u = document.getElementById('url').value;
              const r = await fetch('/ingest_url',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:u})});
              const j = await r.json();
              document.getElementById('ing').textContent = JSON.stringify(j,null,2);
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

    if method == "POST" and path == "/tunisai":
        # Read full body
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
            await send({"type": "http.response.start", "status": 400, "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b"{\"error\":\"invalid json\"}"})
            return
        prompt = (payload.get("prompt") or "").strip()
        if not prompt:
            await send({"type": "http.response.start", "status": 400, "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b"{\"error\":\"prompt required\"}"})
            return
        ranked = bm25_score(prompt)[:5]
        snippets = []
        sources = []
        for idx, sc in ranked:
            d = bm25_docs[idx]
            snippets.append(d["text"])
            if d.get("link"):
                sources.append(d["link"])
        reply = "\n\n".join(snippets[:3]) if snippets else "ما لقيتش معلومات كافية توّا. جرّب سؤال آخر."
        resp = json.dumps({"assistant": reply, "sources": sources[:5]}, ensure_ascii=False).encode("utf-8")
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json; charset=utf-8")]})
        await send({"type": "http.response.body", "body": resp})
        return

    if method == "POST" and path == "/ingest_url":
        # Read full body
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
            url = (payload.get("url") or "").strip()
        except Exception:
            url = ""
        if not url:
            await send({"type": "http.response.start", "status": 400, "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b"{\"error\":\"url required\"}"})
            return
        # Fetch page
        text = ""
        title = ""
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (compatible; TunisAI/0.1)"})
            r.raise_for_status()
            html = r.text
            # crude text extraction
            title_match = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
            if title_match:
                title = re.sub(r"\s+", " ", title_match.group(1)).strip()
            no_script = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
            no_style = re.sub(r"<style[\s\S]*?</style>", " ", no_script, flags=re.I)
            text = re.sub(r"<[^>]+>", " ", no_style)
            text = re.sub(r"\s+", " ", text).strip()
        except Exception:
            pass
        if not text:
            await send({"type": "http.response.start", "status": 502, "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b"{\"error\":\"failed to fetch or parse\"}"})
            return
        # Append to data/raw and rebuild index
        outfp = PROJECT_ROOT / "data" / "raw" / "ingested_urls.jsonl"
        try:
            outfp.parent.mkdir(parents=True, exist_ok=True)
            with open(outfp, "a", encoding="utf-8") as f:
                rec = {"title": title, "text": text, "url": url}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass
        build_bm25_index()
        resp = json.dumps({"status": "ok", "title": title, "chars": len(text)}, ensure_ascii=False).encode("utf-8")
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json; charset=utf-8")]})
        await send({"type": "http.response.body", "body": resp})
        return

    await send({"type": "http.response.start", "status": 404, "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": b"{\"error\":\"not found\"}"})
