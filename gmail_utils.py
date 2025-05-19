# gmail_utils.py
import os
import time
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from logs import log_message

# Scope for read-only access to Gmail
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
RETRIES = 3
BATCH_SIZE = 25  # Reduced batch size for better reliability
RETRY_DELAY = 2  # Seconds to wait between retries

def gmail_authenticate():
    """Authenticate with Gmail API and return service object"""
    creds = None
    
    # Check for existing token
    if os.path.exists("token.json"):
        try:
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
            log_message("Found existing credentials")
        except Exception as e:
            log_message(f"Error loading existing token: {str(e)}")
            # If token is invalid, we'll create a new one below
    
    # If no valid credentials, authenticate with OAuth flow
    if not creds or not creds.valid:
        try:
            # Check for credentials file
            if not os.path.exists("credentials.json"):
                log_message("❌ credentials.json not found. Please obtain OAuth credentials from Google Cloud Console")
                raise FileNotFoundError("credentials.json not found")
                
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
            
            # Save credentials for future use
            with open("token.json", "w") as token:
                token.write(creds.to_json())
                log_message("✅ New token saved successfully")
                
        except Exception as e:
            log_message(f"❌ Authentication flow failed: {str(e)}")
            raise
    
    try:
        # Build the Gmail API service
        service = build("gmail", "v1", credentials=creds)
        
        # Test the connection with a simple API call
        service.users().getProfile(userId='me').execute()
        log_message("✅ Successfully connected to Gmail API")
        
        return service
    except Exception as e:
        log_message(f"❌ Failed to build Gmail service: {str(e)}")
        raise

def search_messages(service, query, max_results=100):
    """Search Gmail for messages matching the query with improved error handling"""
    messages = []
    page_token = None
    
    log_message(f"Searching Gmail with query: {query}")
    
    for attempt in range(RETRIES):
        try:
            while len(messages) < max_results:
                # Calculate proper batch size
                current_batch = min(BATCH_SIZE, max_results - len(messages))
                
                # Make the API request
                result = service.users().messages().list(
                    userId='me',
                    q=query,
                    maxResults=current_batch,
                    pageToken=page_token
                ).execute(num_retries=RETRIES)
                
                # Add the messages from this page
                batch_messages = result.get('messages', [])
                if not batch_messages:
                    log_message("No more messages found in search")
                    break
                    
                messages.extend(batch_messages)
                log_message(f"Found {len(messages)} messages so far")
                
                # Get the token for the next page
                page_token = result.get('nextPageToken')
                if not page_token:
                    log_message("No more pages to fetch")
                    break
                    
            log_message(f"Search complete: found {len(messages)} messages")
            return messages[:max_results]

        except HttpError as e:
            if e.resp.status in [429, 500, 503]:  # Rate limit or server errors
                if attempt < RETRIES - 1:
                    wait_time = RETRY_DELAY * (attempt + 1)
                    log_message(f"API error: {e.resp.status}. Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
            log_message(f"❌ Search failed with HTTP error: {str(e)}")
            raise
            
        except Exception as e:
            if attempt < RETRIES - 1:
                log_message(f"Retrying search... Attempt {attempt+1}/{RETRIES}: {str(e)}")
                time.sleep(RETRY_DELAY)
                continue
            log_message(f"❌ Search failed after {RETRIES} attempts: {str(e)}")
            raise

    return messages[:max_results]

def get_unique_senders(service, max_messages=150):
    """Get a list of unique email senders who have sent attachments"""
    try:
        log_message("Fetching sender list from recent emails with attachments")
        messages = search_messages(service, "has:attachment", max_messages)
        senders = {}  # Use dict to store both email and display name
        
        if not messages:
            log_message("No messages with attachments found")
            return []

        for i in range(0, len(messages), BATCH_SIZE):
            batch = messages[i:i+BATCH_SIZE]
            for msg in batch:
                try:
                    message = service.users().messages().get(
                        userId='me', id=msg['id'], format='metadata',
                        metadataHeaders=['From']
                    ).execute()
                    
                    headers = message['payload'].get('headers', [])
                    sender = next((h['value'] for h in headers if h['name'] == "From"), "")
                    
                    if sender:
                        # Extract email and name from the sender string
                        if "<" in sender and ">" in sender:
                            display_name = sender.split("<")[0].strip()
                            if display_name.endswith('"') and display_name.startswith('"'):
                                display_name = display_name[1:-1].strip()
                            email = sender.split("<")[1].split(">")[0].strip()
                            
                            # Store with email as key and full string as value for display
                            senders[email] = sender
                        else:
                            # If just an email with no display name
                            senders[sender.strip()] = sender.strip()
                            
                except Exception as e:
                    log_message(f"Skipped message {msg['id']} while getting senders: {str(e)}")
        
        log_message(f"Found {len(senders)} unique senders")
        # Return the full sender strings (with names if available)
        return sorted(senders.values())

    except Exception as e:
        log_message(f"❌ Failed to fetch senders: {str(e)}")
        return []
