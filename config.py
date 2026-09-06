import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Constants
PROJECT_DIR = Path(__file__).parent.resolve()
DATA_DIR = PROJECT_DIR / "data"
TEMPLATES_DIR = PROJECT_DIR / "templates"
CREDENTIALS_DIR = PROJECT_DIR / "credentials"
CV_PATH = DATA_DIR / "your_cv.pdf"
DB_PATH = DATA_DIR / "outreach.db"

# Ensure directories exist
for directory in [DATA_DIR, TEMPLATES_DIR, CREDENTIALS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

@dataclass
class StudentProfile:
    name: str = "YOUR NAME"
    email: str = "your.email@gmail.com"
    phone: str = ""
    course: str = "YOUR COURSE NAME"
    university: str = "YOUR UNIVERSITY NAME"
    year: int = 3
    attachment_start: str = "January 2027"
    attachment_end: str = "March 2027"
    attachment_duration: str = "3 months"
    skills: List[str] = field(default_factory=lambda: ["Python", "JavaScript", "SQL", "Git", "Networking"])
    interests: List[str] = field(default_factory=lambda: [
        "Software Development", "Cybersecurity", "Networking", 
        "Data Science", "IT Support", "Web Development", "Fintech"
    ])

@dataclass
class Zone:
    name: str
    latitude: float
    longitude: float
    radius_meters: int

@dataclass
class SearchConfig:
    zones: List[Zone] = field(default_factory=lambda: [
        Zone("Nairobi CBD", -1.2864, 36.8172, 3000),
        Zone("Westlands", -1.2674, 36.8110, 3000),
        Zone("Upper Hill", -1.2981, 36.8155, 2000),
        Zone("Kilimani", -1.2891, 36.7838, 2000),
        Zone("Parklands", -1.2612, 36.8181, 2000),
        Zone("Industrial Area", -1.3100, 36.8500, 3000),
        Zone("Gigiri", -1.2340, 36.8130, 2000),
    ])
    search_queries: List[str] = field(default_factory=lambda: [
        "Software company", "IT support company", "Cybersecurity company", 
        "Tech startup", "Fintech company", "Data center", "Network solutions"
    ])

    def __post_init__(self):
        queries_file = DATA_DIR / "search_queries.json"
        if queries_file.exists():
            try:
                with open(queries_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Handle nested categories structure
                if isinstance(data, dict) and "categories" in data:
                    flat_queries = []
                    for category_queries in data["categories"].values():
                        flat_queries.extend(category_queries)
                    self.search_queries = flat_queries
                elif isinstance(data, list):
                    self.search_queries = data
            except Exception as e:
                logger.error(f"Failed to load search queries from {queries_file}: {e}")

@dataclass
class EmailConfig:
    daily_send_limit: int = 50
    throttle_min_seconds: int = 30
    throttle_max_seconds: int = 90
    max_followups: int = 2
    followup_interval_days: int = 4

@dataclass
class OllamaConfig:
    model: str = "mistral:7b"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.3
    top_p: float = 0.9

@dataclass
class Config:
    student: StudentProfile = field(default_factory=StudentProfile)
    search: SearchConfig = field(default_factory=SearchConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    google_api_key: str = "YOUR_GOOGLE_API_KEY"
    google_sheet_id: Optional[str] = None

    @property
    def cv_path(self) -> Path:
        if CV_PATH.exists():
            return CV_PATH
        pdf_files = list(DATA_DIR.glob("*.pdf"))
        if pdf_files:
            return pdf_files[0]
        return CV_PATH

    @property
    def credentials_dir(self) -> Path:
        return CREDENTIALS_DIR

    @property
    def db_path(self) -> Path:
        return DB_PATH

def load_config(config_path: Optional[Path] = None) -> Config:
    """Loads configuration from a JSON file, or uses defaults if the file doesn't exist."""
    path = config_path or (PROJECT_DIR / "config.json")
    if not path.exists():
        logger.info(f"Config file not found at {path}, using defaults.")
        return Config()

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        student = StudentProfile(**data.get("student", {}))
        
        search_data = data.get("search", {})
        if "zones" in search_data:
            search_data["zones"] = [Zone(**z) for z in search_data["zones"]]
        search = SearchConfig(**search_data)
        
        email = EmailConfig(**data.get("email", {}))
        ollama = OllamaConfig(**data.get("ollama", {}))
        
        logger.info(f"Loaded config from {path}")
        return Config(
            student=student, 
            search=search, 
            email=email, 
            ollama=ollama,
            google_api_key=data.get("google_api_key", "YOUR_GOOGLE_API_KEY"),
            google_sheet_id=data.get("google_sheet_id", None)
        )
    except Exception as e:
        logger.error(f"Error loading config from {path}: {e}")
        return Config()

def save_config(config: Config, config_path: Optional[Path] = None):
    """Saves the current configuration to a JSON file."""
    path = config_path or (PROJECT_DIR / "config.json")
    try:
        data = asdict(config)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        logger.info(f"Saved config to {path}")
    except Exception as e:
        logger.error(f"Error saving config to {path}: {e}")
