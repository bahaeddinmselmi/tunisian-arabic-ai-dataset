import os
import json
import argparse
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path
import requests
try:
    import tweepy  # tweepy may import imghdr, removed in Python 3.14
    HAS_TWEEPY = True
except Exception:
    tweepy = None
    HAS_TWEEPY = False

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

BEARER = os.getenv("X_BEARER_TOKEN")

DEFAULT_QUERY_CORE = '(تونس OR تونسي OR تونسية OR TN OR "Tn") OR (ch7al OR 3lech OR 9a3da OR 7keya OR barcha)'

def build_query(hashtags: list[str] | None, raw_query: str | None, lang: str, include_retweets: bool) -> str:
    if raw_query:
        core = raw_query
    elif hashtags:
        tags = [f"#{h.lstrip('#')}" for h in hashtags if h.strip()]
        core = " OR ".join(tags)
    else:
        core = DEFAULT_QUERY_CORE
    suffix = f" lang:{lang}"
    if not include_retweets:
        suffix += " -is:retweet"
    return f"{core} {suffix}".strip()


def collect_x(limit: int, out_path: str, query: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    if HAS_TWEEPY:
        client = tweepy.Client(bearer_token=BEARER, wait_on_rate_limit=True)
        with open(out_path, "w", encoding="utf-8") as f:
            for tweet in tweepy.Paginator(
                client.search_recent_tweets,
                query=query,
                tweet_fields=["id", "text", "lang", "created_at", "public_metrics"],
                expansions=None,
                max_results=100,
            ).flatten(limit=limit):
                obj = {
                    "source": "x",
                    "id": str(tweet.id),
                    "text": tweet.text,
                    "lang": tweet.lang,
                    "created_at": tweet.created_at.isoformat() if tweet.created_at else None,
                    "metrics": tweet.public_metrics,
                }
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    else:
        # Fallback: direct HTTP to Twitter v2 Recent Search API
        url = "https://api.twitter.com/2/tweets/search/recent"
        headers = {"Authorization": f"Bearer {BEARER}"}
        params = {
            "query": query,
            "max_results": 100,
            "tweet.fields": "id,text,lang,created_at,public_metrics",
        }
        written = 0
        with open(out_path, "w", encoding="utf-8") as f:
            next_token = None
            while written < limit:
                if next_token:
                    params["next_token"] = next_token
                resp = requests.get(url, headers=headers, params=params, timeout=30)
                if resp.status_code != 200:
                    raise SystemExit(f"X API error {resp.status_code}: {resp.text}")
                data = resp.json()
                for t in data.get("data", [])[: max(0, limit - written)]:
                    obj = {
                        "source": "x",
                        "id": t.get("id"),
                        "text": t.get("text"),
                        "lang": t.get("lang"),
                        "created_at": t.get("created_at"),
                        "metrics": t.get("public_metrics"),
                    }
                    f.write(json.dumps(obj, ensure_ascii=False) + "\n")
                    written += 1
                meta = data.get("meta", {})
                next_token = meta.get("next_token")
                if not next_token:
                    break


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=3000)
    parser.add_argument("--out", type=str, default="data/raw/x_tn.jsonl")
    parser.add_argument("--hashtags", type=str, help="Comma-separated hashtags without # (e.g., derja,تونس)")
    parser.add_argument("--query", type=str, help="Raw X query to override hashtags/default")
    parser.add_argument("--lang", type=str, default="ar")
    parser.add_argument("--include_retweets", action="store_true")
    args = parser.parse_args()

    if not BEARER:
        raise SystemExit("Missing X_BEARER_TOKEN in environment.")
    hashtags = [h.strip() for h in args.hashtags.split(",")] if args.hashtags else None
    q = build_query(hashtags, args.query, args.lang, args.include_retweets)
    collect_x(args.limit, args.out, q)
