"""Send email through the SMTP relay configured in config.ini."""
import smtplib
from email.message import EmailMessage


def send_email(config, to_addrs, subject, html_body, text_body=None, attachments=None):
    """Send an HTML email. `attachments` is an optional list of
    (filename, content_type, bytes) tuples."""
    smtp = config["smtp"]
    msg = EmailMessage()
    msg["From"] = smtp["from_address"]
    msg["To"] = ", ".join(to_addrs)
    msg["Subject"] = subject
    msg.set_content(text_body or "This email is best viewed in an HTML-capable mail client.")
    msg.add_alternative(html_body, subtype="html")
    for filename, content_type, data in (attachments or []):
        maintype, _, subtype = (content_type or "application/octet-stream").partition("/")
        msg.add_attachment(data, maintype=maintype or "application",
                           subtype=subtype or "octet-stream", filename=filename)

    with smtplib.SMTP(smtp["host"], smtp.getint("port", fallback=25), timeout=30) as server:
        if smtp.getboolean("use_tls", fallback=False):
            server.starttls()
        if smtp.get("username"):
            server.login(smtp["username"], smtp["password"])
        server.send_message(msg)
