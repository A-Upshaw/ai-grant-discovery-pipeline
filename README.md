# AI-Driven ELT Pipeline for State-Level Funding Opportunity Discovery

An end-to-end data pipeline that automatically discovers, extracts, and structures state government funding programs for small businesses — built as a capstone project for **Runwei**, a platform that aggregates non-dilutive funding opportunities for entrepreneurs.

> **Maryland validation run:** 54 programs processed end-to-end. 36 clean and database-ready. 15 flagged by automated review for human confirmation. 3 errored due to broken source URLs at the government site — all handled gracefully.

---

## The Problem

State governments publish grants, loans, tax credits, fellowships, and accelerator programs across dozens of agency websites with no standardized format and no unified access point. A small business owner looking for funding must manually visit each agency portal, read each program page, and determine eligibility on their own.

Runwei solves this — but cannot deliver on that promise without reliable, structured, current data. The bottleneck is data acquisition at scale across 50 structurally inconsistent state government sources.

---

## Architecture

```
[Knack API / HTML Source]
         ↓
[Python Fetch + BeautifulSoup Parse]
         ↓  dollar-line grounding (hallucination prevention)
[Claude / OpenAI Extraction — 28 structured fields]
         ↓
[Automated Quality Validation Layer]
         ↓           ↓
     [Clean]      [Flagged → Human Review]
         ↓
   [PostgreSQL — 8 normalized tables]
         ↓
    [FastAPI — sponsor access]
```

---

## Key Design Decisions

**Knack API discovery** — Maryland's `businessexpress.maryland.gov` runs on a Knack database backend, found via Chrome DevTools network inspection. This eliminated HTML scraping for Maryland and enables clean pagination across all 54 programs.

**Dollar-line grounding** — before sending a page to the AI, every line containing `$` is extracted by BeautifulSoup and passed as a numbered, verified list. The model is explicitly instructed to use only those lines for award values. This was the central hallucination prevention mechanism — zero fabricated dollar amounts in the validated run.

**Dual AI versions** — the pipeline ships in two versions: one using the **Anthropic Claude API** (`claude-3-haiku`) and one using the **OpenAI API** (`gpt-4o-mini`). Same prompts, same output schema, same logging — swappable depending on the deployment environment.

**Automated quality routing** — instead of human review of every record, three checks route records to clean or flagged:
1. More than 4 distinct award amounts found → ambiguous individual award value
2. Award marked "Varies" but specific amounts exist → may hide a real individual award
3. Award value contains M/B/million/billion with multiple amounts → likely a fund total, not individual award

**Normalized PostgreSQL schema** — list fields (tags, eligibility criteria, award amounts, SDG alignments, areas of focus) live in separate child tables. No arrays shoved into single columns. Designed to match Runwei's production schema directly.

**FastAPI access layer** — a read-only REST API sits on top of the database with API key auth, pagination, and filtering. Allows the sponsor's team to query the data without direct database access.

---

## Tech Stack

| Layer | Tool |
|---|---|
| Fetch & Parse | Python, `requests`, `BeautifulSoup4`, `requests.Session` |
| AI Extraction | Anthropic Claude API / OpenAI API |
| Retry Logic | Custom `@with_retry` decorator with exponential backoff |
| Database | PostgreSQL (psycopg2) |
| API Layer | FastAPI + uvicorn |
| Credential Management | python-dotenv — keys never in code |
| Source Backend | Knack REST API (Maryland) |

---

## Pipeline Stages

### Stage 1 — Fetch
Dynamic pagination loop hits the Knack API and retrieves all program records. Each record contains the program name, type, category, and a URL to its detail page.

### Stage 2 — Parse
Each detail page is fetched and two operations run in parallel:
- Full text extraction (`BeautifulSoup.get_text`)
- Dollar-line scan — every line containing `$` extracted as numbered ground truth

### Stage 3 — AI Extraction
Page content + verified dollar lines are sent to the AI model with a structured system prompt requesting 28 specific fields at `temperature=0.1`. Near-deterministic extraction — the model follows field definitions closely rather than paraphrasing.

### Stage 4 — Validate
Three automated checks route each record to `clean_records` or `flagged_records`. Flagged records are not discarded — they are queued for targeted human confirmation on the specific ambiguity detected.

### Stage 5 — Load
`load.py` reads the pipeline JSON output and loads records into PostgreSQL across all 8 tables. Deduplication runs on Knack `source_id` before every insert — safe to rerun on refresh cycles.

---

## Results — Maryland Validation Run

| Outcome | Count |
|---|---|
| Clean (database-ready) | 36 |
| Flagged (human review queued) | 15 |
| Errors (broken source URLs) | 3 |
| Total programs | 54 |
| Total tokens used | ~173,000 |

The 15 flagged records are not pipeline failures — they represent programs with genuinely tiered award structures where "individual award value" requires human judgment (e.g., the Biotechnology Investment Tax Credit has 5 distinct amounts based on Opportunity Zone level).

---

## Repo Structure

```
scrapers/
├── Maryland/
│   ├── Phase 1/          early BeautifulSoup + Azure prototype
│   ├── Phase 3/          v3.5 pipeline (Pipeline_v3.5.ipynb)
│   └── Phase 4/          current production pipeline
│       ├── maryland_pipeline_v3.4.ipynb       Claude version
│       └── maryland_pipeline_v3.4_openai.ipynb  OpenAI version
├── database/
│   ├── schema.sql         8-table normalized schema
│   ├── load.py            JSON → PostgreSQL loader with deduplication
│   ├── main.py            FastAPI application
│   └── requirements.txt   API dependencies
└── .gitignore             .env, venv, *.json, *.log excluded
```

---

## Setup

**1. Clone and install**
```bash
git clone <your-repo-url>
cd scrapers
pip install -r database/requirements.txt
```

**2. Configure environment**
```bash
cp .env.example .env
# Fill in your API keys and database credentials
```

**3. Set up the database**
```bash
psql -U postgres -c "CREATE DATABASE funding_opportunities;"
psql -U postgres -d funding_opportunities -f database/schema.sql
```

**4. Run the pipeline**

Open `Maryland/Phase 4/maryland_pipeline_v3.4.ipynb` (Claude) or `maryland_pipeline_v3.4_openai.ipynb` (OpenAI) in VS Code or Jupyter and run all cells.

**5. Load results into PostgreSQL**
```bash
python database/load.py --file Maryland/Phase\ 4/maryland_full_results.json
```

**6. Start the API**
```bash
cd database
uvicorn main:app --reload
# Interactive docs at http://localhost:8000/docs
```

---

## API Endpoints

All endpoints require header: `X-API-Key: <your-key>`

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Health check |
| GET | `/programs` | All programs — filter by `opportunity_type`, `rolling`, `needs_review` |
| GET | `/programs/{id}` | Full record with all child table data joined |
| GET | `/programs/non-dilutive` | No fees, no equity, no SAFE notes only |
| GET | `/summary` | Counts by type, state, flagged vs clean |

Interactive docs with live testing available at `/docs` when running locally.

---

## Possible Extensions

**Multi-state expansion** — the pipeline is state-agnostic. States using Knack (same API pattern as Maryland) can be onboarded with a config entry. States without a structured backend use the HTML fallback path. The primary scaling effort is catalog research, not code changes.

**Parallel processing** — the current pipeline runs sequentially. A multi-agent framework (CrewAI, LangGraph) would allow simultaneous execution across states. A prototype CrewAI implementation was built during this project. A 50-state run estimated at 8+ hours sequentially could complete in under 30 minutes with parallel agents.

**Adaptive scraping** — an AI-driven discovery agent that analyzes a new state's funding page, identifies where grant data lives, and generates a scraper configuration autonomously — eliminating manual inspection per state entirely.

---

## Background

Built as a MSBA Capstone project (INFO 588) at the University of Maryland. Validated end-to-end on Maryland's 54 state funding programs. Architecture is production-aligned with Runwei's Azure infrastructure and designed for the multi-state expansion their platform requires.
