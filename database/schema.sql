-- ============================================================
-- INFO 588 Capstone — Funding Opportunities Pipeline
-- Database Schema — Updated to match Runwei platform columns
-- ============================================================
-- INFO 574 connection: normalization, primary/foreign keys,
-- data types, constraints — all concepts from Database Systems.
--
-- Design philosophy:
--   One table for the funding opportunity itself (core record).
--   Separate tables for list fields (tags, eligibility, amounts,
--   SDGs, areas of focus) so we don't shove arrays into one column.
--   That's 1NF/2NF — one fact per field, no repeating groups.
--
-- Note on empty fields:
--   State government sites won't populate every column.
--   Fields that can't be found are stored as 'Not specified'.
--   That's accurate data — not a failure to extract.
-- ============================================================


-- ------------------------------------------------------------
-- TABLE: opportunities
-- The main record for each funding program.
-- One row = one funding opportunity.
-- All columns match the Runwei platform schema.
-- ------------------------------------------------------------
CREATE TABLE opportunities (
    id                      SERIAL PRIMARY KEY,
    source_id               VARCHAR(100),               -- Knack record ID from the API
    source_url              TEXT NOT NULL,              -- detail page URL we scraped
    state                   VARCHAR(50) DEFAULT 'Maryland',

    -- Core identity
    title                   TEXT NOT NULL,
    opportunity_type        VARCHAR(100),               -- Grant, Loan, Tax Credit, Forgivable Loan, etc.
    summary                 TEXT,                       -- 2 sentences max (Runwei platform field)
    description             TEXT,                       -- 5-10 sentences, full detail

    -- Sponsor info
    sponsor                 VARCHAR(255),               -- entity offering the opportunity
    sponsor_website         TEXT,                       -- sponsor's primary website URL
    logo_url                TEXT,                       -- logo image URL or 'No logo URL found'
    direct_application_url  TEXT,                       -- direct submission/application link

    -- Award info
    award_value             VARCHAR(255),               -- best single amount or 'Varies' / 'Not specified'
    cash_award              VARCHAR(255),               -- cash portion if separate from total award

    -- Dates
    date_posted             VARCHAR(50),                -- MM-DD-YYYY format or 'Not specified'
    deadline                VARCHAR(100),               -- MM-DD-YYYY or 'Rolling'
    rolling                 VARCHAR(10) DEFAULT 'No',   -- Yes / No

    -- Geography
    global_opportunity      VARCHAR(10) DEFAULT 'No',   -- Yes / No
    location                VARCHAR(255),

    -- Compliance flags (important for non-dilutive verification)
    fee_required            VARCHAR(100) DEFAULT 'No',  -- No | Yes - $X
    cost_to_participate     VARCHAR(100) DEFAULT 'No',  -- No | Yes - $X
    equity_percentage       VARCHAR(100) DEFAULT 'No',  -- No | Yes - X%
    safe_note               VARCHAR(100) DEFAULT 'No',  -- No | Yes - details

    -- Contact
    contact_names           TEXT,                       -- names if available
    contact_email           TEXT,                       -- email if available

    -- Classification
    industry                VARCHAR(255),

    -- Pipeline metadata
    needs_review            BOOLEAN DEFAULT FALSE,
    review_reason           TEXT,
    tokens_used             INTEGER,
    scraped_at              TIMESTAMP DEFAULT NOW()
);


-- ------------------------------------------------------------
-- TABLE: award_amounts
-- All dollar amounts found on the page, each with context.
-- One row = one dollar amount for one opportunity.
-- Scraper field: award_amounts (list of {amount, context})
-- ------------------------------------------------------------
CREATE TABLE award_amounts (
    id              SERIAL PRIMARY KEY,
    opportunity_id  INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    amount          VARCHAR(100) NOT NULL,
    context         TEXT
);


-- ------------------------------------------------------------
-- TABLE: tags
-- Keyword tags extracted by Azure.
-- One row = one tag for one opportunity.
-- Scraper field: tags (list of strings)
-- ------------------------------------------------------------
CREATE TABLE tags (
    id              SERIAL PRIMARY KEY,
    opportunity_id  INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    tag             VARCHAR(255) NOT NULL
);


-- ------------------------------------------------------------
-- TABLE: opportunity_categories
-- Full category list from Runwei platform.
-- One row = one category for one opportunity.
-- Examples: Grant, Loan, Tax Credit, Forgivable Loan,
--           Accelerator, Incubator, Fellowship, etc.
-- ------------------------------------------------------------
CREATE TABLE opportunity_categories (
    id              SERIAL PRIMARY KEY,
    opportunity_id  INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    category        VARCHAR(255) NOT NULL
);


-- ------------------------------------------------------------
-- TABLE: areas_of_focus
-- Opportunity Gap Resources from Runwei spec.
-- Options: Capital, Networks, Capacity Building
-- One row = one area for one opportunity.
-- ------------------------------------------------------------
CREATE TABLE areas_of_focus (
    id              SERIAL PRIMARY KEY,
    opportunity_id  INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    area            VARCHAR(255) NOT NULL
);


-- ------------------------------------------------------------
-- TABLE: eligibility_criteria
-- Eligibility bullet points extracted by Azure.
-- One row = one requirement for one opportunity.
-- Scraper field: eligibility (list of strings)
-- ------------------------------------------------------------
CREATE TABLE eligibility_criteria (
    id              SERIAL PRIMARY KEY,
    opportunity_id  INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    criterion       TEXT NOT NULL
);


-- ------------------------------------------------------------
-- TABLE: sdg_alignments
-- UN SDG tags if present on the page.
-- Example: 'SDG 8 Decent Work and Economic Growth'
-- One row = one SDG for one opportunity.
-- ------------------------------------------------------------
CREATE TABLE sdg_alignments (
    id              SERIAL PRIMARY KEY,
    opportunity_id  INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    sdg_tag         VARCHAR(255) NOT NULL
);


-- ------------------------------------------------------------
-- TABLE: dollar_scan_lines
-- Raw BS4 ground truth scan — every line containing "$".
-- Audit trail: proves Azure didn't hallucinate amounts.
-- One row = one raw line from the page.
-- ------------------------------------------------------------
CREATE TABLE dollar_scan_lines (
    id              SERIAL PRIMARY KEY,
    opportunity_id  INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    raw_line        TEXT NOT NULL
);


-- ============================================================
-- EXAMPLE QUERIES
-- ============================================================

-- Q1: All Maryland grants, clean records only
-- SELECT title, award_value, deadline, rolling
-- FROM opportunities
-- WHERE state = 'Maryland'
--   AND opportunity_type = 'Grant'
--   AND needs_review = FALSE
-- ORDER BY title;

-- Q2: All flagged records
-- SELECT title, review_reason
-- FROM opportunities
-- WHERE needs_review = TRUE;

-- Q3: All non-dilutive verified records (no fee, no equity, no debt)
-- SELECT title, award_value, opportunity_type
-- FROM opportunities
-- WHERE fee_required = 'No'
--   AND equity_percentage = 'No'
--   AND safe_note = 'No';

-- Q4: Full amount audit trail for one program
-- SELECT o.title, a.amount, a.context
-- FROM opportunities o
-- JOIN award_amounts a ON o.id = a.opportunity_id
-- WHERE o.title = 'Maryland E-Nnovation Initiative';

-- Q5: Programs by opportunity type
-- SELECT opportunity_type, COUNT(*) AS total
-- FROM opportunities
-- GROUP BY opportunity_type
-- ORDER BY total DESC;

-- Q6: Programs by state (when PA, NY, DC are added)
-- SELECT state, COUNT(*) AS programs
-- FROM opportunities
-- GROUP BY state
-- ORDER BY state;

-- Q7: Token cost tracking
-- SELECT state, SUM(tokens_used) AS total_tokens
-- FROM opportunities
-- GROUP BY state;
