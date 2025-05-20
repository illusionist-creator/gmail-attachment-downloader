# app.py
import streamlit as st
import pandas as pd
from gmail_utils import gmail_authenticate, search_messages, get_unique_senders
from attachment_handler import download_attachments, create_zip_from_attachments
from ui_components import sidebar_filters, format_query
from logs import log_message, get_logs, clear_logs
import datetime

# Initialize session state
if "logs" not in st.session_state:
    st.session_state.logs = []
if "service" not in st.session_state:
    st.session_state.service = None
if "df" not in st.session_state:
    st.session_state.df = None
if "sender_list" not in st.session_state:
    st.session_state.sender_list = []
if "download_status" not in st.session_state:
    st.session_state.download_status = None
if "show_logs" not in st.session_state:
    st.session_state.show_logs = False
if "zip_buffer" not in st.session_state:
    st.session_state.zip_buffer = None
if "zip_details" not in st.session_state:
    st.session_state.zip_details = None

# App config
st.set_page_config(
    page_title="Gmail Attachment Manager",
    page_icon="📎",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for a cleaner look
st.markdown("""
<style>
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    .stProgress > div > div {
        background-color: #4CAF50;
    }
    .stAlert {
        border-radius: 8px;
    }
    div[data-testid="stExpander"] {
        border-radius: 8px;
    }
    div[data-testid="stDataFrame"] {
        border-radius: 8px;
    }
    .stButton button {
        border-radius: 6px;
        padding: 0.5rem 1rem;
        font-weight: 500;
    }
    .download-btn button {
        background-color: #4CAF50;
        color: white;
    }
    .fetch-btn button {
        background-color: #2196F3;
        color: white;
    }
    .auth-btn button {
        background-color: #FF9800;
        color: white;
    }
    h1, h2, h3 {
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.header("📎 Gmail Attachment Manager")
st.caption("Easily search and download attachments from your Gmail")

# Authentication section
auth_col1, auth_col2 = st.columns([3, 1])

with auth_col1:
    if not st.session_state.service:
        st.info("👋 Welcome! Please authenticate with your Google account to get started.")
    else:
        st.success("✅ Connected to Gmail")

with auth_col2:
    if not st.session_state.service:
        st.markdown('<div class="auth-btn">', unsafe_allow_html=True)
        if st.button("🔐 Connect Gmail"):
            try:
                with st.spinner("Preparing Gmail connection..."):
                    st.session_state.service = gmail_authenticate()
                if st.session_state.service:
                    st.session_state.sender_list = get_unique_senders(st.session_state.service)
                    st.success("Authentication successful!")
                    st.rerun()
            except Exception as e:
                st.error(f"Authentication failed: {str(e)}")
                log_message(f"Authentication error: {str(e)}")
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        if st.button("🔒 Logout"):
            for key in ["service", "df", "sender_list", "sender_select", "download_status", "token_info", "zip_buffer", "zip_details"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

# Main functionality
if st.session_state.service:
    # Fetch senders only if not present
    if not st.session_state.sender_list:
        with st.spinner("Loading sender list..."):
            st.session_state.sender_list = get_unique_senders(st.session_state.service)
    
    # Create a clean division between sections
    st.divider()
    
    # Search and results section in main area
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📥 Email Search")
    
    with col2:
        st.markdown('<div class="fetch-btn" style="text-align: right;">', unsafe_allow_html=True)
        fetch_button = st.button("🔍 Search Emails", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Filters and controls
    try:
        sender, keyword, start_date, end_date, max_results = sidebar_filters(st.session_state.service)
    except Exception as e:
        st.error(f"Filter error: {str(e)}")
        log_message(f"Filter setup error: {str(e)}")
        st.stop()

    # Email fetching
    if fetch_button:
        try:
            with st.spinner(f"Searching for emails with attachments..."):
                query = format_query(sender, keyword, start_date, end_date)
                log_message(f"Search query: {query}")
                messages = search_messages(st.session_state.service, query, max_results)

            if not messages:
                st.warning("No messages found matching your criteria")
                st.session_state.df = None
                log_message("Search returned no results")
            else:
                results = []
                progress_container = st.empty()
                status_container = st.empty()
                
                status_container.info(f"Processing {len(messages)} emails...")
                progress_bar = progress_container.progress(0)

                # Batch processing
                for i in range(0, len(messages), 20):
                    batch = messages[i:i+20]
                    batch_results = []
                    
                    status_container.info(f"Processing emails {i+1}-{min(i+20, len(messages))} of {len(messages)}...")

                    for msg in batch:
                        try:
                            msg_data = st.session_state.service.users().messages().get(
                                userId='me', id=msg['id'], format='metadata'
                            ).execute()
                            headers = msg_data['payload'].get('headers', [])
                            subject = next((h['value'] for h in headers if h['name'] == "Subject"), "(No Subject)")
                            sender_email = next((h['value'] for h in headers if h['name'] == "From"), "Unknown")
                            date = next((h['value'] for h in headers if h['name'] == "Date"), "")
                            
                            # Extract display name from sender
                            display_name = sender_email
                            if "<" in sender_email and ">" in sender_email:
                                display_name = sender_email.split("<")[0].strip()
                                if display_name.endswith('"') and display_name.startswith('"'):
                                    display_name = display_name[1:-1]
                                
                            batch_results.append({
                                "ID": msg["id"],
                                "Sender Name": display_name,
                                "Email": sender_email if "<" in sender_email else sender_email,
                                "Subject": subject,
                                "Date": date
                            })
                        except Exception as e:
                            log_message(f"Skipped message {msg['id']}: {str(e)}")

                    results.extend(batch_results)
                    progress = (i + len(batch)) / len(messages)
                    progress_bar.progress(min(progress, 1.0))

                st.session_state.df = pd.DataFrame(results)
                
                # Clean up progress indicators
                progress_container.empty()
                status_container.empty()
                
                st.success(f"Found {len(results)} emails with attachments")
                log_message(f"Search complete: found {len(results)} messages")

        except Exception as e:
            st.error(f"Search failed: {str(e)}")
            log_message(f"Critical search error: {str(e)}")

    # Results display
    if st.session_state.df is not None and not st.session_state.df.empty:
        st.subheader(f"📋 Results: {len(st.session_state.df)} emails found")
        
        # Display the email data in a clean format
        display_df = st.session_state.df.copy()
        
        # Clean up columns for display
        if "Email" in display_df.columns:
            display_df["Email"] = display_df["Email"].apply(
                lambda x: x.split("<")[1].split(">")[0] if "<" in x and ">" in x else x
            )
        
        # Format date for better readability
        if "Date" in display_df.columns:
            display_df["Date"] = pd.to_datetime(display_df["Date"], errors='coerce')
            display_df["Date"] = display_df["Date"].dt.strftime('%Y-%m-%d %H:%M')
            display_df = display_df.sort_values(by="Date", ascending=False)
        
        # Display only relevant columns
        display_cols = ["Sender Name", "Email", "Subject", "Date"]
        display_df = display_df[display_cols]
        
        # Show dataframe with improved styling
        st.dataframe(
            display_df,
            use_container_width=True,
            column_config={
                "Sender Name": st.column_config.TextColumn("Sender"),
                "Email": st.column_config.TextColumn("Email Address"),
                "Subject": st.column_config.TextColumn("Subject"),
                "Date": st.column_config.TextColumn("Date")
            },
            hide_index=True
        )
        
        # Download section
        st.markdown("### 📥 Download Options")
        
        download_col1, download_col2, download_col3 = st.columns([2, 1, 1])
        
        with download_col1:
            download_type = st.radio(
                "How do you want to download attachments?",
                ["Save to my computer", "Save on server"],
                horizontal=True,
                index=0  # Default to local download
            )
            
            if download_type == "Save on server":
                dest_folder = st.text_input(
                    "Server folder path", 
                    value="downloads", 
                    help="Folder on the server where attachments will be saved"
                )
            else:
                # Generate a descriptive zip filename
                today = datetime.date.today()
                default_zip_name = f"gmail_attachments_{today.strftime('%Y%m%d')}"
                if sender:
                    if "<" in sender and ">" in sender:
                        email = sender.split("<")[1].split(">")[0].strip()
                        default_zip_name += f"_{email.split('@')[0]}"
                    else:
                        default_zip_name += f"_{sender.split('@')[0]}"
                
                if keyword:
                    # Add first keyword to filename
                    first_keyword = keyword.split(',')[0].strip()
                    default_zip_name += f"_{first_keyword}"
                
                zip_filename = st.text_input(
                    "Zip filename",
                    value=default_zip_name,
                    help="Name for the zip file containing all attachments"
                )
        
        with download_col2:
            st.markdown('<div class="download-btn" style="margin-top: 30px;">', unsafe_allow_html=True)
            download_button = st.button("📥 Download Attachments", use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
        # Download process
        if download_button:
            log_message("Starting download process...")
            
            progress_container = st.empty()
            status_container = st.empty()
            summary_container = st.empty()
            
            progress_bar = progress_container.progress(0)
            status_container.info("Preparing downloads...")
            
            success_count = 0
            error_count = 0
            total_files = 0

            try:
                # For local downloads, use an in-memory collection
                memory_files = {}
                in_memory = (download_type == "Save to my computer")
                dest_folder = "downloads" if not in_memory and not 'dest_folder' in locals() else dest_folder
                
                for i, row in st.session_state.df.iterrows():
                    try:
                        status_text = f"Processing email {i+1}/{len(st.session_state.df)}: {row['Subject'][:50]}..."
                        status_container.info(status_text)
                        
                        files_count = download_attachments(
                            st.session_state.service,
                            row["ID"],
                            row["Email"],
                            keyword,
                            dest_folder,
                            in_memory,
                            memory_files if in_memory else None
                        )
                        
                        total_files += files_count
                        success_count += 1
                    except Exception as e:
                        error_count += 1
                        log_message(f"Failed {row['Subject']}: {str(e)}")
                    finally:
                        progress_bar.progress((i + 1) / len(st.session_state.df))
                
                # Clean up progress indicators
                progress_container.empty()
                status_container.empty()
                
                if in_memory:
                    # Create a zip file from memory files
                    if total_files > 0:
                        zip_buffer = create_zip_from_attachments(memory_files)
                        
                        # Store in session state for download button
                        st.session_state.zip_buffer = zip_buffer
                        st.session_state.zip_details = {
                            "filename": f"{zip_filename}.zip",
                            "count": total_files
                        }
                        
                        st.session_state.download_status = {
                            "success": True,
                            "message": f"✅ Found {total_files} attachments from {success_count} emails",
                            "details": f"Click the download button below to save them to your computer"
                        }
                    else:
                        st.session_state.download_status = {
                            "success": False,
                            "message": "⚠️ No attachments found in the selected emails",
                            "details": "Try adjusting your search criteria"
                        }
                else:
                    # Server-side storage (original behavior)
                    if total_files > 0:
                        st.session_state.download_status = {
                            "success": True,
                            "message": f"✅ Download complete: {total_files} attachments from {success_count} emails",
                            "details": f"Files saved to server folder: {dest_folder}"
                        }
                    else:
                        st.session_state.download_status = {
                            "success": False,
                            "message": "⚠️ No attachments found in the selected emails",
                            "details": "Try adjusting your search criteria"
                        }
                
                log_message(f"Download summary: {success_count} successes, {error_count} errors, {total_files} files")
                st.rerun()
                
            except Exception as e:
                st.error(f"Download process failed: {str(e)}")
                log_message(f"Critical download error: {str(e)}")
        
        # Show download status and download button
        if st.session_state.download_status:
            if st.session_state.download_status["success"]:
                st.success(st.session_state.download_status["message"])
                st.caption(st.session_state.download_status["details"])
                
                # Add download button if we have a zip file ready
                if st.session_state.zip_buffer and st.session_state.zip_details:
                    zip_name = st.session_state.zip_details["filename"]
                    file_count = st.session_state.zip_details["count"]
                    
                    col1, col2 = st.columns([3, 1])
                    with col2:
                        st.download_button(
                            label=f"⬇️ Save {file_count} Files (.zip)",
                            data=st.session_state.zip_buffer,
                            file_name=zip_name,
                            mime="application/zip",
                            use_container_width=True
                        )
            else:
                st.warning(st.session_state.download_status["message"])
                st.caption(st.session_state.download_status["details"])

# Logs section (collapsible)
st.divider()
with st.expander("📋 System Logs", expanded=st.session_state.show_logs):
    log_col1, log_col2 = st.columns([3, 1])
    
    with log_col1:
        st.text_area("", get_logs(), height=150, key="logs_area")
    
    with log_col2:
        if st.button("Clear Logs", key="clear_logs", use_container_width=True):
            clear_logs()
            st.session_state.show_logs = False
            st.rerun()

# Footer
st.caption("© 2025 Gmail Attachment Manager")