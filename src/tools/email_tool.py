"""Email sender tool using SMTP.

If SMTP settings are not configured, it writes the outgoing email to logs
for demo purposes.
"""
from typing import Tuple, List
import smtplib
from email.message import EmailMessage
import os


def run(args: dict, context: dict) -> Tuple[List[str], dict]:
    to = args.get("to") or ""
    subject = args.get("subject") or "Agent result"
    body = args.get("body")

    logs = []

    # If body not provided, collect summary from context
    if not body:
        # Look for summary first
        for v in context.values():
            if isinstance(v, dict) and v.get("summary"):
                body = v.get("summary")
                break
        
        # If no summary, try to collect search results or scraped content
        if not body:
            content_parts = []
            for v in context.values():
                if isinstance(v, dict):
                    # Search results
                    if v.get("results"):
                        content_parts.append("Search Results:\n" + "="*50)
                        for i, r in enumerate(v.get("results", [])[:10], 1):
                            title = r.get("title", "")
                            snippet = r.get("snippet", "")
                            link = r.get("url") or r.get("link", "")  # Support both field names
                            content_parts.append(f"\n{i}. {title}")
                            content_parts.append(f"   {snippet}")
                            if link:
                                content_parts.append(f"   {link}\n")
                    # Scraped pages
                    elif v.get("pages"):
                        content_parts.append("Scraped Content:\n" + "="*50)
                        for p in v.get("pages", [])[:3]:
                            url = p.get("url", "")
                            text = p.get("text", "")[:500]
                            content_parts.append(f"\n🔗 {url}\n{text}...\n")
            
            if content_parts:
                body = "\n".join(content_parts)

    if not body:
        body = "(no content available)"

    # Check SMTP env
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", 587)) if os.getenv("SMTP_PORT") else None
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    default_from = os.getenv("DEFAULT_FROM", smtp_user)

    if not smtp_host or not smtp_user or not smtp_pass:
        # Demo fallback: write to logs and return
        logs.append(f"SMTP not configured - would send email to {to} with subject '{subject}'")
        logs.append(f"Email body:\n{body}")
        return logs, {"email_sent": False, "to": to, "subject": subject}

    msg = EmailMessage()
    msg["From"] = default_from
    msg["To"] = to
    msg["Subject"] = subject
    
    # Set plain text version
    msg.set_content(body)
    
    # Add HTML version with clickable links
    import re
    # Convert all URLs to clickable links - match any http/https URL
    url_pattern = r'(https?://[^\s<>]+)'
    html_body = re.sub(url_pattern, r'<a href="\1" style="color: #0066cc; text-decoration: underline;">\1</a>', body)
    
    # Format as HTML with proper styling
    html_body = html_body.replace("\n", "<br>\n")
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 800px; margin: 0 auto; padding: 20px;">
            {html_body}
        </div>
    </body>
    </html>
    """
    msg.add_alternative(html_content, subtype='html')

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        logs.append(f"Email sent to {to}")
        return logs, {"email_sent": True, "to": to, "subject": subject}
    except Exception as e:
        logs.append(f"Failed to send email: {e}")
        return logs, {"email_sent": False, "error": str(e)}
