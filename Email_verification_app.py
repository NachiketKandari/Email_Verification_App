import pandas as pd
import socket
import time
import logging
import dns.resolver
from datetime import datetime
import concurrent.futures
import streamlit as st
import os
from datetime import timedelta

st.set_page_config(
    page_title="Email Verification App",
    page_icon="android-chrome-512x512.png",  # This sets the favicon 
)

# Function to delete the uploaded file
def delete_file(file_path):
    if os.path.exists(file_path):
        os.remove(file_path)

# Streamlit UI components
st.title('Email Verification App')

uploaded_file = st.file_uploader('Choose an Excel file', type='xlsx', accept_multiple_files=False)
start_row = st.number_input('Start Row', min_value=1, value=1)
end_row = st.number_input('End Row', min_value=1, value=20000)

save_in_same_folder = st.checkbox('Save in the same folder as the uploaded file')
if not save_in_same_folder:
    save_folder = st.text_input('Choose Save Folder', '')

custom_name = st.text_input('Enter custom file name (optional)', '')

if st.button('Start Verification'):
    if uploaded_file and (save_in_same_folder or save_folder):
        verified_count = 0
        unverified_count = 0
        start_time = datetime.now()

        # Clear progress file at the start
        with open('progress.txt', 'w') as f:
            f.write('')

        default_smtp_servers = [
            'alt4.gmail-smtp-in.l.google.com',
            'gmail-smtp-in.l.google.com'
        ]

        logging.basicConfig(filename='email_verification.log', level=logging.INFO, 
                            format='%(asctime)s %(levelname)s:%(message)s')

        email_no = start_row

        start_index = start_row - 1
        df = pd.read_excel(uploaded_file)
        end_index = min(end_row, len(df))

        df = df.iloc[start_index:end_index]
        emails = df['Email']

        error_messages = {
            "250": "Requested mail action okay, completed",
            "450": "Requested mail action not taken: mailbox unavailable (e.g., mailbox busy)",
            "451": "Requested action aborted: local error in processing",
            "452": "Requested action not taken: insufficient system storage",
            "421": "Service not available, closing transmission channel",
            "550": "Requested action not taken: mailbox unavailable (e.g., mailbox not found, no access)",
            "551": "User not local; please try <forward-path>",
            "552": "Requested mail action aborted: exceeded storage allocation",
            "553": "Requested action not taken: mailbox name not allowed",
            "554": "Transaction failed",
            "Timeout": "Timeout while verifying email",
            "Exception": "Exception occurred during verification"
        }

        def verify_email(email, smtp_server, attempt=1, max_attempts=3):
            port = 25
            sender_email = 'abc@gmail.com'
            try:
                server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server.connect((smtp_server, port))
                server.settimeout(10)
                server.recv(1024)
                server.sendall(b"HELO gmail.com\r\n")
                helo_response = server.recv(1024).decode('ascii')
                if '250' not in helo_response:
                    server.close()
                    return False, "Exception"
                server.sendall(f"MAIL FROM:<{sender_email}>\r\n".encode('ascii'))
                mail_from_response = server.recv(1024).decode('ascii')
                if '250' not in mail_from_response:
                    server.close()
                    return False, "Exception"
                server.sendall(f"RCPT TO:<{email}>\r\n".encode('ascii'))
                rcpt_to_response = server.recv(1024).decode('ascii')
                server.sendall(b"QUIT\r\n")
                server.close()
                if '250' in rcpt_to_response:
                    return True, "250"
                elif '450' in rcpt_to_response and attempt < max_attempts:
                    wait_time = 2 ** attempt
                    logging.info(f"Temporary error (450). Retrying in {wait_time} seconds for email {email}")
                    time.sleep(wait_time)
                    return verify_email(email, smtp_server, attempt + 1, max_attempts)
                elif attempt < max_attempts:
                    wait_time = 2 ** attempt
                    logging.info(f"Timeout error. Retrying in {wait_time} seconds for email {email}")
                    time.sleep(wait_time)
                    return verify_email(email, smtp_server, attempt + 1, max_attempts)
                else:
                    error_code = 'Exception'
                    return False, error_code
            except Exception as e:
                logging.error(f"Exception occurred while verifying email {email}: {e}")
                return False, "Exception"

        def extract_domain(email):
            if isinstance(email, str) and '@' in email:
                return email.split('@')[-1]
            else:
                return None

        def get_mx_records(domain):
            try:
                answers = dns.resolver.resolve(domain, 'MX')
                return [rdata.exchange.to_text() for rdata in answers]
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
                return []

        def process_email(index, email, last_successful_server_index, mx_cache):
            try:
                domain = extract_domain(email)
                if domain is None:
                    logging.info(f"Invalid email format: {email}. Skipping email.")
                    return index, email, "Invalid Email", "Email is not a string or missing '@'"

                if domain not in mx_cache:
                    mx_cache[domain] = get_mx_records(domain)

                mx_records = mx_cache[domain]
                if not mx_records:
                    logging.info(f"Domain {domain} has no valid MX records. Skipping email {email}")
                    return index, email, "Invalid Domain", "Domain has no valid MX records"

                for server_index, smtp_server in enumerate(default_smtp_servers):
                    is_verified, error_code = verify_email(email, smtp_server)
                    if is_verified:
                        last_successful_server_index[domain] = server_index
                        return index, email, "250", "Verified"
                    elif error_code in ['550', '551', '553', '554']:
                        break

                smtp_servers = mx_records
                server_index = last_successful_server_index.get(domain, 0)
                start_index = server_index
                while True:
                    is_verified, error_code = verify_email(email, smtp_servers[server_index])
                    if is_verified:
                        last_successful_server_index[domain] = server_index
                        return index, email, "250", "Verified"
                    elif error_code not in ['550', '551', '553', '554']:
                        server_index = (server_index + 1) % len(smtp_servers)
                        if server_index == start_index:
                            break
                    else:
                        break

                return index, email, error_code, error_messages.get(error_code, "Unknown error")
            except Exception as e:
                logging.error(f"Unexpected error at index {index} for email {email}: {e}")
                return index, email, "Exception", "Unexpected error"

        verified_rows = []
        unverified_rows = []
        last_successful_server_index = {}
        mx_cache = {}
        progress_start_index = 0
        try:
            with open('progress.txt', 'r') as f:
                content = f.read().strip()
                if content:
                    progress_start_index = int(content)
        except FileNotFoundError:
            pass

        progress_bar = st.progress(0)
        progress_text = st.empty()

        total_emails = end_index - start_row + 1  # Calculate the total emails to be processed
        processed_count = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(process_email, index, row['Email'], last_successful_server_index, mx_cache): (index, row) for index, row in df.iterrows()}

            for future in concurrent.futures.as_completed(futures):
                index, row = futures[future]
                try:
                    result = future.result()
                    idx, email, error_code, error_message = result
                    row['Error Code'] = error_code
                    row['Error Message'] = error_message
                    processed_count += 1
                    # Calculate elapsed time and estimated time to completion
                    time_elapsed = (datetime.now() - start_time).total_seconds()
                    time_per_email = time_elapsed / processed_count
                    emails_left = total_emails - processed_count
                    time_left = time_per_email * emails_left
                    time_left_str = str(timedelta(seconds=time_left)).split(".")[0]  # Format to H:M:S

                    progress_text.text(f"Email No: {processed_count} of {total_emails} | Verified: {verified_count} | Unverified: {unverified_count} \nTime Elapsed: {time_elapsed.__round__(2)} seconds | Time to completion: {time_left_str}")
                    progress_bar.progress(processed_count / total_emails)

                    if error_code == "250":
                        verified_rows.append(row)
                        verified_count += 1
                    else:
                        unverified_rows.append(row)
                        unverified_count += 1

                    if processed_count % 10 == 0:
                        with open('progress.txt', 'w') as f:
                            f.write(str(index))
                        verified_df = pd.DataFrame(verified_rows, columns=df.columns)
                        unverified_df = pd.DataFrame(unverified_rows, columns=df.columns.tolist() + ['Error Code', 'Error Message'])
                        if save_in_same_folder:
                            folder = os.path.dirname(uploaded_file.name)
                        else:
                            folder = save_folder
                        verified_df.to_excel(os.path.join(folder, f"{custom_name if custom_name else 'data'}_verified.xlsx"), index=False)
                        unverified_df.to_excel(os.path.join(folder, f"{custom_name if custom_name else 'data'}_unverified.xlsx"), index=False)

                except Exception as e:
                    logging.error(f"Exception in future for index {index}: {e}")

        verified_df = pd.DataFrame(verified_rows, columns=df.columns)
        unverified_df = pd.DataFrame(unverified_rows, columns=df.columns.tolist() + ['Error Code', 'Error Message'])
        if save_in_same_folder:
            folder = os.path.dirname(uploaded_file.name)
        else:
            folder = save_folder
        verified_df.to_excel(os.path.join(folder, f"{custom_name if custom_name else 'data'}_verified.xlsx"), index=False)
        unverified_df.to_excel(os.path.join(folder, f"{custom_name if custom_name else 'data'}_unverified.xlsx"), index=False)

        # Delete the uploaded file after processing
        delete_file(uploaded_file.name)

        with open('progress.txt', 'w') as f:
            f.write('')

        st.success(f"Email verification completed. \n| Verified : {verified_count} |\nUnverified : {unverified_count} |")
        st.success(f" Results saved to '{os.path.abspath(folder)}'")
        st.success(f"Verified file saved as: {os.path.join(folder, f'{custom_name if custom_name else 'data'}_verified.xlsx')}")
        st.success(f"Unverified file saved as: {os.path.join(folder, f'{custom_name if custom_name else 'data'}_unverified.xlsx')}")

    else:
        st.error('Please upload an Excel file and provide a save folder if not saving in the same folder.')
