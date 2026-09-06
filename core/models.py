from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

class CompanyStatus(Enum):
    DISCOVERED = "DISCOVERED"
    EMAILS_FOUND = "EMAILS_FOUND"
    EMAIL_COMPOSED = "EMAIL_COMPOSED"
    DRAFT_CREATED = "DRAFT_CREATED"
    SENT = "SENT"
    FOLLOWED_UP_1 = "FOLLOWED_UP_1"
    FOLLOWED_UP_2 = "FOLLOWED_UP_2"
    RESPONDED = "RESPONDED"
    NO_RESPONSE = "NO_RESPONSE"
    BOUNCED = "BOUNCED"
    OPTED_OUT = "OPTED_OUT"

@dataclass
class Company:
    place_id: str
    name: str
    address: str
    latitude: float
    longitude: float
    zone: str
    discovered_at: datetime
    types: List[str] = field(default_factory=list)
    phone: Optional[str] = None
    website: Optional[str] = None
    id: Optional[int] = None

@dataclass
class ContactEmail:
    company_id: int
    email: str
    source_url: str
    confidence: float
    discovered_at: datetime
    id: Optional[int] = None

@dataclass
class EmailDraft:
    company_id: int
    to_email: str
    subject: str
    body: str
    status: str
    created_at: datetime
    gmail_draft_id: Optional[str] = None
    gmail_thread_id: Optional[str] = None
    sent_at: Optional[datetime] = None
    id: Optional[int] = None

@dataclass
class FollowUp:
    original_draft_id: int
    company_id: int
    follow_up_number: int
    to_email: str
    subject: str
    body: str
    created_at: datetime
    gmail_draft_id: Optional[str] = None
    sent_at: Optional[datetime] = None
    id: Optional[int] = None
