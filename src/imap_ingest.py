from imapclient import IMAPClient
import email
from email.policy import default
import re

def match_from_pattern(from_address, pattern):
    # pattern like exact address or wildcard *@domain
    if pattern.startswith("*@"):
        domain = pattern[2:].lower()
        return from_address.lower().endswith("@" + domain)
    return from_address.lower() == pattern.lower()

def extract_emails(from_header):
    # crude extraction of addresses
    return re.findall(r'[\w\.-]+@[\w\.-]+', from_header)

def fetch_new_messages(config, sources, state):
    host = config.IMAP_HOST
    port = config.IMAP_PORT
    user = config.IMAP_USER
    password = config.IMAP_PASSWORD
    results = []
    with IMAPClient(host, ssl=True, port=port) as client:
        client.login(user, password)
        client.select_folder("INBOX")
        # fetch recent messages (all UIDs) — we will filter
        messages = client.search(['ALL'])
        if not messages:
            return results
        fetch_data = client.fetch(messages, ['RFC822', 'ENVELOPE', 'UID'])
        for uid, data in fetch_data.items():
            msg = email.message_from_bytes(data[b'RFC822'], policy=default)
            msg_id = msg.get('Message-ID') or str(uid)
            if msg_id in state.get("processed_message_ids", []):
                continue
            from_header = (msg.get('From') or "")
            addrs = extract_emails(from_header)
            for src in sources:
                if not src.get("enabled", True):
                    continue
                pat = src.get("from_pattern")
                if not pat:
                    continue
                if any(match_from_pattern(a, pat) for a in addrs):
                    results.append({"source": src, "uid": uid, "msg": msg, "message_id": msg_id})
                    break
    return results
