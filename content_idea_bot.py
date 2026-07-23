"""
Daily content-idea bot.

Pulls raw signal from dev.to, Hacker News, and Substack (all zero-signup),
plus Reddit if credentials are provided, scores each item with a single
OpenAI call (relevance 0-10 + best content format), and writes anything
above MIN_SCORE_TO_SAVE into a Notion database as a new row.

Only 3 secrets are required to run at all: OPENAI_API_KEY, NOTION_API_KEY,
NOTION_DATABASE_ID. Reddit's two secrets are optional — leave them unset and
that source is skipped automatically.

Run daily via GitHub Actions (see .github/workflows/daily-content-ideas.yml).
Only dependency: requests.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

# ---------------------------------------------------------------------------
# CONFIG — edit this block for your niche. Nothing else below needs to change.
# ---------------------------------------------------------------------------

SUBREDDITS = ["SaaS", "artificial", "AI_Agents", "LocalLLaMA", "automation"]
REDDIT_MIN_SCORE = 20          # skip low-engagement posts
REDDIT_TIME_WINDOW = "day"     # day | week

DEVTO_TAGS = ["ai", "automation", "machinelearning"]

# Hacker News needs no API key at all (Algolia's public HN search API).
# Keyword-based since HN has no per-topic feeds like subreddits do.
HN_KEYWORDS = ["AI agent", "MCP", "LLM"]
HN_MIN_POINTS = 20

# Substack has no site-wide "trending" API, so list the specific newsletters
# you want tracked (the part before ".substack.com").
SUBSTACK_PUBLICATIONS = ["stratechery", "platformer"]

CONTENT_PILLARS = (
    "A tech company writing about AI agents, developer tools, automation, "
    "and building software with LLMs. Audience: developers, indie hackers, "
    "and technical founders."
)

MIN_SCORE_TO_SAVE = 6  # 0-10 — only items scoring at/above this get saved

# ---------------------------------------------------------------------------
# Secrets — set these as GitHub repo secrets, never hardcode them.
# ---------------------------------------------------------------------------

REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.environ.get("REDDIT_USER_AGENT", "content-idea-bot/0.1")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")

# Cheap, fast, supports guaranteed JSON output — good fit for a per-item
# classification call. Swap this string if you'd rather use another model.
OPENAI_MODEL = "gpt-4o-mini"

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# Reddit is deliberately NOT in this list — if its keys are missing, the
# script just skips that one source instead of failing. This is the only
# source that needs an approved developer account right now.
REQUIRED_ENV = ["OPENAI_API_KEY", "NOTION_API_KEY", "NOTION_DATABASE_ID"]


def check_env():
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        sys.exit(f"Missing required environment variables: {', '.join(missing)}")


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def get_reddit_token():
    resp = requests.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": REDDIT_USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_reddit():
    items = []
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        print("  [reddit] no credentials set — skipping this source for now")
        return items
    try:
        token = get_reddit_token()
    except requests.RequestException as e:
        print(f"  [reddit] could not get token: {e}")
        return items

    headers = {"Authorization": f"bearer {token}", "User-Agent": REDDIT_USER_AGENT}
    for sub in SUBREDDITS:
        try:
            r = requests.get(
                f"https://oauth.reddit.com/r/{sub}/top",
                headers=headers,
                params={"t": REDDIT_TIME_WINDOW, "limit": 15},
                timeout=15,
            )
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"  [reddit] skipped r/{sub}: {e}")
            continue
        for child in r.json()["data"]["children"]:
            d = child["data"]
            if d.get("score", 0) < REDDIT_MIN_SCORE:
                continue
            items.append({
                "platform": "reddit",
                "title": d["title"],
                "body": (d.get("selftext") or "")[:500],
                "url": "https://reddit.com" + d["permalink"],
                "engagement": d.get("score", 0) + d.get("num_comments", 0),
            })
    return items


def fetch_devto():
    items = []
    for tag in DEVTO_TAGS:
        try:
            r = requests.get(
                "https://dev.to/api/articles",
                params={"tag": tag, "top": 1, "per_page": 10},
                timeout=15,
            )
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"  [devto] skipped tag '{tag}': {e}")
            continue
        for a in r.json():
            items.append({
                "platform": "devto",
                "title": a["title"],
                "body": (a.get("description") or "")[:500],
                "url": a["url"],
                "engagement": a.get("positive_reactions_count", 0) + a.get("comments_count", 0),
            })
    return items


def fetch_hackernews():
    items = []
    for kw in HN_KEYWORDS:
        try:
            r = requests.get(
                "https://hn.algolia.com/api/v1/search_by_date",
                params={"query": kw, "tags": "story", "numericFilters": f"points>{HN_MIN_POINTS}"},
                timeout=15,
            )
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"  [hackernews] skipped '{kw}': {e}")
            continue
        for hit in r.json().get("hits", [])[:10]:
            items.append({
                "platform": "hackernews",
                "title": hit.get("title") or "",
                "body": (hit.get("story_text") or "")[:500],
                "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                "engagement": (hit.get("points") or 0) + (hit.get("num_comments") or 0),
            })
    return items


def fetch_substack():
    items = []
    for pub in SUBSTACK_PUBLICATIONS:
        try:
            r = requests.get(
                f"https://{pub}.substack.com/api/v1/archive",
                params={"sort": "new", "limit": 10},
                timeout=15,
            )
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"  [substack] skipped '{pub}': {e}")
            continue
        for p in r.json():
            items.append({
                "platform": "substack",
                "title": p.get("title", ""),
                "body": (p.get("description") or "")[:500],
                "url": p.get("canonical_url", ""),
                "engagement": p.get("reaction_count", 0) + p.get("comment_count", 0),
            })
    return items


# ---------------------------------------------------------------------------
# Dedupe against what's already in Notion (so re-running daily doesn't
# re-add still-hot threads)
# ---------------------------------------------------------------------------

def get_existing_urls():
    urls = set()
    payload = {"page_size": 100}
    while True:
        r = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query",
            headers=NOTION_HEADERS,
            json=payload,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        for page in data["results"]:
            url_val = page["properties"].get("Source URL", {}).get("url")
            if url_val:
                urls.add(url_val)
        if data.get("has_more"):
            payload["start_cursor"] = data["next_cursor"]
        else:
            break
    return urls


# ---------------------------------------------------------------------------
# Scoring — one OpenAI call per item
# ---------------------------------------------------------------------------

def score_item(item):
    prompt = f"""You are helping a content team decide what to write about.

Content focus: {CONTENT_PILLARS}

Here is a raw discussion/article found today:
Platform: {item['platform']}
Title: {item['title']}
Snippet: {item['body']}

Score how good a content idea this is for the team above, from 0-10
(0 = irrelevant/low value, 10 = highly relevant and timely).
Then pick the single best format for it: one of "blog", "linkedin", "devto", "youtube".
Then give a one-sentence reason.

Respond with ONLY a JSON object, no other text, in this exact shape:
{{"score": <int 0-10>, "format": "<blog|linkedin|devto|youtube>", "reason": "<one sentence>"}}
"""
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENAI_MODEL,
            "max_tokens": 200,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30,
    )
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        print(f"  [score] could not parse response: {text[:200]}")
        return None
    if not all(k in parsed for k in ("score", "format", "reason")):
        return None
    return parsed


# ---------------------------------------------------------------------------
# Output — write to Notion
# ---------------------------------------------------------------------------

def save_to_notion(item, scored):
    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Idea": {"title": [{"text": {"content": item["title"][:200]}}]},
            "Format": {"select": {"name": scored["format"]}},
            "Score": {"number": scored["score"]},
            "Source Platform": {"select": {"name": item["platform"]}},
            "Source URL": {"url": item["url"]},
            "Why": {"rich_text": [{"text": {"content": scored["reason"][:500]}}]},
            "Status": {"select": {"name": "New"}},
            "Date Added": {"date": {"start": datetime.now(timezone.utc).date().isoformat()}},
        },
    }
    r = requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json=payload, timeout=15)
    if r.status_code >= 300:
        print(f"  [notion] failed to save '{item['title'][:50]}': {r.status_code} {r.text[:200]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    check_env()

    print("Fetching raw items...")
    raw = fetch_reddit() + fetch_devto() + fetch_hackernews() + fetch_substack()
    print(f"  found {len(raw)} raw items")

    print("Checking against existing Notion rows...")
    existing = get_existing_urls()
    fresh = [i for i in raw if i["url"] and i["url"] not in existing]
    print(f"  {len(fresh)} are new")

    saved = 0
    for item in fresh:
        scored = score_item(item)
        time.sleep(0.5)  # be gentle on rate limits
        if not scored:
            continue
        if scored["score"] >= MIN_SCORE_TO_SAVE:
            save_to_notion(item, scored)
            saved += 1
            print(f"  saved ({scored['score']}/10, {scored['format']}): {item['title'][:70]}")

    print(f"Done. Saved {saved} new ideas to Notion.")


if __name__ == "__main__":
    main()
