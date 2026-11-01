"""Email sender tool using SMTP.

If SMTP settings are not configured, it writes the outgoing email to logs
for demo purposes.
"""
from typing import Tuple, List
import smtplib
from email.message import EmailMessage
import os
from html import escape
import re
from urllib.parse import urlsplit


def _compact_text(value: object, limit: int = 320) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    excerpt = text[:limit - 1].rsplit(" ", 1)[0].rstrip(".,;:—- ")
    return f"{excerpt}…"


def _summary_lines(summary: str) -> list[str]:
    return [
        line.strip().lstrip("-•* ").strip()
        for line in summary.splitlines()
        if line.strip().lstrip("-•* ").strip()
    ]


def _email_bodies(summary: str, results: list[dict], fallback: str = "", is_job_search: bool = True) -> tuple[str, str]:
    """Build a short, readable plaintext digest and email-client-safe HTML."""
    summary_items = _summary_lines(summary)
    if not results and not summary_items:
        plain = fallback.strip() or "No content was available for this journey."
        return plain, f'<p style="margin:0;line-height:1.6">{escape(plain).replace(chr(10), "<br>")}</p>'

    title = "Job search results" if is_job_search else "Research digest"
    section_label = "OPPORTUNITIES" if is_job_search else "SOURCES"
    plain_parts = [f"AURA  /  {title.upper()}", ""]
    html_parts = []
    if summary_items:
        summary_items = [_compact_text(line, 240) for line in summary_items]
        plain_parts.extend(["QUICK SUMMARY", *[f"• {line}" for line in summary_items], ""])
        html_parts.append(
            '<section style="padding:18px 20px;border:1px solid #e6e1d8;border-radius:10px;background:#faf8f3;margin:0 0 22px">'
            '<div style="margin:0 0 10px;color:#74658c;font:700 11px Arial,sans-serif;letter-spacing:1.2px">QUICK SUMMARY</div>'
            '<ul style="padding-left:19px;margin:0;color:#44404a;font:14px/1.65 Arial,sans-serif">'
            + "".join(f'<li style="padding:0 0 5px">{escape(item)}</li>' for item in summary_items)
            + "</ul></section>"
        )

    if results:
        plain_parts.extend([f"{len(results)} {section_label}", ""])
        html_parts.append(
            f'<div style="margin:0 0 12px;color:#74658c;font:700 11px Arial,sans-serif;letter-spacing:1.2px">{len(results)} {section_label}</div>'
        )
        for index, result in enumerate(results, 1):
            title = _compact_text(result.get("title") or "Opportunity", 150)
            snippet = _compact_text(result.get("snippet"), 320)
            source = _compact_text(result.get("source"), 70)
            facts = [_compact_text(fact, 90) for fact in result.get("facts", []) if str(fact).strip()]
            url = str(result.get("url") or "")
            plain_parts.append(f"{index}. {title}")
            if facts:
                plain_parts.append("   " + " · ".join(facts))
            if source:
                plain_parts.append(f"   Source: {source}")
            if snippet:
                plain_parts.append(f"   {snippet}")
            plain_parts.extend([f"   Open {'opportunity' if is_job_search else 'source'}: {url}", ""])

            facts_html = (
                f'<div style="margin:7px 0;color:#77717e;font:12px/1.5 Arial,sans-serif">{escape(" · ".join(facts))}</div>'
                if facts else ""
            )
            source_html = (
                f'<span style="color:#817b87;font:11px Arial,sans-serif">{escape(source)}</span>'
                if source else ""
            )
            snippet_html = (
                f'<p style="margin:9px 0 12px;color:#5f5b64;font:13px/1.6 Arial,sans-serif">{escape(snippet)}</p>'
                if snippet else ""
            )
            html_parts.append(
                '<article style="padding:17px 0;border-bottom:1px solid #e9e5de">'
                f'<div style="color:#817b87;font:11px Arial,sans-serif;margin-bottom:6px">{index:02d}  /  OPPORTUNITY</div>'
                f'<h2 style="margin:0;color:#292630;font:600 17px/1.4 Arial,sans-serif">{escape(title)}</h2>'
                f'{facts_html}{snippet_html}'
                f'<a href="{escape(url, quote=True)}" style="display:inline-block;color:#674e88;font:700 13px Arial,sans-serif;text-decoration:none">Open {"opportunity" if is_job_search else "source"}&nbsp; →</a>'
                f'<div style="margin-top:8px">{source_html}</div>'
                '</article>'
            )

    plain = "\n".join(plain_parts).strip()
    content = "".join(html_parts)
    html = (
        '<div style="margin:0;background:#f3f0e9;padding:28px 12px">'
        '<div style="max-width:680px;margin:0 auto;padding:30px 34px;background:#fffefa;border:1px solid #e8e2d8;border-radius:12px">'
        '<div style="margin:0 0 8px;color:#756888;font:700 11px Arial,sans-serif;letter-spacing:1.6px">AURA&nbsp; / &nbsp;WORKSPACE</div>'
        f'<h1 style="margin:0 0 24px;color:#292630;font:600 25px/1.25 Arial,sans-serif">{escape(title)}</h1>'
        f'{content}'
        '<div style="padding-top:22px;color:#89838d;font:11px/1.5 Arial,sans-serif">Collected for you by AURA</div>'
        '</div></div>'
    )
    return plain, html


def run(args: dict, context: dict) -> Tuple[List[str], dict]:
    to = args.get("to") or ""
    subject = args.get("subject") or "Agent result"
    body = args.get("body")

    logs = []

    search_results = []
    page_results = []
    summaries = []
    seen_urls = set()
    for value in context.values():
        if not isinstance(value, dict):
            continue
        if value.get("summary"):
            summaries.append(str(value["summary"]))
        for result in value.get("job_matches") or value.get("results") or []:
            if not isinstance(result, dict):
                continue
            url = (result.get("url") or result.get("link") or "").strip()
            if not url.startswith(("https://", "http://")) or "example.com/" in url or url in seen_urls:
                continue
            seen_urls.add(url)
            search_results.append({
                "title": result.get("title") or "Opportunity",
                "snippet": result.get("snippet") or "",
                "url": url,
                "source": result.get("source") or "",
                "provider": result.get("provider") or "",
                "found_at": result.get("found_at") or "",
                "published_at": result.get("published_at") or "",
                "facts": [str(result.get(key) or "").strip() for key in ("company", "location", "work_mode", "employment_type", "salary") if result.get(key)],
            })
        for page in value.get("pages", []) or []:
            if not isinstance(page, dict):
                continue
            url = str(page.get("url") or "").strip()
            if not url.startswith(("https://", "http://")) or "example.com/" in url or url in seen_urls:
                continue
            seen_urls.add(url)
            try:
                source = (urlsplit(url).hostname or "Source page").removeprefix("www.")
            except ValueError:
                source = "Source page"
            page_results.append({
                "title": page.get("title") or source,
                "snippet": str(page.get("text") or "")[:280],
                "url": url,
                "source": source,
                "provider": "AURA page reader",
                "found_at": "",
            })

    # Search results are the actual opportunities. Scraped pages are used only
    # when a journey has no search results, so advice pages do not appear as jobs.
    if not search_results:
        search_results = page_results
    search_results = search_results[:8]
    goal = str(context.get("plan_input") or "").lower()
    is_job_search = any(word in goal for word in ("job", "role", "intern", "career", "position", "vacancy", "fresher", "hiring"))
    is_job_search = is_job_search or any(result.get("facts") for result in search_results)
    generated_body, html_content = _email_bodies(summaries[-1] if summaries else "", search_results, str(body or ""), is_job_search)
    # Use the same captured summary and ordered links shown in AURA so email
    # cannot silently replace or omit results with planner-authored text.
    body = generated_body or str(body or "").strip()

    if not body:
        body = "(no content available)"

    if not to:
        logs.append("Email skipped: no recipient address was supplied")
        return logs, {"email_sent": False, "reason": "missing_recipient", "subject": subject}

    # Check SMTP env
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", 587)) if os.getenv("SMTP_PORT") else None
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    default_from = (
        os.getenv("SMTP_FROM", "").strip()
        or os.getenv("DEFAULT_FROM", "").strip()
        or smtp_user
    )

    if not smtp_host or not smtp_user or not smtp_pass:
        message = "Email not sent: configure SMTP_HOST, SMTP_USER, and SMTP_PASSWORD first."
        logs.append(message)
        return logs, {
            "email_sent": False,
            "to": to,
            "subject": subject,
            "error": message,
        }

    msg = EmailMessage()
    msg["From"] = default_from
    msg["To"] = to
    msg["Subject"] = subject
    
    # Set plain text version
    msg.set_content(body)
    
    if not html_content:
        html_content = f'<p style="font:14px/1.6 Arial,sans-serif">{escape(body).replace(chr(10), "<br>")}</p>'
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
