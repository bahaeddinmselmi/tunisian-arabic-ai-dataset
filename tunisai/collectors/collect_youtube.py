import os
import json
import argparse
from youtube_transcript_api import YouTubeTranscriptApi
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("YOUTUBE_API_KEY")


def channel_videos(channel_id: str, max_pages: int = 2):
    # Import only when needed to avoid requiring the API client for --videos mode
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", developerKey=API_KEY)
    next_page_token = None
    ids = []
    for _ in range(max_pages):
        resp = (
            yt.search()
            .list(part="id", channelId=channel_id, maxResults=50, pageToken=next_page_token, type="video")
            .execute()
        )
        ids += [i["id"]["videoId"] for i in resp.get("items", []) if i["id"]["kind"] == "youtube#video"]
        next_page_token = resp.get("nextPageToken")
        if not next_page_token:
            break
    return ids


def search_videos(query: str, max_pages: int = 2):
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", developerKey=API_KEY)
    next_page_token = None
    ids = []
    for _ in range(max_pages):
        resp = (
            yt.search()
            .list(part="id", q=query, maxResults=50, pageToken=next_page_token, type="video")
            .execute()
        )
        ids += [i["id"]["videoId"] for i in resp.get("items", []) if i["id"]["kind"] == "youtube#video"]
        next_page_token = resp.get("nextPageToken")
        if not next_page_token:
            break
    return ids


def fetch_transcript(video_id: str):
    try:
        tr = YouTubeTranscriptApi.get_transcript(video_id, languages=["ar", "ar-TN", "fr", "en"])
        return " ".join([t["text"] for t in tr])
    except Exception:
        return ""


def collect_youtube_channel(channel_id: str, out_path: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    vids = channel_videos(channel_id)
    with open(out_path, "w", encoding="utf-8") as f:
        for vid in vids:
            obj = {"source": "youtube", "video_id": vid, "transcript": fetch_transcript(vid), "comments": []}
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def collect_youtube_videos(video_ids: list[str], out_path: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for vid in video_ids:
            obj = {"source": "youtube", "video_id": vid, "transcript": fetch_transcript(vid), "comments": []}
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", type=str, help="YouTube channel ID (requires YOUTUBE_API_KEY)")
    parser.add_argument("--videos", type=str, help="Comma-separated list of video IDs (no API key required)")
    parser.add_argument("--search", type=str, help="Search query / hashtags (requires YOUTUBE_API_KEY)")
    parser.add_argument("--out", type=str, default="data/raw/youtube_tn.jsonl")
    parser.add_argument("--pages", type=int, default=2, help="Max pages for channel/search (50 results per page)")
    args = parser.parse_args()

    if args.videos:
        vids = [v.strip() for v in args.videos.split(",") if v.strip()]
        collect_youtube_videos(vids, args.out)
    elif args.channel:
        if not API_KEY:
            raise SystemExit("Missing YOUTUBE_API_KEY in environment for --channel mode.")
        collect_youtube_channel(args.channel, args.out)
    elif args.search:
        if not API_KEY:
            raise SystemExit("Missing YOUTUBE_API_KEY in environment for --search mode.")
        vids = search_videos(args.search, max_pages=args.pages)
        collect_youtube_videos(vids, args.out)
    else:
        raise SystemExit("Provide either --videos <id1,id2,...> or --channel <CHANNEL_ID>.")
