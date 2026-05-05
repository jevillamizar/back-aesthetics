"""
Google Calendar integration helpers.

Required env vars (set per-deployment):
  GOOGLE_CLIENT_ID
  GOOGLE_CLIENT_SECRET
  GOOGLE_REDIRECT_URI   e.g. http://demo-clinic.lvh.me:8000/api/gcal/oauth2callback/
"""
import datetime
import os

from .models import GoogleCalendarToken

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
]

SLOT_DURATION_MINUTES = 60
TIMEZONE_OFFSET_HOURS = 5   # UTC-5 (Colombia)
WORK_START_HOUR = 7         # 7:00 AM local
WORK_END_HOUR   = 19        # 7:00 PM local


def _client_config() -> dict:
    return {
        'web': {
            'client_id': os.environ['GOOGLE_CLIENT_ID'],
            'client_secret': os.environ['GOOGLE_CLIENT_SECRET'],
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'redirect_uris': [os.environ['GOOGLE_REDIRECT_URI']],
        }
    }


def get_oauth_flow():
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=os.environ['GOOGLE_REDIRECT_URI'],
    )
    return flow


def get_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token = GoogleCalendarToken.objects.first()
    if token is None:
        return None

    creds = Credentials(
        token=token.access_token,
        refresh_token=token.refresh_token,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=os.environ['GOOGLE_CLIENT_ID'],
        client_secret=os.environ['GOOGLE_CLIENT_SECRET'],
        scopes=SCOPES,
    )
    if token.token_expiry:
        creds.expiry = token.token_expiry.replace(tzinfo=None)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token.access_token = creds.token
        token.token_expiry = (
            datetime.datetime.utcnow() + datetime.timedelta(seconds=3600)
            if creds.expiry is None
            else creds.expiry.replace(tzinfo=datetime.timezone.utc)
        )
        token.save(update_fields=['access_token', 'token_expiry', 'updated_at'])

    return creds


def get_calendar_id() -> str | None:
    token = GoogleCalendarToken.objects.first()
    if token and token.calendar_id:
        return token.calendar_id
    return 'primary'


def get_free_slots(date: datetime.date, duration_minutes: int | None = None) -> list[dict]:
    """
    Returns a list of free slot dicts for the given date:
    [{"starts_at": "2025-05-10T09:00:00+00:00", "ends_at": "2025-05-10T10:00:00+00:00"}, ...]

    duration_minutes: slot size in minutes. Defaults to SLOT_DURATION_MINUTES (60).
    """
    from googleapiclient.discovery import build

    creds = get_credentials()
    if creds is None:
        return []

    slot_mins = int(duration_minutes) if duration_minutes and duration_minutes > 0 else SLOT_DURATION_MINUTES

    service = build('calendar', 'v3', credentials=creds)
    calendar_id = get_calendar_id()

    local_tz  = datetime.timezone(datetime.timedelta(hours=-TIMEZONE_OFFSET_HOURS))
    day_start = datetime.datetime(date.year, date.month, date.day, WORK_START_HOUR, 0, 0, tzinfo=local_tz)
    day_end   = datetime.datetime(date.year, date.month, date.day, WORK_END_HOUR,   0, 0, tzinfo=local_tz)

    freebusy_result = service.freebusy().query(body={
        'timeMin': day_start.isoformat(),
        'timeMax': day_end.isoformat(),
        'items': [{'id': calendar_id}],
    }).execute()

    busy_periods = freebusy_result.get('calendars', {}).get(calendar_id, {}).get('busy', [])

    busy_ranges = []
    for period in busy_periods:
        b_start = datetime.datetime.fromisoformat(period['start'].replace('Z', '+00:00'))
        b_end   = datetime.datetime.fromisoformat(period['end'].replace('Z', '+00:00'))
        busy_ranges.append((b_start, b_end))

    free_slots = []
    slot_start = day_start
    delta = datetime.timedelta(minutes=slot_mins)

    while slot_start + delta <= day_end:
        slot_end = slot_start + delta
        overlaps = any(
            b_start < slot_end and b_end > slot_start
            for b_start, b_end in busy_ranges
        )
        if not overlaps:
            free_slots.append({
                'starts_at': slot_start.isoformat(),
                'ends_at': slot_end.isoformat(),
            })
        slot_start = slot_end

    return free_slots


def create_event(starts_at: datetime.datetime, ends_at: datetime.datetime, summary: str, description: str = '') -> str | None:
    """
    Creates a Google Calendar event and returns the event ID.
    """
    from googleapiclient.discovery import build

    creds = get_credentials()
    if creds is None:
        return None

    service = build('calendar', 'v3', credentials=creds)
    calendar_id = get_calendar_id()

    event = service.events().insert(
        calendarId=calendar_id,
        body={
            'summary': summary,
            'description': description,
            'start': {'dateTime': starts_at.isoformat(), 'timeZone': 'UTC'},
            'end':   {'dateTime': ends_at.isoformat(),   'timeZone': 'UTC'},
        },
    ).execute()

    return event.get('id')


def delete_event(event_id: str) -> None:
    from googleapiclient.discovery import build

    creds = get_credentials()
    if creds is None:
        return

    service = build('calendar', 'v3', credentials=creds)
    calendar_id = get_calendar_id()

    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    except Exception:
        pass
