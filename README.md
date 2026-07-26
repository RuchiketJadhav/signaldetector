Content Idea Bot — tuned for HydraDB

A daily job that reads dev.to, Hacker News, Substack, and (optionally) Reddit, scores each item against HydraDB's actual positioning and five content pillars with one OpenAI call, and writes anything good into a Notion database — a running, ranked list of article/LinkedIn/dev.to ideas instead of a one-time report. Optionally also writes into HydraDB itself.

How it works
INGEST (dev.to, HN, Medium, Substack, [Reddit])
   → DEDUPE (skip anything already in the Notion database)
   → SCORE (1 OpenAI call/item → relevance, narrative strength, format,
            funnel stage, framing-risk check, pain point — see below)
   → WRITE (relevance ≥ threshold → new row in Notion, [+ a memory in HydraDB])

Runs on a schedule via GitHub Actions — no server, no scraping infrastructure, no framework. One Python file, one dependency (requests) (Medium is read via its public per-tag RSS feeds — no API key needed, same zero-signup deal as dev.to and Hacker News).

How ranking works (and why it changed)

The first version scored a single generic "relevance" number against a placeholder content description. Two real problems fell out of that: the seed sources (subreddits, Substacks) weren't HydraDB's actual niche, and nothing ever got classified as "linkedin" because the prompt had no sense of what a sharp, on-brand HydraDB take even looks like.

Fixed both. The seed sources now match the assignment's actual list (r/vectordatabase, r/LLMDevs, r/AI_Agents, r/databases, r/MachineLearning, r/Rag; Gradient Flow and TheSequence on Substack — both genuinely cover vector/graph databases, not generic tech). And the scoring prompt now carries HydraDB's real positioning: the five pillars (Agent Memory, Ontologies, Company Brain, Agentic Actions, Context Engineering), the two hard framing rules from the assignment brief (never "the memory layer," never "a stateful GraphDB"), and an explicit list of adjacent categories (vector DBs, memory-layer products, agent frameworks) worth jumping into.

Each item now gets scored on four dimensions instead of one:

relevance_score (0-10) — fit to HydraDB's actual pillars, not generic AI content. Gates whether it's saved at all (MIN_SCORE_TO_SAVE).
narrative_score (0-10) — does this let us make a sharp, opinionated point, not just a recap? Sort the Notion view by this to find the strongest LinkedIn-shaped opportunities first.
format — the prompt explicitly pushes back on defaulting everything technical to "blog": a debate, complaint, or contrarian thread is often a better fit for a LinkedIn reaction post than a full article.
funnel_stage (TOFU/MOFU/BOFU) — TOFU material (doesn't know they need a graph DB yet) is what Deliverable 3 asks for; this tags it so you can filter straight to it.

Plus a framing_risk flag: true when the natural way to write about a topic would tempt the "memory layer" or "stateful GraphDB" mistake (mostly items directly about memory-layer products), so a human editor knows to double-check the framing before publishing.

And a pain_point field: a short summary of the specific complaint or unsolved problem being discussed, filled in only when one is clearly present — a neutral announcement or benchmark post legitimately has none, so most rows leave this blank rather than forcing an answer. This is the column to scan when you want raw material for Deliverable 1 (genuinely useful Reddit replies start from a real, specific complaint) or for leading a TOFU blog post with a real engineering problem instead of a pitch.

Required accounts (only 2)
Service	Why	Cost
OpenAI	scores + classifies each item (gpt-4o-mini)	pay-per-use, a few cents/day at this volume
Notion	destination database	free

Reddit is intentionally optional. Reddit currently requires human-verification on new/flagged developer accounts, which can block the classic reddit.com/prefs/apps signup for reasons unrelated to anything you did wrong. Rather than block this project on that queue, Reddit's two secrets are simply left unset by default — the script detects that and skips Reddit cleanly, no error. Everyone grading/running this gets a fully working pipeline on dev.to + Hacker News + Substack alone. Add Reddit later if/when your app gets approved (steps below).

Setup (5–10 minutes)
1. Get an OpenAI API key

platform.openai.com/api-keys → Create new secret key. (Needs a payment method on file, but this workload costs a few cents a day at gpt-4o-mini rates.)

2. Create the Notion database

New database in Notion with these exact properties:

Property	Type	Notes
Idea	Title	rename Notion's default title column
Format	Select	options: blog, linkedin, devto, youtube
Score	Number	relevance score, 0-10
Narrative Score	Number	0-10 — sort by this to surface the sharpest takes
Funnel Stage	Select	options: TOFU, MOFU, BOFU
Framing Risk	Checkbox	flags items worth a manual framing double-check
Pain Point	Text	filled in only when the source clearly expresses one — most rows leave this blank on purpose
Source Platform	Select	options: reddit, devto, hackernews, medium, substack
Source URL	URL	
Why	Text	
Status	Select	options: New, Queued, Published
Date Added	Date	
3. Create a Notion integration

notion.so/my-integrations → New integration → copy the secret (this is NOTION_API_KEY) → open your database → ••• → Connections → add your integration → copy the database ID from the URL, the 32-character string right after your workspace name and before ?v= (this is NOTION_DATABASE_ID).

4. Put this repo on GitHub

No git required: create a new repo on github.com, then use Add file → Upload files for content_idea_bot.py and requirements.txt. For the workflow file, use Add file → Create new file and type .github/workflows/daily-content-ideas.yml as the file name (GitHub creates the folders automatically) — paste its contents in.

(Or, if you do use git: clone, copy these files in, git add . && git commit -m "content idea bot" && git push.)

5. Add your secrets

Repo → Settings → Secrets and variables → Actions → New repository secret. Add:

OPENAI_API_KEY
NOTION_API_KEY
NOTION_DATABASE_ID

That's it — those 3 are all that's required.

6. Run it

Actions tab → "Daily Content Idea Pull" → Run workflow. Check the logs; it prints what it fetched, skipped, and saved. After that it runs automatically every day on the schedule in the workflow file.

Adding Reddit later (optional)

Reddit closed self-service API registration in November 2025 (their "Responsible Builder Policy") — the old instant create-an-app flow at reddit.com/prefs/apps no longer issues credentials. There's no zero-wait path anymore:

Apply via Reddit's Developer Support form, describing your use case, which subreddits you'll read, and expected request volume. Review the Responsible Builder Policy first. Reddit's target response time is ~7 days.
If approved, you'll get a client ID and secret exactly like the old flow — add them as REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET repo secrets (REDDIT_USER_AGENT is optional).
Next run automatically includes Reddit — no code changes needed.

This is exactly why Reddit is optional here rather than required: a ~7-day manual approval isn't something to block the rest of the pipeline on.
