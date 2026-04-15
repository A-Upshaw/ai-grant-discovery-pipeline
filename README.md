# AI-Driven ELT Pipeline for State-Level Funding Opportunity Discovery

An end-to-end data pipeline that automatically discovers, extracts, and structures state government funding programs for small businesses.


---

## Background

Built as a MSBA Capstone project (INFO 588) at Montclair State University. Small businesses face a fragmented funding landscape state governments publish grants, loans, tax credits, fellowships, and accelerator programs across dozens of agency websites with no standardized format and no unified access point. This pipeline automates discovery and extraction at scale, turning unstructured government web pages into structured, queryable data.

The project progressed through three phases:
- **Phase 1**: Evaluated two extraction approaches independently: Azure OpenAI (AI-driven) vs. BeautifulSoup (rule-based HTML parsing)
- **Phase 2**: Combined both: BeautifulSoup as a dollar-line ground truth check to prevent AI hallucination, Azure OpenAI for structured 28-field extraction
- **Phase 3 (Final)**: Added secondary URL analysis, timestamped logging per run, retry logic with exponential backoff, and dual AI support (Claude + OpenAI)

---

## Architecture

> _Architecture diagram coming soon: built with draw.io_


---

## Key Design Decisions

**Knack API discovery**: Maryland's `businessexpress.maryland.gov` runs on a Knack database backend, found via Chrome DevTools network inspection. This eliminated HTML scraping for Maryland and enables clean pagination across all pages.

**Dollar-line grounding**: before sending a page to the AI, every line containing `$` is extracted by BeautifulSoup and passed as a numbered, verified list. The model is explicitly instructed to use only those lines for award values. This was the central hallucination prevention mechanism: zero fabricated dollar amounts in the validated run.

**Dual AI versions**: the pipeline ships in two versions: one using the **Anthropic Claude API** (`claude-3-haiku`) and one using the **OpenAI API** (`gpt-4o-mini`). Same prompts, same output schema, same logging: swappable depending on the deployment environment.

**Automated quality routing**: instead of human review of every record, three checks route records to clean or flagged:
1. More than 4 distinct award amounts found → ambiguous individual award value
2. Award marked "Varies" but specific amounts exist → may hide a real individual award
3. Award value contains M/B/million/billion with multiple amounts → likely a fund total, not individual award

**Normalized PostgreSQL schema**: list fields (tags, eligibility criteria, award amounts, SDG alignments, areas of focus) live in separate child tables. No arrays shoved into single columns.

**FastAPI access layer**: a read-only REST API sits on top of the database with API key auth, pagination, and filtering.

---

## Tech Stack

| Layer | Tool |
|---|---|
| Fetch & Parse | Python, `requests`, `BeautifulSoup4`, `requests.Session` |
| AI Extraction | Anthropic Claude API / OpenAI API |
| Retry Logic | Custom `@with_retry` decorator with exponential backoff |
| Database | PostgreSQL (psycopg2) |
| API Layer | FastAPI + uvicorn |
| Credential Management | python-dotenv: keys never in code |
| Source Backend | Knack REST API (Maryland) |

---

## Pipeline Stages

### Stage 1: Fetch
Dynamic pagination loop hits the Knack API and retrieves all program records. Each record contains the program name, type, category, and a URL to its detail page.

### Stage 2: Parse
Each detail page is fetched and two operations run in parallel:
- Full text extraction (`BeautifulSoup.get_text`)
- Dollar-line scan: every line containing `$` extracted as numbered ground truth

### Stage 3: AI Extraction
Page content + verified dollar lines are sent to the AI model with a structured system prompt requesting 28 specific fields at `temperature=0.1`. Near-deterministic extraction the model follows field definitions closely rather than paraphrasing.

### Stage 4: Validate
Three automated checks route each record to `clean_records` or `flagged_records`. Flagged records are not discarded: they are queued for targeted human confirmation on the specific ambiguity detected.

### Stage 5: Load
`load.py` reads the pipeline JSON output and loads records into PostgreSQL across all 8 tables. Deduplication runs on Knack `source_id` before every insert safe to rerun on refresh cycles.

---

## Results: Maryland Validation Run

| Outcome | Count |
|---|---|
| Clean (database-ready) | 36 |
| Flagged (human review queued) | 15 |
| Errors (broken source URLs) | 3 |
| Total programs | 54 |
| Total tokens used | ~173,000 |

The 15 flagged records are not pipeline failures they represent programs with genuinely tiered award structures where "individual award value" requires human judgment.

---

## Repo Structure

├── Phase 1/
│   ├── maryland_pipeline_azure_v1.0.ipynb    Azure-only approach
│   └── maryland_pipeline_bs4_v1.0.ipynb      BeautifulSoup-only approach
├── Phase 2/
│   └── maryland_pipeline_v2.0.ipynb          Combined: BS4 ground truth + Azure extraction
├── Phase 3 - Final/
│   ├── maryland_pipeline_claude.ipynb         Production pipeline (Claude)
│   └── maryland_pipeline_openai.ipynb         Production pipeline (OpenAI)
├── database/
│   ├── schema.sql         8-table normalized schema
│   └── requirements.txt   Dependencies
├── .env.example           Credential template
└── .gitignore

---

## Setup

**1. Clone and install**
```bash
git clone https://github.com/A-Upshaw/ai-grant-discovery-pipeline.git
cd ai-grant-discovery-pipeline
pip install -r database/requirements.txt

**2. Configure environment**
```bash
cp .env.example .env
# Fill in your API keys and database credentials

**3. Set up the database**
```bash
psql -U postgres -c "CREATE DATABASE funding_opportunities;"
psql -U postgres -d funding_opportunities -f database/schema.sql

**4. Run the pipeline**
Open `Phase 3 - Final/maryland_pipeline_claude.ipynb` or `maryland_pipeline_openai.ipynb` in VS Code or Jupyter and run all cells.

```bash
python database/load.py

**6. Start the API**
```bash
cd database
uvicorn main:app --reload
# Interactive docs at http://localhost:8000/docs

---

## API Endpoints

All endpoints require header: `X-API-Key: <your-key>`

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Health check |
| GET | `/programs` | All programs: filter by `opportunity_type`, `rolling`, `needs_review` |
| GET | `/programs/{id}` | Full record with all child table data joined |
| GET | `/programs/non-dilutive` | No fees, no equity, no SAFE notes only |
| GET | `/summary` | Counts by type, state, flagged vs clean |

Interactive docs available at `/docs` when running locally.

---
