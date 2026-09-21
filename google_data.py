"""Fetches mail headers and today's calendar events. Read-only."""
import email.utils
import html
from datetime import datetime, timedelta
from googleapiclient.errors import HttpError

from googleapiclient.discovery import build
from google_auth import get_credentials


def _header(headers, name):
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def fetch_messages(cfg):
    """Returns a list of message dicts (sender, subject, snippet, labels, time, link)."""
    creds = get_credentials()
    svc = build("gmail", "v1", credentials=creds, cache_discovery=False)

    limit = max(1, min(int(cfg.get("max_messages", 40)), 50))  # one batch call handles up to 100
    listing = svc.users().messages().list(userId="me", q=cfg["query"], maxResults=limit).execute()
    ids = [m["id"] for m in listing.get("messages", [])]

    fetched = {}

    def on_result(_request_id, response, exception):
        if exception is None:
            fetched[response["id"]] = response

    if ids:
        batch = svc.new_batch_http_request(callback=on_result)
        for mid in ids:
            batch.add(
                svc.users().messages().get(
                    userId="me", id=mid, format="metadata", metadataHeaders=["From", "Subject", "Date"]
                )
            )
        batch.execute()

    account = int(cfg.get("account_index", 0))
    out = []
    for mid in ids:
        msg = fetched.get(mid)
        if not msg:
            continue
        headers = msg.get("payload", {}).get("headers", [])
        name, addr = email.utils.parseaddr(_header(headers, "From"))
        labels = msg.get("labelIds", [])
        thread = msg.get("threadId", mid)
        out.append(
            {
                "id": mid,
                "from_name": name or addr or "Unknown sender",
                "from_email": addr,
                "subject": _header(headers, "Subject") or "(no subject)",
                "snippet": html.unescape(msg.get("snippet", "")),
                "ts": int(msg.get("internalDate", 0)) / 1000,
                "labels": labels,
                "unread": "UNREAD" in labels,
                "url": f"https://mail.google.com/mail/u/{account}/#inbox/{thread}",
            }
        )
    return out


def todays_events():
    creds = get_credentials()
    svc = build("calendar", "v3", credentials=creds, cache_discovery=False)

    start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    resp = (
        svc.events()
        .list(
            calendarId="shivam1234snr@gmail.com",
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=25,
        )
        .execute()
    )

    out = []
    for e in resp.get("items", []):
        if e.get("status") == "cancelled":
            continue
        s, en = e.get("start", {}), e.get("end", {})
        out.append(
            {
                "id": e["id"],
                "title": e.get("summary", "(no title)"),
                "start": s.get("dateTime") or s.get("date"),
                "end": en.get("dateTime") or en.get("date"),
                "all_day": "dateTime" not in s,
                "location": e.get("location", ""),
                "url": e.get("htmlLink", ""),
                "join_url": e.get("hangoutLink", ""),
            }
        )
    return out


def add_task_to_calendar(title, date_str, start_time=None, end_time=None, recurrence=None):
    creds = get_credentials()
    svc = build("calendar", "v3", credentials=creds, cache_discovery=False)
    
    event_body = {'summary': f"Task: {title}"}
    
    # Strip seconds just in case the browser sends them
    if start_time:
        start_time = start_time[:5]
    if end_time:
        end_time = end_time[:5]
    
    # If a start time is given but no end time, default to 1 hour later
    if start_time and not end_time:
        dt = datetime.strptime(start_time, "%H:%M")
        end_time = (dt + timedelta(hours=1)).strftime("%H:%M")
        
    # Handle specific times vs all-day events, explicitly declaring the timezone
    if start_time and end_time:
        event_body['start'] = {
            'dateTime': f"{date_str}T{start_time}:00+05:30",
            'timeZone': 'Asia/Kolkata'
        }
        event_body['end'] = {
            'dateTime': f"{date_str}T{end_time}:00+05:30",
            'timeZone': 'Asia/Kolkata'
        }
    else:
        event_body['start'] = {'date': date_str, 'timeZone': 'Asia/Kolkata'}
        event_body['end'] = {'date': date_str, 'timeZone': 'Asia/Kolkata'}
        
    # Apply recurrence
    if recurrence:
        event_body['recurrence'] = [f"RRULE:FREQ={recurrence.upper()}"]
        
    event = svc.events().insert(calendarId='shivam1234snr@gmail.com', body=event_body).execute()
    
    return event.get('id')


def delete_calendar_event(event_id):
    creds = get_credentials()
    svc = build("calendar", "v3", credentials=creds, cache_discovery=False)
    try:
        svc.events().delete(calendarId='shivam1234snr@gmail.com', eventId=event_id).execute()
    except HttpError as exc:
        if exc.resp.status in (404, 410):   # already deleted, which is what you wanted
            return
        raise 


def mark_message_as_read(message_id):
    creds = get_credentials()
    svc = build('gmail', 'v1', credentials=creds, cache_discovery=False)
    try:
        svc.users().messages().modify(
            userId='me',
            id=message_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()
    except Exception:
        pass # If it fails (e.g., already deleted in Gmail), fail silently