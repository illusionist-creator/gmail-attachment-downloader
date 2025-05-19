# attachment_handler.py
import os
import base64
import re
import uuid
from datetime import datetime
from logs import log_message

def sanitize_filename(filename):
    """Clean up filenames to be safe for all operating systems"""
    # Replace any invalid characters with underscores
    cleaned = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Limit filename length to avoid path length issues
    if len(cleaned) > 100:
        name_parts = cleaned.split('.')
        if len(name_parts) > 1:
            extension = name_parts[-1]
            base_name = '.'.join(name_parts[:-1])
            cleaned = f"{base_name[:95]}_{extension}"
        else:
            cleaned = cleaned[:100]
    return cleaned

def classify_extension(filename):
    """Categorize file by extension for better organization"""
    if not filename or '.' not in filename:
        return "Other"
        
    ext = filename.split(".")[-1].lower()
    
    # Expanded classification map for better organization
    type_map = {
        # Documents
        "pdf": "PDFs",
        "doc": "Documents", "docx": "Documents", "rtf": "Documents", 
        "txt": "Documents", "odt": "Documents",
        
        # Spreadsheets
        "xls": "Spreadsheets", "xlsx": "Spreadsheets", "csv": "Spreadsheets",
        "ods": "Spreadsheets", "numbers": "Spreadsheets",
        
        # Images
        "jpg": "Images", "jpeg": "Images", "png": "Images", "gif": "Images",
        "bmp": "Images", "tiff": "Images", "webp": "Images", "svg": "Images",
        
        # Presentations
        "ppt": "Presentations", "pptx": "Presentations", "key": "Presentations",
        "odp": "Presentations",
        
        # Archives
        "zip": "Archives", "rar": "Archives", "7z": "Archives", 
        "tar": "Archives", "gz": "Archives",
        
        # Audio
        "mp3": "Audio", "wav": "Audio", "ogg": "Audio", "flac": "Audio",
        "m4a": "Audio", "aac": "Audio",
        
        # Video
        "mp4": "Video", "avi": "Video", "mov": "Video", "mkv": "Video",
        "wmv": "Video", "webm": "Video",
        
        # Code
        "py": "Code", "js": "Code", "html": "Code", "css": "Code",
        "java": "Code", "cpp": "Code", "c": "Code", "php": "Code",
        "json": "Code", "xml": "Code",
    }
    
    return type_map.get(ext, "Other")

def save_attachment(service, msg_id, part, sender_email, search_term, base_folder="downloads"):
    """Save an email attachment to disk with better organization and error handling"""
    try:
        # Clean up the filename
        original_name = sanitize_filename(part["filename"])
        
        if not original_name:
            log_message("⚠️ Skipping attachment with empty filename")
            return False
            
        # Generate a unique filename to avoid collisions
        unique_id = uuid.uuid4().hex[:6]
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{timestamp}_{unique_id}_{original_name}"
        
        # Organize files by type
        file_type = classify_extension(original_name)
        search_folder = search_term.strip() if search_term and search_term.strip() else "all-attachments"
        
        # Clean up sender email for folder name
        if "<" in sender_email and ">" in sender_email:
            clean_sender = sender_email.split("<")[1].split(">")[0].strip()
        else:
            clean_sender = sender_email.strip()
            
        # Create the folder structure
        save_path = os.path.join(
            base_folder,
            sanitize_filename(clean_sender),
            sanitize_filename(search_folder),
            file_type,
            filename
        )
        
        # Make sure the directory exists
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        # Get the attachment ID
        attachment_id = part["body"].get("attachmentId")
        if not attachment_id:
            log_message(f"⚠️ No attachment ID for file: {original_name}")
            return False

        # Download the attachment data
        att = service.users().messages().attachments().get(
            userId='me', messageId=msg_id, id=attachment_id).execute()
            
        if not att.get("data"):
            log_message(f"⚠️ No data in attachment: {original_name}")
            return False
            
        # Decode and save the file
        file_data = base64.urlsafe_b64decode(att["data"].encode("UTF-8"))
        
        with open(save_path, "wb") as f:
            f.write(file_data)
        
        log_message(f"✅ Saved: {save_path}")
        return True
        
    except Exception as e:
        log_message(f"❌ Failed to save {part.get('filename', 'unknown file')}: {str(e)}")
        return False
        
def extract_attachments(service, msg_id, payload, sender_email, search_term, base_folder):
    """Recursively extract all attachments from an email"""
    saved_files = 0
    
    # If we have parts, process each part
    if "parts" in payload:
        for part in payload["parts"]:
            saved_files += extract_attachments(service, msg_id, part, sender_email, search_term, base_folder)
    
    # Process this part if it's an attachment
    elif payload.get("filename") and "attachmentId" in payload.get("body", {}):
        if save_attachment(service, msg_id, payload, sender_email, search_term, base_folder):
            saved_files += 1
            
    return saved_files

def download_attachments(service, msg_id, sender_email, search_term="", base_folder="downloads"):
    """Download all attachments from an email and return count of files saved"""
    try:
        # Get the full message
        msg = service.users().messages().get(userId='me', id=msg_id).execute()
        
        if not msg or not msg.get('payload'):
            log_message(f"⚠️ Invalid message structure for ID: {msg_id}")
            return 0
            
        payload = msg['payload']
        
        # Extract and return number of saved files
        return extract_attachments(service, msg_id, payload, sender_email, search_term, base_folder)
        
    except Exception as e:
        log_message(f"❌ Error downloading attachments for message {msg_id}: {str(e)}")
        raise
