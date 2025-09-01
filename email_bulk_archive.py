#!/usr/bin/env python3
"""
Multi-Folder Email Archiver with Recovery Mechanism
===================================================

This script moves all messages from Processing, Correspondence, and Notifications
folders into the Archive folder. Features robust error recovery, transaction logging,
and colorful progress indicators.

Key Features:
- Processes messages in batches of 100 *** CPK: changed to 33
- Robust recovery mechanism with transaction logging
- Colorful progress bars for each batch
- Duplicate detection to prevent re-archiving
- Graceful interruption handling (Ctrl+C)
- Comprehensive error handling and retry logic
- Transaction rollback capability

Author: Derived from existing email automation scripts
"""

import imaplib
import configparser
import signal
import email
import hashlib
import time
import json
import os
from email.utils import parsedate_to_datetime
from rich.console import Console
from rich.theme import Theme
from rich.progress import Progress, TextColumn, BarColumn, MofNCompleteColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.table import Table
from datetime import datetime, timezone, timedelta

# Enhanced color theme for better visual feedback
custom_theme = Theme({
    "info": "blue", 
    "success": "green", 
    "warning": "yellow", 
    "error": "red", 
    "highlight": "cyan",
    "processing": "magenta",
    "archive": "bright_green",
    "recovery": "bright_yellow"
})

console = Console(theme=custom_theme)
stop_processing = False

# Transaction log file for recovery
TRANSACTION_LOG = "archive_transaction_log.json"
RECOVERY_LOG = "archive_recovery_log.json"

def signal_handler(sig, frame):
    global stop_processing
    if not stop_processing:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Graceful shutdown requested (Ctrl+C detected), finishing current batch...[/warning]")
        stop_processing = True

signal.signal(signal.SIGINT, signal_handler)

# Load configuration
config = configparser.ConfigParser()
try:
    config.read('config.ini')
    IMAP_SERVER = config['imap']['server']
    IMAP_PORT = int(config['imap']['port'])
    USERNAME = config['imap']['username']
    PASSWORD = config['imap']['password']
    
    # Source folders to archive from
    SOURCE_FOLDERS = [
        config['processor']['dest_folder'],  # Processing folder
        config['classifier']['dest_folder_correspondence'],  # Correspondence folder
        config['classifier']['dest_folder_notifications']   # Notifications folder
    ]
    
    # Destination archive folder
    ARCHIVE_FOLDER = config['archive_notifications']['dest_folder']  # Archive folder
    BATCH_SIZE = 33  # Fixed batch size as requested
    
except Exception as e:
    console.print(f"[grey50][{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}][/grey50] [error]Error loading config.ini: {e}[/error]")
    exit(1)

def get_utc_timestamp():
    """Get current UTC timestamp in standard format"""
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

def connect_to_imap():
    """Establish connection to IMAP server with error handling"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            mail = imaplib.IMAP4(IMAP_SERVER, IMAP_PORT)
            mail.starttls()
            mail.login(USERNAME, PASSWORD)
            console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [success]Connected to IMAP server at {IMAP_SERVER}:{IMAP_PORT}[/success]")
            return mail
        except Exception as e:
            console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [error]Connection attempt {attempt + 1}/{max_retries} failed: {e}[/error]")
            if attempt < max_retries - 1:
                time.sleep(5)  # Wait before retry
                continue
            console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [error]Failed to connect after {max_retries} attempts[/error]")
            exit(1)

def get_message_signatures_and_dates(mail, folder, start=1, end=None):
    """Fetch message signatures and dates with enhanced progress tracking"""
    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Scanning messages in {folder} (range {start}:{end or 'end'})...[/info]")
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
            BarColumn(complete_style="archive", finished_style="success"),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=False
        ) as progress:
            expected_count = end - start + 1
            task = progress.add_task(f"[processing]Analyzing {folder.split('/')[-1]}[/processing]", total=expected_count)
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
                    
                    # Create unique signature
                    signature = hashlib.md5(
                        (msg.get("Message-ID", "") + msg.get("Subject", "") + 
                         msg.get("Date", "") + msg.get("From", "")).encode()
                    ).hexdigest()
                    
                    date_str = msg.get("Date", "")
                    msg_date = parsedate_to_datetime(date_str).astimezone(timezone.utc) if date_str else datetime.now(timezone.utc)
                    signatures_and_dates[signature] = (uid, msg_id, msg_date, folder)
                    
                except (IndexError, AttributeError, imaplib.IMAP4.error, ValueError) as e:
                    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Error processing message {msg_index}: {e}[/warning]")
                    continue
                
                progress.update(task, advance=1)
        
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Analyzed {len(signatures_and_dates)} messages from {folder}[/info]")
        return signatures_and_dates
    
    except imaplib.IMAP4.error as e:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]IMAP error analyzing {folder}: {e}[/warning]")
        return {}

def load_transaction_log():
    """Load existing transaction log for recovery purposes"""
    if os.path.exists(TRANSACTION_LOG):
        try:
            with open(TRANSACTION_LOG, 'r') as f:
                return json.load(f)
        except Exception as e:
            console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Could not load transaction log: {e}[/warning]")
    return {"processed_signatures": [], "failed_operations": [], "session_start": get_utc_timestamp()}

def save_transaction_log(log_data):
    """Save transaction log for recovery"""
    try:
        with open(TRANSACTION_LOG, 'w') as f:
            json.dump(log_data, f, indent=2, default=str)
    except Exception as e:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Could not save transaction log: {e}[/warning]")

def move_message_with_recovery(mail, msg_id, uid, source_folder, dest_folder, signature, transaction_log):
    """Move message with robust error handling and recovery mechanism"""
    max_retries = 3
    
    # Check if already processed
    if signature in transaction_log.get("processed_signatures", []):
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Message {msg_id} (UID {uid}) already processed, skipping[/info]")
        return True
    
    for attempt in range(max_retries):
        try:
            mail.select(source_folder)
            
            # First, mark message as read and remove flags before copying
            console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Updating flags for message {msg_id} (UID {uid}) - marking as read and unflagging[/info]")
            
            # Mark as read and remove flagged status
            mail.store(msg_id, "+FLAGS", "\\Seen")  # Mark as read
            mail.store(msg_id, "-FLAGS", "\\Flagged")  # Remove flagged status
            
            # Brief delay to ensure flag changes are processed
            time.sleep(1)
            
            # Copy message to destination
            status, _ = mail.copy(msg_id, dest_folder)
            if status == "OK":
                # Verify the copy was successful before deleting
                mail.select(dest_folder)
                search_status, _ = mail.search(None, f'UID {uid}')
                
                if search_status == "OK":
                    # Mark original as deleted
                    mail.select(source_folder)
                    time.sleep(2)  # Brief delay for server consistency
                    mail.store(msg_id, "+FLAGS", "\\Deleted")
                    
                    # Log successful operation
                    transaction_log["processed_signatures"].append(signature)
                    save_transaction_log(transaction_log)
                    
                    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [archive]Successfully processed message {msg_id} (UID {uid}): marked as read, unflagged, and moved from {source_folder} to {dest_folder}[/archive]")
                    return True
                else:
                    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Copy verification failed for message {msg_id} (UID {uid}) on attempt {attempt + 1}[/warning]")
            else:
                console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Copy failed for message {msg_id} (UID {uid}) on attempt {attempt + 1}: status {status}[/warning]")
                
        except imaplib.IMAP4.error as e:
            console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]IMAP error moving message {msg_id} (UID {uid}) on attempt {attempt + 1}: {e}[/warning]")
        except Exception as e:
            console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [error]Unexpected error moving message {msg_id} (UID {uid}) on attempt {attempt + 1}: {e}[/error]")
        
        if attempt < max_retries - 1:
            console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Retrying in 5 seconds...[/info]")
            time.sleep(5)
    
    # Log failed operation
    failed_op = {
        "signature": signature,
        "msg_id": str(msg_id),
        "uid": uid,
        "source_folder": source_folder,
        "dest_folder": dest_folder,
        "timestamp": get_utc_timestamp(),
        "error": "Max retries exceeded"
    }
    transaction_log.setdefault("failed_operations", []).append(failed_op)
    save_transaction_log(transaction_log)
    
    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [error]Failed to move message {msg_id} (UID {uid}) after {max_retries} attempts[/error]")
    return False

def display_summary_table(folder_stats):
    """Display a beautiful summary table of operations"""
    table = Table(title="📧 Bulk Archive Operation Summary", title_style="bold archive")
    
    table.add_column("Source Folder", style="cyan", no_wrap=True)
    table.add_column("Messages Found", justify="right", style="blue")
    table.add_column("Successfully Moved", justify="right", style="green")
    table.add_column("Failed", justify="right", style="red")
    table.add_column("Success Rate", justify="right", style="yellow")
    
    total_found = total_moved = total_failed = 0
    
    for folder, stats in folder_stats.items():
        found = stats['found']
        moved = stats['moved']
        failed = stats['failed']
        
        total_found += found
        total_moved += moved
        total_failed += failed
        
        success_rate = f"{(moved / found * 100):.1f}%" if found > 0 else "N/A"
        
        table.add_row(
            folder.split('/')[-1],
            str(found),
            str(moved),
            str(failed),
            success_rate
        )
    
    # Add totals row
    overall_success_rate = f"{(total_moved / total_found * 100):.1f}%" if total_found > 0 else "N/A"
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{total_found}[/bold]",
        f"[bold]{total_moved}[/bold]",
        f"[bold]{total_failed}[/bold]",
        f"[bold]{overall_success_rate}[/bold]",
        style="bright_white"
    )
    
    console.print(table)

def process_bulk_archive():
    """Main function to process bulk archiving with recovery mechanism"""
    global stop_processing
    
    # Display startup banner
    console.print(Panel.fit(
        "[bold archive]📦 Multi-Folder Email Bulk Archiver[/bold archive]\n\n"
        f"Source Folders: {', '.join([f.split('/')[-1] for f in SOURCE_FOLDERS])}\n"
        f"Destination: {ARCHIVE_FOLDER}\n"
        f"Batch Size: {BATCH_SIZE} messages\n"
        f"Recovery Log: {TRANSACTION_LOG}",
        title="🚀 Starting Operation",
        title_align="center",
        style="cyan"
    ))
    
    # Load transaction log for recovery
    transaction_log = load_transaction_log()
    previously_processed = len(transaction_log.get("processed_signatures", []))
    if previously_processed > 0:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [recovery]Found {previously_processed} previously processed messages in recovery log[/recovery]")
    
    mail = connect_to_imap()
    folder_stats = {}
    
    try:
        # First, get archive folder signatures to prevent duplicates
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Scanning existing messages in {ARCHIVE_FOLDER} to prevent duplicates...[/info]")
        archive_signatures = set(get_message_signatures_and_dates(mail, ARCHIVE_FOLDER).keys())
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Found {len(archive_signatures)} existing messages in archive[/info]")
        
        # Process each source folder
        for source_folder in SOURCE_FOLDERS:
            if stop_processing:
                break
                
            console.print(f"\n[grey50][{get_utc_timestamp()}][/grey50] [highlight]Starting processing of {source_folder}[/highlight]")
            
            # Get total message count
            try:
                mail.select(source_folder)
                status, messages = mail.search(None, 'ALL')
                if status != "OK":
                    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Failed to access {source_folder}[/warning]")
                    folder_stats[source_folder] = {'found': 0, 'moved': 0, 'failed': 0}
                    continue
                
                total_msgs = len(messages[0].split()) if messages[0] else 0
                console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Found {total_msgs} messages in {source_folder}[/info]")
                
                if total_msgs == 0:
                    folder_stats[source_folder] = {'found': 0, 'moved': 0, 'failed': 0}
                    continue
                
                folder_stats[source_folder] = {'found': total_msgs, 'moved': 0, 'failed': 0}
                
            except Exception as e:
                console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [error]Error accessing {source_folder}: {e}[/error]")
                folder_stats[source_folder] = {'found': 0, 'moved': 0, 'failed': 0}
                continue
            
            # Process in batches
            batch_start = 1
            while batch_start <= total_msgs and not stop_processing:
                batch_end = min(batch_start + BATCH_SIZE - 1, total_msgs)
                
                console.print(f"\n[grey50][{get_utc_timestamp()}][/grey50] [processing]Processing batch {batch_start}-{batch_end} from {source_folder.split('/')[-1]}[/processing]")
                
                # Get batch data
                batch_data = get_message_signatures_and_dates(mail, source_folder, start=batch_start, end=batch_end)
                
                if not batch_data:
                    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]No messages in this batch[/info]")
                    batch_start += BATCH_SIZE
                    continue
                
                # Filter out messages already in archive
                messages_to_move = [
                    (signature, uid, msg_id, msg_date, folder)
                    for signature, (uid, msg_id, msg_date, folder) in batch_data.items()
                    if signature not in archive_signatures
                ]
                
                if not messages_to_move:
                    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]All messages in this batch already exist in archive[/info]")
                    batch_start += BATCH_SIZE
                    continue
                
                console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Moving {len(messages_to_move)} unique messages to {ARCHIVE_FOLDER}...[/info]")
                
                # Move messages with colorful progress bar
                with Progress(
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(complete_style="archive", finished_style="success"),
                    MofNCompleteColumn(),
                    TimeElapsedColumn(),
                    console=console,
                    transient=False
                ) as progress:
                    task = progress.add_task(f"[archive]Archiving from {source_folder.split('/')[-1]}[/archive]", total=len(messages_to_move))
                    
                    for signature, uid, msg_id, msg_date, folder in messages_to_move:
                        if stop_processing:
                            break
                        
                        success = move_message_with_recovery(mail, msg_id, uid, source_folder, ARCHIVE_FOLDER, signature, transaction_log)
                        if success:
                            folder_stats[source_folder]['moved'] += 1
                            archive_signatures.add(signature)  # Update local cache
                        else:
                            folder_stats[source_folder]['failed'] += 1
                        
                        progress.update(task, advance=1)
                
                # Expunge deleted messages
                try:
                    mail.select(source_folder)
                    mail.expunge()
                    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Batch complete - {folder_stats[source_folder]['moved']} messages moved so far[/info]")
                except Exception as e:
                    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Error expunging messages: {e}[/warning]")
                
                batch_start += BATCH_SIZE
                
                # Brief pause between batches
                if not stop_processing and batch_start <= total_msgs:
                    time.sleep(1)
        
    except Exception as e:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [error]Critical error during processing: {e}[/error]")
    
    finally:
        try:
            mail.logout()
        except:
            pass
    
    # Display final summary
    console.print(f"\n[grey50][{get_utc_timestamp()}][/grey50] [highlight]Operation Complete![/highlight]")
    display_summary_table(folder_stats)
    
    # Save recovery information
    recovery_info = {
        "completion_time": get_utc_timestamp(),
        "folder_stats": folder_stats,
        "total_processed": len(transaction_log.get("processed_signatures", [])),
        "total_failed": len(transaction_log.get("failed_operations", [])),
        "interrupted": stop_processing
    }
    
    try:
        with open(RECOVERY_LOG, 'w') as f:
            json.dump(recovery_info, f, indent=2, default=str)
    except Exception as e:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Could not save recovery information: {e}[/warning]")
    
    if stop_processing:
        console.print(Panel.fit(
            "[warning]⚠️  Operation was interrupted by user[/warning]\n\n"
            f"Progress has been saved to {TRANSACTION_LOG}\n"
            "You can resume the operation by running the script again.",
            title="🛑 Graceful Shutdown",
            title_align="center",
            style="yellow"
        ))
    else:
        total_moved = sum(stats['moved'] for stats in folder_stats.values())
        total_failed = sum(stats['failed'] for stats in folder_stats.values())
        
        console.print(Panel.fit(
            f"[success]✅ Successfully completed bulk archive operation![/success]\n\n"
            f"📦 Total Messages Moved: {total_moved}\n"
            f"❌ Total Failed: {total_failed}\n"
            f"📝 Transaction Log: {TRANSACTION_LOG}\n"
            f"🔄 Recovery Log: {RECOVERY_LOG}",
            title="🎉 Success",
            title_align="center",
            style="green"
        ))

def main():
    """Entry point with error handling"""
    try:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Starting Multi-Folder Email Bulk Archiver...[/info]")
        process_bulk_archive()
    except KeyboardInterrupt:
        console.print(f"\n[grey50][{get_utc_timestamp()}][/grey50] [warning]Script interrupted by user[/warning]")
    except Exception as e:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [error]Fatal error: {e}[/error]")
        raise

if __name__ == "__main__":
    main()
