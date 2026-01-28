import os
import json
import time
import argparse
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

def _ensure_parent(path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)

def _jsonl_write(fp, obj):
    fp.write(json.dumps(obj, ensure_ascii=False) + "\n")

def _login_and_context(pw, headed: bool, storage_path: str | None, interactive: bool, username: str | None, password: str | None):
    browser = pw.chromium.launch(headless=not headed)
    if storage_path and Path(storage_path).exists():
        context = browser.new_context(storage_state=str(storage_path))
        return browser, context
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://www.reddit.com/login", timeout=120000)
    if interactive or not (username and password):
        input("Complete Reddit login in the opened browser, then press Enter here...")
    else:
        page.fill("input#loginUsername", username)
        page.fill("input#loginPassword", password)
        page.click("button[type='submit']")
        page.wait_for_timeout(4000)
    if storage_path:
        Path(storage_path).parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(storage_path))
    return browser, context

def _extract_listing_posts(page):
    return page.evaluate(
        """
        () => Array.from(document.querySelectorAll('div.thing.link')).map(el => {
            const a = el.querySelector('a.title');
            const cu = el.querySelector('a.comments');
            const authorEl = el.querySelector('a.author');
            const timeEl = el.querySelector('time');
            return {
                id: el.getAttribute('data-fullname') || '',
                title: a ? a.innerText : '',
                post_url: a ? a.href : (cu ? cu.href : ''),
                comments_url: cu ? cu.href : '',
                author: authorEl ? authorEl.textContent : (el.getAttribute('data-author') || ''),
                created_utc: timeEl ? Math.floor(new Date(timeEl.getAttribute('datetime')).getTime()/1000) : null
            }
        })
        """
    )

def _next_listing_url(page):
    return page.evaluate(
        """
        () => { const a = document.querySelector('span.nextprev a[rel="next"]'); return a ? a.href : null; }
        """
    )

def _extract_post(page):
    return page.evaluate(
        """
        () => {
            const t = document.querySelector('#siteTable div.thing.link a.title');
            const a = document.querySelector('#siteTable div.thing.link a.author');
            const timeEl = document.querySelector('#siteTable div.thing.link time');
            const bodyEl = document.querySelector('#siteTable div.thing.link .expando .usertext-body');
            return {
                title: t ? t.innerText : '',
                author: a ? a.textContent : '',
                selftext: bodyEl ? bodyEl.innerText.trim() : '',
                created_utc: timeEl ? Math.floor(new Date(timeEl.getAttribute('datetime')).getTime()/1000) : null
            };
        }
        """
    )

def _expand_comments(page, max_rounds: int = 20, per_round: int = 25):
    for _ in range(max_rounds):
        try:
            links = page.locator("a.morecomments")
            n = links.count()
        except Exception:
            n = 0
        if n == 0:
            break
        m = min(n, per_round)
        for i in range(m):
            try:
                links.nth(i).scroll_into_view_if_needed()
                links.nth(i).click()
                page.wait_for_timeout(800)
            except Exception:
                pass
        page.wait_for_timeout(1000)

def _extract_comments(page):
    return page.evaluate(
        """
        () => {
            const out = [];
            const nodes = Array.from(document.querySelectorAll('div.thing.comment'));
            for (const el of nodes) {
                const bodyEl = el.querySelector('div.entry .usertext-body');
                const authorEl = el.querySelector('a.author');
                const timeEl = el.querySelector('time');
                out.push({
                    comment_id: el.getAttribute('data-fullname') || el.id || '',
                    parent_id: el.getAttribute('data-parent') || '',
                    author: authorEl ? authorEl.textContent : (el.getAttribute('data-author') || ''),
                    body: bodyEl ? bodyEl.innerText.trim() : '',
                    created_utc: timeEl ? Math.floor(new Date(timeEl.getAttribute('datetime')).getTime()/1000) : null
                });
            }
            return out;
        }
        """
    )

def collect(sub: str, limit: int, sort: str, time_filter: str, with_comments: bool, out_posts: str, out_comments: str | None, headed: bool, storage_state: str | None, interactive_login: bool):
    _ensure_parent(out_posts)
    if out_comments:
        _ensure_parent(out_comments)
    with sync_playwright() as pw:
        username = os.getenv("REDDIT_USERNAME")
        password = os.getenv("REDDIT_PASSWORD")
        browser, context = _login_and_context(pw, headed=headed, storage_path=storage_state, interactive=interactive_login, username=username, password=password)
        page = context.new_page()
        base = f"https://old.reddit.com/r/{sub}/"
        if sort == "top":
            url = f"{base}top/?t={time_filter}"
        elif sort == "new":
            url = f"{base}new/"
        elif sort == "hot":
            url = base
        else:
            url = base
        seen = set()
        total = 0
        with open(out_posts, "w", encoding="utf-8") as fpost:
            fcom = open(out_comments, "w", encoding="utf-8") if (with_comments and out_comments) else None
            try:
                while total < limit and url:
                    page.goto(url, timeout=120000, wait_until="networkidle")
                    time.sleep(1.0)
                    items = _extract_listing_posts(page)
                    for it in items:
                        if total >= limit:
                            break
                        cu = it.get("comments_url") or ""
                        if not cu or cu in seen:
                            continue
                        seen.add(cu)
                        ppage = context.new_page()
                        ppage.goto(cu, timeout=120000, wait_until="domcontentloaded")
                        time.sleep(0.5)
                        meta = _extract_post(ppage)
                        rec = {
                            "subreddit": sub,
                            "url": cu,
                            "title": meta.get("title") or it.get("title") or "",
                            "author": meta.get("author") or it.get("author") or "",
                            "selftext": meta.get("selftext") or "",
                            "created_utc": meta.get("created_utc") or it.get("created_utc")
                        }
                        _jsonl_write(fpost, rec)
                        if with_comments and fcom:
                            _expand_comments(ppage)
                            clist = _extract_comments(ppage)
                            for c in clist:
                                cobj = {
                                    "subreddit": sub,
                                    "post_url": cu,
                                    "comment_id": c.get("comment_id") or "",
                                    "parent_id": c.get("parent_id") or "",
                                    "author": c.get("author") or "",
                                    "body": c.get("body") or "",
                                    "created_utc": c.get("created_utc")
                                }
                                _jsonl_write(fcom, cobj)
                        ppage.close()
                        total += 1
                        time.sleep(0.4)
                    nxt = _next_listing_url(page)
                    url = nxt
            finally:
                if fcom:
                    fcom.close()
                context.storage_state(path=str(storage_state)) if storage_state else None
                context.close()
                browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sub", type=str, default="Tunisia")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--sort", type=str, default="new", choices=["new", "hot", "top"])
    parser.add_argument("--time_filter", type=str, default="year", choices=["hour", "day", "week", "month", "year", "all"])
    parser.add_argument("--with_comments", action="store_true")
    parser.add_argument("--out_posts", type=str, default=str(PROJECT_ROOT/"data"/"raw"/"reddit_posts_pw.jsonl"))
    parser.add_argument("--out_comments", type=str, default=str(PROJECT_ROOT/"data"/"raw"/"reddit_comments_pw.jsonl"))
    parser.add_argument("--storage", type=str, default=str(PROJECT_ROOT/".cache"/"reddit_storage.json"))
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--interactive_login", action="store_true")
    args = parser.parse_args()
    collect(
        sub=args.sub,
        limit=args.limit,
        sort=args.sort,
        time_filter=args.time_filter,
        with_comments=args.with_comments,
        out_posts=args.out_posts,
        out_comments=args.out_comments,
        headed=args.headed,
        storage_state=args.storage,
        interactive_login=args.interactive_login,
    )
