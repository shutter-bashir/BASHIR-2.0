import logging
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

class GmailAuth:
    SCOPES = [
        'https://www.googleapis.com/auth/gmail.compose',
        'https://www.googleapis.com/auth/gmail.readonly'
    ]

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

        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except Exception as e:
                    logger.warning(f"Failed to refresh token: {e}")
                    self.creds = None

            if not self.creds:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(f"Credentials file not found at {self.credentials_path}")
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), self.SCOPES
                )
                self.creds = flow.run_local_server(port=0)

            with open(self.token_path, 'w') as token:
                token.write(self.creds.to_json())

        return self.creds

    def get_service(self):
        creds = self.authenticate()
        try:
            service = build('gmail', 'v1', credentials=creds)
            return service
        except HttpError as error:
            logger.error(f"An error occurred building Gmail service: {error}")
            return None

    def test_connection(self) -> bool:
        try:
            service = self.get_service()
            if not service:
                return False
            profile = service.users().getProfile(userId='me').execute()
            logger.info(f"Successfully connected to Gmail as {profile.get('emailAddress')}")
            return True
        except Exception as e:
            logger.error(f"Failed to test Gmail connection: {e}")
            return False
