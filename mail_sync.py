"""Read-only configurable IMAP attachment retrieval. Never marks messages read."""
import email
from email import policy
import imaplib
import ssl
from datetime import datetime, timedelta


def attachment_files(raw):
    msg = email.message_from_bytes(raw, policy=policy.default)
    files = []
    for part in msg.walk():
        name = part.get_filename() or ''
        content = part.get_payload(decode=True)
        if '行程' in name and content and content.startswith(b'%PDF-'):
            files.append(('通行费电子票据汇总单(行程).pdf', content))
            continue
        if (name.lower().endswith('.zip') and ('通行费电子发票' in name or '汇聚' in name or '汇总' in name)) or (name.lower().endswith('.pdf') and '行程' in name):
            content = part.get_payload(decode=True)
            if content:
                files.append((name, content))
    return files


def fetch_messages(account, password, days=90, lodging=False, rail=False):
    from local_config import load_settings, require_mail
    settings = dict(load_settings(), account=account)
    require_mail(settings)
    client = imaplib.IMAP4_SSL(settings['imap_server'], int(settings['imap_port']), ssl_context=ssl.create_default_context(), timeout=25)
    try:
        client.login(account, password)
        # NetEase requires an IMAP ID before mailbox access for some accounts.
        imaplib.Commands.setdefault('ID', ('AUTH',))
        if 'ID' in client.capabilities or b'ID' in client.capabilities:
            client._simple_command('ID', '("name" "DateArchivePublic" "version" "1.0")')
        typ, _ = client.select('INBOX', readonly=True)
        if typ != 'OK':
            raise ValueError('无法打开收件箱，请检查 IMAP 是否开启')
        since = (datetime.now() - timedelta(days=int(days))).strftime('%d-%b-%Y')
        typ, data = client.uid('search', None, 'SINCE', since)
        if typ != 'OK':
            raise ValueError('邮件检索失败')
        for uid in data[0].split():
            typ, headers = client.uid('fetch', uid, '(BODY.PEEK[HEADER.FIELDS (SUBJECT MESSAGE-ID)])')
            raw_header = b''.join(x[1] for x in headers if isinstance(x, tuple))
            header = email.message_from_bytes(raw_header, policy=policy.default)
            subject = str(header.get('Subject', ''))
            if rail:
                if not ('网上购票系统' in subject and '电子发票通知' in subject): continue
            elif lodging:
                if '通行费' in subject or not any(word in subject for word in ['发票','住宿','酒店','房费']): continue
            elif '通行费' not in subject:
                continue
            typ, parts = client.uid('fetch', uid, '(BODY.PEEK[])')
            if typ != 'OK':
                raise ValueError('附件下载失败：' + uid.decode())
            raw = b''.join(x[1] for x in parts if isinstance(x, tuple))
            files = attachment_files(raw)
            if lodging or rail:
                files=[]
                message=email.message_from_bytes(raw,policy=policy.default)
                for part in message.walk():
                    content=part.get_payload(decode=True)
                    if content and content.startswith(b'%PDF-'):
                        files.append(('邮件附件'+str(len(files)+1)+'.pdf',content))
            if files:
                yield {'id': str(header.get('Message-ID') or uid.decode()), 'subject': subject, 'files': files}
    finally:
        try: client.logout()
        except Exception: pass
