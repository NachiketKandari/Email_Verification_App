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
from io import BytesIO

st.set_page_config(
    page_title="Email Verification App",
    page_icon="android-chrome-512x512.png"  
)

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

default_smtp_servers = [
    'alt4.gmail-smtp-in.l.google.com',
    'gmail-smtp-in.l.google.com'
]

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

def save_partial_results(verified_rows, unverified_rows, folder, custom_name):
    verified_df = pd.DataFrame(verified_rows)
    unverified_df = pd.DataFrame(unverified_rows)

    verified_file_path = os.path.join(folder, f"{custom_name if custom_name else 'data'}_verified_partial.xlsx")
    unverified_file_path = os.path.join(folder, f"{custom_name if custom_name else 'data'}_unverified_partial.xlsx")

    verified_df.to_excel(verified_file_path, index=False)
    unverified_df.to_excel(unverified_file_path, index=False)

    with open(verified_file_path, 'rb') as vf:
        st.session_state.verified_file_data = vf.read()
    with open(unverified_file_path, 'rb') as uf:
        st.session_state.unverified_file_data = uf.read()

    st.session_state.show_buttons = True  
    st.session_state.interrupted = True   

if 'verified_file_data' not in st.session_state:
    st.session_state.verified_file_data = None
if 'unverified_file_data' not in st.session_state:
    st.session_state.unverified_file_data = None
if 'show_buttons' not in st.session_state:
    st.session_state.show_buttons = False
if 'interrupted' not in st.session_state:
    st.session_state.interrupted = False
if 'mode' not in st.session_state:
    st.session_state.mode = "Single Verification"


st.title('Email Verification App')

tab1, tab2 = st.tabs(["Single Verification", "Batch Verification"])

with tab1 or tab1.activeTab :
    
    st.session_state.mode =  "Single Verification"
    st.subheader("🔍 Single Verification")
    single_email = st.text_input("Enter the email address to verify")
    if st.button("Check"):
        if single_email.strip():
            domain = extract_domain(single_email)
            if domain is None:
                st.error("Invalid Email: missing '@' or invalid format.")
            else:
                mx_records = get_mx_records(domain)
                if not mx_records:
                    st.error("Invalid Domain: no valid MX records found.")
                else:
                    verified = False
                    result_msg = "Unknown error"
                    for smtp_server in default_smtp_servers:
                        is_verified, error_code = verify_email(single_email, smtp_server)
                        if is_verified:
                            verified = True
                            result_msg = "Verified"
                            break
                        elif error_code in ['550', '551', '553', '554']:
                            result_msg = error_messages.get(error_code, "Unknown error")
                            break

                    if not verified and mx_records:
                        server_index = 0
                        start_index = 0
                        tried_all = False

                        while not verified and not tried_all:
                            is_verified, error_code = verify_email(single_email, mx_records[server_index])
                            if is_verified:
                                verified = True
                                result_msg = "Verified"
                            else:
                                if error_code not in ['550', '551', '553', '554']:
                                    server_index = (server_index + 1) % len(mx_records)
                                    if server_index == start_index:
                                        tried_all = True
                                        result_msg = error_messages.get(error_code, "Unknown error")
                                else:
                                    result_msg = error_messages.get(error_code, "Unknown error")
                                    tried_all = True

                    if verified:
                        st.success("✅ This email is verified!")
                    else:
                        st.warning(f"❗ Email Unverified: {result_msg}")
        else:
            st.warning("Please enter an email address to check.")
        if st.session_state.show_buttons or st.session_state.interrupted :

            if st.button("Exit"):
                st.session_state.show_buttons = False
                st.session_state.interrupted = False
                st.session_state.verified_file_data = None
                st.session_state.unverified_file_data = None
                st.rerun()

with tab2 :
    st.session_state.mode = "Batch Verification"
    st.subheader("🗂 Batch Verification")
    st.info("Please ensure that the Excel sheet has a column named 'Email' under which the email addresses should be listed.")
    uploaded_file = st.file_uploader('Choose an Excel', type='xlsx', accept_multiple_files=False)
    start_row = st.number_input('Start Row', min_value=1, value=1)
    end_row = st.number_input('End Row', min_value=1, value=20000)
    custom_name = st.text_input('Enter custom file name (optional)', '')

    if st.button('Start Verification'):
        st.session_state.show_buttons = True
        st.session_state.interrupted = False

        if uploaded_file:
            verified_count = 0
            unverified_count = 0
            start_time = datetime.now()

            with open('progress.txt', 'w') as f:
                f.write('')

            logging.basicConfig(filename='email_verification.log', level=logging.INFO,
                                format='%(asctime)s %(levelname)s:%(message)s')

            start_index = start_row - 1
            df = pd.read_excel(uploaded_file)
            end_index = min(end_row, len(df))

            df = df.iloc[start_index:end_index]
            if 'Email' not in df.columns:
                st.error("The uploaded file must have an 'Email' column.")
            else:
                emails = df['Email']

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

                total_emails = end_index - start_row + 1
                processed_count = 0

                folder = "output"
                if not os.path.exists(folder):
                    os.makedirs(folder)

                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                        futures = {
                            executor.submit(process_email, index, row['Email'], last_successful_server_index, mx_cache): (index, row)
                            for index, row in df.iterrows()
                        }

                        for future in concurrent.futures.as_completed(futures):
                            index, row = futures[future]
                            try:
                                result = future.result()
                                idx, email, error_code, error_message = result
                                row['Error Code'] = error_code
                                row['Error Message'] = error_message
                                processed_count += 1

                                time_elapsed = (datetime.now() - start_time).total_seconds()
                                time_per_email = time_elapsed / processed_count if processed_count > 0 else 0
                                emails_left = total_emails - processed_count
                                time_left = time_per_email * emails_left
                                time_left_str = str(timedelta(seconds=time_left)).split(".")[0]

                                progress_text.text(
                                    f"Email No: {processed_count} of {total_emails} | Verified: {verified_count} | Unverified: {unverified_count}\n"
                                    f"Time Elapsed: {time_elapsed.__round__(2)} seconds | Time to completion: {time_left_str}"
                                )
                                progress_bar.progress(processed_count / total_emails)

                                if error_code == "250":
                                    verified_rows.append(row)
                                    verified_count += 1
                                else:
                                    unverified_rows.append(row)
                                    unverified_count += 1

                                if processed_count % 10 == 0:
                                    save_partial_results(verified_rows, unverified_rows, folder, custom_name)

                            except Exception as e:
                                logging.error(f"Exception in future for index {index}: {e}")
                                save_partial_results(verified_rows, unverified_rows, folder, custom_name)
                                st.session_state.interrupted = True
                                break

                    verified_df = pd.DataFrame(verified_rows, columns=df.columns)
                    unverified_df = pd.DataFrame(unverified_rows, columns=df.columns.tolist() + ['Error Code', 'Error Message'])

                    verified_file_path = os.path.join(folder, f"{custom_name if custom_name else 'data'}_verified.xlsx")
                    unverified_file_path = os.path.join(folder, f"{custom_name if custom_name else 'data'}_unverified.xlsx")

                    verified_df.to_excel(verified_file_path, index=False)
                    unverified_df.to_excel(unverified_file_path, index=False)

                    with open(verified_file_path, 'rb') as vf:
                        st.session_state.verified_file_data = vf.read()
                    with open(unverified_file_path, 'rb') as uf:
                        st.session_state.unverified_file_data = uf.read()

                    st.session_state.show_buttons = True
                    st.session_state.interrupted = False
                    
                except Exception as e:
                    logging.error(f"Unexpected error: {e}")
                    save_partial_results(verified_rows, unverified_rows, folder, custom_name)
                    st.session_state.interrupted = True
                    st.warning("Download partially processed data below due to an interruption.")

                if st.session_state.interrupted :
                    st.warning("Download partially processed data below due to an interruption.")
                else:   
                    st.success(f"Email verification completed successfully! | Verified: {verified_count} | Unverified: {unverified_count}")
        else:
            st.warning("Please upload a file to start the verification process.")

        if st.session_state.show_buttons or st.session_state.interrupted :
    
            if st.session_state.mode == "Batch Verification" and st.session_state.verified_file_data is not None and st.download_button(
                label="Download Verified Emails",
                data=st.session_state.verified_file_data,
                file_name=f"{custom_name if custom_name else 'data'}_verified.xlsx"
            ):
                pass 

            if  st.session_state.mode == "Batch Verification" and st.session_state.unverified_file_data is not None and st.download_button(
                label="Download Unverified Emails",
                data=st.session_state.unverified_file_data,
                file_name=f"{custom_name if custom_name else 'data'}_unverified.xlsx"
            ):
                pass

            if st.button("Exit"):
                st.session_state.show_buttons = False
                st.session_state.interrupted = False
                st.session_state.verified_file_data = None
                st.session_state.unverified_file_data = None
                st.rerun()

        

