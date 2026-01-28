import os
import re
import json
import glob
import argparse
import emoji
from dotenv import load_dotenv

load_dotenv()

URL_RE = re.compile(r"https?://\S+|www\.\S+")
MENTION_RE = re.compile(r"[@#]\w+")
EMAIL_RE = re.compile(r"\b[\w\.-]+@[\w\.-]+\.\w+\b")
PHONE_RE = re.compile(r"\b(\+?\d[\d\-\s]{6,}\d)\b")
DIACRITICS = re.compile(r"[\u0617-\u061A\u064B-\u0652]")

EMOJI_MAP = {"😂": "[LOL]", "😢": "[SAD]", "❤️": "[LOVE]", "🔥": "[HOT]", "👍": "[OK]"}


def map_emojis(text: str) -> str:
    return "".join(EMOJI_MAP.get(ch, "") if ch in EMOJI_MAP else ch for ch in text)


def normalize_arabic(text: str) -> str:
    t = text
    t = DIACRITICS.sub("", t)
    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    t = t.replace("ى", "ي")
    t = t.replace("ة", "ة")  # keep taa marbuta as is
    return t


def roman_to_arabic_tn(txt: str) -> str:
    t = txt
    t = re.sub(r"ch", "ش", t, flags=re.IGNORECASE)
    t = re.sub(r"gh", "غ", t, flags=re.IGNORECASE)
    t = re.sub(r"kh", "خ", t, flags=re.IGNORECASE)
    t = re.sub(r"th", "ث", t, flags=re.IGNORECASE)
    t = re.sub(r"dh", "ذ", t, flags=re.IGNORECASE)
    t = re.sub(r"\b9", "ق", t)
    t = re.sub(r"\b3", "ع", t)
    t = re.sub(r"\b7", "ح", t)
    t = re.sub(r"\b5", "خ", t)
    t = re.sub(r"\b2", "ق", t)
    t = re.sub(r"\bch7al\b", "قداش", t, flags=re.IGNORECASE)
    t = re.sub(r"\b9a3da\b", "قعدة", t, flags=re.IGNORECASE)
    t = re.sub(r"\bbarsha\b", "برشا", t, flags=re.IGNORECASE)
    t = re.sub(r"\b3lech\b", "علاش", t, flags=re.IGNORECASE)
    return t


def clean_text(t: str) -> str:
    t = t.strip()
    t = URL_RE.sub("", t)
    t = EMAIL_RE.sub("[EMAIL]", t)
    t = PHONE_RE.sub("[PHONE]", t)
    t = MENTION_RE.sub("", t)
    t = map_emojis(t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


def process_raw_dir(raw_dir: str, out_path: str, normalize_roman: bool = True):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    files = glob.glob(os.path.join(raw_dir, "*.jsonl"))
    with open(out_path, "w", encoding="utf-8") as fo:
        for fp in files:
            with open(fp, "r", encoding="utf-8") as fi:
                for line in fi:
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    text = (
                        obj.get("text")
                        or obj.get("selftext")
                        or obj.get("transcript")
                        or ""
                    )
                    title = obj.get("title") or ""
                    comments = obj.get("comments") or []
                    blocks = [title, text] + [c.get("text") or c.get("textDisplay") or "" for c in comments]
                    for b in blocks:
                        if not b:
                            continue
                        raw = b
                        cleaned = clean_text(raw)
                        ar_norm = normalize_arabic(cleaned)
                        roman_norm = roman_to_arabic_tn(cleaned) if normalize_roman else cleaned
                        fo.write(
                            json.dumps(
                                {
                                    "source": obj.get("source", "unknown"),
                                    "clean": cleaned,
                                    "arabic_norm": ar_norm,
                                    "roman_norm": roman_norm,
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw_dir", type=str, default="data/raw")
    parser.add_argument("--out", type=str, default="data/processed/cleaned.jsonl")
    parser.add_argument("--no_roman", action="store_true")
    args = parser.parse_args()
    process_raw_dir(args.raw_dir, args.out, normalize_roman=not args.no_roman)
