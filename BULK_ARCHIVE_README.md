# 📦 Email Bulk Archive Scripts

This directory contains two new scripts derived from your existing email automation system for bulk archiving operations.

## 🚀 Scripts Overview

### `email_bulk_archive.py` - Main Archiving Script
The primary script that moves all messages from the "Processing", "Correspondence", and "Notifications" folders to the "Archive" folder.

### `email_bulk_archive_recovery.py` - Recovery Utility
A companion utility for managing recovery operations and viewing transaction logs.

## ✨ Key Features

- **📊 Batch Processing**: Processes messages in batches of 100 as requested
- **🎨 Colorful Progress Bars**: Rich visual feedback with colorful progress indicators
- **🛡️ Robust Recovery Mechanism**: Transaction logging with automatic resume capability
- **🔄 Duplicate Prevention**: Prevents re-archiving of messages already in the archive
- **⚠️ Graceful Interruption**: Handle Ctrl+C gracefully, saving progress
- **📝 Comprehensive Logging**: Detailed transaction and recovery logs
- **🔁 Retry Logic**: Multiple retry attempts for failed operations
- **📈 Summary Statistics**: Beautiful summary tables with success rates
- **🏷️ Flag Management**: Marks messages as read and removes flags before archiving
- **✅ State Consistency**: Ensures all archived messages have consistent flag states

## 🏃‍♂️ Quick Start

### Running the Bulk Archive
```bash
# Navigate to the project directory
cd /home/cpknight/Projects/email-automation

# Run the bulk archive script
python3 ./email_bulk_archive.py
```

### Using the Recovery Utility
```bash
# Run the recovery utility
python3 ./email_bulk_archive_recovery.py

# Available commands in the utility:
# - status: Show current transaction log status  
# - recovery: Show recovery log information
# - clear: Clear all logs for a fresh start
# - help: Show help information
# - quit: Exit the utility
```

## 📁 Source and Destination Folders

The script automatically reads from your `config.ini` and processes:

**Source Folders:**
- `Folders/Processing` (from processor.dest_folder)
- `Folders/Correspondence` (from classifier.dest_folder_correspondence)  
- `Folders/Notifications` (from classifier.dest_folder_notifications)

**Destination Folder:**
- `Archive` (from archive_notifications.dest_folder)

## 🛡️ Recovery Mechanism

### Transaction Logging
- **File**: `archive_transaction_log.json`
- **Purpose**: Tracks all processed messages and failed operations
- **Resumability**: Script automatically resumes from where it left off

### Recovery Logging  
- **File**: `archive_recovery_log.json`
- **Purpose**: Stores completion statistics and operation summary
- **Use Case**: Post-operation analysis and reporting

### Recovery Process
1. If the script is interrupted (Ctrl+C), it saves current progress
2. Next run automatically detects and loads previous progress
3. Already processed messages are skipped
4. Use the recovery utility to check status and manage logs

## 🏷️ Flag Management

The script automatically manages message flags during the archiving process:

### Automatic Flag Updates
- **Mark as Read**: All messages are marked as read (\Seen flag) before archiving
- **Remove Flags**: Any flagged status (\Flagged) is removed before archiving
- **Consistent State**: Ensures all archived messages have uniform flag states
- **No Manual Action**: Flag management is completely automatic

### Flag Processing Order
1. **Update Flags**: Mark as read and remove flagged status
2. **Brief Delay**: Allow server to process flag changes
3. **Copy Message**: Copy to Archive folder with updated flags
4. **Verify Copy**: Ensure message was successfully copied
5. **Delete Original**: Mark original message for deletion

## 🎨 Progress Visualization

The script features rich, colorful progress indicators:

- **🔍 Scanning Phase**: Analyzes messages in each folder
- **📦 Archiving Phase**: Moves messages with real-time progress
- **📊 Batch Progress**: Shows current batch progress (X/100)
- **⏱️ Time Tracking**: Displays elapsed time for operations
- **📈 Summary Tables**: Beautiful final summary with statistics

## ⚙️ Configuration

The script uses your existing `config.ini` file and automatically detects:
- IMAP server settings
- Source folder mappings  
- Archive destination folder
- Batch size is fixed at 100 messages as requested

## 🚨 Error Handling

### Retry Logic
- **3 retry attempts** for each failed message
- **5-second delays** between retry attempts
- **Copy verification** before deleting original messages
- **Comprehensive error logging** with timestamps

### Failure Recovery
- Failed operations are logged with full details
- Messages are never lost due to verification steps
- Transaction log enables surgical retry of failed operations
- Recovery utility provides detailed failure analysis

## 📊 Example Output

```
🚀 Starting Operation
┌─────────────────────────────────────────────────┐
│ 📦 Multi-Folder Email Bulk Archiver            │
│                                                 │
│ Source Folders: Processing, Correspondence, ... │
│ Destination: Archive                            │
│ Batch Size: 100 messages                       │
│ Recovery Log: archive_transaction_log.json     │
└─────────────────────────────────────────────────┘

📧 Bulk Archive Operation Summary
┌─────────────────┬────────────────┬──────────────────┬────────┬──────────────┐
│ Source Folder   │ Messages Found │ Successfully ... │ Failed │ Success Rate │
├─────────────────┼────────────────┼──────────────────┼────────┼──────────────┤
│ Processing      │ 150            │ 148              │ 2      │ 98.7%        │
│ Correspondence  │ 89             │ 89               │ 0      │ 100.0%       │
│ Notifications   │ 234            │ 231              │ 3      │ 98.7%        │
├─────────────────┼────────────────┼──────────────────┼────────┼──────────────┤
│ TOTAL           │ 473            │ 468              │ 5      │ 98.9%        │
└─────────────────┴────────────────┴──────────────────┴────────┴──────────────┘
```

## 🔧 Advanced Usage

### Interrupted Operations
If the script is interrupted:
1. It will display a graceful shutdown message
2. Progress is automatically saved
3. Re-run the script to continue from where it left off

### Fresh Start
To start completely fresh:
```bash
# Use the recovery utility
python3 ./email_bulk_archive_recovery.py
# Type 'clear' to remove all logs
# Then run the main script again
```

### Monitoring Progress
The recovery utility can be used in a separate terminal to monitor progress:
```bash
python3 ./email_bulk_archive_recovery.py
# Type 'status' to see current progress
```

## 🔍 Troubleshooting

### Common Issues

1. **Connection Errors**: Check your IMAP settings in `config.ini`
2. **Permission Errors**: Ensure the script has write access for log files
3. **Memory Issues**: The script processes in small batches to minimize memory usage
4. **Duplicate Messages**: The script automatically detects and skips duplicates

### Log Files Location
- Transaction Log: `./archive_transaction_log.json`
- Recovery Log: `./archive_recovery_log.json` 
- Both files are in the same directory as the scripts

## 🤝 Integration

The scripts follow the same patterns as your existing email automation scripts:
- Same error handling approach
- Same configuration file usage
- Same logging and progress reporting style
- Same IMAP connection and retry logic

## 📝 Dependencies

The scripts require the same dependencies as your existing scripts:
- `rich` - For colorful console output and progress bars
- `imaplib` - Built-in Python IMAP library
- `configparser` - Built-in Python configuration parser
- `email` - Built-in Python email parsing

## 🎯 Performance Considerations

- **Batch Size**: Fixed at 100 messages for optimal performance
- **Memory Usage**: Minimal memory footprint through streaming processing
- **Network Efficiency**: Optimized IMAP commands and connection reuse
- **Duplicate Checking**: Efficient signature-based duplicate detection
- **Progress Saving**: Frequent progress saves for interruption safety

---

**Note**: These scripts are designed to work with your existing email automation setup and follow the same patterns and conventions as your current scripts.
