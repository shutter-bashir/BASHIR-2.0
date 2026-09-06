import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

from .models import Company, ContactEmail, EmailDraft, FollowUp, CompanyStatus

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.commit()
            conn.close()

    def _init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS companies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    place_id TEXT UNIQUE,
                    name TEXT NOT NULL,
                    address TEXT,
                    phone TEXT,
                    website TEXT,
                    types TEXT,
                    latitude REAL,
                    longitude REAL,
                    zone TEXT,
                    discovered_at TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS emails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER,
                    email TEXT,
                    source_url TEXT,
                    confidence REAL,
                    discovered_at TIMESTAMP,
                    FOREIGN KEY(company_id) REFERENCES companies(id),
                    UNIQUE(company_id, email)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER,
                    to_email TEXT,
                    subject TEXT,
                    body TEXT,
                    gmail_draft_id TEXT,
                    gmail_thread_id TEXT,
                    status TEXT,
                    sent_at TIMESTAMP,
                    created_at TIMESTAMP,
                    FOREIGN KEY(company_id) REFERENCES companies(id)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS followups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_draft_id INTEGER,
                    company_id INTEGER,
                    follow_up_number INTEGER,
                    to_email TEXT,
                    subject TEXT,
                    body TEXT,
                    gmail_draft_id TEXT,
                    sent_at TIMESTAMP,
                    created_at TIMESTAMP,
                    FOREIGN KEY(original_draft_id) REFERENCES drafts(id),
                    FOREIGN KEY(company_id) REFERENCES companies(id)
                )
            ''')

    def add_company(self, company: Company) -> Optional[int]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO companies (
                        place_id, name, address, phone, website, types, 
                        latitude, longitude, zone, discovered_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(place_id) DO NOTHING
                ''', (
                    company.place_id, company.name, company.address, company.phone,
                    company.website, json.dumps(company.types), company.latitude,
                    company.longitude, company.zone, company.discovered_at.isoformat()
                ))
                if cursor.lastrowid:
                    company.id = cursor.lastrowid
                    return company.id
                
                # Fetch id if it existed
                cursor.execute('SELECT id FROM companies WHERE place_id = ?', (company.place_id,))
                row = cursor.fetchone()
                if row:
                    return row['id']
        except sqlite3.Error as e:
            logger.error(f"Database error adding company: {e}")
        return None

    def add_email(self, contact_email: ContactEmail) -> Optional[int]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO emails (
                        company_id, email, source_url, confidence, discovered_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(company_id, email) DO NOTHING
                ''', (
                    contact_email.company_id, contact_email.email, contact_email.source_url,
                    contact_email.confidence, contact_email.discovered_at.isoformat()
                ))
                if cursor.lastrowid:
                    contact_email.id = cursor.lastrowid
                    return contact_email.id
        except sqlite3.Error as e:
            logger.error(f"Database error adding email: {e}")
        return None

    def add_draft(self, draft: EmailDraft) -> Optional[int]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO drafts (
                        company_id, to_email, subject, body, gmail_draft_id,
                        gmail_thread_id, status, sent_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    draft.company_id, draft.to_email, draft.subject, draft.body,
                    draft.gmail_draft_id, draft.gmail_thread_id, draft.status,
                    draft.sent_at.isoformat() if draft.sent_at else None,
                    draft.created_at.isoformat()
                ))
                draft.id = cursor.lastrowid
                return draft.id
        except sqlite3.Error as e:
            logger.error(f"Database error adding draft: {e}")
        return None

    def add_followup(self, followup: FollowUp) -> Optional[int]:
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO followups (
                        original_draft_id, company_id, follow_up_number, to_email,
                        subject, body, gmail_draft_id, sent_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    followup.original_draft_id, followup.company_id, followup.follow_up_number,
                    followup.to_email, followup.subject, followup.body, followup.gmail_draft_id,
                    followup.sent_at.isoformat() if followup.sent_at else None,
                    followup.created_at.isoformat()
                ))
                followup.id = cursor.lastrowid
                return followup.id
        except sqlite3.Error as e:
            logger.error(f"Database error adding followup: {e}")
        return None

    def _row_to_company(self, row: sqlite3.Row) -> Company:
        return Company(
            id=row['id'],
            place_id=row['place_id'],
            name=row['name'],
            address=row['address'],
            phone=row['phone'],
            website=row['website'],
            types=json.loads(row['types']) if row['types'] else [],
            latitude=row['latitude'],
            longitude=row['longitude'],
            zone=row['zone'],
            discovered_at=datetime.fromisoformat(row['discovered_at'])
        )

    def get_all_companies(self) -> List[Company]:
        companies = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM companies')
            for row in cursor.fetchall():
                companies.append(self._row_to_company(row))
        return companies

    def get_companies_without_emails(self) -> List[Company]:
        companies = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT c.* FROM companies c
                LEFT JOIN emails e ON c.id = e.company_id
                WHERE e.id IS NULL
            ''')
            for row in cursor.fetchall():
                companies.append(self._row_to_company(row))
        return companies

    def get_companies_with_emails(self) -> List[Tuple[Company, List[ContactEmail]]]:
        result = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM companies c WHERE EXISTS (SELECT 1 FROM emails e WHERE e.company_id = c.id)')
            companies_rows = cursor.fetchall()
            
            for c_row in companies_rows:
                company = self._row_to_company(c_row)
                cursor.execute('SELECT * FROM emails WHERE company_id = ?', (company.id,))
                emails = []
                for e_row in cursor.fetchall():
                    emails.append(ContactEmail(
                        id=e_row['id'],
                        company_id=e_row['company_id'],
                        email=e_row['email'],
                        source_url=e_row['source_url'],
                        confidence=e_row['confidence'],
                        discovered_at=datetime.fromisoformat(e_row['discovered_at'])
                    ))
                result.append((company, emails))
        return result

    def get_companies_without_drafts(self) -> List[Tuple[Company, ContactEmail]]:
        result = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT c.*, e.id as e_id, e.email, e.source_url, e.confidence, e.discovered_at as e_discovered_at 
                FROM companies c
                JOIN emails e ON c.id = e.company_id
                LEFT JOIN drafts d ON c.id = d.company_id
                WHERE d.id IS NULL
                GROUP BY c.id
            ''')
            for row in cursor.fetchall():
                company = self._row_to_company(row)
                email = ContactEmail(
                    id=row['e_id'],
                    company_id=company.id,
                    email=row['email'],
                    source_url=row['source_url'],
                    confidence=row['confidence'],
                    discovered_at=datetime.fromisoformat(row['e_discovered_at'])
                )
                result.append((company, email))
        return result

    def get_unsent_drafts(self) -> List[EmailDraft]:
        drafts = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM drafts 
                WHERE status IN (?, ?)
            ''', (CompanyStatus.DRAFT_CREATED.value, CompanyStatus.EMAIL_COMPOSED.value))
            for row in cursor.fetchall():
                drafts.append(EmailDraft(
                    id=row['id'],
                    company_id=row['company_id'],
                    to_email=row['to_email'],
                    subject=row['subject'],
                    body=row['body'],
                    status=row['status'],
                    created_at=datetime.fromisoformat(row['created_at']),
                    gmail_draft_id=row['gmail_draft_id'],
                    gmail_thread_id=row['gmail_thread_id'],
                    sent_at=datetime.fromisoformat(row['sent_at']) if row['sent_at'] else None
                ))
        return drafts

    def get_sent_needing_followup(self, days: int = 4) -> List[Tuple[EmailDraft, Company]]:
        result = []
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT d.*, c.place_id, c.name, c.address, c.phone, c.website, c.types, c.latitude, c.longitude, c.zone, c.discovered_at as c_discovered_at 
                FROM drafts d
                JOIN companies c ON d.company_id = c.id
                WHERE d.status IN (?, ?) 
                AND d.sent_at <= ?
                AND NOT EXISTS (
                    SELECT 1 FROM followups f WHERE f.original_draft_id = d.id AND f.follow_up_number >= 2
                )
            ''', (CompanyStatus.SENT.value, CompanyStatus.FOLLOWED_UP_1.value, cutoff_date))
            
            for row in cursor.fetchall():
                company = Company(
                    id=row['company_id'],
                    place_id=row['place_id'],
                    name=row['name'],
                    address=row['address'],
                    phone=row['phone'],
                    website=row['website'],
                    types=json.loads(row['types']) if row['types'] else [],
                    latitude=row['latitude'],
                    longitude=row['longitude'],
                    zone=row['zone'],
                    discovered_at=datetime.fromisoformat(row['c_discovered_at'])
                )
                draft = EmailDraft(
                    id=row['id'],
                    company_id=row['company_id'],
                    to_email=row['to_email'],
                    subject=row['subject'],
                    body=row['body'],
                    status=row['status'],
                    created_at=datetime.fromisoformat(row['created_at']),
                    gmail_draft_id=row['gmail_draft_id'],
                    gmail_thread_id=row['gmail_thread_id'],
                    sent_at=datetime.fromisoformat(row['sent_at']) if row['sent_at'] else None
                )
                result.append((draft, company))
        return result

    def update_draft_status(self, draft_id: int, status: str, gmail_draft_id: Optional[str] = None, gmail_thread_id: Optional[str] = None, sent_at: Optional[datetime] = None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            updates = ["status = ?"]
            params = [status]
            
            if gmail_draft_id is not None:
                updates.append("gmail_draft_id = ?")
                params.append(gmail_draft_id)
            if gmail_thread_id is not None:
                updates.append("gmail_thread_id = ?")
                params.append(gmail_thread_id)
            if sent_at is not None:
                updates.append("sent_at = ?")
                params.append(sent_at.isoformat())
                
            params.append(draft_id)
            
            query = f"UPDATE drafts SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)

    def mark_company_responded(self, company_id: int, response_summary: str = ''):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE drafts SET status = ? WHERE company_id = ?
            ''', (CompanyStatus.RESPONDED.value, company_id))

    def get_pipeline_stats(self) -> Dict[str, int]:
        stats = {status.value: 0 for status in CompanyStatus}
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) as cnt FROM companies')
            stats[CompanyStatus.DISCOVERED.value] = cursor.fetchone()['cnt']
            
            cursor.execute('SELECT COUNT(DISTINCT company_id) as cnt FROM emails')
            stats[CompanyStatus.EMAILS_FOUND.value] = cursor.fetchone()['cnt']
            
            cursor.execute('SELECT status, COUNT(*) as cnt FROM drafts GROUP BY status')
            for row in cursor.fetchall():
                if row['status'] in stats:
                    stats[row['status']] += row['cnt']
                    
        return stats

    def get_all_for_sheet_sync(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT c.name as company_name, c.address, c.website, c.zone,
                       e.email as contact_email,
                       d.status, d.sent_at, d.gmail_thread_id
                FROM companies c
                LEFT JOIN emails e ON c.id = e.company_id
                LEFT JOIN drafts d ON c.id = d.company_id
                GROUP BY c.id
            ''')
            return [dict(row) for row in cursor.fetchall()]

    def get_unresponded_sent_drafts(self) -> List[EmailDraft]:
        """Get all sent drafts that haven't received a response yet."""
        drafts = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM drafts 
                WHERE status IN (?, ?, ?)
                AND gmail_thread_id IS NOT NULL
            ''', (CompanyStatus.SENT.value, CompanyStatus.FOLLOWED_UP_1.value, CompanyStatus.FOLLOWED_UP_2.value))
            for row in cursor.fetchall():
                drafts.append(EmailDraft(
                    id=row['id'],
                    company_id=row['company_id'],
                    to_email=row['to_email'],
                    subject=row['subject'],
                    body=row['body'],
                    status=row['status'],
                    created_at=datetime.fromisoformat(row['created_at']),
                    gmail_draft_id=row['gmail_draft_id'],
                    gmail_thread_id=row['gmail_thread_id'],
                    sent_at=datetime.fromisoformat(row['sent_at']) if row['sent_at'] else None
                ))
        return drafts

    def get_followup_count(self, draft_id: int) -> int:
        """Get the number of follow-ups sent for a specific draft."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as cnt FROM followups WHERE original_draft_id = ?', (draft_id,))
            return cursor.fetchone()['cnt']
