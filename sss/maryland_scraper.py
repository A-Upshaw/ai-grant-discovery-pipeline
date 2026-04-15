"""
Maryland Grant Scraper
Capstone Project - AI-Powered Grant Discovery Pipeline

Maryland has TWO great data sources:
1. Knack Database: commerce.knack.com/maryland-funding-incentives (structured!)
2. Finance Tracker: commerce.maryland.gov/fund/maryland-finance-tracker

This scraper targets the Knack database first (API potential).
"""

import requests
import json
from datetime import datetime
from typing import List, Dict, Any
from grant_scraper_base import Grant, FundingInfo, DateInfo, EligibilityInfo, BaseGrantScraper, logger


class MarylandScraper(BaseGrantScraper):
    """
    Maryland-specific scraper targeting the Knack database
    """
    
    def __init__(self):
        super().__init__(
            state="MD",
            base_url="https://commerce.knack.com/maryland-funding-incentives"
        )
        # Knack apps often have an API endpoint - let's find it
        self.knack_api_base = None
    
    def discover_knack_api(self) -> Dict[str, Any]:
        """
        Knack databases often expose their data via API.
        This method inspects the page to find the API structure.
        
        WHAT WE'RE LOOKING FOR:
        - Application ID
        - Scene/View structure  
        - API endpoints in network requests
        """
        print("\n🔍 DISCOVERING KNACK API STRUCTURE...")
        print("-" * 50)
        
        # Fetch the main page
        html = self.fetch_page(self.base_url)
        
        # Look for Knack configuration in the page
        # Knack apps typically have a JavaScript object with config
        findings = {
            "has_knack": "Knack" in html,
            "potential_app_id": None,
            "api_hints": [],
            "data_tables": []
        }
        
        # Look for app ID pattern (often in script tags or data attributes)
        import re
        
        # Pattern 1: Look for application_id
        app_id_match = re.search(r'application_id["\s:]+["\']([a-zA-Z0-9]+)["\']', html)
        if app_id_match:
            findings["potential_app_id"] = app_id_match.group(1)
            print(f"  ✅ Found App ID: {findings['potential_app_id']}")
        
        # Pattern 2: Look for API URLs
        api_urls = re.findall(r'(https?://api\.knack\.com[^"\']+)', html)
        if api_urls:
            findings["api_hints"] = list(set(api_urls))
            print(f"  ✅ Found {len(findings['api_hints'])} API endpoints")
        
        # Pattern 3: Look for scene/view references
        scenes = re.findall(r'scene_(\d+)', html)
        views = re.findall(r'view_(\d+)', html)
        if scenes:
            findings["scenes"] = list(set(scenes))
            print(f"  ✅ Found scenes: {findings['scenes']}")
        if views:
            findings["views"] = list(set(views))
            print(f"  ✅ Found views: {findings['views']}")
        
        return findings
    
    def fetch_knack_data(self, app_id: str, scene: str, view: str) -> List[Dict]:
        """
        If we find the Knack API structure, we can fetch data directly!
        
        Knack's public API format:
        GET https://api.knack.com/v1/pages/{scene}/views/{view}/records
        Headers: X-Knack-Application-Id: {app_id}
        """
        url = f"https://api.knack.com/v1/pages/scene_{scene}/views/view_{view}/records"
        
        headers = {
            "X-Knack-Application-Id": app_id,
            "X-Knack-REST-API-Key": "knack",  # Sometimes "knack" works for public data
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Successfully fetched {len(data.get('records', []))} records from Knack")
                return data.get("records", [])
            else:
                logger.warning(f"Knack API returned {response.status_code}: {response.text[:200]}")
                return []
        except Exception as e:
            logger.error(f"Error fetching Knack data: {e}")
            return []
    
    def parse_knack_record(self, record: Dict) -> Grant:
        """
        Convert a Knack record to our Grant schema.
        
        NOTE: You'll need to map the actual field names once we see the data!
        This is a template based on common patterns.
        """
        # These field mappings will need adjustment based on actual Knack schema
        # Run the discovery first to see what fields exist
        
        grant = Grant(
            id=record.get("id", ""),
            title=record.get("field_1", record.get("Program Name", "")),  # Adjust field names
            description=record.get("field_2", record.get("Description", "")),
            state="MD",
            source_url=self.base_url,
            source_agency=record.get("field_3", record.get("Agency", "Maryland")),
            funding=FundingInfo(
                amount_min=self._parse_amount(record.get("field_4", "")),
                amount_max=self._parse_amount(record.get("field_5", "")),
            ),
            dates=DateInfo(
                deadline=record.get("field_6", ""),
            ),
            eligibility=EligibilityInfo(
                business_types=self._parse_list(record.get("field_7", "")),
            ),
            program_type=record.get("field_8", "grant"),
        )
        return grant
    
    def _parse_amount(self, value: str) -> float:
        """Parse currency string to float"""
        if not value:
            return None
        # Remove $, commas, and convert
        try:
            cleaned = str(value).replace("$", "").replace(",", "").strip()
            return float(cleaned)
        except:
            return None
    
    def _parse_list(self, value: str) -> List[str]:
        """Parse comma-separated string to list"""
        if not value:
            return []
        return [x.strip() for x in str(value).split(",")]
    
    def extract_grants(self) -> List[Grant]:
        """Main extraction method"""
        # Step 1: Discover API structure
        api_info = self.discover_knack_api()
        
        if api_info.get("potential_app_id") and api_info.get("scenes"):
            # Try to fetch via API
            app_id = api_info["potential_app_id"]
            for scene in api_info.get("scenes", []):
                for view in api_info.get("views", []):
                    records = self.fetch_knack_data(app_id, scene, view)
                    if records:
                        return [self.parse_knack_record(r) for r in records]
        
        # Fallback: HTML scraping
        logger.info("API not available, falling back to HTML scraping")
        return self._scrape_html()
    
    def _scrape_html(self) -> List[Grant]:
        """Fallback HTML scraping if API isn't accessible"""
        html = self.fetch_page(self.base_url)
        soup = self.parse_html(html)
        
        grants = []
        # Look for table rows or list items containing grant data
        # This needs to be customized based on actual page structure
        
        # Example: Look for table rows
        rows = soup.select("table tr")
        for row in rows[1:]:  # Skip header
            cells = row.select("td")
            if len(cells) >= 3:
                grant = Grant(
                    id=f"md-{len(grants)}",
                    title=cells[0].get_text(strip=True),
                    description=cells[1].get_text(strip=True) if len(cells) > 1 else "",
                    state="MD",
                    source_url=self.base_url,
                    source_agency="Maryland",
                    funding=FundingInfo(),
                    dates=DateInfo(),
                    eligibility=EligibilityInfo(),
                )
                grants.append(grant)
        
        return grants


# ============================================================================
# QUICK TEST / DISCOVERY SCRIPT
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("MARYLAND GRANT SCRAPER - DISCOVERY MODE")
    print("="*60)
    
    scraper = MarylandScraper()
    
    # Run discovery to see what we're working with
    api_info = scraper.discover_knack_api()
    
    print("\n📊 DISCOVERY RESULTS:")
    print("-" * 50)
    print(json.dumps(api_info, indent=2))
    
    print("\n" + "="*60)
    print("NEXT STEPS:")
    print("="*60)
    print("""
1. If App ID found: Try the API endpoints
2. If no API: Fall back to HTML scraping
3. Either way: Map the field names to Grant schema
4. Test extraction and save to JSON

RUN THIS TO TRY EXTRACTION:
    grants = scraper.extract_grants()
    scraper.save_to_json(grants, "maryland_grants.json")
    """)
