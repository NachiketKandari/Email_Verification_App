# README

## Overview
The **Email Verification App** is a Streamlit-based web application designed to validate email addresses using SMTP checks. It provides two modes of operation:

1. **Single Verification**: Verify a single email address.
2. **Batch Verification**: Verify multiple email addresses from an uploaded Excel file.

In batch mode, the application displays a progress bar, calculates estimated completion time, and allows for partial results to be saved and downloaded in case of interruptions.

## Features
- **Single Verification**:
  - Input a single email address.
  - Checks the email against default SMTP servers and domain-specific MX records.
  - Displays whether the email is verified or not.

- **Batch Verification**:
  - Upload an Excel file containing a column named "Email".
  - Specify start and end rows to limit the range of emails to verify.
  - Customize the output file name.
  - Shows real-time progress updates, including elapsed time and estimated completion time.
  - Periodically saves partial results every 10 records processed, enabling partial recovery if the process is interrupted.
  - Offers downloadable Excel files for both verified and unverified emails once processing is complete or interrupted.

## How It Works
1. **Email Verification Logic**:
   - Extracts domain from the email.
   - Retrieves MX records for the domain via DNS lookups.
   - Attempts verification first against default Gmail SMTP servers. If unsuccessful, tries domain-specific MX servers.
   - Verification attempts include handling temporary and timeout errors by retrying after exponential backoff intervals.

2. **Batch Processing**:
   - Utilizes Python's `concurrent.futures.ThreadPoolExecutor` for parallel processing of multiple emails.
   - Tracks progress using a progress bar and dynamically updated status text.
   - Saves partial results periodically to prevent data loss.

3. **Session State**:
   - Uses Streamlit's session state to manage intermediate data (verified/unverified emails), progress indicators, and mode switches.
   - Allows clean restarts and interrupts to the verification process.

## Requirements
- Python 3.7+
- Packages:
  - `streamlit`
  - `pandas`
  - `dns.resolver` (from `dnspython`)
  - `openpyxl` (for reading/writing Excel files)
  
Install the required packages with:
```bash
pip install streamlit pandas dnspython openpyxl
```

## Running the App
Run the following command in your terminal:
```bash
streamlit run app.py
```
Replace `app.py` with the filename of the script if different.

## Usage
- Select a mode from the radio button: **Single Verification** or **Batch Verification**.
- In **Single Verification**:
  - Enter an email address and click "Check".
  - Results will be displayed on the screen.
  
- In **Batch Verification**:
  - Upload an Excel file containing a column named "Email".
  - Specify `Start Row` and `End Row` to define the verification range.
  - (Optional) Enter a custom file name prefix.
  - Click "Start Verification" to begin.
  - Monitor the progress bar and status updates.
  - Download the verified and unverified results once done or after an interruption.
  
## Notes
- If the verification process is interrupted or encounters an error, partial results (verified/unverified emails) can be downloaded.
- The app tries to handle temporary SMTP errors by retrying connections.
- Valid emails are marked as "250" status, while invalid or undeliverable emails have associated error codes and messages.

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
