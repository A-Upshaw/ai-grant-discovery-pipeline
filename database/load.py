"""
load.py — INFO 588 Capstone
Reads maryland_full_results.json and loads all records into PostgreSQL.

Pipeline position:
    Scraper → maryland_full_results.json → load.py → PostgreSQL

Usage:
    python load.py --file path/to/maryland_full_results.json

    Or with defaults (looks for maryland_full_results.json in current dir):
    python load.py

"""

import json
import argparse
import os
import psycopg2
from psycopg2.extras import execute_values

# Reads from environment variables so no passwords are hardcoded.
# Set these in your terminal before running:
#   export PG_HOST="localhost"
#   export PG_USER="capstone_admin"
#   export PG_PASSWORD="capstonepw"
#   export PG_DB="funding_opportunities"

DB_CONFIG = {
    "host":     os.environ.get("PG_HOST",     "localhost"),
    "port":     int(os.environ.get("PG_PORT", "5432")),
    "database": os.environ.get("PG_DB",       "funding_opportunities"),
    "user":     os.environ.get("PG_USER",     "capstone_admin"),
    "password": os.environ.get("PG_PASSWORD", "capstonepw"),
}


# ── Insert one opportunity record 

def insert_opportunity(cur, record):
    """
    Inserts one record into the opportunities table.
    Returns the new row's id (used for child table inserts).

    .get() with defaults everywhere — if Azure didn't return a field,
    we fall back to a safe value rather than crashing.
    """

    sql = """
        INSERT INTO opportunities (
            source_id, source_url, state,
            title, opportunity_type, summary, description,
            sponsor, sponsor_website, logo_url, direct_application_url,
            award_value, cash_award,
            date_posted, deadline, rolling,
            global_opportunity, location,
            fee_required, cost_to_participate, equity_percentage, safe_note,
            contact_names, contact_email,
            industry,
            needs_review, review_reason, tokens_used
        ) VALUES (
            %(source_id)s, %(source_url)s, %(state)s,
            %(title)s, %(opportunity_type)s, %(summary)s, %(description)s,
            %(sponsor)s, %(sponsor_website)s, %(logo_url)s, %(direct_application_url)s,
            %(award_value)s, %(cash_award)s,
            %(date_posted)s, %(deadline)s, %(rolling)s,
            %(global_opportunity)s, %(location)s,
            %(fee_required)s, %(cost_to_participate)s, %(equity_percentage)s, %(safe_note)s,
            %(contact_names)s, %(contact_email)s,
            %(industry)s,
            %(needs_review)s, %(review_reason)s, %(tokens_used)s
        ) RETURNING id;
    """

    values = {
        "source_id":             record.get("id",                    None),
        "source_url":            record.get("source_url",            ""),
        "state":                 record.get("state",                 "Maryland"),
        "title":                 record.get("title",                 "Untitled"),
        "opportunity_type":      record.get("opportunity_type",      None),
        "summary":               record.get("summary",               None),
        "description":           record.get("description",           None),
        "sponsor":               record.get("sponsor",               None),
        "sponsor_website":       record.get("sponsor_website",       None),
        "logo_url":              record.get("logo_url",              None),
        "direct_application_url":record.get("direct_application_url",None),
        "award_value":           record.get("award_value",           "Not specified"),
        "cash_award":            record.get("cash_award",            "Not specified"),
        "date_posted":           record.get("date_posted",           "Not specified"),
        "deadline":              record.get("deadline",              "Not specified"),
        "rolling":               record.get("rolling",              "No"),
        "global_opportunity":    record.get("global_opportunity",    "No"),
        "location":              record.get("location",              None),
        "fee_required":          record.get("fee_required",          "No"),
        "cost_to_participate":   record.get("cost_to_participate",   "No"),
        "equity_percentage":     record.get("equity_percentage",     "No"),
        "safe_note":             record.get("safe_note",             "No"),
        "contact_names":         record.get("contact_names",         None),
        "contact_email":         record.get("contact_email",         None),
        "industry":              record.get("industry",              None),
        "needs_review":          record.get("needs_review",          False),
        "review_reason":         record.get("review_reason",         ""),
        "tokens_used":           record.get("tokens_used",           0),
    }

    cur.execute(sql, values)
    return cur.fetchone()[0]   # the new opportunity's id


# Insert child table rows 
# Each of these takes a list from the JSON record and inserts
# one row per item into the appropriate child table.
# execute_values() does a bulk insert — one SQL call instead of N calls.

def insert_award_amounts(cur, opportunity_id, amounts):
    """
    amounts is a list of dicts: [{amount: "$X", context: "..."}, ...]
    """
    if not amounts:
        return
    rows = [(opportunity_id, a.get("amount", ""), a.get("context", "")) for a in amounts]
    execute_values(cur,
        "INSERT INTO award_amounts (opportunity_id, amount, context) VALUES %s",
        rows
    )

def insert_tags(cur, opportunity_id, tags):
    """tags is a list of strings"""
    if not tags:
        return
    rows = [(opportunity_id, tag) for tag in tags]
    execute_values(cur,
        "INSERT INTO tags (opportunity_id, tag) VALUES %s",
        rows
    )

def insert_eligibility(cur, opportunity_id, eligibility):
    """eligibility is a list of strings"""
    if not eligibility:
        return
    rows = [(opportunity_id, criterion) for criterion in eligibility]
    execute_values(cur,
        "INSERT INTO eligibility_criteria (opportunity_id, criterion) VALUES %s",
        rows
    )

def insert_areas_of_focus(cur, opportunity_id, areas):
    """areas is a list of strings"""
    if not areas:
        return
    rows = [(opportunity_id, area) for area in areas]
    execute_values(cur,
        "INSERT INTO areas_of_focus (opportunity_id, area) VALUES %s",
        rows
    )

def insert_sdg(cur, opportunity_id, sdg_value):
    """
    sdg_alignment in the JSON is a single string, not a list.
    We skip empty / 'Not specified' values.
    """
    if not sdg_value or sdg_value.lower() in ("not specified", "none", ""):
        return
    cur.execute(
        "INSERT INTO sdg_alignments (opportunity_id, sdg_tag) VALUES (%s, %s)",
        (opportunity_id, sdg_value)
    )

def insert_dollar_scan(cur, opportunity_id, dollar_lines):
    """dollar_scan is a list of raw strings from BS4"""
    if not dollar_lines:
        return
    rows = [(opportunity_id, line) for line in dollar_lines]
    execute_values(cur,
        "INSERT INTO dollar_scan_lines (opportunity_id, raw_line) VALUES %s",
        rows
    )



# Deduplication check

def already_exists(cur, source_id, source_url):
    """
    Checks if a record is already in the database.
    Returns True if it exists, False if it is new.

    source_id (Knack record ID) is the primary deduplication key — it is the
    ID Knack assigns to each record and it never changes even if the URL does.
    source_url is a fallback check if source_id is missing.

    This is what prevents the daily cron from adding duplicates on repeat runs.
    """
    if source_id:
        cur.execute(
            "SELECT 1 FROM opportunities WHERE source_id = %s LIMIT 1;",
            (source_id,)
        )
        if cur.fetchone():
            return True
    # Fallback: check by URL
    cur.execute(
        "SELECT 1 FROM opportunities WHERE source_url = %s LIMIT 1;",
        (source_url,)
    )
    return cur.fetchone() is not None


# Load one record (parent + all children) 

def load_record(cur, record):
    """
    Inserts one complete opportunity record into all tables.
    Skips the record if it already exists (deduplication via source_id).
    All inserts happen inside the same transaction — if any fail,
    the whole record rolls back. No partial data.

    Returns: 'inserted', 'skipped', or raises an exception.
    """
    source_id  = record.get("id",         "")
    source_url = record.get("source_url", "")

    # Deduplication check — skip if already in the database
    if already_exists(cur, source_id, source_url):
        return "skipped"

    opp_id = insert_opportunity(cur, record)

    insert_award_amounts(cur, opp_id, record.get("award_amounts", []))
    insert_tags(        cur, opp_id, record.get("tags",          []))
    insert_eligibility( cur, opp_id, record.get("eligibility",   []))
    insert_areas_of_focus(cur, opp_id, record.get("areas_of_focus", []))
    insert_sdg(         cur, opp_id, record.get("sdg_alignment", ""))
    insert_dollar_scan( cur, opp_id, record.get("dollar_scan",   []))

    return "inserted"



# Main 

def main():
    parser = argparse.ArgumentParser(description="Load Maryland scraper JSON into PostgreSQL")
    parser.add_argument(
        "--file",
        default="maryland_full_results.json",
        help="Path to the scraper output JSON file"
    )
    parser.add_argument(
        "--include-flagged",
        action="store_true",
        default=True,
        help="Also load flagged records (default: True — loads clean + flagged)"
    )
    args = parser.parse_args()

    #Read JSON 
    print(f"Reading: {args.file}")
    with open(args.file, "r") as f:
        data = json.load(f)

    clean_records   = data.get("clean",   [])
    flagged_records = data.get("flagged", [])
    error_records   = data.get("errors",  [])

    records_to_load = clean_records
    if args.include_flagged:
        records_to_load = clean_records + flagged_records

    print(f"  Clean:   {len(clean_records)}")
    print(f"  Flagged: {len(flagged_records)}")
    print(f"  Errors:  {len(error_records)}  (skipped — no data to insert)")
    print(f"  Loading: {len(records_to_load)} records")

    # Connect
    print(f"\nConnecting to {DB_CONFIG['host']}:{DB_CONFIG['port']} → {DB_CONFIG['database']}")
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()

    # Load records
    loaded   = 0
    skipped  = 0
    dupes    = 0

    for record in records_to_load:
        try:
            result = load_record(cur, record)
            conn.commit()
            if result == "inserted":
                loaded += 1
                print(f"  NEW [{loaded}] {record.get('title', 'Unknown')}")
            else:
                dupes += 1
                print(f"  DUP  {record.get('title', 'Unknown')}  (already in DB)")
        except Exception as e:
            conn.rollback()
            skipped += 1
            print(f"  ERR  {record.get('title', 'Unknown')} -- {e}")

    # Summary 
    print(f"\nDone.")
    print(f"  New records loaded: {loaded}")
    print(f"  Duplicates skipped: {dupes}")
    print(f"  Errors skipped:     {skipped}")
    # Quick verify
    cur.execute("SELECT COUNT(*) FROM opportunities;")
    total = cur.fetchone()[0]
    print(f"  Total rows in opportunities table: {total}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
