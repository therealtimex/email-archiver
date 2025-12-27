import os
import atexit
import logging
import time
import msal
import requests

class GraphHandler:
    def __init__(self, config):
        from email_archiver.core.paths import get_auth_dir
        self.config = config
        self.app = None
        self.token = None
        self.token_path = str(get_auth_dir() / 'm365_token.json')
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

    def initiate_device_flow(self):
        """Starts the MSAL device code flow."""
        client_id = self.config['m365']['client_id']
        authority = self.config['m365']['authority']
        scopes = self.config['m365']['scopes']
        
        self._load_cache()
        self.app = msal.PublicClientApplication(
            client_id, 
            authority=authority,
            token_cache=self.cache
        )
        
        flow = self.app.initiate_device_flow(scopes=scopes)
        if "user_code" not in flow:
            raise Exception(f"Could not initiate device flow: {flow.get('error_description')}")
        return flow

    def complete_device_flow(self, flow):
        """Waits for/completes the device flow started by initiate_device_flow."""
        if not self.app:
            raise Exception("Device flow not initiated")
        
        result = self.app.acquire_token_by_device_flow(flow)
        if "access_token" in result:
            self.token = result['access_token']
            self._save_cache()
            logging.info("M365 Authentication successful via Device Flow.")
            return True
        else:
            error = result.get('error_description', 'Unknown error during device flow')
            logging.error(f"Device flow failed: {error}")
            return False

    def authenticate(self):
        """
        Authenticates against Microsoft Graph API.
        """
        client_id = self.config['m365']['client_id']
        authority = self.config['m365']['authority']
        scopes = self.config['m365']['scopes']
        
        self._load_cache()
        
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
            # If we're not in a TTY, we can't do interactive browser
            import sys
            if not sys.stdin.isatty():
                # For non-TTY (like the UI), we expect the UI to handle the flow
                # but if authenticate() is called directly, we fail gracefully
                logging.info("Silent auth failed and no TTY available. Use Device Flow via UI.")
                return False

            logging.info("No suitable token exists in cache. Launching interactive auth.")
            try:
                result = self.app.acquire_token_interactive(scopes=scopes)
            except Exception as e:
                logging.error(f"Authentication failed: {e}")
                raise
        
        if result and "access_token" in result:
            self.token = result['access_token']
            self._save_cache()
            logging.info("M365 Authentication successful.")
            return True
        return False

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
                response = requests.get(endpoint, headers=headers, timeout=30)
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
            response = requests.get(endpoint, headers=headers, timeout=30)
            if response.status_code == 200:
                return response.content
            else:
                logging.error(f"Error downloading message {message_id}: {response.status_code}")
                return None
        except Exception as e:
            logging.error(f"Exception downloading message {message_id}: {e}")
            return None
