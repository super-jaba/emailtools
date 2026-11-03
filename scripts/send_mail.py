import argparse
import mimetypes
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

SMTP_HOST = "127.0.0.1"
SMTP_PORT = 3025
DEV_DOMAIN = "emailtool.local"


def build_message(args: argparse.Namespace) -> EmailMessage:
    message = EmailMessage()
    message["From"] = args.sender
    message["To"] = args.to
    message["Subject"] = args.subject
    message["Message-ID"] = make_msgid(domain=DEV_DOMAIN)
    if args.reply_to:
        message["In-Reply-To"] = args.reply_to
        message["References"] = args.reply_to
    message.set_content(args.body)

    if args.attach:
        path = Path(args.attach)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        maintype, subtype = content_type.split("/", 1)
        message.add_attachment(
            path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name
        )
    return message


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send a message to the dev mail server."
    )
    parser.add_argument("--to", required=True)
    parser.add_argument("--from", dest="sender", default=f"dev@{DEV_DOMAIN}")
    parser.add_argument("--subject", default="Test message")
    parser.add_argument("--body", default="Test body")
    parser.add_argument("--attach", help="Path of a file to attach")
    parser.add_argument("--reply-to", help="Message-ID of the message to reply to")
    args = parser.parse_args()

    message = build_message(args)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.send_message(message)
    print(message["Message-ID"])


if __name__ == "__main__":
    main()
