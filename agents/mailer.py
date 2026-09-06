import base64
import mimetypes
import time
import random
import logging
from email.message import EmailMessage
from pathlib import Path
from datetime import datetime

from googleapiclient.discovery import Resource
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn

from core.models import Company, ContactEmail, EmailDraft, CompanyStatus, FollowUp
from core.database import Database
from core.gmail_auth import GmailAuth
from config import Config, load_config

console = Console()

class MailerAgent:
    """Agent responsible for creating and sending Gmail drafts with CV attached."""
    
    def __init__(self, config: Config, database: Database, gmail_service: Resource = None):
        """Initialize the Mailer Agent."""
        self.config = config
        self.db = database
        if gmail_service:
            self.service = gmail_service
        else:
            auth_dir = Path(self.config.credentials_dir)
            auth = GmailAuth(auth_dir / 'credentials.json', auth_dir / 'token.json')
            self.service = auth.get_service()
            
    def create_drafts(self, dry_run: bool = False, limit: int = 0) -> int:
        """Create Gmail drafts for all unsent composed emails. Returns count."""
        drafts = self.db.get_unsent_drafts()
        # Filter to those in EMAIL_COMPOSED status (not yet drafted)
        drafts = [d for d in drafts if d.status == CompanyStatus.EMAIL_COMPOSED.value]
        if limit > 0:
            drafts = drafts[:limit]
        count = 0
        
        if not drafts:
            console.print("[dim]No drafts pending creation.[/dim]")
            return 0
            
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Creating Gmail drafts...", total=len(drafts))
            
            for draft in drafts:
                if not dry_run:
                    try:
                        gmail_draft_id = self.create_single_draft(draft, attach_cv=True)
                        self.db.update_draft_status(
                            draft.id,
                            CompanyStatus.DRAFT_CREATED.value,
                            gmail_draft_id=gmail_draft_id
                        )
                        count += 1
                    except Exception as e:
                        logging.error(f"Failed to create draft for draft_id {draft.id}: {e}")
                else:
                    count += 1
                progress.advance(task)
                
        return count
        
    def create_single_draft(self, draft: EmailDraft, attach_cv: bool = True) -> str:
        """Create a single Gmail draft. Returns gmail_draft_id."""
        pdf_path = Path(self.config.cv_path) if attach_cv else None
        
        raw_message = self._build_email_message(
            to=draft.to_email,
            subject=draft.subject,
            body=draft.body,
            pdf_path=pdf_path
        )
        
        message_body = {'message': {'raw': raw_message}}
        created_draft = self.service.users().drafts().create(
            userId='me',
            body=message_body
        ).execute()
        
        return created_draft['id']
        
    def send_all_drafts(self, limit: int = 0) -> int:
        """Send all created drafts with throttling. Returns count sent."""
        drafts = self.db.get_unsent_drafts()
        # Filter to only those with a gmail_draft_id
        drafts = [d for d in drafts if d.gmail_draft_id]
        if limit > 0:
            drafts = drafts[:limit]
        
        if not drafts:
            console.print("[dim]No valid Gmail drafts to send.[/dim]")
            return 0
            
        sent_today = self.check_sent_today()
        daily_limit = self.config.email.daily_send_limit
        available_quota = daily_limit - sent_today
        
        if available_quota <= 0:
            console.print("[yellow]Daily email limit reached. Try again tomorrow.[/yellow]")
            return 0
            
        to_send = drafts[:available_quota]
        count = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[green]Sending emails...", total=len(to_send))
            
            for i, draft in enumerate(to_send):
                try:
                    success = self.send_draft(draft.id)
                    if success:
                        count += 1
                        
                        # Throttle between sends, except after the last one
                        if i < len(to_send) - 1:
                            delay = random.randint(
                                self.config.email.throttle_min_seconds,
                                self.config.email.throttle_max_seconds
                            )
                            progress.console.print(f"[dim]Waiting {delay}s before next send...[/dim]")
                            time.sleep(delay)
                except Exception as e:
                    logging.error(f"Error sending draft {draft.id}: {e}")
                
                progress.advance(task)
                
        return count
        
    def send_draft(self, draft_id: int) -> bool:
        """Send a specific draft by DB id."""
        # Find the draft in unsent drafts
        drafts = self.db.get_unsent_drafts()
        draft = next((d for d in drafts if d.id == draft_id), None)
        if not draft or not draft.gmail_draft_id:
            logging.error(f"Draft {draft_id} not found or has no Gmail draft ID")
            return False
            
        try:
            result = self.send_gmail_draft(draft.gmail_draft_id)
            thread_id = result.get('threadId')
            self.db.update_draft_status(
                draft.id,
                CompanyStatus.SENT.value,
                gmail_thread_id=thread_id,
                sent_at=datetime.now()
            )
            return True
        except Exception as e:
            logging.error(f"Failed to send draft {draft_id}: {e}")
            return False
            
    def send_gmail_draft(self, gmail_draft_id: str) -> dict:
        """Send a draft using Gmail API."""
        return self.service.users().drafts().send(
            userId='me',
            body={'id': gmail_draft_id}
        ).execute()
        
    def create_followup_draft(self, followup: FollowUp, original_thread_id: str = None, attach_cv: bool = True) -> str:
        """Create a follow-up draft, optionally in the same thread."""
        pdf_path = Path(self.config.cv_path) if attach_cv else None
        
        raw_message = self._build_email_message(
            to=followup.to_email,
            subject=followup.subject,
            body=followup.body,
            pdf_path=pdf_path
        )
        
        message_body = {'message': {'raw': raw_message}}
        if original_thread_id:
            message_body['message']['threadId'] = original_thread_id
            
        created_draft = self.service.users().drafts().create(
            userId='me',
            body=message_body
        ).execute()
        
        return created_draft['id']
        
    def _build_email_message(self, to: str, subject: str, body: str, pdf_path: Path = None) -> str:
        """Build a MIME email message with optional PDF attachment. Returns base64url encoded string."""
        msg = EmailMessage()
        
        # Get from email (student email)
        student_email = getattr(self.config.student, 'email', 'student@example.com')
        msg['From'] = student_email
        msg['To'] = to
        msg['Subject'] = subject
        msg.set_content(body)
        
        if pdf_path and pdf_path.exists():
            mime_type, _ = mimetypes.guess_type(str(pdf_path))
            if not mime_type:
                mime_type = 'application/pdf'
            maintype, subtype = mime_type.split('/', 1)
            
            with open(pdf_path, 'rb') as f:
                msg.add_attachment(
                    f.read(), 
                    maintype=maintype, 
                    subtype=subtype, 
                    filename=pdf_path.name
                )
        elif pdf_path:
            logging.warning(f"CV file not found at {pdf_path}. Attaching skipped.")
            
        return base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
        
    def list_gmail_drafts(self, max_results: int = 50) -> list:
        """List drafts from Gmail."""
        try:
            results = self.service.users().drafts().list(
                userId='me',
                maxResults=max_results
            ).execute()
            return results.get('drafts', [])
        except Exception as e:
            logging.error(f"Failed to list drafts: {e}")
            return []
            
    def delete_draft(self, gmail_draft_id: str) -> bool:
        """Delete a draft from Gmail."""
        try:
            self.service.users().drafts().delete(
                userId='me',
                id=gmail_draft_id
            ).execute()
            return True
        except Exception as e:
            logging.error(f"Failed to delete draft {gmail_draft_id}: {e}")
            return False
            
    def check_sent_today(self) -> int:
        """Count emails sent today to enforce daily limit."""
        today = datetime.now().date()
        
        # Try getting all drafts from DB that are marked as SENT
        try:
            sent_drafts = self.db.get_drafts_by_status('SENT')
            sent_today = [d for d in sent_drafts if d.sent_at and d.sent_at.date() == today]
            return len(sent_today)
        except Exception as e:
            logging.warning(f"Could not count sent emails from DB: {e}")
            return 0
