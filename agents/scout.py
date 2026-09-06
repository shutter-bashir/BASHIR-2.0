import logging
import time
import requests
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from core.models import Company, ContactEmail, CompanyStatus
from core.database import Database
from config import Config, load_config

logger = logging.getLogger(__name__)

class ScoutAgent:
    """Scout Agent to find IT companies using Google Places API (New)."""
    
    def __init__(self, config: Config, database: Database):
        self.config = config
        self.db = database
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.config.google_api_key,
            "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.internationalPhoneNumber,places.websiteUri,places.types,places.location"
        })
        self.endpoint = "https://places.googleapis.com/v1/places:searchText"

    def run(self, dry_run: bool = False) -> int:
        """Run full scout pipeline across all zones and queries. Returns total companies found."""
        total_found = 0
        duplicates = 0
        irrelevant = 0
        
        zones = self.config.search.zones
        queries = self.config.search.search_queries
        
        if dry_run:
            zones = zones[:1]
            queries = queries[:1]
            logger.info("Dry run mode: using 1 zone and 1 query.")
            
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            transient=True,
        ) as progress:
            total_tasks = len(zones) * len(queries)
            main_task = progress.add_task("Scouting companies...", total=total_tasks)
            
            for zone in zones:
                for query in queries:
                    try:
                        results = self._search(query, zone)
                        for place_data in results:
                            if not self._is_relevant(place_data):
                                irrelevant += 1
                                continue
                            
                            company = self._parse_place(place_data, zone.name)
                            try:
                                added = self.db.add_company(company)
                                if added:
                                    total_found += 1
                                else:
                                    duplicates += 1
                            except Exception as e:
                                logger.error(f"Error adding company to DB: {e}")
                    except Exception as e:
                        logger.error(f"Search error for {query} in {zone.name}: {e}")
                    
                    progress.advance(main_task)
                    
        logger.info(f"Scout complete. Found: {total_found}, Duplicates: {duplicates}, Irrelevant: {irrelevant}")
        return total_found

    def _search(self, query: str, zone, page_size: int = 20) -> list[dict]:
        """Execute a single Places API text search."""
        all_results = []
        next_page_token = None
        
        while True:
            body = {
                "textQuery": f"{query} in Nairobi, Kenya",
                "pageSize": page_size,
            }
            if zone:
                body["locationBias"] = {
                    "circle": {
                        "center": {
                            "latitude": zone.latitude,
                            "longitude": zone.longitude
                        },
                        "radius": zone.radius_meters
                    }
                }
            if next_page_token:
                body["pageToken"] = next_page_token
                
            try:
                response = self.session.post(self.endpoint, json=body)
                response.raise_for_status()
                data = response.json()
                
                places = data.get("places", [])
                all_results.extend(places)
                
                next_page_token = data.get("nextPageToken")
                if not next_page_token:
                    break
                    
                time.sleep(0.3)  # Rate limiting
                
            except requests.exceptions.RequestException as e:
                logger.error(f"API request failed: {e}")
                break
                
        return all_results

    def _parse_place(self, place_data: dict, zone_name: str) -> Company:
        """Parse a Places API response into a Company model."""
        from datetime import datetime
        display_name = place_data.get("displayName", {}).get("text", "Unknown Company")
        location = place_data.get("location", {})
        
        return Company(
            place_id=place_data.get("id", ""),
            name=display_name,
            address=place_data.get("formattedAddress", ""),
            phone=place_data.get("nationalPhoneNumber") or place_data.get("internationalPhoneNumber"),
            website=place_data.get("websiteUri"),
            latitude=location.get("latitude", 0.0),
            longitude=location.get("longitude", 0.0),
            zone=zone_name,
            types=place_data.get("types", []),
            discovered_at=datetime.now()
        )

    def _is_relevant(self, place_data: dict) -> bool:
        """Filter out irrelevant place types (restaurants, hotels, etc)."""
        irrelevant_types = {'restaurant', 'lodging', 'food', 'gas_station', 'hospital', 'cafe', 'bar', 'grocery_or_supermarket'}
        place_types = set(place_data.get("types", []))
        
        if place_types.intersection(irrelevant_types):
            return False
            
        it_types = {'software_company', 'corporate_office', 'electronics_store', 'computer_store', 'information_technology_company'}
        if place_types.intersection(it_types) or not place_types:
            return True
            
        return True
