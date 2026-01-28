import re
import json
from functools import lru_cache
from pathlib import Path
from typing import Dict

# Simple heuristic-based Tunisian Derja detector.
# Uses Arabic/roman patterns and the derja_ninja vocabulary if available.

DATA_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def _load_derja_vocab() -> set[str]:
    """Load known Derja words from processed vocab if present.

    File format expected: derja_ninja_words.json {"vocab": [{"word": ..., ...}, ...]}
    """
    vocab_path = DATA_DIR / "processed" / "derja_ninja_words.json"
    words: set[str] = set()
    if vocab_path.exists():
        try:
            with vocab_path.open("r", encoding="utf-8") as f:
                obj = json.load(f)
            for item in obj.get("vocab", []):
                w = (item.get("word") or "").strip()
                if w:
                    words.add(w)
        except Exception:
            # Fail soft; just use heuristics
            pass
    return words


_AR_WORD_RE = re.compile(r"[\u0600-\u06FF]{2,}")
_ROMAN_WORD_RE = re.compile(r"[A-Za-z0-9]{3,}")
_ROMAN_DIGIT_RE = re.compile(r"[2395678]")

# Common Derja-ish roman patterns
_ROMAN_HINTS = [
    "toun", "tuns", "tunsi", "tounsi", "tounes", "barsha", "barcha",
    "3leh", "3ach", "sahbi", "s7ab", "malla", "7ot", "9a", "3adi",
]


def score_derja(text: str) -> Dict[str, float]:
    """Return a heuristic score indicating how likely `text` is Tunisian Derja.

    score in [0, 1+] (not strictly bounded) – higher is more Derja-like.
    """
    if not text:
        return {"score": 0.0, "tokens": 0, "ar_derja": 0, "roman_derja": 0}

    vocab = _load_derja_vocab()

    ar_tokens = _AR_WORD_RE.findall(text)
    roman_tokens_all = [t.lower() for t in _ROMAN_WORD_RE.findall(text)]

    ar_derja = []
    for t in ar_tokens:
        # treat any Arabic token as candidate Derja; optionally intersect with vocab
        if t in vocab or len(t) >= 3:
            ar_derja.append(t)

    roman_derja = []
    for t in roman_tokens_all:
        if _ROMAN_DIGIT_RE.search(t):
            roman_derja.append(t)
            continue
        if any(h in t for h in _ROMAN_HINTS):
            roman_derja.append(t)
            continue
        if t in vocab:
            roman_derja.append(t)

    total_tokens = len(ar_tokens) + len(roman_tokens_all)
    if total_tokens == 0:
        return {"score": 0.0, "tokens": 0, "ar_derja": 0, "roman_derja": 0}

    # Arabic tokens are more reliable; give them higher weight
    score = (1.0 * len(ar_derja) + 0.7 * len(roman_derja)) / float(total_tokens)

    return {
        "score": float(score),
        "tokens": float(total_tokens),
        "ar_derja": float(len(ar_derja)),
        "roman_derja": float(len(roman_derja)),
    }


def is_likely_derja(text: str, threshold: float = 0.12) -> bool:
    """Quick boolean check: is this probably Tunisian Derja?"""
    return score_derja(text)["score"] >= threshold
