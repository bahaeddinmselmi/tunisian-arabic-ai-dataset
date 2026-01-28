import os
import json
import time
import argparse
import praw
from dotenv import load_dotenv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")


def write_post(f, post):
    f.write(
        json.dumps(
            {
                "source": "reddit",
                "id": post.id,
                "title": getattr(post, "title", "") or "",
                "selftext": getattr(post, "selftext", "") or "",
                "created_utc": getattr(post, "created_utc", None),
                "url": getattr(post, "url", ""),
                "score": getattr(post, "score", 0),
                "subreddit": str(getattr(post, "subreddit", "")),
                "permalink": getattr(post, "permalink", "") or "",
            },
            ensure_ascii=False,
        )
        + "\n"
    )


def write_comment(f, cmt, submission_id: str):
    try:
        permalink = getattr(cmt, "permalink", None) or ""
        if permalink and not permalink.startswith("http"):
            permalink = "https://www.reddit.com" + permalink
        f.write(
            json.dumps(
                {
                    "source": "reddit_comment",
                    "id": cmt.id,
                    "link_id": getattr(cmt, "link_id", submission_id),
                    "parent_id": getattr(cmt, "parent_id", None),
                    "body": getattr(cmt, "body", "") or "",
                    "created_utc": getattr(cmt, "created_utc", None),
                    "score": getattr(cmt, "score", 0),
                    "permalink": permalink,
                    "subreddit": str(getattr(cmt, "subreddit", "")),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    except Exception:
        return


def iter_submissions(sr, sort: str, limit: int, time_filter: str):
    sort = (sort or "new").lower()
    time_filter = (time_filter or "all").lower()
    if sort == "hot":
        return sr.hot(limit=limit)
    if sort == "top":
        return sr.top(time_filter=time_filter, limit=limit)
    if sort == "rising":
        return sr.rising(limit=limit)
    # default: new
    return sr.new(limit=limit)


def collect_posts_and_comments(sub: str, limit: int, sort: str, time_filter: str, out_posts: str, out_comments: str | None, with_comments: bool, reddit):
    os.makedirs(os.path.dirname(out_posts), exist_ok=True)
    if out_comments:
        os.makedirs(os.path.dirname(out_comments), exist_ok=True)
    sr = reddit.subreddit(sub)
    with open(out_posts, "w", encoding="utf-8") as fp:
        fc = open(out_comments, "w", encoding="utf-8") if (with_comments and out_comments) else None
        try:
            for post in iter_submissions(sr, sort, limit, time_filter):
                write_post(fp, post)
                if with_comments and fc is not None:
                    try:
                        post.comments.replace_more(limit=None)
                        for c in post.comments.list():
                            write_comment(fc, c, post.id)
                        # be gentle
                        time.sleep(0.2)
                    except Exception:
                        continue
        finally:
            if fc:
                fc.close()


def collect_reddit_search(subs: list[str], query: str, per_sub_limit: int, out_path: str, reddit):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for sub in subs:
            for post in reddit.subreddit(sub).search(query=query, sort="new", limit=per_sub_limit):
                write_post(f, post)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sub", type=str, default="Tunisia", help="Subreddit name (e.g., Tunisia)")
    parser.add_argument("--limit", type=int, default=1000, help="Max submissions to fetch")
    parser.add_argument("--sort", type=str, default="new", choices=["new", "hot", "top", "rising"], help="Submission sort order")
    parser.add_argument("--time_filter", type=str, default="all", choices=["hour", "day", "week", "month", "year", "all"], help="Time filter for top sort")
    parser.add_argument("--with_comments", action="store_true", help="Also fetch all comments for each submission")
    parser.add_argument("--out_posts", type=str, default=str(Path("tunisai")/"data"/"raw"/"reddit_posts.jsonl"))
    parser.add_argument("--out_comments", type=str, default=str(Path("tunisai")/"data"/"raw"/"reddit_comments.jsonl"))
    # Legacy options retained for backward compatibility
    parser.add_argument("--subs", type=str, help="(legacy) Comma-separated subreddits for search mode")
    parser.add_argument("--query", type=str, help="(legacy) Search query; if present, uses search mode and writes posts only to --out_posts")
    args = parser.parse_args()

    if not (CLIENT_ID and CLIENT_SECRET):
        raise SystemExit("Missing REDDIT_CLIENT_ID/SECRET in environment.")
    reddit = praw.Reddit(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        user_agent="tunisai/0.1",
    )

    if args.query:
        # Legacy search mode (posts only)
        subs = [s.strip() for s in args.subs.split(",")] if args.subs else [args.sub]
        per_sub = max(1, args.limit // max(1, len(subs)))
        os.makedirs(Path(args.out_posts).parent, exist_ok=True)
        with open(args.out_posts, "w", encoding="utf-8") as f:
            for sub in subs:
                for post in reddit.subreddit(sub).search(query=args.query, sort="new", limit=per_sub):
                    write_post(f, post)
    else:
        collect_posts_and_comments(
            sub=args.sub,
            limit=args.limit,
            sort=args.sort,
            time_filter=args.time_filter,
            out_posts=args.out_posts,
            out_comments=args.out_comments,
            with_comments=args.with_comments,
            reddit=reddit,
        )
