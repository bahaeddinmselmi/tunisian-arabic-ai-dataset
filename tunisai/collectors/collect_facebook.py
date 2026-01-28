import os
import time
import json
import argparse
import requests
from urllib.parse import urlparse
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (../.env relative to this file)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
TOKEN = os.getenv("META_GRAPH_TOKEN")
GRAPH = "https://graph.facebook.com/v19.0"


def is_group_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.netloc.endswith("facebook.com") and "/groups/" in p.path
    except Exception:
        return False


def resolve_object_id(url_or_id: str) -> str:
    # If numeric, assume it's already an ID
    if url_or_id.isdigit():
        return url_or_id
    # Resolve via Graph API
    r = requests.get(f"{GRAPH}/", params={"id": url_or_id, "access_token": TOKEN})
    if r.status_code != 200:
        raise RuntimeError(f"Failed to resolve id for {url_or_id}: {r.status_code} {r.text}")
    data = r.json()
    oid = data.get("id")
    if not oid:
        raise RuntimeError(f"Could not resolve id for {url_or_id}")
    return oid


def collect_group_feed(group_id: str, out_path: str, per_group_limit: int = 300, sleep_sec: float = 0.3):
    params = {
        "access_token": TOKEN,
        "limit": 100,
        "fields": (
            "message,created_time,from,permalink_url,"
            "comments.limit(50){message,created_time,from,permalink_url}"
        ),
    }
    url = f"{GRAPH}/{group_id}/feed"
    written = 0
    with open(out_path, "a", encoding="utf-8") as f:
        while True:
            r = requests.get(url, params=params)
            if r.status_code != 200:
                raise RuntimeError(
                    f"Graph error for group {group_id}: {r.status_code} {r.text}. "
                    "You likely need groups_access_member_info and the app added to the group."
                )
            data = r.json()
            for p in data.get("data", []):
                obj = {"source": "facebook_group", "group_id": group_id, "post": p}
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
                written += 1
                if written >= per_group_limit:
                    return written
            paging = data.get("paging", {})
            next_url = paging.get("next")
            if not next_url:
                return written
            url = next_url
            params = {}
            time.sleep(sleep_sec)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--groups", type=str, required=True, help="Comma-separated group URLs or IDs")
    parser.add_argument("--out", type=str, default="data/raw/facebook_groups.jsonl")
    parser.add_argument("--per_group_limit", type=int, default=300)
    args = parser.parse_args()

    if not TOKEN:
        raise SystemExit("Missing META_GRAPH_TOKEN in environment. Put it in tunisai/.env or env vars.")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    items = [g.strip() for g in args.groups.split(",") if g.strip()]

    for it in items:
        try:
            gid = resolve_object_id(it)
        except Exception as e:
            print(f"[resolve] Skipping {it}: {e}")
            continue
        try:
            n = collect_group_feed(gid, args.out, args.per_group_limit)
            print(f"[group {gid}] collected {n} posts")
        except Exception as e:
            print(f"[collect] Error for group {gid}: {e}")


if __name__ == "__main__":
    main()
