# ui_components.py
import streamlit as st
import datetime
from gmail_utils import get_unique_senders

def sidebar_filters(service):
    st.sidebar.subheader("🔍 Search Filters")
    
    # Create collapsible sections for better organization
    with st.sidebar.expander("✉️ Sender", expanded=True):
        # Sender selection
        sender_type = st.radio(
            "Find emails from:",
            ["Choose from recent senders", "Enter custom email"],
            horizontal=True,
            label_visibility="collapsed"
        )

        if sender_type == "Choose from recent senders":
            if "sender_select" not in st.session_state and st.session_state.sender_list:
                st.session_state.sender_select = st.session_state.sender_list[0]
                
            if st.session_state.sender_list:
                sender = st.selectbox(
                    "Select a sender",
                    st.session_state.sender_list,
                    index=(st.session_state.sender_list.index(st.session_state.sender_select)
                        if "sender_select" in st.session_state and 
                        st.session_state.sender_select in st.session_state.sender_list else 0),
                    key="sender_select",
                    placeholder="Choose a sender email"
                )
            else:
                st.info("No recent senders found. Try refreshing the sender list.")
                sender = ""
                
            if st.button("🔄 Refresh Sender List", key="refresh_senders"):
                with st.spinner("Updating sender list..."):
                    st.session_state.sender_list = get_unique_senders(service)
                st.success(f"Found {len(st.session_state.sender_list)} senders")
        else:
            sender = st.text_input(
                "Enter sender email", 
                value="", 
                key="custom_sender",
                placeholder="example@gmail.com"
            )

    # Date filter in a collapsible section
    with st.sidebar.expander("📅 Date Range", expanded=True):
        # Date range with more intuitive presets
        date_filter = st.radio(
            "Time period:",
            ["Last 7 days", "Last 30 days", "Last 90 days", "Custom range"],
            horizontal=True
        )
        
        today = datetime.date.today()
        
        if date_filter == "Last 7 days":
            start_date = today - datetime.timedelta(days=7)
            end_date = today
            st.caption(f"From {start_date.strftime('%b %d, %Y')} to {end_date.strftime('%b %d, %Y')}")
        elif date_filter == "Last 30 days":
            start_date = today - datetime.timedelta(days=30)
            end_date = today
            st.caption(f"From {start_date.strftime('%b %d, %Y')} to {end_date.strftime('%b %d, %Y')}")
        elif date_filter == "Last 90 days":
            start_date = today - datetime.timedelta(days=90)
            end_date = today
            st.caption(f"From {start_date.strftime('%b %d, %Y')} to {end_date.strftime('%b %d, %Y')}")
        else:
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("Start Date", value=today.replace(day=1), key="start_date")
            with col2:
                end_date = st.date_input("End Date", value=today, key="end_date")

    # Content filter in a collapsible section
    with st.sidebar.expander("🔤 Content Filter", expanded=True):
        # Search term with examples
        keyword = st.text_input(
            "Search in emails",
            value="",
            key="search_term",
            placeholder="invoice, report, contract, etc."
        )
        
        if not keyword:
            st.caption("Leave empty to search all emails with attachments")

    # Max results in a collapsible section
    with st.sidebar.expander("⚙️ Search Options", expanded=True):
        st.caption("Maximum number of emails to search")
        max_results = st.slider("Max Results", 10, 300, 50, step=10)
    
    # Help section
    with st.sidebar.expander("❓ Help", expanded=False):
        st.markdown("""
        **Quick Guide:**
        1. Select a sender or enter an email address
        2. Choose a date range for your search
        3. Add keywords to narrow down results (optional)
        4. Click "Search Emails" to find messages
        5. Use "Download Attachments" to save all files
        
        All attachments are organized by sender, search term, and file type for easy access.
        """)
    
    return sender, keyword, start_date, end_date, max_results

def format_query(sender, keyword, start_date, end_date):
    # Base query - always search for attachments
    query = ["has:attachment"]
    
    # Add sender filter if provided
    if sender:
        if "<" in sender and ">" in sender:
            # Extract email from format "Name <email>"
            email = sender.split("<")[1].split(">")[0].strip()
            query.append(f"from:{email}")
        else:
            query.append(f"from:{sender}")
    
    # Add keyword search if provided
    if keyword:
        # Handle multiple keywords separated by commas
        if "," in keyword:
            keywords = [k.strip() for k in keyword.split(",")]
            keyword_query = " OR ".join([f'"{k}"' for k in keywords if k])
            if keyword_query:
                query.append(f"({keyword_query})")
        else:
            query.append(f'"{keyword}"')
    
    # Add date range
    if start_date:
        query.append(f"after:{start_date.strftime('%Y/%m/%d')}")
    if end_date:
        # Add 1 day to end_date to make the search inclusive
        adjusted_end_date = end_date + datetime.timedelta(days=1)
        query.append(f"before:{adjusted_end_date.strftime('%Y/%m/%d')}")
    
    return " ".join(query)
