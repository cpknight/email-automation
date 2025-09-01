#!/usr/bin/env python3
"""
Email Bulk Archive Recovery Utility
===================================

This utility helps with recovery operations for the bulk archive script.
It can display transaction logs, retry failed operations, and provide
recovery information.

Features:
- View transaction and recovery logs
- Retry failed operations
- Clear transaction logs for fresh start
- Display detailed recovery statistics

Author: Companion to email_bulk_archive.py
"""

import json
import os
import sys
from rich.console import Console
from rich.theme import Theme
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Confirm, Prompt
from datetime import datetime

# Enhanced color theme
custom_theme = Theme({
    "info": "blue", 
    "success": "green", 
    "warning": "yellow", 
    "error": "red", 
    "highlight": "cyan",
    "recovery": "bright_yellow"
})

console = Console(theme=custom_theme)

TRANSACTION_LOG = "archive_transaction_log.json"
RECOVERY_LOG = "archive_recovery_log.json"

def load_json_file(filename):
    """Load JSON file with error handling"""
    if not os.path.exists(filename):
        return None
    
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except Exception as e:
        console.print(f"[error]Error loading {filename}: {e}[/error]")
        return None

def display_transaction_log():
    """Display current transaction log status"""
    data = load_json_file(TRANSACTION_LOG)
    if not data:
        console.print(f"[warning]No transaction log found at {TRANSACTION_LOG}[/warning]")
        return
    
    console.print(Panel.fit(
        f"[highlight]Transaction Log Status[/highlight]\n\n"
        f"📅 Session Started: {data.get('session_start', 'Unknown')}\n"
        f"✅ Successfully Processed: {len(data.get('processed_signatures', []))}\n"
        f"❌ Failed Operations: {len(data.get('failed_operations', []))}\n"
        f"📝 Log File: {TRANSACTION_LOG}",
        title="📊 Current Status",
        title_align="center",
        style="blue"
    ))
    
    # Show failed operations if any
    failed_ops = data.get('failed_operations', [])
    if failed_ops:
        console.print(f"\n[warning]Failed Operations ({len(failed_ops)}):[/warning]")
        table = Table()
        table.add_column("Message ID", style="cyan")
        table.add_column("UID", style="blue")
        table.add_column("Source Folder", style="yellow")
        table.add_column("Timestamp", style="green")
        table.add_column("Error", style="red")
        
        for op in failed_ops[-10]:  # Show last 10 failures
            table.add_row(
                op.get('msg_id', 'Unknown'),
                op.get('uid', 'Unknown'),
                op.get('source_folder', 'Unknown'),
                op.get('timestamp', 'Unknown'),
                op.get('error', 'Unknown')[:50] + "..." if len(op.get('error', '')) > 50 else op.get('error', 'Unknown')
            )
        
        console.print(table)
        if len(failed_ops) > 10:
            console.print(f"[info]... and {len(failed_ops) - 10} more failed operations[/info]")

def display_recovery_log():
    """Display recovery log information"""
    data = load_json_file(RECOVERY_LOG)
    if not data:
        console.print(f"[warning]No recovery log found at {RECOVERY_LOG}[/warning]")
        return
    
    console.print(Panel.fit(
        f"[highlight]Recovery Log Information[/highlight]\n\n"
        f"🏁 Completion Time: {data.get('completion_time', 'Unknown')}\n"
        f"📊 Total Processed: {data.get('total_processed', 0)}\n"
        f"❌ Total Failed: {data.get('total_failed', 0)}\n"
        f"⚠️  Was Interrupted: {'Yes' if data.get('interrupted', False) else 'No'}",
        title="🔄 Recovery Information",
        title_align="center",
        style="recovery"
    ))
    
    # Show folder statistics
    folder_stats = data.get('folder_stats', {})
    if folder_stats:
        console.print(f"\n[highlight]Folder Statistics:[/highlight]")
        table = Table()
        table.add_column("Folder", style="cyan")
        table.add_column("Found", justify="right", style="blue")
        table.add_column("Moved", justify="right", style="green")
        table.add_column("Failed", justify="right", style="red")
        table.add_column("Success Rate", justify="right", style="yellow")
        
        for folder, stats in folder_stats.items():
            found = stats.get('found', 0)
            moved = stats.get('moved', 0)
            failed = stats.get('failed', 0)
            success_rate = f"{(moved / found * 100):.1f}%" if found > 0 else "N/A"
            
            table.add_row(
                folder.split('/')[-1],
                str(found),
                str(moved),
                str(failed),
                success_rate
            )
        
        console.print(table)

def clear_logs():
    """Clear transaction and recovery logs"""
    files_to_clear = []
    
    if os.path.exists(TRANSACTION_LOG):
        files_to_clear.append(TRANSACTION_LOG)
    
    if os.path.exists(RECOVERY_LOG):
        files_to_clear.append(RECOVERY_LOG)
    
    if not files_to_clear:
        console.print("[info]No log files found to clear[/info]")
        return
    
    console.print(f"[warning]The following files will be deleted:[/warning]")
    for file in files_to_clear:
        console.print(f"  • {file}")
    
    if Confirm.ask("\n[warning]Are you sure you want to clear all logs?[/warning]", default=False):
        for file in files_to_clear:
            try:
                os.remove(file)
                console.print(f"[success]Deleted {file}[/success]")
            except Exception as e:
                console.print(f"[error]Failed to delete {file}: {e}[/error]")
        
        console.print(f"\n[success]Log cleanup complete![/success]")
    else:
        console.print("[info]Operation cancelled[/info]")

def show_help():
    """Display help information"""
    console.print(Panel.fit(
        "[bold highlight]Email Bulk Archive Recovery Utility[/bold highlight]\n\n"
        "[cyan]Available Commands:[/cyan]\n"
        "  [yellow]status[/yellow]     - Show current transaction log status\n"
        "  [yellow]recovery[/yellow]   - Show recovery log information  \n"
        "  [yellow]clear[/yellow]      - Clear all transaction and recovery logs\n"
        "  [yellow]help[/yellow]       - Show this help message\n"
        "  [yellow]quit[/yellow]       - Exit the utility\n\n"
        "[cyan]Recovery Process:[/cyan]\n"
        "1. Run this utility to check the status of previous operations\n"
        "2. If there are failed operations, you can clear logs and retry\n"
        "3. The main archive script will automatically resume from where it left off\n\n"
        "[cyan]Files:[/cyan]\n"
        f"  📝 Transaction Log: {TRANSACTION_LOG}\n"
        f"  🔄 Recovery Log: {RECOVERY_LOG}",
        title="📚 Help",
        title_align="center",
        style="blue"
    ))

def main():
    """Main interactive recovery utility"""
    console.print(Panel.fit(
        "[bold recovery]📧 Email Bulk Archive Recovery Utility[/bold recovery]\n\n"
        "This utility helps you manage and recover from bulk archive operations.\n"
        "Type 'help' for available commands or 'quit' to exit.",
        title="🛠️ Recovery Utility",
        title_align="center",
        style="cyan"
    ))
    
    while True:
        try:
            command = Prompt.ask("\n[highlight]Recovery>[/highlight]", default="help").lower().strip()
            
            if command in ['quit', 'exit', 'q']:
                console.print("[success]Goodbye![/success]")
                break
            elif command in ['help', 'h']:
                show_help()
            elif command in ['status', 's']:
                display_transaction_log()
            elif command in ['recovery', 'r']:
                display_recovery_log()
            elif command in ['clear', 'c']:
                clear_logs()
            else:
                console.print(f"[error]Unknown command: {command}[/error]")
                console.print("[info]Type 'help' for available commands[/info]")
                
        except KeyboardInterrupt:
            console.print("\n[warning]Interrupted by user[/warning]")
            break
        except Exception as e:
            console.print(f"[error]Error: {e}[/error]")

if __name__ == "__main__":
    main()
