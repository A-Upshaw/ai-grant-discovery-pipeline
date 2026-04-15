"""
Grant Scraper Foundation
Capstone Project - AI-Powered Grant Discovery Pipeline
Author: Anthony Upshaw
Date: February 2026

This module provides base classes and utilities for scraping state grant websites.
"""

import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional, List
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# DATA CLASSES - These define the COLUMNS/FIELDS we're extracting
# ============================================================================

@dataclass
class FundingInfo:
    """Funding details for a grant"""
    amount_min: Optional[float] = None
    amount_max: Optional[float] = None
    total_pool: Optional[float] = None
    awards_count: Optional[int] = None


@dataclass  
class DateInfo:
    """Important dates for a grant"""
    posted_date: Optional[str] = None
    application_opens: Optional[str] = None
    deadline: Optional[str] = None
    decision_date: Optional[str] = None


@dataclass
class EligibilityInfo:
    """Who can apply for this grant"""
    business_types: List[str] = None
    location_requirements: Optional[str] = None
    certifications_required: List[str] = None
    other_requirements: Optional[str] = None
    
    def __post_init__(self):
        if self.business_types is None:
            self.business_types = []
        if self.certifications_required is None:
            self.certifications_required = []


@dataclass
class Grant:
    """
    Main Grant data class - THIS IS YOUR SCHEMA
    
    Every field here = a column in your database
    """
    # Core identifiers
    id: str
    title: str
    description: str
    state: str  # NY, PA, MD, DC
    source_url: str
    source_agency: str
    
    # Nested data
    funding: FundingInfo
    dates: DateInfo
    eligibility: EligibilityInfo
    
    # Categorization
    sector: Optional[str] = None  # Technology, Manufacturing, etc.
    program_type: Optional[str] = None  # grant, loan, tax_credit
    
    # Metadata
    scraped_at: str = None
    raw_html: Optional[str] = None  # Store raw for reprocessing
    
    def __post_init__(self):
        if self.scraped_at is None:
            self.scraped_at = datetime.now().isoformat()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON/database storage"""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2, default=str)


# ============================================================================
# BASE SCRAPER CLASS
# ============================================================================

class BaseGrantScraper:
    """
    Base class for all state-specific scrapers.
    
    HOW TO USE:
    1. Subclass this for each state (MarylandScraper, DCScraper, etc.)
    2. Override the extract_grants() method
    3. Use the helper methods to parse HTML
    """
    
    def __init__(self, state: str, base_url: str):
        self.state = state
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'GrantDiscoveryBot/1.0 (Capstone Research Project)'
        })
    
    def fetch_page(self, url: str) -> str:
        """
        Fetch HTML content from a URL
        
        Returns: Raw HTML string
        """
        logger.info(f"Fetching: {url}")
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return response.text
    
    def parse_html(self, html: str) -> BeautifulSoup:
        """
        Parse HTML into BeautifulSoup object for querying
        
        This is where you can inspect the structure!
        """
        return BeautifulSoup(html, 'html.parser')
    
    def extract_text(self, element, selector: str, default: str = "") -> str:
        """Helper to safely extract text from an element"""
        found = element.select_one(selector)
        return found.get_text(strip=True) if found else default
    
    def extract_all_text(self, element, selector: str) -> List[str]:
        """Helper to extract text from multiple matching elements"""
        found = element.select(selector)
        return [f.get_text(strip=True) for f in found]
    
    def extract_grants(self) -> List[Grant]:
        """
        Override this in subclass!
        
        Should return a list of Grant objects
        """
        raise NotImplementedError("Subclass must implement extract_grants()")
    
    def save_to_json(self, grants: List[Grant], filename: str):
        """Save extracted grants to JSON file"""
        data = [g.to_dict() for g in grants]
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(f"Saved {len(grants)} grants to {filename}")


# ============================================================================
# HOW TO INSPECT A PAGE AND FIND DATA FIELDS
# ============================================================================

def inspect_page_structure(url: str):
    """
    UTILITY: Use this to inspect a page and find where the data lives
    
    This is what you do FIRST before writing a scraper:
    1. Look at the HTML structure
    2. Find the CSS selectors for data
    3. Map them to your Grant fields
    """
    print(f"\n{'='*60}")
    print(f"INSPECTING: {url}")
    print(f"{'='*60}\n")
    
    # Fetch the page
    response = requests.get(url, headers={
        'User-Agent': 'GrantDiscoveryBot/1.0 (Capstone Research Project)'
    })
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find potential data containers
    print("📦 POTENTIAL DATA CONTAINERS:")
    print("-" * 40)
    
    # Look for common patterns
    patterns = [
        ('Tables', 'table'),
        ('Lists', 'ul.grants, ul.results, ul.opportunities'),
        ('Cards/Items', 'div.grant, div.card, div.item, article'),
        ('Data attributes', '[data-grant], [data-id]'),
        ('JSON in script tags', 'script[type="application/json"]'),
    ]
    
    for name, selector in patterns:
        found = soup.select(selector)
        if found:
            print(f"  ✅ {name}: Found {len(found)} elements")
            # Show first one's structure
            if len(found) > 0:
                print(f"     Sample: {str(found[0])[:200]}...")
        else:
            print(f"  ❌ {name}: Not found")
    
    # Look for links that might be grant detail pages
    print("\n🔗 POTENTIAL GRANT LINKS:")
    print("-" * 40)
    links = soup.select('a[href*="grant"], a[href*="fund"], a[href*="program"]')
    for link in links[:10]:  # Show first 10
        href = link.get('href', '')
        text = link.get_text(strip=True)[:50]
        print(f"  • {text}: {href}")
    
    # Show all headings to understand page structure
    print("\n📝 PAGE HEADINGS (structure overview):")
    print("-" * 40)
    for h in soup.select('h1, h2, h3')[:15]:
        level = h.name
        text = h.get_text(strip=True)[:60]
        indent = "  " * (int(level[1]) - 1)
        print(f"{indent}{level}: {text}")
    
    return soup


# ============================================================================
# EXAMPLE: QUICK DATA EXTRACTION
# ============================================================================

if __name__ == "__main__":
    # Example: Inspect the Maryland funding page
    print("\n" + "="*60)
    print("GRANT SCRAPER - PAGE INSPECTION UTILITY")
    print("="*60)
    
    # You can change this URL to inspect any page
    test_url = "https://businessexpress.maryland.gov/grow/funding-and-incentives"
    
    soup = inspect_page_structure(test_url)
    
    print("\n" + "="*60)
    print("NEXT STEPS:")
    print("="*60)
    print("""
1. Run this script to see the page structure
2. Open the page in browser, right-click → Inspect
3. Find the CSS selectors for:
   - Grant title
   - Description
   - Funding amount
   - Deadline
   - Eligibility info
4. Create a state-specific scraper class
5. Map HTML elements to Grant fields
    """)
