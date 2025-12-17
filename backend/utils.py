from datetime import datetime, timedelta, timezone
from uuid import uuid4
import os
import json
from pathlib import Path

from django.conf import settings

def parse_iso_to_utc(dt_str):
    if dt_str is None:
        return None
    s = dt_str
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def intersect_intervals(a, b):
    res = []
    i, j = 0, 0
    a_sorted = sorted(a, key=lambda x: x['start'])
    b_sorted = sorted(b, key=lambda x: x['start'])
    while i < len(a_sorted) and j < len(b_sorted):
        s = max(a_sorted[i]['start'], b_sorted[j]['start'])
        e = min(a_sorted[i]['end'], b_sorted[j]['end'])
        if s < e:
            res.append({'start': s, 'end': e})
        if a_sorted[i]['end'] < b_sorted[j]['end']:
            i += 1
        else:
            j += 1
    return res

def slice_into_slots(intervals, duration_minutes=60, step_minutes=30):
    slots = []
    dur = timedelta(minutes=duration_minutes)
    step = timedelta(minutes=step_minutes)
    for iv in intervals:
        cursor = iv['start']
        while cursor + dur <= iv['end']:
            slots.append({'start': cursor, 'end': cursor + dur})
            cursor = cursor + step
    return slots

def compute_common_slots(avail1, avail2, duration_minutes=60, step_minutes=30, limit=20):
    def to_dt_list(av):
        out = []
        for it in (av or []):
            s = parse_iso_to_utc(it.get('start'))
            e = parse_iso_to_utc(it.get('end'))
            if s and e and s < e:
                out.append({'start': s, 'end': e})
        return sorted(out, key=lambda x: x['start'])
    a = to_dt_list(avail1)
    b = to_dt_list(avail2)
    inter = intersect_intervals(a, b)
    slots_dt = slice_into_slots(inter, duration_minutes, step_minutes)
    def to_iso_z(dt):
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    out = []
    for s in slots_dt[:limit]:
        out.append({'start': to_iso_z(s['start']), 'end': to_iso_z(s['end'])})
    return out

def generate_meet_link():
    return f"https://meet.jit.si/{uuid4()}"

def _resolve_service_account_file():
    sa_path = getattr(settings, "GOOGLE_SERVICE_ACCOUNT_FILE", None)
    if sa_path:
        if os.path.isabs(sa_path):
            p = Path(sa_path)
        else:
            p = Path(settings.BASE_DIR) / sa_path
        if p.exists():
            return str(p)
    default = Path(settings.BASE_DIR) / "service-account.json"
    if default.exists():
        return str(default)
    return None

def create_google_meet_event(start_dt, end_dt, summary, description, attendees_emails, organizer_email=None):
    sa_file = _resolve_service_account_file()
    if not sa_file:
        print("create_google_meet_event: service account file not found, returning fallback Jitsi link")
        return generate_meet_link()

    scopes = [
        'https://www.googleapis.com/auth/calendar',
        'https://www.googleapis.com/auth/calendar.events',
    ]

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from google.auth.exceptions import RefreshError
        from googleapiclient.errors import HttpError
    except Exception as e:
        print("create_google_meet_event: google libraries not available:", e)
        return generate_meet_link()

    def _parse_http_error_reason(err):
        try:
            info = json.loads(err.content.decode())
            errs = info.get('error', {})
            if isinstance(errs, dict):
                return errs.get('errors')
            return None
        except Exception:
            return None

    def _create_with_credentials(creds, calendar_id, include_attendees=True, include_conference=True, send_updates='none'):
        try:
            service = build('calendar', 'v3', credentials=creds, cache_discovery=False)
        except Exception as e:
            raise RuntimeError(f"Failed to build calendar service: {e}")

        event = {
            'summary': summary,
            'description': description,
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'UTC'},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'UTC'},
        }

        if include_conference and include_attendees:
            event['conferenceData'] = {
                'createRequest': {
                    'requestId': str(uuid4()),
                    'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                }
            }

        if include_attendees and attendees_emails:
            event['attendees'] = [{'email': e} for e in attendees_emails]

        try:
            created = service.events().insert(
                calendarId=calendar_id,
                body=event,
                conferenceDataVersion=1 if include_conference and include_attendees else 0,
                sendUpdates=send_updates
            ).execute()
        except HttpError as he:
            raise he
        except Exception as ex:
            raise ex

        if isinstance(created, dict):
            if created.get('hangoutLink'):
                return created.get('hangoutLink')
            cd = created.get('conferenceData', {}) or {}
            for ep in cd.get('entryPoints', []):
                uri = ep.get('uri')
                if uri:
                    return uri
        return None

    if organizer_email:
        try:
            creds = service_account.Credentials.from_service_account_file(sa_file, scopes=scopes, subject=organizer_email)
            try:
                link = _create_with_credentials(creds, organizer_email, include_attendees=True, include_conference=True, send_updates='all')
                if link:
                    return link
            except HttpError as he:
                reasons = _parse_http_error_reason(he)
                print(f"create_google_meet_event: impersonation attempt failed for {organizer_email}: {he}; reasons={reasons}")
            except Exception as e:
                print(f"create_google_meet_event: impersonation unexpected error for {organizer_email}: {e}")
        except Exception as e:
            print(f"create_google_meet_event: failed to load credentials for impersonation: {e}")

    try:
        creds2 = service_account.Credentials.from_service_account_file(sa_file, scopes=scopes)
        calendar_id = getattr(settings, "GOOGLE_CALENDAR_ID", None) or getattr(creds2, "service_account_email", None)
        if not calendar_id:
            print("create_google_meet_event: no calendar_id available from settings or service account")
        else:
            try:
                link = _create_with_credentials(creds2, calendar_id, include_attendees=True, include_conference=True, send_updates='all')
                if link:
                    return link
            except HttpError as he:
                reasons = _parse_http_error_reason(he)
                print(f"create_google_meet_event: create event on service account calendar failed for {calendar_id}: {he}; reasons={reasons}")
                try:
                    if reasons:
                        for r in reasons:
                            if r.get('reason') == 'forbiddenForServiceAccounts':
                                try:
                                    link = _create_with_credentials(creds2, calendar_id, include_attendees=False, include_conference=False, send_updates='none')
                                    if link:
                                        return link
                                except Exception as e2:
                                    print(f"create_google_meet_event: retry without attendees failed: {e2}")
                                break
                except Exception:
                    pass
            except Exception as e:
                print(f"create_google_meet_event: unexpected error creating event on {calendar_id}: {e}")
    except Exception as e:
        print("create_google_meet_event: failed to load service account credentials:", e)

    print("create_google_meet_event: all google attempts failed, returning fallback Jitsi link")
    return generate_meet_link()