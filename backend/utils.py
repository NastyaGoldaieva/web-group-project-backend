from datetime import datetime, timedelta, timezone
from uuid import uuid4

def parse_iso_to_utc(dt_str):
    """Parse ISO string (accepts trailing Z) into timezone-aware UTC datetime."""
    if dt_str is None:
        return None
    s = dt_str
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # Python fromisoformat supports offsets like +00:00
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def intersect_intervals(a, b):
    """a and b are lists of intervals dicts with 'start' and 'end' as datetimes (UTC). Returns list of dicts."""
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
    """
    avail1, avail2: lists of dicts with 'start' and 'end' as ISO strings (UTC)
    Returns list of slots as dicts with ISO strings in UTC (ending with Z).
    """
    # parse
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
    # limit and format to ISO Z
    def to_iso_z(dt):
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    out = []
    for s in slots_dt[:limit]:
        out.append({'start': to_iso_z(s['start']), 'end': to_iso_z(s['end'])})
    return out

def generate_meet_link():
    return f"https://meet.example.com/{uuid4()}"