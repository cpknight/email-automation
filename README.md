# Email Automation System

## Overview
This project is a suite of Python and Bash scripts designed to automate email management for a Proton Mail account via the Proton Mail Bridge. It processes, classifies, summarizes, and archives emails across various folders, running continuously as a systemd service to streamline email handling for the user, cpknight.

The system operates in a pipeline:
1. **Processing**: New emails in `INBOX` are moved to `Folders/Processing` after 24 hours.
2. **Classification**: Emails in `Folders/Processing` are sorted hourly into `Folders/Notifications` or `Folders/Correspondence`.
3. **Archiving**: Older emails from `Folders/Notifications`, `Spam`, `Folders/Correspondence`, and `Sent` are archived or trashed daily.
4. **Summarizing**: Daily reports for `INBOX` and `Spam` provide insights into email activity.

The wrapper script `email_automation.sh` orchestrates this via a systemd service, ensuring single-instance execution and persistent scheduling.

## User Workflow
As cpknight, your workflow leverages this automation to keep your email organized with minimal manual effort:
- **Daily Use**: Check `INBOX` for recent emails (<24 hours old) to handle manually; older emails are auto-processed. Review daily summary drafts in `Drafts` for insights, and trust archiving to keep `Sent`, `Spam`, and other folders tidy.
- **Management**: Start/stop the system with `install-email-automation.sh` or `uninstall-email-automation.sh`, or run `email_automation.sh` manually to test; rely on journald logs (`journalctl -u email-automation`) for debugging when running as a service.

## Scripts

- **`email_processor.py`**
  - Moves emails from `INBOX` to `Folders/Processing` every 15 minutes if they’re older than 24 hours, leaving newer ones for manual review.
  - Main rule: Only emails >24 hours old are processed, ensuring recent messages remain in `INBOX`.

- **`email_classifier.py`**
  - Runs hourly to classify emails in `Folders/Processing` into `Folders/Notifications` or `Folders/Correspondence` based on sender, recipient, and content analysis.
  - Main rule: Messages are `Correspondence` if sender matches signature and either recipient is addressed or subject matter is clear (e.g., request/response); otherwise, they’re `Notifications`.

- **`email_archive_notifications.py`**
  - Archives emails in `Folders/Notifications` older than 7 days to `Folders/Archive` daily.
  - Main rule: Messages >7 days old are moved to `Folders/Archive` to keep the folder current.

- **`email_archive_spam.py`**
  - Moves emails in `Spam` older than 7 days to `Trash` daily for eventual deletion.
  - Main rule: Spam >7 days old is trashed, clearing out junk without archiving.

- **`email_archive_correspondence.py`**
  - Archives emails in `Folders/Correspondence` older than 7 days to `Folders/Archive` daily.
  - Main rule: Correspondence >7 days old is preserved in `Folders/Archive` for long-term storage.

- **`email_archive_sent.py`**
  - Archives emails in `Sent` older than 48 hours to `Folders/Archive` daily.
  - Main rule: Sent messages >48 hours old are moved to `Folders/Archive` to maintain a lean `Sent` folder.

- **`email_summary_inbox.py`**
  - Generates a daily HTML summary of `INBOX` as a draft in `Drafts`, classifying emails as "Recent" (<24 hours) or "Pending" (>24 hours).
  - Main rule: Summarizes all `INBOX` emails, highlighting recent arrivals vs. those awaiting processing.

- **`email_summary_spam.py`**
  - Creates a daily HTML summary of `Spam` as a draft in `Drafts`, analyzing sender patterns and potential threats.
  - Main rule: Summarizes all `Spam` emails, focusing on volume and security indicators like code injections.

- **`email_automation.sh`**
  - Bash wrapper script that runs all Python scripts on a schedule (processor every 15 minutes, classifier hourly, archives then summaries daily) while enforcing single-instance execution.
  - Main rule: Ensures continuous automation with persistent state, running archives before summaries daily.

- **`email-automation.service`**
  - Systemd service file to run `email_automation.sh` as user `cpknight` on system boot.
  - Main rule: Executes the wrapper script continuously, restarting on failure.

- **`install-email-automation.sh`**
  - Installs and starts the `email-automation` service by copying the service file to `/etc/systemd/system` and enabling it.
  - Main rule: Sets up the service to run automatically as `cpknight`.

- **`uninstall-email-automation.sh`**
  - Stops and removes the `email-automation` service, cleaning up systemd configuration.
  - Main rule: Disables and deletes the service when automation is no longer needed.

## Dependencies
- **Python 3**: Core runtime for all Python scripts (`sudo apt install python3`).
- **Python Libraries**: 
  - `imaplib` (standard library) for IMAP interactions.
  - `email` (standard library) for email parsing.
  - `hashlib` (standard library) for signature generation.
  - `matplotlib` for pie charts (`pip3 install matplotlib`).
  - `rich` for console output (`pip3 install rich`).
- **Proton Mail Bridge**: Required for IMAP access to Proton Mail (`127.0.0.1:1143`).
- **Systemd**: For service management (standard on most Linux distros).
- **Bash**: For the wrapper and install/uninstall scripts (standard on Linux).

Install Python dependencies with:
```bash
pip3 install matplotlib rich
```

## Setup
Follow these steps to get the email automation system running on your Linux machine (tested with Proton Mail Bridge):

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/cpknight/email-automation.git
   cd email-automation
   ```

2. **Install Dependencies**:
   - Ensure Python 3 is installed: ^sudo apt install python3^.
   - Install required Python libraries:
     ```bash
     pip3 install matplotlib rich
     ```
   - Install and configure Proton Mail Bridge (see [Proton Mail Bridge documentation](https://proton.me/support/protonmail-bridge)) to enable IMAP access on `127.0.0.1:1143`.

3. **Configure the System**:
   - Copy the example configuration file and rename it:
     ```bash
     cp example.config.ini config.ini
     ```
   - Edit `config.ini` with your text editor (e.g., `nano config.ini`):
     - Replace `your_email@example.com` and `your_password_here` with your Proton Mail Bridge IMAP credentials.
     - Adjust folder names (e.g., `INBOX`, `Spam`, `Drafts`) if your email provider uses different labels.
   - Ensure folder paths match your IMAP setup (e.g., `Folders/Processing` for nested folders).

4. **Test Manually (Optional)**:
   - Make the wrapper script executable:
     ```bash
     chmod +x email_automation.sh
     ```
   - Run it to verify functionality:
     ```bash
     ./email_automation.sh
     ```
   - Check console output for script execution; Ctrl+C to stop.

5. **Install as a Systemd Service**:
   - Make install/uninstall scripts executable:
     ```bash
     chmod +x install-email-automation.sh uninstall-email-automation.sh
     ```
   - Install and start the service:
     ```bash
     ./install-email-automation.sh
     ```
   - Verify it’s running:
     ```bash
     systemctl status email-automation
     ```
   - Logs are available via ^journalctl -u email-automation^.

6. **Uninstall (If Needed)**:
   - Stop and remove the service:
     ```bash
     ./uninstall-email-automation.sh
     ```

**Notes**:
- Ensure Proton Mail Bridge is running before starting the service.
- Adjust `batch_size` in `config.ini` if processing large email volumes (default is 100).


## Credits

Credits

This is an example of an AI-generated project. I built this with Grok (v3 Beta).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


