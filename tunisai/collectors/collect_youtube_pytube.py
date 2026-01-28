import os
import json
import argparse
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from pytube import Channel
from youtube_transcript_api import YouTubeTranscriptApi


def video_id_from_url(url: str) -> str | None:
    try:
        p = urlparse(url)
        if p.netloc in {"youtu.be"}:
            vid = p.path.lstrip("/")
            return vid or None
        qs = parse_qs(p.query)
        vid = qs.get("v", [None])[0]
        return vid
    except Exception:
        return None


def fetch_transcript(video_id: str) -> str:
    try:
        tr = YouTubeTranscriptApi.get_transcript(video_id, languages=["ar", "ar-TN", "fr", "en"])
        return " ".join([t["text"] for t in tr])
    except Exception:
        return ""


def collect_channels(channels: list[str], per_channel: int, out_path: str):
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for ch_url in channels:
            try:
                c = Channel(ch_url)
                urls = list(c.video_urls)[:per_channel]
            except Exception as e:
                print(f"[channel] skip {ch_url}: {e}")
                continue
            for u in urls:
                vid = video_id_from_url(u)
                if not vid:
                    continue
                text = fetch_transcript(vid)
                obj = {"source": "youtube", "channel": ch_url, "video_id": vid, "transcript": text, "comments": []}
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--channels", type=str, required=True, help="Comma-separated YouTube channel URLs")
    parser.add_argument("--per_channel", type=int, default=20)
    parser.add_argument("--out", type=str, default="data/raw/youtube_channels.jsonl")
    args = parser.parse_args()

    chans = [c.strip() for c in args.channels.split(",") if c.strip()]
    collect_channels(chans, args.per_channel, args.out)
