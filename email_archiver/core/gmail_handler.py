import os
import base64
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Allow OAuthlib to use HTTP for local testing
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

class GmailHandler:
    def __init__(self, config):
        from email_archiver.core.paths import get_auth_dir
        self.config = config
        self.creds = None
        self.service = None
        self.token_path = str(get_auth_dir() / 'gmail_token.json')
        
    def get_auth_url(self):
        """Returns the authorization URL to be shown in the UI."""
        scopes = self.config['gmail']['scopes']
        client_secrets = self.config['gmail']['client_secrets_file']
        if not os.path.exists(client_secrets):
            raise FileNotFoundError(f"Client secrets file not found at: {client_secrets}")
        
        flow = InstalledAppFlow.from_client_secrets_file(client_secrets, scopes)
        flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
        auth_url, _ = flow.authorization_url(prompt='consent')
        return auth_url

    def submit_code(self, code):
        """Validates the code and saves the token."""
        scopes = self.config['gmail']['scopes']
        client_secrets = self.config['gmail']['client_secrets_file']
        flow = InstalledAppFlow.from_client_secrets_file(client_secrets, scopes)
        flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
        flow.fetch_token(code=code)
        self.creds = flow.credentials
        
        # Save the credentials
        os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
        with open(self.token_path, 'w') as token:
            token.write(self.creds.to_json())
        os.chmod(self.token_path, 0o600)
        
        self.service = build('gmail', 'v1', credentials=self.creds)
        return True

    def authenticate(self):
        """
        Authenticates against Gmail API using OAuth2.
        Loads existing token or launches browser flow (interactive).
        """
        scopes = self.config['gmail']['scopes']
        
        if os.path.exists(self.token_path):
            self.creds = Credentials.from_authorized_user_file(self.token_path, scopes)
            
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except Exception as e:
                    logging.warning(f"Failed to refresh token: {e}. Re-authenticating.")
                    self.creds = None
            
            if not self.creds:
                # If we are in the UI (started via FastAPI), we shouldn't do input()
                # But for CLI users, we maintain compatibility
                import sys
                if not sys.stdin.isatty():
                    raise Exception("Authentication required. Please use the Web UI to authorize.")
                
                auth_url = self.get_auth_url()
                print('-' * 80)
                print(f'Please visit this URL to authorize the application:\n{auth_url}')
                print('-' * 80)
                
                code = input('Enter the authorization code: ')
                self.submit_code(code)
            else:
                # Refreshed successfully
                with open(self.token_path, 'w') as token:
                    token.write(self.creds.to_json())

        self.service = build('gmail', 'v1', credentials=self.creds)
        logging.info("Gmail authentication successful.")

    def fetch_ids(self, query=""):
        """
        Fetches message IDs matching the query.
        Returns a list of message objects ({'id': ..., 'threadId': ...}).
        """
        if not self.service:
            self.authenticate()
            
        messages = []
        try:
            request = self.service.users().messages().list(userId='me', q=query)
            while request is not None:
                response = request.execute()
                if 'messages' in response:
                    messages.extend(response['messages'])
                    if len(messages) % 1000 == 0:
                        logging.info(f"Fetched {len(messages)} message IDs so far...")
                
                request = self.service.users().messages().list_next(request, response)
                
        except HttpError as error:
            logging.error(f"An error occurred searching emails: {error}")
            raise
            
        logging.info(f"Found {len(messages)} messages matching query: '{query}'")
        return messages

    def download_message(self, message_id):
        """
        Downloads the raw content of a message.
        Returns bytes of the .eml content.
        """
        if not self.service:
            self.authenticate()
            
        try:
            # format='raw' returns the full email message as a base64url encoded string
            # It also returns 'internalDate' (timestamp in ms)
            message = self.service.users().messages().get(userId='me', id=message_id, format='raw').execute()
            
            raw_data = message['raw']
            internal_date = message.get('internalDate')
            
            # Decode: URL-safe base64 decoding
            decoded_data = base64.urlsafe_b64decode(raw_data)
            
            return decoded_data, internal_date
            
        except HttpError as error:
            logging.error(f"An error occurred downloading message {message_id}: {error}")
            return None
