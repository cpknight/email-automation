import imaplib
import configparser
import signal
import email
import hashlib
import time
import re
from rich.console import Console
from rich.theme import Theme
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from datetime import datetime, timezone

custom_theme = Theme({"info": "blue", "success": "green", "warning": "yellow", "error": "red", "highlight": "cyan"})
console = Console(theme=custom_theme)

stop_processing = False

def signal_handler(sig, frame):
    global stop_processing
    if not stop_processing:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Abort requested (Ctrl+C detected), finishing current message...[/warning]")
        stop_processing = True

signal.signal(signal.SIGINT, signal_handler)

config = configparser.ConfigParser()
try:
    config.read('config.ini')
    IMAP_SERVER = config['imap']['server']
    IMAP_PORT = int(config['imap']['port'])
    USERNAME = config['imap']['username']
    PASSWORD = config['imap']['password']
    SOURCE_FOLDER = config['classifier']['source_folder']
    DEST_FOLDER_NOTIFICATIONS = config['classifier']['dest_folder_notifications']
    DEST_FOLDER_CORRESPONDENCE = config['classifier']['dest_folder_correspondence']
    BATCH_SIZE = int(config['classifier']['batch_size'])
except Exception as e:
    console.print(f"[grey50][{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}][/grey50] [error]Error loading config.ini: {e}[/error]")
    exit(1)

def get_utc_timestamp():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

def connect_to_imap():
    try:
        mail = imaplib.IMAP4(IMAP_SERVER, IMAP_PORT)
        mail.starttls()
        mail.login(USERNAME, PASSWORD)
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [success]Connected to IMAP server at {IMAP_SERVER}:{IMAP_PORT}[/success]")
        return mail
    except Exception as e:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [error]Failed to connect/login: {e}[/error]")
        exit(1)

def get_message_signatures(mail, folder, start=1, end=None, use_progress=True):
    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Fetching message signatures from {folder} ({start}:{end or 'end'})...[/info]")
    try:
        mail.select(folder)
        status, messages = mail.search(None, 'ALL')
        if status != "OK":
            console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Failed to search folder {folder}[/warning]")
            return {}
        msg_ids = messages[0].split()
        if not msg_ids:
            return {}
        
        total_msgs = len(msg_ids)
        end = min(end, total_msgs) if end else total_msgs
        start = max(1, min(start, total_msgs))
        if start > end:
            return {}
        
        batch_range = f"{start}:{end}"
        status, fetch_data = mail.fetch(batch_range, "(BODY[HEADER] UID)")
        if status != "OK":
            console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Failed to fetch headers for range {batch_range} in {folder}[/warning]")
            return {}
        
        signatures = {}
        if use_progress:
            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                console=console,
                transient=True
            ) as progress:
                expected_count = end - start + 1
                task = progress.add_task(f"[highlight]Fetching signatures from {expected_count} messages in {folder}[/highlight]", total=expected_count)
                msg_index = start - 1
                for i in range(0, len(fetch_data), 2):
                    if stop_processing:
                        break
                    try:
                        if i + 1 >= len(fetch_data):
                            break
                        msg_data = fetch_data[i]
                        uid_data = fetch_data[i + 1]
                        msg_id = msg_ids[msg_index]
                        msg_index += 1
                        raw_headers = msg_data[1]
                        uid = uid_data.decode().split('UID ')[-1].strip(')')
                        msg = email.message_from_bytes(raw_headers)
                        signature = hashlib.md5(
                            (msg.get("Message-ID", "") + msg.get("Subject", "") + msg.get("Date", "") + msg.get("From", "")).encode()
                        ).hexdigest()
                        signatures[signature] = (uid, msg_id)
                    except (IndexError, AttributeError, imaplib.IMAP4.error) as e:
                        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Error processing msg {msg_index + 1}: {e}[/warning]")
                        continue
                    progress.update(task, advance=1)
        else:
            msg_index = start - 1
            for i in range(0, len(fetch_data), 2):
                if stop_processing:
                    break
                try:
                    if i + 1 >= len(fetch_data):
                        break
                    msg_data = fetch_data[i]
                    uid_data = fetch_data[i + 1]
                    msg_id = msg_ids[msg_index]
                    msg_index += 1
                    raw_headers = msg_data[1]
                    uid = uid_data.decode().split('UID ')[-1].strip(')')
                    msg = email.message_from_bytes(raw_headers)
                    signature = hashlib.md5(
                        (msg.get("Message-ID", "") + msg.get("Subject", "") + msg.get("Date", "") + msg.get("From", "")).encode()
                    ).hexdigest()
                    signatures[signature] = (uid, msg_id)
                except (IndexError, AttributeError, imaplib.IMAP4.error):
                    continue
        
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Fetched {len(signatures)} signatures from {folder}[/info]")
        return signatures
    except imaplib.IMAP4.error as e:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]IMAP error searching {folder}: {e}[/warning]")
        return {}

def fetch_email_headers_and_body(mail, msg_id):
    try:
        mail.select(SOURCE_FOLDER)
        status, msg_data = mail.fetch(msg_id, "(BODY[HEADER] BODY[TEXT])")
        if status != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
            return None
        raw_headers = msg_data[0][1]
        raw_text = msg_data[1][1].decode('utf-8', errors='ignore') if isinstance(msg_data[1][1], bytes) else ""
        msg = email.message_from_bytes(raw_headers)
        msg["BODY[TEXT]"] = raw_text
        return msg
    except imaplib.IMAP4.error:
        return None

def classify_email(msg):
    if msg is None:
        return DEST_FOLDER_NOTIFICATIONS
    
    subject = msg.get("Subject", "").lower()
    from_addr = msg.get("From", "").lower()
    body = msg.get("BODY[TEXT]", "").lower().replace('\r\n', '\n')
    
    # Default to Correspondence
    dest = DEST_FOLDER_CORRESPONDENCE
    
    # 1. Sender Identity Match (fuzzy)
    sender_name = None
    salutations = re.findall(r'(best|regards|sincerely|thanks|cheers|kind regards),\s*([a-zA-Z\s]+)$', body, re.MULTILINE)
    if salutations:
        sender_name = salutations[-1][1].strip().lower()
    from_name = re.search(r'([^<]+)<?', from_addr).group(1).strip().lower() if '<' in from_addr else from_addr.split('@')[0].lower()
    sender_match = sender_name and (
        sender_name in from_name or 
        from_name in sender_name or 
        any(part in from_addr for part in sender_name.split()) or 
        len(sender_name) > 2  # Loose check for any reasonable name
    )
    
    # 2. Recipient Addressing (fuzzy)
    recipient_match = False
    greeting_lines = body.split('\n')[:10]  # Check first 10 lines for broader coverage
    for line in greeting_lines:
        if re.search(r'^(chris|knight|cpknight|dear\s+(sir|mr\.?\s+knight|chris)|hi\s+(chris|knight)|hello\s+(chris|knight)),?', line):
            recipient_match = True
            break
    
    # 3. Subject Matter (must be clear)
    request_keywords = ["please reply", "can you", "could you", "let me know", "waiting for", "your input", "need your", "respond"]
    update_keywords = ["here’s the", "update on", "latest", "status", "progress"]
    response_keywords = ["re:", "fwd:", "regarding your", "in response", "following up"]
    
    has_request = any(keyword in body for keyword in request_keywords)
    has_update = any(keyword in body for keyword in update_keywords)
    has_response = any(keyword in subject or keyword in body for keyword in response_keywords)
    subject_matter = has_request or has_update or has_response
    
    # Decision: (Sender OR Recipient) AND Subject Matter for Correspondence
    if not ((sender_match or recipient_match) and subject_matter):
        dest = DEST_FOLDER_NOTIFICATIONS
    
    return dest

def move_message(mail, msg_id, uid, source_folder, dest_folder, dest_signatures):
    try:
        mail.select(source_folder)
        msg = fetch_email_headers_and_body(mail, msg_id)
        if msg is None:
            console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Failed to fetch headers for msg {msg_id} (UID {uid}), skipping[/warning]")
            return False
        
        signature = hashlib.md5(
            (msg.get("Message-ID", "") + msg.get("Subject", "") + msg.get("Date", "") + msg.get("From", "")).encode()
        ).hexdigest()
        
        if signature in dest_signatures:
            console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Message {msg_id} (UID {uid}) already in {dest_folder}, marking for deletion[/info]")
            mail.store(msg_id, "+FLAGS", "\\Deleted")
            return True
        
        status, _ = mail.copy(msg_id, dest_folder)
        if status == "OK":
            time.sleep(5)
            mail.store(msg_id, "+FLAGS", "\\Deleted")
            console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Moved msg {msg_id} (UID {uid}) to {dest_folder}[/info]")
            return True
        else:
            console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Failed to copy msg {msg_id} (UID {uid}) to {dest_folder}[/warning]")
            return False
    except imaplib.IMAP4.error as e:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]IMAP error moving msg {msg_id} (UID {uid}) to {dest_folder}: {e}[/warning]")
        return False

def move_messages(mail, signatures, source_folder, notifications_msgs, correspondence_msgs):
    global stop_processing
    failed_moves = []
    notif_moves = 0
    corr_moves = 0
    
    notif_signatures = get_message_signatures(mail, DEST_FOLDER_NOTIFICATIONS, use_progress=False)
    corr_signatures = get_message_signatures(mail, DEST_FOLDER_CORRESPONDENCE, use_progress=False)
    
    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Starting message moves for batch...[/info]")
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console,
        transient=True
    ) as progress:
        notif_task = progress.add_task(f"[highlight]Moving to {DEST_FOLDER_NOTIFICATIONS}[/highlight]", total=len(notifications_msgs))
        corr_task = progress.add_task(f"[highlight]Moving to {DEST_FOLDER_CORRESPONDENCE}[/highlight]", total=len(correspondence_msgs))
        
        for signature, (uid, msg_id) in signatures.items():
            if stop_processing:
                console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Aborting batch processing[/warning]")
                break
            dest_folder = DEST_FOLDER_NOTIFICATIONS if (signature, uid, msg_id) in notifications_msgs else DEST_FOLDER_CORRESPONDENCE
            dest_signatures = notif_signatures if dest_folder == DEST_FOLDER_NOTIFICATIONS else corr_signatures
            success = move_message(mail, msg_id, uid, source_folder, dest_folder, dest_signatures)
            if not success:
                failed_moves.append(msg_id)
            else:
                if dest_folder == DEST_FOLDER_NOTIFICATIONS:
                    notif_moves += 1
                    notif_signatures[signature] = (uid, msg_id)
                    progress.update(notif_task, advance=1)
                else:
                    corr_moves += 1
                    corr_signatures[signature] = (uid, msg_id)
                    progress.update(corr_task, advance=1)
    
    mail.select(source_folder)
    mail.expunge()
    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Batch moves complete: {notif_moves} to Notifications, {corr_moves} to Correspondence[/info]")
    return not stop_processing and not failed_moves, failed_moves

def verify_moved_messages(mail, signatures, notifications_msgs, correspondence_msgs):
    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Verifying moved messages...[/info]")
    notif_signatures = get_message_signatures(mail, DEST_FOLDER_NOTIFICATIONS, use_progress=False)
    corr_signatures = get_message_signatures(mail, DEST_FOLDER_CORRESPONDENCE, use_progress=False)
    
    all_verified = True
    failed_notifications = []
    failed_correspondence = []
    
    for signature, uid, msg_id in notifications_msgs:
        if signature not in notif_signatures:
            failed_notifications.append(msg_id)
            all_verified = False
    
    for signature, uid, msg_id in correspondence_msgs:
        if signature not in corr_signatures:
            failed_correspondence.append(msg_id)
            all_verified = False
    
    if not all_verified:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Verification failed: {len(failed_notifications)} Notifications, {len(failed_correspondence)} Correspondence not found[/warning]")
    else:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [success]All messages verified successfully[/success]")
    return all_verified

def process_emails():
    global stop_processing
    mail = connect_to_imap()
    
    mail.select(SOURCE_FOLDER)
    status, messages = mail.search(None, 'ALL')
    if status != "OK":
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Failed to search {SOURCE_FOLDER}[/warning]")
        mail.logout()
        return
    total_msgs = len(messages[0].split())
    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Found {total_msgs} messages in {SOURCE_FOLDER}[/info]")

    if total_msgs == 0:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]No messages to process[/info]")
        mail.logout()
        return

    batch_start = 1
    while batch_start <= total_msgs and not stop_processing:
        batch_end = min(batch_start + BATCH_SIZE - 1, total_msgs)
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [highlight]Processing batch {batch_start}-{batch_end} of {total_msgs}[/highlight]")
        
        batch_signatures = get_message_signatures(mail, SOURCE_FOLDER, start=batch_start, end=batch_end)
        
        notifications_msgs = []
        correspondence_msgs = []
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Classifying {len(batch_signatures)} messages...[/info]")
        with Progress(
            SpinnerColumn(),
            TextColumn("[highlight]Classifying {task.total} messages[/highlight]"),
            console=console,
            transient=True
        ) as progress:
            task = progress.add_task("", total=len(batch_signatures))
            for signature, (uid, msg_id) in batch_signatures.items():
                if stop_processing:
                    break
                msg = fetch_email_headers_and_body(mail, msg_id)
                dest = classify_email(msg)
                if dest == DEST_FOLDER_NOTIFICATIONS:
                    notifications_msgs.append((signature, uid, msg_id))
                else:
                    correspondence_msgs.append((signature, uid, msg_id))
                progress.update(task, advance=1)
        
        if stop_processing:
            break
        
        completed, failed_moves = move_messages(mail, batch_signatures, SOURCE_FOLDER, notifications_msgs, correspondence_msgs)
        
        if not completed and not failed_moves:
            break
        
        if verify_moved_messages(mail, batch_signatures, notifications_msgs, correspondence_msgs):
            console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [success]Batch moved and verified successfully[/success]")
        else:
            console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Some messages in batch may not have moved correctly: {failed_moves}[/warning]")
        
        batch_start += BATCH_SIZE

    if stop_processing:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Processing aborted by user[/warning]")
    else:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [success]Processing complete[/success]")
    mail.logout()

if __name__ == "__main__":
    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Starting email processing script...[/info]")
    process_emails()
