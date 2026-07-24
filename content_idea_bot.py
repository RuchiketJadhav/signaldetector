"""
Daily content-idea bot — tuned for HydraDB's actual positioning and pillars.

Pulls raw signal from dev.to, Hacker News, and Substack (all zero-signup),
plus Reddit if credentials are provided, scores each item against HydraDB's
real brand context with a single OpenAI call (relevance, narrative strength,
format, funnel stage, framing-risk check), and writes anything above
MIN_SCORE_TO_SAVE into a Notion database as a new row.

Only 3 secrets are required to run at all: OPENAI_API_KEY, NOTION_API_KEY,
NOTION_DATABASE_ID. Reddit's two secrets are optional — leave them unset and
that source is skipped automatically. HYDRADB_API_KEY is also optional: set
it to additionally store every saved idea as a memory in HydraDB's own graph
(dogfooding the product as its own "Company Brain" content-intelligence
store) alongside the Notion write.

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

SUBREDDITS = ["vectordatabase", "LLMDevs", "AI_Agents", "databases", "MachineLearning", "Rag"]
REDDIT_MIN_SCORE = 10          # these are smaller/more niche subreddits than generic AI ones
REDDIT_TIME_WINDOW = "day"     # day | week

DEVTO_TAGS = ["ai", "machinelearning", "database", "llm"]

# Hacker News needs no API key at all (Algolia's public HN search API).
# Keyword-based since HN has no per-topic feeds like subreddits do.
HN_KEYWORDS = ["graph database", "vector database", "AI agent memory", "knowledge graph"]
HN_MIN_POINTS = 15

# Substack has no site-wide "trending" API, so list the specific newsletters
# you want tracked (the part before ".substack.com" — custom-domain Substacks
# like latent.space don't follow this pattern and need a different URL).
# These two are genuinely on-topic: Gradient Flow covers vector/graph DBs and
# GraphRAG specifically; TheSequence is a large, technical AI/ML newsletter.
SUBSTACK_PUBLICATIONS = ["gradientflow", "thesequence"]

HYDRADB_BRAND = """
COMPANY: HydraDB — a fast, cheap graph database built on object storage,
purpose-built for AI agent memory, ontologies, company brain, and agentic
actions. HydraDB is the INFRASTRUCTURE LAYER other things (including memory
layers, ontology tools, and agent frameworks) get built ON TOP OF. It is not
itself a memory layer.

FIVE CONTENT PILLARS (every idea should map to at least one):
1. Agent Memory — building in-house, owned memory systems for AI agents
2. Ontologies — structured knowledge graphs and entity/relationship modeling
3. Company Brain — an org's institutional knowledge as a queryable graph
4. Agentic Actions — agents that act on structured context, not just retrieve it
5. Context Engineering — assembling the right context (not just similar context)
   for an agent at the right moment

HARD RULES — violating either of these is a real error, not a style nitpick:
- NEVER describe HydraDB itself as "the memory layer" or "a memory layer."
  HydraDB is what memory layers are built on top of. ("Own your memory
  layer, built on HydraDB" is fine — positioning HydraDB itself AS the
  memory layer is not.)
- NEVER call HydraDB "a stateful GraphDB" or describe statefulness as what
  HydraDB is. Statefulness is an OUTCOME for apps built on HydraDB, not a
  description of the product.

PREFERRED LANGUAGE: "context substrate," "graph AI runs on," "infrastructure
layer," "primitives, not abstractions," "the graph other things are built on."

AUDIENCE FOR BLOG/TOFU CONTENT: a developer who doesn't know they need a
graph database yet — not someone already comparing vendors. Lead with a
real engineering problem (retrieval breaking at scale, embeddings losing
relationships, agents forgetting context), not a product pitch.

ADJACENT CATEGORIES WORTH JUMPING INTO (raw items mentioning these are
high-value "join the conversation" opportunities, since HydraDB positions
itself as the substrate underneath these categories, not a direct
competitor to them): vector databases (Pinecone, Weaviate, Qdrant, Milvus),
memory-layer products (Zep, Mem0, Letta/MemGPT), agent frameworks
(LangGraph, CrewAI, AutoGen, LlamaIndex), knowledge-graph/GraphRAG tooling.
"""

MIN_SCORE_TO_SAVE = 6  # 0-10 — only items scoring at/above this get saved

# Notion property names — must match your database's column names exactly
# (Notion property names are case- and space-sensitive). If your database
# already uses different names, edit the values here instead of renaming
# your Notion columns.
NOTION_PROPS = {
    "idea": "Idea",
    "format": "Format",
    "score": "Score",
    "narrative_score": "Narrative Score",
    "funnel_stage": "Funnel Stage",
    "framing_risk": "Framing Risk",
    "source_platform": "Source Platform",
    "source_url": "Source URL",
    "why": "Why",
    "status": "Status",
    "date_added": "Date Added",
}

# ---------------------------------------------------------------------------
# Secrets — set these as GitHub repo secrets, never hardcode them.
# ---------------------------------------------------------------------------

REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.environ.get("REDDIT_USER_AGENT", "content-idea-bot/0.1")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")

# Optional — dogfooding HydraDB itself as a second, parallel write target.
# Notion stays the reliable, always-on running list; this is a "Company
# Brain" bonus: raw signal stored as memories in HydraDB's own graph, which
# auto-extracts entities/relationships (competitor mentions, pillar themes)
# as it ingests. Leave HYDRADB_API_KEY unset and this is skipped entirely.
HYDRADB_API_KEY = os.environ.get("HYDRADB_API_KEY", "")
HYDRADB_TENANT_ID = os.environ.get("HYDRADB_TENANT_ID", "content-signal-brain")

# Cheap, fast, supports guaranteed JSON output — good fit for a per-item
# classification call. Swap this string if you'd rather use another model.
OPENAI_MODEL = "gpt-4o-mini"

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# Some publications block the default python-requests user agent. This
# doesn't help if a site is blocking by IP range (some do block known
# cloud/datacenter ranges, which GitHub Actions runners are), but it's a
# real fix for plain user-agent-based bot filters, which is more common.
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
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
                headers={**BROWSER_HEADERS, "Referer": f"https://{pub}.substack.com/"},
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

def validate_notion_schema():
    r = requests.get(
        f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}",
        headers=NOTION_HEADERS,
        timeout=15,
    )
    if r.status_code >= 300:
        print(f"  [notion] could not read the database schema: {r.status_code} {r.text[:300]}")
        if r.status_code == 404:
            print("  [notion] check the database is shared with your integration (see README)")
        sys.exit(1)
    existing = r.json().get("properties", {})
    missing = [name for name in NOTION_PROPS.values() if name not in existing]
    if missing:
        print("  [notion] your database is missing these properties (name AND type must match exactly):")
        for name in missing:
            print(f"    - {name}")
        print("  [notion] either add them in Notion, or edit NOTION_PROPS at the top of this")
        print("  [notion] script to match whatever names your database already uses.")
        sys.exit(1)
    print("  [notion] schema check passed")


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
        if r.status_code >= 300:
            print(f"  [notion] could not query the database: {r.status_code} {r.text[:300]}")
            if r.status_code == 404:
                print("  [notion] a 404 here almost always means the database hasn't been")
                print("  [notion] shared with your integration yet. Fix: open the database in")
                print("  [notion] Notion -> ••• (top right) -> Connections -> add your integration.")
            sys.exit(1)
        data = r.json()
        for page in data["results"]:
            url_val = page["properties"].get(NOTION_PROPS["source_url"], {}).get("url")
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
    prompt = f"""You are the content strategist for HydraDB, deciding what's
worth writing about from a raw discussion found today.

{HYDRADB_BRAND}

Raw item found today:
Platform: {item['platform']}
Title: {item['title']}
Snippet: {item['body']}

Score this on FOUR dimensions:

1. relevance_score (0-10): how well this maps to HydraDB's actual pillars
   and use cases above — not generic "AI/LLM" relevance. A post about
   vector DB limitations, agent memory, ontologies, or GraphRAG scores
   high. A post about AI in general with no infra angle scores low.

2. narrative_score (0-10): does this raw material let us make a SHARP,
   differentiated point of view — a real opinion, not a recap? Threads
   with a debate, a misconception, a complaint, or a contrarian angle
   score higher here than neutral tutorials, even if both are relevant.

3. format: the single best fit — one of "blog", "linkedin", "devto",
   "youtube". Don't default to "blog" for everything technical: if the raw
   material has a strong opinion, debate, or hot-take shape, that's often
   a BETTER fit for "linkedin" (a reaction/POV post) than a full article,
   even when the source itself is a technical thread.

4. funnel_stage: "TOFU" (doesn't know they need a graph DB yet — lead with
   an engineering problem), "MOFU" (knows the category, evaluating
   approaches), or "BOFU" (comparing specific vendors).

Also check: would writing about this risk violating either hard rule above
(calling HydraDB "the memory layer" itself, or "a stateful GraphDB")? Set
framing_risk to true if the natural way to write this topic would tempt
that mistake (e.g. anything about memory-layer products directly), so a
human editor knows to watch for it. Otherwise false.

Respond with ONLY a JSON object, no other text, in this exact shape:
{{"relevance_score": <int 0-10>, "narrative_score": <int 0-10>,
  "format": "<blog|linkedin|devto|youtube>", "funnel_stage": "<TOFU|MOFU|BOFU>",
  "framing_risk": <true|false>, "reason": "<one sentence>"}}
"""
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENAI_MODEL,
            "max_tokens": 300,
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
    required = ("relevance_score", "narrative_score", "format", "funnel_stage", "framing_risk", "reason")
    if not all(k in parsed for k in required):
        print(f"  [score] response missing expected fields: {text[:200]}")
        return None
    return parsed


# ---------------------------------------------------------------------------
# Output — write to Notion
# ---------------------------------------------------------------------------

def save_to_notion(item, scored):
    p = NOTION_PROPS
    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            p["idea"]: {"title": [{"text": {"content": item["title"][:200]}}]},
            p["format"]: {"select": {"name": scored["format"]}},
            p["score"]: {"number": scored["relevance_score"]},
            p["narrative_score"]: {"number": scored["narrative_score"]},
            p["funnel_stage"]: {"select": {"name": scored["funnel_stage"]}},
            p["framing_risk"]: {"checkbox": bool(scored["framing_risk"])},
            p["source_platform"]: {"select": {"name": item["platform"]}},
            p["source_url"]: {"url": item["url"]},
            p["why"]: {"rich_text": [{"text": {"content": scored["reason"][:500]}}]},
            p["status"]: {"select": {"name": "New"}},
            p["date_added"]: {"date": {"start": datetime.now(timezone.utc).date().isoformat()}},
        },
    }
    r = requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json=payload, timeout=15)
    if r.status_code >= 300:
        print(f"  [notion] failed to save '{item['title'][:50]}': {r.status_code} {r.text[:200]}")
        if r.status_code == 404:
            print("  [notion] check the database is shared with your integration (see README)")
        return False
    return True


# ---------------------------------------------------------------------------
# Optional — dogfood HydraDB itself as a second write target ("Company
# Brain" use case: our own content-intelligence graph, built on HydraDB).
# ---------------------------------------------------------------------------

def save_to_hydradb(item, scored):
    if not HYDRADB_API_KEY:
        return None  # silently skip — this is a bonus layer, not required
    text = (
        f"[{item['platform']}] {item['title']} — {scored['reason']} "
        f"(relevance {scored['relevance_score']}/10, narrative {scored['narrative_score']}/10, "
        f"format: {scored['format']}, funnel: {scored['funnel_stage']}) Source: {item['url']}"
    )
    r = requests.post(
        "https://api.hydradb.com/memories/add_memory",
        headers={"Authorization": f"Bearer {HYDRADB_API_KEY}", "Content-Type": "application/json"},
        json={
            "tenant_id": HYDRADB_TENANT_ID,
            "sub_tenant_id": "content-signals",
            "memories": [{"text": text, "infer": True}],  # infer=True: let HydraDB
            # extract entities/relationships (competitors, pillars, themes)
            # automatically instead of storing this as an inert blob.
        },
        timeout=15,
    )
    if r.status_code >= 300:
        print(f"  [hydradb] failed to save '{item['title'][:50]}': {r.status_code} {r.text[:200]}")
        return False
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    check_env()

    print("Checking Notion database schema...")
    validate_notion_schema()

    print("Fetching raw items...")
    raw = fetch_reddit() + fetch_devto() + fetch_hackernews() + fetch_substack()
    print(f"  found {len(raw)} raw items")

    print("Checking against existing Notion rows...")
    existing = get_existing_urls()
    fresh = [i for i in raw if i["url"] and i["url"] not in existing]
    print(f"  {len(fresh)} are new")

    saved, failed_to_save, scoring_failed = 0, 0, 0
    hydradb_saved = 0
    for item in fresh:
        scored = score_item(item)
        time.sleep(0.5)  # be gentle on rate limits
        if not scored:
            scoring_failed += 1
            continue
        if scored["relevance_score"] >= MIN_SCORE_TO_SAVE:
            if save_to_notion(item, scored):
                saved += 1
                flag = " ⚠ framing risk" if scored["framing_risk"] else ""
                print(f"  saved (rel {scored['relevance_score']}/10, narr {scored['narrative_score']}/10, "
                      f"{scored['format']}, {scored['funnel_stage']}){flag}: {item['title'][:60]}")
                if save_to_hydradb(item, scored):
                    hydradb_saved += 1
            else:
                failed_to_save += 1

    print(f"Done. Saved {saved} new ideas to Notion.")
    if HYDRADB_API_KEY:
        print(f"Also saved {hydradb_saved} to HydraDB's own graph (tenant: {HYDRADB_TENANT_ID}).")
    if failed_to_save:
        print(f"WARNING: {failed_to_save} items scored high enough but failed to write — see [notion] errors above.")
    if scoring_failed:
        print(f"Note: {scoring_failed} items could not be scored and were skipped.")


if __name__ == "__main__":
    main()
