import imaplib
import configparser
import signal
import email
import hashlib
import time
import re
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime
import matplotlib.pyplot as plt
import io
import base64
from rich.console import Console
from rich.theme import Theme
from rich.progress import Progress, TextColumn, BarColumn
from datetime import datetime, timezone, timedelta
from collections import Counter

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
    INBOX_FOLDER = config['summary_inbox']['inbox_folder']
    DRAFTS_FOLDER = config['summary_inbox']['drafts_folder']
    BATCH_SIZE = int(config['summary_inbox']['batch_size'])
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

def detect_code_injection(text):
    if not text or text == "Unknown" or text == "No Subject" or text == "No Date":
        return False
    patterns = [
        r'<\w+[^>]*>',
        r'http[s]?://[^\s]{50,}',
        r'(eval\(|<script|javascript:)'
    ]
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)

def classify_inbox(msg):
    date_str = msg.get("Date", "")
    msg_date = parsedate_to_datetime(date_str).astimezone(timezone.utc) if date_str else datetime.now(timezone.utc)
    cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    
    if msg_date >= cutoff_24h:
        return "Recent"
    if msg_date < cutoff_24h:
        return "Pending"
    return "Other"  # Fallback, should be rare

def get_message_signatures_and_headers(mail, folder, start=1, end=None):
    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Fetching message signatures and headers from {folder} ({start}:{end or 'end'})...[/info]")
    try:
        mail.select(folder)
        status, messages = mail.search(None, 'ALL')
        if status != "OK" or not messages[0]:
            console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Failed to search folder {folder}[/warning]")
            return {}
        
        msg_ids = messages[0].split()
        total_msgs = len(msg_ids)
        end = min(end, total_msgs) if end else total_msgs
        start = max(1, min(start, total_msgs))
        if start > end:
            return {}
        
        batch_range = f"{start}:{end}"
        status, fetch_data = mail.fetch(batch_range, "(BODY[HEADER] BODY[TEXT] UID)")
        if status != "OK":
            console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Failed to fetch headers for range {batch_range} in {folder}[/warning]")
            return {}
        
        signatures_and_headers = {}
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console,
            transient=True
        ) as progress:
            expected_count = end - start + 1
            task = progress.add_task(f"[highlight]Fetching data from {expected_count} messages in {folder}[/highlight]", total=expected_count)
            msg_index = start - 1
            i = 0
            while i < len(fetch_data) and msg_index < end:
                if stop_processing:
                    break
                try:
                    if i + 1 >= len(fetch_data) or not isinstance(fetch_data[i], tuple):
                        i += 1
                        continue
                    header_data = fetch_data[i]
                    raw_headers = header_data[1]
                    i += 1
                    
                    if i + 1 >= len(fetch_data) or not isinstance(fetch_data[i], tuple):
                        i += 1
                        continue
                    text_data = fetch_data[i]
                    raw_text = text_data[1].decode('utf-8', errors='ignore') if isinstance(text_data[1], bytes) else ""
                    i += 1
                    
                    if i >= len(fetch_data):
                        break
                    uid_data = fetch_data[i]
                    uid = uid_data.decode('utf-8', errors='ignore').split('UID ')[-1].strip(')') if isinstance(uid_data, bytes) else "Unknown"
                    i += 1
                    
                    msg_id = msg_ids[msg_index]
                    msg_index += 1
                    msg = email.message_from_bytes(raw_headers)
                    msg["BODY[TEXT]"] = raw_text
                    signature = hashlib.md5(
                        (msg.get("Message-ID", "") + msg.get("Subject", "") + msg.get("Date", "") + msg.get("From", "")).encode()
                    ).hexdigest()
                    classification = classify_inbox(msg)
                    subject_injection = detect_code_injection(msg.get("Subject", ""))
                    from_injection = detect_code_injection(msg.get("From", ""))
                    return_path_injection = detect_code_injection(msg.get("Return-Path", ""))
                    signatures_and_headers[signature] = {
                        'uid': uid,
                        'msg_id': msg_id,
                        'from': msg.get("From", "Unknown"),
                        'return_path': msg.get("Return-Path", "Unknown"),
                        'subject': msg.get("Subject", "No Subject"),
                        'date': msg.get("Date", "No Date"),
                        'classification': classification,
                        'subject_injection': subject_injection,
                        'from_injection': from_injection,
                        'return_path_injection': return_path_injection
                    }
                    progress.update(task, advance=1)
                except Exception as e:
                    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Error processing msg {msg_index + 1}: {e}[/warning]")
                    i += 1
                    continue
        
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Fetched {len(signatures_and_headers)} signatures and headers from {folder}[/info]")
        return signatures_and_headers
    except imaplib.IMAP4.error as e:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]IMAP error searching {folder}: {e}[/warning]")
        return {}

def generate_pie_chart(classifications):
    counts = Counter(classifications)
    labels = list(counts.keys())
    sizes = list(counts.values())
    
    plt.figure(figsize=(6, 6))
    plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140, colors=['#4CAF50', '#FF5722', '#2196F3'])
    plt.title("Inbox Classifications")
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    img_str = base64.b64encode(buf.getvalue()).decode('utf-8')
    plt.close()
    return img_str

def truncate_text(text, max_length=50):
    return text[:max_length] + "..." if len(text) > max_length else text

def create_draft_summary(mail, inbox_data):
    timestamp = get_utc_timestamp()
    subject = f"INBOX Folder Summary as at {timestamp}"
    
    if not inbox_data:
        return
    
    dates = [data['date'] for data in inbox_data.values()]
    classifications = [data['classification'] for data in inbox_data.values()]
    senders = [data['from'] for data in inbox_data.values()]
    discrepancies = sum(1 for data in inbox_data.values() if data['from'] != data['return_path'])
    injections = sum(1 for data in inbox_data.values() if data['subject_injection'] or data['from_injection'] or data['return_path_injection'])
    
    date_range_start = min(dates, default='N/A')
    date_range_end = max(dates, default='N/A')
    class_counts = Counter(classifications)
    sender_counts = Counter(senders).most_common(5)
    total_msgs = len(inbox_data)
    
    pie_chart_img = generate_pie_chart(classifications)
    
    table_rows = []
    for idx, data in enumerate(inbox_data.values()):
        bg_color = "#f9f9f9" if idx % 2 == 0 else "#ffffff"
        from_style = "color: #e91e63;" if data['from_injection'] else ""
        rp_style = "color: #e91e63;" if data['return_path_injection'] else ""
        subj_style = "color: #e91e63;" if data['subject_injection'] else ""
        table_rows.append(f"""
            <tr style="background-color: {bg_color};">
                <td style="font-size: 12px;">From:</td>
                <td style="font-size: 12px; {from_style}">{truncate_text(data['from'])}</td>
            </tr>
            <tr style="background-color: {bg_color};">
                <td style="font-size: 12px;">Return-Path:</td>
                <td style="font-size: 12px; {rp_style}">{truncate_text(data['return_path'])}</td>
            </tr>
            <tr style="background-color: {bg_color}; border-bottom: 2px solid #1a73e8;">
                <td style="font-size: 12px;">Subject:<br>Date:<br>Class:</td>
                <td style="font-size: 12px;">
                    <span style="{subj_style}">{truncate_text(data['subject'])}</span><br>
                    {truncate_text(data['date'], 30)}<br>
                    {data['classification']}
                </td>
            </tr>
        """)
    table_html = f"""
        <table>
            {''.join(table_rows)}
        </table>
    """
    
    sender_text = ", ".join(f"<b style='color: #d81b60;'>{sender}</b> ({count})" for sender, count in sender_counts)
    
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: 'Roboto', Arial, sans-serif; color: #333; margin: 0; padding: 20px; background-color: #f5f5f5; }}
            .container {{ max-width: 600px; margin: auto; background: #fff; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); padding: 20px; }}
            h1 {{ color: #1a73e8; font-size: 28px; margin-bottom: 10px; border-bottom: 2px solid #1a73e8; padding-bottom: 5px; }}
            h2 {{ color: #444; font-size: 22px; margin-top: 20px; }}
            p {{ line-height: 1.6; font-size: 16px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            td {{ border: 1px solid #ddd; padding: 5px; text-align: left; vertical-align: top; }}
            img {{ max-width: 100%; height: auto; margin: 20px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>INBOX Folder Summary</h1>
            <p>This report summarizes your INBOX as of {timestamp}, capturing messages awaiting processing. Covering the period from {date_range_start} to {date_range_end}, our system analyzed <b style='color: #d81b60;'>{total_msgs}</b> messages. Of these, <b style='color: #d81b60;'>{class_counts.get('Recent', 0)}</b> are recent arrivals (received within the last 24 hours), <b style='color: #d81b60;'>{class_counts.get('Pending', 0)}</b> are pending processing (older than 24 hours), and <b style='color: #d81b60;'>{class_counts.get('Other', 0)}</b> fall into an miscellaneous category. We detected <b style='color: #d81b60;'>{discrepancies}</b> messages with 'From' and 'Return-Path' mismatches, which may suggest delivery anomalies, and <b style='color: #d81b60;'>{injections}</b> potential code injections, indicating security risks. Frequent senders include {sender_text}, spotlighting key sources in your incoming mail.</p>
            
            <h2>INBOX Classification Breakdown</h2>
            <img src="data:image/png;base64,{pie_chart_img}" alt="Inbox Classifications Pie Chart">
            
            <h2>INBOX Messages</h2>
            {table_html}
        </div>
    </body>
    </html>
    """
    
    msg = MIMEText(html_content, 'html')
    msg['From'] = USERNAME
    msg['To'] = USERNAME
    msg['Subject'] = subject
    msg['List-ID'] = "InboxSummary"
    msg['Date'] = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')
    
    mail.select(DRAFTS_FOLDER)
    status, _ = mail.append(
        DRAFTS_FOLDER,
        None,
        imaplib.Time2Internaldate(time.time()),
        msg.as_bytes()
    )
    if status == "OK":
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [success]Draft created in {DRAFTS_FOLDER} with subject: {subject}[/success]")
    else:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Failed to create draft in {DRAFTS_FOLDER}[/warning]")

def process_inbox_folder():
    global stop_processing
    mail = connect_to_imap()
    
    mail.select(INBOX_FOLDER)
    status, messages = mail.search(None, 'ALL')
    if status != "OK" or not messages[0]:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Failed to search {INBOX_FOLDER}[/warning]")
        mail.logout()
        return
    total_msgs = len(messages[0].split())
    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Found {total_msgs} messages in {INBOX_FOLDER}[/info]")

    if total_msgs == 0:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]No messages in {INBOX_FOLDER}, skipping summary[/info]")
        mail.logout()
        return

    all_inbox_data = {}
    batch_start = 1
    while batch_start <= total_msgs and not stop_processing:
        batch_end = min(batch_start + BATCH_SIZE - 1, total_msgs)
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [highlight]Scanning batch {batch_start}-{batch_end} of {total_msgs}[/highlight]")
        
        batch_data = get_message_signatures_and_headers(mail, INBOX_FOLDER, start=batch_start, end=batch_end)
        all_inbox_data.update(batch_data)
        
        batch_start += BATCH_SIZE

    if stop_processing:
        console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [warning]Processing aborted by user[/warning]")
        mail.logout()
        return

    create_draft_summary(mail, all_inbox_data)
    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [success]Processing complete[/success]")
    mail.logout()

if __name__ == "__main__":
    console.print(f"[grey50][{get_utc_timestamp()}][/grey50] [info]Starting inbox summary script...[/info]")
    process_inbox_folder()
