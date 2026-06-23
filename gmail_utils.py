# gmail_utils.py
import os
import time
import json
import streamlit as st
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from logs import log_message

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
RETRIES = 3
BATCH_SIZE = 25
RETRY_DELAY = 2

REDIRECT_URI = "https://gmail-attachment-downloader.streamlit.app/"


def gmail_authenticate():
    """Authenticate with Gmail API using the Streamlit web interface.

    NOTE ON THE FIX:
    The previous version built a new Flow on every Streamlit rerun and called
    authorization_url() unconditionally. authorization_url() auto-generates a
    PKCE code_verifier; because the callback rerun generated a *different*
    verifier than the one whose challenge was sent to Google, fetch_token()
    failed with "invalid_grant: Invalid code verifier".

    PKCE is disabled here (autogenerate_code_verifier=False) on BOTH legs of
    the flow. This is valid for a Web-application OAuth client, which is
    secured by its client_secret. With no verifier, there is nothing to
    persist across the OAuth redirect (which on Streamlit is a full page
    reload that typically resets st.session_state), so the mismatch cannot
    happen.
    """
    creds = None

    # 1) Reuse a cached token within this session if we already have one.
    if "token_info" in st.session_state:
        try:
            creds = Credentials.from_authorized_user_info(
                st.session_state.token_info, SCOPES)
            if creds and creds.valid:
                return build("gmail", "v1", credentials=creds)
        except Exception as e:
            log_message(f"⚠️ Failed to use cached token: {str(e)}")

    # 2) Make sure we actually have credentials configured.
    if "google" not in st.secrets or "credentials_json" not in st.secrets["google"]:
        st.error("Google credentials missing in Streamlit secrets")
        log_message("❌ Google credentials missing in Streamlit secrets")
        return None

    creds_data = json.loads(st.secrets["google"]["credentials_json"])

    # NOTE: st.experimental_get_query_params / set_query_params are deprecated
    # in recent Streamlit versions (replaced by st.query_params). They are kept
    # here because they were already working in your app. If you hit a
    # deprecation/removal error, switch to:
    #     query_params = st.query_params          # dict-like, values are str
    #     code = st.query_params["code"]          # no [0] indexing
    #     st.query_params.clear()
    query_params = st.experimental_get_query_params()

    if "code" in query_params:
        # ---- Callback leg: exchange the authorization code for a token ----
        try:
            flow = Flow.from_client_config(
                client_config=creds_data,
                scopes=SCOPES,
                redirect_uri=REDIRECT_URI,
                autogenerate_code_verifier=False,  # <-- the fix (no PKCE)
            )

            code = query_params["code"][0]
            flow.fetch_token(code=code)
            creds = flow.credentials

            # Save credentials for reuse within this session.
            st.session_state.token_info = json.loads(creds.to_json())
            log_message("✅ Successfully connected to Gmail API")

            # Clear ?code= (and any other params) from the URL.
            st.experimental_set_query_params()
            return build("gmail", "v1", credentials=creds)

        except Exception as e:
            st.error(f"Authentication failed: {str(e)}")
            log_message(f"❌ Authentication error: {str(e)}")
            return None

    else:
        # ---- Auth-URL leg: send the user to Google to consent ----
        flow = Flow.from_client_config(
            client_config=creds_data,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI,
            autogenerate_code_verifier=False,  # <-- must match the callback leg
        )
        auth_url, _ = flow.authorization_url(prompt="consent")

        st.markdown("### Google Authentication Required")
        st.markdown(
            f"1. [Authorize with Google]({auth_url})\n"
            "2. You'll be redirected back automatically"
        )
        st.stop()

    return None


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
