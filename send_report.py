"""
send_report.py
Sends the FA Prospect List PDF via Gmail.
Reads credentials from environment variables set as GitHub Secrets.
"""

import os
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

GMAIL_USER       = os.environ["GMAIL_USER"]
GMAIL_APP_PW     = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENT        = os.environ["RECIPIENT_EMAIL"]
PDF_PATH         = "FA_Prospect_List_CentralFlorida.pdf"

now_str  = datetime.now().strftime("%B %Y")
run_date = datetime.now().strftime("%B %d, %Y")


def build_email():
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"FA Prospect List — Central Florida | {now_str}"
    msg["From"]    = f"FA Prospector <{GMAIL_USER}>"
    msg["To"]      = RECIPIENT

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #1a2e4a; background: #f4f7fb; padding: 0; margin: 0;">
      <div style="max-width: 560px; margin: 32px auto; background: #ffffff;
                  border-radius: 10px; overflow: hidden;
                  border: 1px solid #c8d8ec;">

        <!-- Header -->
        <div style="background: #0D1F3C; padding: 28px 32px;">
          <p style="margin: 0; color: #7AAED4; font-size: 11px; letter-spacing: 1px;
                    text-transform: uppercase;">Steward Partners</p>
          <h1 style="margin: 6px 0 0; color: #ffffff; font-size: 20px; font-weight: 700;">
            FA Prospect List
          </h1>
          <p style="margin: 4px 0 0; color: #5B9BD5; font-size: 13px;">
            Central Florida Market &nbsp;|&nbsp; {now_str}
          </p>
        </div>

        <!-- Body -->
        <div style="padding: 28px 32px;">
          <p style="margin: 0 0 14px; font-size: 14px; line-height: 1.6; color: #2B3A52;">
            Your monthly FA acquisition prospect list is attached. This run searched
            <strong>50+ Central Florida zip codes</strong> via FINRA BrokerCheck,
            filtering for advisors registered before 2000 with clean compliance records
            at transition-friendly firms.
          </p>

          <div style="background: #EEF4FC; border-left: 4px solid #2563C0;
                      border-radius: 4px; padding: 14px 16px; margin: 18px 0;">
            <p style="margin: 0; font-size: 13px; color: #1A4A8A; font-weight: 700;">
              What to do with this report
            </p>
            <ul style="margin: 8px 0 0; padding-left: 18px; font-size: 13px;
                       color: #2B5278; line-height: 1.8;">
              <li>Fill in Phone / Email / LinkedIn columns using Apollo.io or Hunter.io</li>
              <li>Prioritize advisors registered pre-1990 — deepest in succession window</li>
              <li>Cross-reference firm transition notes in Appendix A</li>
              <li>Begin LinkedIn outreach in Month 2 per the 6-month strategy in Appendix B</li>
            </ul>
          </div>

          <p style="margin: 18px 0 0; font-size: 13px; color: #4a6080;">
            This report runs automatically on the <strong>1st of each month</strong>.
            To run manually or adjust the registration year cutoff, go to your
            GitHub Actions tab and trigger a manual workflow run.
          </p>
        </div>

        <!-- Footer -->
        <div style="background: #0D1F3C; padding: 16px 32px; text-align: center;">
          <p style="margin: 0; color: #5B9BD5; font-size: 11px;">
            Generated {run_date} &nbsp;|&nbsp; FA Prospector Pipeline &nbsp;|&nbsp;
            Data: FINRA BrokerCheck
          </p>
          <p style="margin: 4px 0 0; color: #3A5A7A; font-size: 10px;">
            For internal Steward Partners use only
          </p>
        </div>

      </div>
    </body>
    </html>
    """

    msg.attach(MIMEText(html, "html"))

    # Attach PDF
    if os.path.exists(PDF_PATH):
        with open(PDF_PATH, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="FA_Prospect_List_{now_str.replace(" ", "_")}.pdf"',
        )
        msg.attach(part)
        print(f"Attached: {PDF_PATH}")
    else:
        print(f"WARNING: PDF not found at {PDF_PATH} — sending without attachment")

    return msg


def send():
    msg = build_email()
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(GMAIL_USER, GMAIL_APP_PW)
        server.sendmail(GMAIL_USER, RECIPIENT, msg.as_string())
    print(f"Email sent to {RECIPIENT}")


if __name__ == "__main__":
    send()
