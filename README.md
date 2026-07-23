# Content Idea Bot

A daily job that reads dev.to, Hacker News, Substack, and (optionally) Reddit,
scores each item for relevance with one Claude call, and writes anything
good into a Notion database — a running, ranked list of article/LinkedIn/
dev.to/YouTube ideas instead of a one-time report.

## How it works

```
INGEST (dev.to, HN, Substack, [Reddit])
   → DEDUPE (skip anything already in the Notion database)
   → SCORE (1 Claude call/item → relevance 0-10 + best format)
   → WRITE (score ≥ threshold → new row in Notion)
```

Runs on a schedule via GitHub Actions — no server, no scraping
infrastructure, no framework. One Python file, one dependency (`requests`).

## Required accounts (only 2)

| Service | Why | Cost |
|---|---|---|
| **OpenAI** | scores + classifies each item (`gpt-4o-mini`) | pay-per-use, a few cents/day at this volume |
| **Notion** | destination database | free |

**Reddit is intentionally optional.** Reddit currently requires
[human-verification on new/flagged developer accounts](https://alternativeto.net/news/2026/3/reddit-will-start-requiring-fishy-accounts-to-verify-they-are-run-by-a-human),
which can block the classic `reddit.com/prefs/apps` signup for reasons
unrelated to anything you did wrong. Rather than block this project on that
queue, Reddit's two secrets are simply left unset by default — the script
detects that and skips Reddit cleanly, no error. Everyone grading/running
this gets a fully working pipeline on dev.to + Hacker News + Substack alone.
Add Reddit later if/when your app gets approved (steps below).

## Setup (5–10 minutes)

### 1. Get an OpenAI API key
platform.openai.com/api-keys → **Create new secret key**. (Needs a payment
method on file, but this workload costs a few cents a day at `gpt-4o-mini`
rates.)

### 2. Create the Notion database
New database in Notion with these exact properties:

| Property | Type | Notes |
|---|---|---|
| Idea | Title | rename Notion's default title column |
| Format | Select | options: `blog`, `linkedin`, `devto`, `youtube` |
| Score | Number | |
| Source Platform | Select | options: `reddit`, `devto`, `hackernews`, `substack` |
| Source URL | URL | |
| Why | Text | |
| Status | Select | options: `New`, `Queued`, `Published` |
| Date Added | Date | |

### 3. Create a Notion integration
notion.so/my-integrations → **New integration** → copy the secret
(this is `NOTION_API_KEY`) → open your database → `•••` → **Connections** →
add your integration → copy the database ID from the URL, the 32-character
string right after your workspace name and before `?v=` (this is
`NOTION_DATABASE_ID`).

### 4. Put this repo on GitHub
**No git required:** create a new repo on github.com, then use
**Add file → Upload files** for `content_idea_bot.py` and
`requirements.txt`. For the workflow file, use **Add file → Create new
file** and type `.github/workflows/daily-content-ideas.yml` as the file
name (GitHub creates the folders automatically) — paste its contents in.

*(Or, if you do use git: clone, copy these files in, `git add . && git commit -m "content idea bot" && git push`.)*

### 5. Add your secrets
Repo → **Settings → Secrets and variables → Actions → New repository
secret**. Add:

- `OPENAI_API_KEY`
- `NOTION_API_KEY`
- `NOTION_DATABASE_ID`

That's it — those 3 are all that's required.

### 6. Run it
**Actions** tab → "Daily Content Idea Pull" → **Run workflow**. Check the
logs; it prints what it fetched, skipped, and saved. After that it runs
automatically every day on the schedule in the workflow file.

## Adding Reddit later (optional)

1. reddit.com/prefs/apps → **create app** → type **script**
   - If this errors or hangs on verification, try old.reddit.com/prefs/apps,
     a different browser/incognito window, and confirm your account's email
     is verified — the human-verification check is account-based, not
     browser-based, so those are the levers that actually help.
2. Add `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` as repo secrets
   (`REDDIT_USER_AGENT` is optional — it defaults to a generic string)
3. Next run automatically includes Reddit — no code changes needed.

## Before relying on it for real

Edit the `CONFIG` block at the top of `content_idea_bot.py` — `SUBREDDITS`,
`DEVTO_TAGS`, `HN_KEYWORDS`, `SUBSTACK_PUBLICATIONS`, and `CONTENT_PILLARS`
are all placeholders. Set them to your actual niche and sources.
