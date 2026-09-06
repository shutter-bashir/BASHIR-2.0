import logging
import requests
from datetime import datetime, timedelta
from googleapiclient.errors import HttpError
from core.models import Company, ContactEmail, EmailDraft, FollowUp, CompanyStatus
from core.database import Database
from core.gmail_auth import GmailAuth
from agents.composer import ComposerAgent
from agents.mailer import MailerAgent
from config import Config, load_config

logger = logging.getLogger(__name__)

class FollowUpAgent:
    """Agent that checks for responses and sends follow-ups."""
    
    def __init__(self, config: Config, database: Database, gmail_service=None):
        self.config = config
        self.db = database
        if gmail_service:
            self.gmail_service = gmail_service
        else:
            auth = GmailAuth(config.credentials_dir / 'credentials.json', config.credentials_dir / 'token.json')
            self.gmail_service = auth.get_service()
        self.composer = ComposerAgent(config, database)
        self.mailer = MailerAgent(config, database, self.gmail_service)
    
    def run(self, auto_send: bool = False) -> dict:
        """Check for responses and send follow-ups. Returns stats dict."""
        stats = {'responses_found': 0, 'followups_created': 0, 'followups_sent': 0, 'bounced': 0}
        
        # Step 1: Check for responses to all sent emails
        self._check_all_responses(stats)
        
        # Step 2: Find emails needing follow-up
        try:
            needing_followup = self.db.get_sent_needing_followup(days=self.config.email.followup_interval_days)
        except AttributeError:
            needing_followup = []
            logger.warning("Database missing get_sent_needing_followup method.")
            
        for draft, company in needing_followup:
            followup_num = self._get_next_followup_number(draft.id)
            if followup_num > self.config.email.max_followups:
                self.db.update_draft_status(draft.id, CompanyStatus.NO_RESPONSE.value)
                continue
            
            followup_content = self.composer.compose_followup_email(draft, company, followup_num)
            
            followup = FollowUp(
                original_draft_id=draft.id,
                company_id=company.id,
                follow_up_number=followup_num,
                to_email=draft.to_email,
                subject=followup_content.get('subject', f"Following up: {draft.subject}"),
                body=followup_content.get('body', ''),
                created_at=datetime.now()
            )
            try:
                followup_id = self.db.add_followup(followup)
                stats['followups_created'] += 1
                
                if auto_send:
                    gmail_draft_id = self.mailer.create_followup_draft(followup, draft.gmail_thread_id)
                    self.mailer.send_gmail_draft(gmail_draft_id)
                    stats['followups_sent'] += 1
                else:
                    self.mailer.create_followup_draft(followup, draft.gmail_thread_id)
            except Exception as e:
                logger.error(f"Error processing follow-up for draft {draft.id}: {e}")
        
        return stats
    
    def _check_all_responses(self, stats: dict):
        """Check Gmail inbox for replies to all sent emails."""
        try:
            sent_drafts = self.db.get_unresponded_sent_drafts()
        except AttributeError:
            sent_drafts = []
            
        for draft in sent_drafts:
            response = self._check_for_response(draft, stats=stats)
            if response:
                summary = self._summarize_response(response['snippet'])
                self.db.update_draft_status(draft.id, CompanyStatus.RESPONDED.value)
                stats['responses_found'] += 1
                
    def _check_for_response(self, draft: EmailDraft, stats: dict = None) -> dict | None:
        """Check if a specific email has received a response."""
        if not draft.gmail_thread_id:
            return None
            
        try:
            thread = self.gmail_service.users().threads().get(
                userId='me', id=draft.gmail_thread_id, format='metadata'
            ).execute()
            messages = thread.get('messages', [])
            
            if len(messages) > 1:
                latest = messages[-1]
                snippet = latest.get('snippet', '')
                
                headers = latest.get('payload', {}).get('headers', [])
                sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
                date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
                
                return {'date': date, 'snippet': snippet, 'from': sender}
        except HttpError as e:
            if e.resp.status == 404:
                logger.warning(
                    f"Thread {draft.gmail_thread_id} no longer exists in Gmail "
                    f"(draft #{draft.id}, to: {draft.to_email}). Marking as BOUNCED."
                )
                try:
                    self.db.update_draft_status(draft.id, CompanyStatus.BOUNCED.value)
                    if stats is not None:
                        stats['bounced'] += 1
                except Exception as db_err:
                    logger.error(f"Failed to mark draft {draft.id} as bounced: {db_err}")
            else:
                logger.error(f"Gmail API error checking thread {draft.gmail_thread_id}: {e}")
        except Exception as e:
            logger.error(f"Error checking thread {draft.gmail_thread_id}: {e}")
            
        return None
    
    def _summarize_response(self, response_text: str) -> str:
        """Use Ollama to generate a brief summary of the company's response."""
        prompt = f"Summarize this email response in 10 words or less: {response_text}"
        try:
            response = requests.post(
                f"{self.config.ollama.base_url}/api/generate",
                json={
                    "model": self.config.ollama.model,
                    "prompt": prompt,
                    "stream": False
                }
            )
            response.raise_for_status()
            return response.json().get('response', '').strip()
        except Exception as e:
            logger.error(f"Error summarizing response: {e}")
            return "Response received"
            
    def _get_next_followup_number(self, draft_id: int) -> int:
        """Get the next follow-up number for a draft."""
        try:
            count = self.db.get_followup_count(draft_id)
            return count + 1
        except AttributeError:
            return 1
