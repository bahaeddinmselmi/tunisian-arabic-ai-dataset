import argparse
import json
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import requests

try:
    from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
except Exception as e:
    raise SystemExit("Missing dependency: youtube-transcript-api. Install it with: pip install youtube-transcript-api")

try:
    from yt_dlp import YoutubeDL  # optional
except Exception:
    YoutubeDL = None  # type: ignore


def video_id_from_url(url: str) -> str | None:
    m = re.search(r"v=([\w-]{11})", url)
    if m:
        return m.group(1)
    m = re.search(r"youtu\.be/([\w-]{11})", url)
    if m:
        return m.group(1)
    m = re.search(r"/shorts/([\w-]{11})", url)
    if m:
        return m.group(1)
    return None


def fetch_title(vid: str) -> str | None:
    if not YoutubeDL:
        return None
    try:
        with YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
            return info.get("title") if isinstance(info, dict) else None
    except Exception:
        return None


def choose_transcript(vid: str):
    """Try preferred langs (manual first), then generated, then any available."""
    langs_pref = [["ar", "ar-001", "ar-TN"], ["fr"], ["en"]]
    tl = YouTubeTranscriptApi.list_transcripts(vid)

    # Preferred manual
    for lang_group in langs_pref:
        try:
            tr = tl.find_transcript(lang_group)
            if tr is not None:
                return tr, bool(getattr(tr, "is_generated", False))
        except Exception:
            pass
    # Preferred generated
    for lang_group in langs_pref:
        try:
            tr = tl.find_generated_transcript(lang_group)
            if tr is not None:
                return tr, True
        except Exception:
            pass

    # Any manual
    for tr in tl:
        if not getattr(tr, "is_generated", False):
            return tr, False
    # Any generated
    for tr in tl:
        if getattr(tr, "is_generated", False):
            return tr, True

    raise NoTranscriptFound(vid)


def _parse_vtt_to_segments(vtt_text: str) -> List[Dict]:
    """Minimal VTT parser -> list of {text} segments."""
    segs: List[Dict] = []
    lines = vtt_text.replace("\r", "\n").splitlines()
    buf: List[str] = []
    in_cue = False
    ts_re = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}")
    for ln in lines:
        if not ln.strip():
            # flush
            if buf:
                text = " ".join([b.strip() for b in buf if b.strip()])
                text = re.sub(r"\s+", " ", text).strip()
                if text:
                    segs.append({"text": text})
                buf = []
            in_cue = False
            continue
        if ln.strip().upper().startswith("WEBVTT"):
            continue
        if ts_re.match(ln.strip()):
            in_cue = True
            continue
        if in_cue:
            buf.append(ln)
    # tail
    if buf:
        text = " ".join([b.strip() for b in buf if b.strip()])
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            segs.append({"text": text})
    return segs


def fetch_auto_captions_via_ytdlp(vid: str) -> Tuple[List[Dict], Optional[str]]:
    """Use yt-dlp to fetch auto captions (VTT) if available. Returns (segments, lang)."""
    if not YoutubeDL:
        return [], None
    try:
        with YoutubeDL({
            "quiet": True,
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitlesformat": "vtt",
        }) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
            if not isinstance(info, dict):
                return [], None
            # Prefer manual subtitles first, then automatic
            for captions_key in ("subtitles", "automatic_captions"):
                caps = info.get(captions_key) or {}
                if not isinstance(caps, dict):
                    continue
                # Preference order
                pref_langs = ["ar", "ar-001", "ar-TN", "fr", "en"]
                # Find best matching language key
                lang_key = None
                for pref in pref_langs:
                    for k in caps.keys():
                        if k == pref or k.startswith(pref):
                            lang_key = k
                            break
                    if lang_key:
                        break
                if not lang_key and caps:
                    lang_key = next(iter(caps.keys()))
                if not lang_key:
                    continue
                tracks = caps.get(lang_key) or []
                # Prefer VTT
                vtt_track = None
                for tr in tracks:
                    if isinstance(tr, dict) and tr.get("ext") == "vtt" and tr.get("url"):
                        vtt_track = tr
                        break
                if not vtt_track and tracks:
                    # take first available
                    vtt_track = tracks[0] if isinstance(tracks[0], dict) else None
                if not vtt_track or not isinstance(vtt_track, dict) or not vtt_track.get("url"):
                    continue
                url = vtt_track["url"]
                try:
                    resp = requests.get(url, timeout=20)
                    if resp.status_code == 200 and resp.text:
                        segs = _parse_vtt_to_segments(resp.text)
                        if segs:
                            return segs, lang_key
                except Exception:
                    continue
    except Exception:
        return [], None
    return [], None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default=str(Path("tunisai") / "data" / "raw" / "youtube_transcripts.jsonl"))
    ap.add_argument("--urls", nargs="*", default=[])
    ap.add_argument("--urls_file", type=str, default="")
    args = ap.parse_args()

    urls: list[str] = []
    urls.extend(args.urls)
    if args.urls_file:
        p = Path(args.urls_file)
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    urls.append(line)
    urls = [u.strip() for u in urls if u.strip()]
    if not urls:
        raise SystemExit("Provide URLs via --urls or --urls_file")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    n_ok = 0
    with open(args.out, "w", encoding="utf-8") as w:
        for url in urls:
            vid = video_id_from_url(url)
            if not vid:
                continue
            title = fetch_title(vid)
            segs: Optional[List[Dict]] = None
            lang: Optional[str] = None
            is_generated: bool = False

            # Try official API
            try:
                tr, is_generated = choose_transcript(vid)
                segs = tr.fetch()
                lang = getattr(tr, "language", None) or getattr(tr, "language_code", None)
            except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable):
                segs = None
            except Exception:
                segs = None

            # Fallback: yt-dlp auto captions
            if not segs or len(segs) == 0:
                segs2, lang2 = fetch_auto_captions_via_ytdlp(vid)
                if segs2:
                    obj = {
                        "url": url,
                        "video_id": vid,
                        "title": title,
                        "language": lang2,
                        "is_generated": True,
                        "segments": segs2,
                    }
                    w.write(json.dumps(obj, ensure_ascii=False) + "\n")
                    n_ok += 1
                    continue

            # If we got segments from the API
            if segs:
                obj = {
                    "url": url,
                    "video_id": vid,
                    "title": title,
                    "language": lang,
                    "is_generated": bool(is_generated),
                    "segments": segs,
                }
                w.write(json.dumps(obj, ensure_ascii=False) + "\n")
                n_ok += 1

    print(f"Wrote {n_ok} transcripts -> {args.out}")


if __name__ == "__main__":
    main()
