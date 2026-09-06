import logging
from datetime import datetime
from googleapiclient.discovery import Resource
from core.models import Company, ContactEmail, EmailDraft, FollowUp, CompanyStatus
from core.database import Database
from core.sheets_auth import SheetsAuth
from config import Config, load_config

logger = logging.getLogger(__name__)

class TrackerAgent:
    """Agent that syncs all pipeline data to a live Google Sheet."""
    
    def __init__(self, config: Config, database: Database, sheets_service: Resource = None):
        self.config = config
        self.db = database
        self.sheet_id = config.google_sheet_id  # None if not yet created
        if sheets_service:
            self.service = sheets_service
        else:
            auth = SheetsAuth(config.credentials_dir / 'credentials.json', config.credentials_dir / 'token_sheets.json')
            self.service = auth.get_service()
    
    def run(self, dry_run: bool = False) -> str:
        """Full sync: create sheet if needed, update all data. Returns sheet URL."""
        if not self.sheet_id:
            self.sheet_id = self._create_spreadsheet()
        else:
            self._ensure_sheets_exist()
        
        if not dry_run:
            self._sync_companies_sheet()
            self._sync_dashboard_sheet()
            self._apply_conditional_formatting()
            
        url = f"https://docs.google.com/spreadsheets/d/{self.sheet_id}"
        return url
    
    def _ensure_sheets_exist(self):
        """Ensure required sheet tabs exist in the existing spreadsheet."""
        try:
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.sheet_id, fields='sheets.properties'
            ).execute()
            existing_sheets = {s['properties']['title']: s['properties']['sheetId'] 
                             for s in spreadsheet.get('sheets', [])}
            
            requests = []
            
            # Rename Sheet1 to 'Companies & Outreach' if it exists and our target doesn't
            if 'Sheet1' in existing_sheets and 'Companies & Outreach' not in existing_sheets:
                requests.append({
                    'updateSheetProperties': {
                        'properties': {
                            'sheetId': existing_sheets['Sheet1'],
                            'title': 'Companies & Outreach'
                        },
                        'fields': 'title'
                    }
                })
                existing_sheets['Companies & Outreach'] = existing_sheets.pop('Sheet1')
            
            # Create Dashboard if it doesn't exist
            if 'Dashboard' not in existing_sheets:
                requests.append({
                    'addSheet': {
                        'properties': {'title': 'Dashboard'}
                    }
                })
            
            if requests:
                self.service.spreadsheets().batchUpdate(
                    spreadsheetId=self.sheet_id,
                    body={'requests': requests}
                ).execute()
                logger.info("Ensured required sheets exist.")
        except Exception as e:
            logger.warning(f"Could not ensure sheets exist: {e}")
    
    def _create_spreadsheet(self) -> str:
        """Create a new Google Spreadsheet with two sheets. Returns spreadsheet ID."""
        spreadsheet_details = {
            'properties': {
                'title': f"Attachment Outreach — {self.config.student.name}"
            },
            'sheets': [
                {'properties': {'title': 'Companies & Outreach'}},
                {'properties': {'title': 'Dashboard'}}
            ]
        }
        try:
            spreadsheet = self.service.spreadsheets().create(
                body=spreadsheet_details, fields='spreadsheetId'
            ).execute()
            sheet_id = spreadsheet.get('spreadsheetId')
            
            logger.info(f"Created new spreadsheet with ID: {sheet_id}")
            return sheet_id
        except Exception as e:
            logger.error(f"Error creating spreadsheet: {e}")
            raise
    
    def _sync_companies_sheet(self):
        """Sync all company and outreach data to Sheet 1."""
        companies = self.db.get_all_companies()
        
        headers = [
            "#", "Company Name", "Industry/Type", "Address", "Zone", "Phone", "Website", 
            "Email Found", "Email Confidence", "Email Sent?", "Date Sent",
            "Follow-up 1", "Follow-up 2", "Response?", "Response Date", 
            "Response Summary", "Status", "Notes"
        ]
        
        rows = [headers]
        
        # Build lookup dicts for emails, drafts, followups
        email_map = {}   # company_id -> list of ContactEmail
        draft_map = {}    # company_id -> EmailDraft (latest)
        followup_map = {} # company_id -> {1: FollowUp, 2: FollowUp}
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Load all emails
            cursor.execute('SELECT * FROM emails')
            for row in cursor.fetchall():
                cid = row['company_id']
                if cid not in email_map:
                    email_map[cid] = []
                email_map[cid].append(row)
            
            # Load all drafts (latest per company)
            cursor.execute('SELECT * FROM drafts ORDER BY created_at DESC')
            for row in cursor.fetchall():
                cid = row['company_id']
                if cid not in draft_map:
                    draft_map[cid] = row
            
            # Load all followups
            cursor.execute('SELECT * FROM followups ORDER BY follow_up_number')
            for row in cursor.fetchall():
                cid = row['company_id']
                if cid not in followup_map:
                    followup_map[cid] = {}
                followup_map[cid][row['follow_up_number']] = row
        
        for idx, company in enumerate(companies, 1):
            cid = company.id
            
            # Email info
            emails_list = email_map.get(cid, [])
            email_found = ", ".join([e['email'] for e in emails_list]) if emails_list else ""
            best_confidence = max([e['confidence'] for e in emails_list], default=0) if emails_list else 0
            confidence_str = self._format_confidence(best_confidence) if emails_list else ""
            
            # Draft info
            draft = draft_map.get(cid)
            email_sent = ""
            date_sent = ""
            status_val = "DISCOVERED"
            if draft:
                status_val = draft['status'] or "DRAFT_CREATED"
                if status_val in ('SENT', 'FOLLOWED_UP_1', 'FOLLOWED_UP_2', 'RESPONDED', 'NO_RESPONSE', 'BOUNCED'):
                    email_sent = "✅ Yes"
                    date_sent = draft['sent_at'] or ""
                elif status_val in ('DRAFT_CREATED', 'EMAIL_COMPOSED'):
                    email_sent = "📝 Draft"
            elif emails_list:
                status_val = "EMAILS_FOUND"
            
            # Follow-up info
            followups = followup_map.get(cid, {})
            fu1 = followups.get(1)
            fu2 = followups.get(2)
            fu1_str = f"✅ {fu1['sent_at']}" if fu1 and fu1['sent_at'] else ("📝 Draft" if fu1 else "")
            fu2_str = f"✅ {fu2['sent_at']}" if fu2 and fu2['sent_at'] else ("📝 Draft" if fu2 else "")
            
            # Response info
            responded = ""
            response_date = ""
            response_summary = ""
            if status_val == 'RESPONDED':
                responded = "✅ Yes"
            elif status_val == 'BOUNCED':
                responded = "⛔ Bounced"
            elif status_val == 'NO_RESPONSE':
                responded = "🔴 No"
            
            industry = ", ".join(company.types) if company.types else ""
            
            row = [
                idx,
                company.name,
                industry,
                company.address or "",
                company.zone or "",
                company.phone or "",
                company.website or "",
                email_found,
                confidence_str,
                email_sent,
                date_sent,
                fu1_str,
                fu2_str,
                responded,
                response_date,
                response_summary,
                self._format_status_emoji(status_val),
                ""
            ]
            rows.append(row)
            
        try:
            # Clear existing data first to handle deleted rows
            self.service.spreadsheets().values().clear(
                spreadsheetId=self.sheet_id,
                range="'Companies & Outreach'!A1:R"
            ).execute()
            
            body = {
                'values': rows
            }
            self.service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range="'Companies & Outreach'!A1:R",
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            logger.info(f"Successfully synced {len(rows)-1} companies to sheet.")
        except Exception as e:
            logger.error(f"Error syncing companies sheet: {e}")
            raise
    
    def _sync_dashboard_sheet(self):
        """Update the dashboard/summary sheet with pipeline stats."""
        stats = self.db.get_pipeline_stats() if hasattr(self.db, 'get_pipeline_stats') else {}
        
        total_companies = stats.get('DISCOVERED', 0)
        emails_found = stats.get('EMAILS_FOUND', 0)
        emails_sent = stats.get('SENT', 0)
        fu1 = stats.get('FOLLOWED_UP_1', 0)
        fu2 = stats.get('FOLLOWED_UP_2', 0)
        responded = stats.get('RESPONDED', 0)
        total_sent = emails_sent + fu1 + fu2
        response_rate = round((responded / total_sent * 100), 1) if total_sent > 0 else 0.0
        
        rows = [
            ["Pipeline Dashboard", ""],
            ["", ""],
            ["Total Companies Discovered", total_companies],
            ["Companies with Email Found", emails_found],
            ["Emails Drafted", stats.get('DRAFT_CREATED', 0) + stats.get('EMAIL_COMPOSED', 0)],
            ["Initial Emails Sent", emails_sent],
            ["Follow-up 1 Sent", fu1],
            ["Follow-up 2 Sent", fu2],
            ["Total Responses Received", responded],
            ["Bounced", stats.get('BOUNCED', 0)],
            ["Response Rate (%)", f"{response_rate}%"],
            ["", ""],
            ["Last Updated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
        ]
        
        try:
            body = {
                'values': rows
            }
            self.service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range='Dashboard!A1:B15',
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            logger.info("Successfully synced dashboard sheet.")
        except Exception as e:
            logger.error(f"Error syncing dashboard sheet: {e}")
            raise
    
    def _format_status_emoji(self, status: str) -> str:
        """Convert status enum to emoji representation."""
        status_map = {
            'DISCOVERED': '🔵 Discovered',
            'EMAILS_FOUND': '🟡 Email Found',
            'EMAIL_COMPOSED': '🟠 Drafted',
            'DRAFT_CREATED': '🟠 Draft Ready',
            'SENT': '🟢 Sent',
            'FOLLOWED_UP_1': '🔄 Follow-up 1 Sent',
            'FOLLOWED_UP_2': '🔄 Follow-up 2 Sent',
            'RESPONDED': '✅ Responded',
            'NO_RESPONSE': '🔴 No Response',
            'BOUNCED': '⛔ Bounced',
            'OPTED_OUT': '🚫 Opted Out'
        }
        return status_map.get(status, status)
    
    def _format_confidence(self, score: float) -> str:
        """Convert confidence score to star rating."""
        if score >= 0.9: return '⭐⭐⭐ High'
        if score >= 0.7: return '⭐⭐ Medium'
        if score >= 0.4: return '⭐ Low'
        return '❓ Guess'
    
    def _apply_conditional_formatting(self):
        """Apply color-coded row formatting based on status column."""
        pass
