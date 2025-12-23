import os
import atexit
import logging
import time
import msal
import requests

class GraphHandler:
    def __init__(self, config):
        self.config = config
        self.app = None
        self.token = None
        self.token_path = 'auth/m365_token.json'
        # Memory cache for the session
        self.cache = msal.SerializableTokenCache()

    def _load_cache(self):
        if os.path.exists(self.token_path):
            with open(self.token_path, 'r') as f:
                self.cache.deserialize(f.read())

    def _save_cache(self):
        if self.cache.has_state_changed:
            with open(self.token_path, 'w') as f:
                f.write(self.cache.serialize())
            if os.path.exists(self.token_path):
                os.chmod(self.token_path, 0o600)

    def authenticate(self):
        """
        Authenticates against Microsoft Graph API.
        """
        client_id = self.config['m365']['client_id']
        authority = self.config['m365']['authority']
        scopes = self.config['m365']['scopes']
        
        self._load_cache()
        atexit.register(self._save_cache)
        
        self.app = msal.PublicClientApplication(
            client_id, 
            authority=authority,
            token_cache=self.cache
        )
        
        accounts = self.app.get_accounts()
        result = None
        if accounts:
            # Try to acquire silent token for the first account
            result = self.app.acquire_token_silent(scopes, account=accounts[0])
            
        if not result:
            logging.info("No suitable token exists in cache. Let's get a new one from AAD.")
            # Interactive flow
            try:
                # This opens the browser
                result = self.app.acquire_token_interactive(scopes=scopes)
            except Exception as e:
                logging.error(f"Authentication failed: {e}")
                raise
        
        if "access_token" in result:
            self.token = result['access_token']
            logging.info("M365 Authentication successful.")
        else:
            error_description = result.get('error_description', 'No error description provided')
            logging.error(f"Could not authenticate: {error_description}")
            raise Exception(f"Authentication Failed: {error_description}")

    def fetch_ids(self, filter_str=None, search_str=None):
        """
        Fetches message IDs matching the OData filter or Search.
        Note: Microsoft Graph API prefers $filter for structured queries and $search for text.
        Returns a list of message objects ({'id': ..., 'receivedDateTime': ...}).
        """
        if not self.token:
            self.authenticate()
            
        headers = {'Authorization': 'Bearer ' + self.token}
        # Select only needed fields to save bandwidth, unless we need more for logic
        # For listing, we need id and receivedDateTime for sorting/checkpointing
        endpoint = "https://graph.microsoft.com/v1.0/me/messages?$select=id,receivedDateTime,internetMessageId"
        
        if filter_str:
            endpoint += f"&$filter={filter_str}"
        
        if search_str:
            # $search requires consistency="eventual" usually, or might just work
            # Note: $filter and $search can sometimes conflict or have restrictions
            endpoint += f"&$search=\"{search_str}\""
            
        # Order by receivedDateTime ascending to help with incremental logic if needed, 
        # but the spec says 'since' which implies a range. 
        # For simplicity, we just fetch whatever the query returns.
        endpoint += "&$top=50" 
        
        messages = []
        while endpoint:
            try:
                response = requests.get(endpoint, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    messages.extend(data.get('value', []))
                    endpoint = data.get('@odata.nextLink')
                elif response.status_code == 429:
                    # Rate limiting
                    retry_after = int(response.headers.get('Retry-After', 5))
                    logging.warning(f"Rate limited. Waiting {retry_after} seconds.")
                    time.sleep(retry_after)
                    # Retry current endpoint (loop doesn't advance)
                    continue 
                else:
                    logging.error(f"Error fetching messages: {response.status_code} {response.text}")
                    break
            except Exception as e:
                logging.error(f"Exception during fetch: {e}")
                break
                
        logging.info(f"Found {len(messages)} messages.")
        return messages

    def download_message(self, message_id):
        """
        Downloads the MIME content of a message.
        """
        if not self.token:
            self.authenticate()
            
        headers = {'Authorization': 'Bearer ' + self.token}
        endpoint = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/$value"
        
        try:
            response = requests.get(endpoint, headers=headers)
            if response.status_code == 200:
                return response.content
            else:
                logging.error(f"Error downloading message {message_id}: {response.status_code}")
                return None
        except Exception as e:
            logging.error(f"Exception downloading message {message_id}: {e}")
            return None
