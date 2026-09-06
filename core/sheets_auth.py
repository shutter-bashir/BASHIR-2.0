import logging
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

class SheetsAuth:
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

    def __init__(self, credentials_path: Path, token_path: Path):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.creds = None

    def authenticate(self) -> Credentials:
        if self.token_path.exists():
            try:
                self.creds = Credentials.from_authorized_user_file(str(self.token_path), self.SCOPES)
            except Exception as e:
                logger.warning(f"Failed to load existing token: {e}")

        needs_refresh = False
        if self.creds and self.creds.valid:
            if not set(self.SCOPES).issubset(set(self.creds.scopes)):
                logger.info("Current token is missing required scopes for Sheets, will re-authenticate.")
                needs_refresh = True
        else:
            needs_refresh = True

        if needs_refresh:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except Exception as e:
                    logger.warning(f"Failed to refresh token: {e}")
                    self.creds = None

            if not self.creds or not set(self.SCOPES).issubset(set(self.creds.scopes if self.creds else [])):
                if not self.credentials_path.exists():
                    raise FileNotFoundError(f"Credentials file not found at {self.credentials_path}")
                
                # Combine scopes for Gmail + Sheets
                combined_scopes = list(set(self.SCOPES + [
                    'https://www.googleapis.com/auth/gmail.compose', 
                    'https://www.googleapis.com/auth/gmail.readonly'
                ]))
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), combined_scopes
                )
                self.creds = flow.run_local_server(port=0)

            with open(self.token_path, 'w') as token:
                token.write(self.creds.to_json())

        return self.creds

    def get_service(self):
        creds = self.authenticate()
        try:
            service = build('sheets', 'v4', credentials=creds)
            return service
        except HttpError as error:
            logger.error(f"An error occurred building Sheets service: {error}")
            return None

    def test_connection(self) -> bool:
        try:
            service = self.get_service()
            if not service:
                return False
            logger.info("Successfully connected to Google Sheets API")
            return True
        except Exception as e:
            logger.error(f"Failed to test Sheets connection: {e}")
            return False
