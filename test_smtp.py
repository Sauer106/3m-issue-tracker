"""Verify the SMTP relay works before scheduling the real emails.

    python test_smtp.py you@yourdomain.com
"""
import sys

import db
from mailer import send_email


def main():
    if len(sys.argv) != 2:
        print("Usage: python test_smtp.py <recipient-email>")
        sys.exit(1)
    recipient = sys.argv[1]
    config = db.get_config()
    print(f"Sending test message to {recipient} via {config['smtp']['host']}:{config['smtp'].get('port', '25')}...")
    send_email(
        config, [recipient],
        "[3M Issues & Projects Tracker] SMTP relay test",
        "<p>If you can read this, the issue tracker can send mail through your relay.</p>",
    )
    print("Sent. Check the inbox (and spam folder).")


if __name__ == "__main__":
    main()
