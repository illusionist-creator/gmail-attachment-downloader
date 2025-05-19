# gmail_utils.py
import os
import time
import json
import streamlit as st
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from logs import log_message

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
RETRIES = 3
BATCH_SIZE = 25
RETRY_DELAY = 2

def gmail_authenticate():
    """Authenticate with Gmail API and return service object."""
    creds = None

    # Load token locally (for local development only)
    is_cloud = st.secrets.get("IS_CLOUD_DEPLOYMENT", False)
    if not is_cloud and os.path.exists("token.json"):
        try:
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
            log_message("✅ Loaded local token.json")
        except Exception as e:
            log_message(f"⚠️ Failed to load token.json: {str(e)}")

    # Use OAuth flow if no valid credentials
    if not creds or not creds.valid:
        try:
            if "google" in st.secrets and "credentials_json" in st.secrets["google"]:
                creds_data = json.loads(st.secrets["google"]["credentials_json"])
                flow = InstalledAppFlow.from_client_config(creds_data, SCOPES)

                if is_cloud:
                    log_message("🌐 Running on Streamlit Cloud – using run_console()")
                    creds = flow.run_console()
                else:
                    log_message("🖥️ Running locally – using run_local_server()")
                    creds = flow.run_local_server(port=0)

                # Save token.json locally (for dev only)
                if not is_cloud:
                    with open("token.json", "w") as token_file:
                        token_file.write(creds.to_json())
                    log_message("✅ Saved token.json locally")

            else:
                raise FileNotFoundError("❌ Google credentials missing in Streamlit secrets")
        except Exception as e:
            log_message(f"❌ Authentication failed: {str(e)}")
            raise

    # Build Gmail service
    try:
        service = build("gmail", "v1", credentials=creds)
        service.users().getProfile(userId='me').execute()
        log_message("✅ Successfully connected to Gmail API")
        return service
    except Exception as e:
        log_message(f"❌ Failed to build Gmail service: {str(e)}")
        raise

def search_messages(service, query, max_results=100):
    """Search Gmail for messages matching the query."""
    messages = []
    page_token = None
    log_message(f"Searching Gmail with query: {query}")

    for attempt in range(RETRIES):
        try:
            while len(messages) < max_results:
                current_batch = min(BATCH_SIZE, max_results - len(messages))
                result = service.users().messages().list(
                    userId='me',
                    q=query,
                    maxResults=current_batch,
                    pageToken=page_token
                ).execute(num_retries=RETRIES)

                batch_messages = result.get('messages', [])
                if not batch_messages:
                    log_message("No more messages found")
                    break

                messages.extend(batch_messages)
                log_message(f"Found {len(messages)} messages so far")

                page_token = result.get('nextPageToken')
                if not page_token:
                    break

            log_message(f"Search complete: {len(messages)} messages found")
            return messages[:max_results]

        except HttpError as e:
            if e.resp.status in [429, 500, 503] and attempt < RETRIES - 1:
                wait_time = RETRY_DELAY * (attempt + 1)
                log_message(f"⚠️ API error {e.resp.status}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                log_message(f"❌ HTTP error: {str(e)}")
                raise
        except Exception as e:
            if attempt < RETRIES - 1:
                log_message(f"⚠️ Retry attempt {attempt + 1}: {str(e)}")
                time.sleep(RETRY_DELAY)
            else:
                log_message(f"❌ Search failed after {RETRIES} attempts: {str(e)}")
                raise

    return messages[:max_results]

def get_unique_senders(service, max_messages=150):
    """Get a list of unique email senders who have sent attachments."""
    try:
        log_message("🔍 Fetching unique senders")
        messages = search_messages(service, "has:attachment", max_messages)
        senders = {}

        for i in range(0, len(messages), BATCH_SIZE):
            for msg in messages[i:i + BATCH_SIZE]:
                try:
                    message = service.users().messages().get(
                        userId='me', id=msg['id'], format='metadata',
                        metadataHeaders=['From']
                    ).execute()

                    headers = message['payload'].get('headers', [])
                    sender = next((h['value'] for h in headers if h['name'] == "From"), "")

                    if sender:
                        if "<" in sender and ">" in sender:
                            display_name = sender.split("<")[0].strip().strip('"')
                            email = sender.split("<")[1].split(">")[0].strip()
                            senders[email] = sender
                        else:
                            senders[sender.strip()] = sender.strip()

                except Exception as e:
                    log_message(f"⚠️ Skipped sender in message {msg['id']}: {str(e)}")

        log_message(f"✅ Found {len(senders)} unique senders")
        return sorted(senders.values())

    except Exception as e:
        log_message(f"❌ Failed to get senders: {str(e)}")
        return []
