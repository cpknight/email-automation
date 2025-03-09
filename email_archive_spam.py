import imaplib
import configparser
import signal
import email
import hashlib
import time
from email.utils import parsedate_to_datetime
from rich.console import Console
from rich.theme import Theme
from rich.progress import Progress, TextColumn, BarColumn
from datetime import datetime, timezone, timedelta

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
    SOURCE_FOLDER = config['archive_spam']['source_folder']
    TRASH_FOLDER = config['archive_spam']['trash_folder']
    BATCH_SIZE = int(config['archive_spam']['batch_size'])
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

def get_message_signatures_and_dates(mail, folder, start=1, end=None):
    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Fetching message signatures and dates from {folder} ({start}:{end or 'end'})...[/info]")
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
        
        signatures_and_dates = {}
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console,
            transient=True
        ) as progress:
            expected_count = end - start + 1
            task = progress.add_task(f"[highlight]Fetching data from {expected_count} messages in {folder}[/highlight]", total=expected_count)
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
                    date_str = msg.get("Date", "")
                    msg_date = parsedate_to_datetime(date_str).astimezone(timezone.utc) if date_str else datetime.now(timezone.utc)
                    signatures_and_dates[signature] = (uid, msg_id, msg_date)
                except (IndexError, AttributeError, imaplib.IMAP4.error, ValueError) as e:
                    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Error processing msg {msg_index + 1}: {e}[/warning]")
                    continue
                progress.update(task, advance=1)
        
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Fetched {len(signatures_and_dates)} signatures and dates from {folder}[/info]")
        return signatures_and_dates
    except imaplib.IMAP4.error as e:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]IMAP error searching {folder}: {e}[/warning]")
        return {}

def move_message_to_trash(mail, msg_id, uid, source_folder, trash_folder):
    try:
        mail.select(source_folder)
        status, _ = mail.copy(msg_id, trash_folder)
        if status == "OK":
            time.sleep(5)  # Delay for Proton Bridge sync
            mail.store(msg_id, "+FLAGS", "\\Deleted")
            console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Moved msg {msg_id} (UID {uid}) to {trash_folder}[/info]")
            return True
        else:
            console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Failed to copy msg {msg_id} (UID {uid}) to {trash_folder}[/warning]")
            return False
    except imaplib.IMAP4.error as e:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]IMAP error moving msg {msg_id} (UID {uid}) to {trash_folder}: {e}[/warning]")
        return False

def process_spam():
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

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)
    batch_start = 1
    trashed_count = 0
    
    while batch_start <= total_msgs and not stop_processing:
        batch_end = min(batch_start + BATCH_SIZE - 1, total_msgs)
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [highlight]Processing batch {batch_start}-{batch_end} of {total_msgs}[/highlight]")
        
        batch_data = get_message_signatures_and_dates(mail, SOURCE_FOLDER, start=batch_start, end=batch_end)
        
        messages_to_trash = [
            (signature, uid, msg_id)
            for signature, (uid, msg_id, msg_date) in batch_data.items()
            if msg_date < cutoff_date
        ]
        
        if not messages_to_trash:
            console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]No messages to move to Trash in this batch[/info]")
            batch_start += BATCH_SIZE
            continue
        
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Moving {len(messages_to_trash)} messages to Trash...[/info]")
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console,
            transient=True
        ) as progress:
            task = progress.add_task(f"[highlight]Moving to {TRASH_FOLDER}[/highlight]", total=len(messages_to_trash))
            for signature, uid, msg_id in messages_to_trash:
                if stop_processing:
                    break
                success = move_message_to_trash(mail, msg_id, uid, SOURCE_FOLDER, TRASH_FOLDER)
                if success:
                    trashed_count += 1
                    progress.update(task, advance=1)
        
        mail.select(SOURCE_FOLDER)
        mail.expunge()
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Batch complete: {trashed_count} moved to {TRASH_FOLDER}[/info]")
        batch_start += BATCH_SIZE

    if stop_processing:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Processing aborted by user[/warning]")
    else:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [success]Processing complete: {trashed_count} messages moved to Trash[/success]")
    mail.logout()

if __name__ == "__main__":
    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Starting spam archiving script...[/info]")
    process_spam()
