"""Durable local queue; an interrupted upload is never blindly repeated."""
import calendar
import json
from datetime import datetime, timedelta, timezone

from youtube_client import QuotaWait, quota_reason, friendly_error

UTC = timezone.utc

STATUS = {
    'pending': ('● Chờ tải', 'waiting'),
    'running': ('● Đang tải', 'waiting'),
    'waiting': ('● Chờ hạn mức', 'waiting'),
    'done': ('✓ Đã tải', 'done'),
    'attention': ('✕ Cần kiểm tra', 'error'),
    'interrupted': ('✕ Bị gián đoạn', 'error'),
}


def estimate_remaining(items, current_id=None, fraction=0.0, bytes_per_second=None):
    """Estimate active transfer time; None means insufficient reliable data."""
    if not bytes_per_second or bytes_per_second <= 0:
        return None
    total = 0
    for item in items:
        if item['state'] not in ('pending', 'running', 'waiting'):
            continue
        size = json.loads(item['row_json']).get('size_mb')
        if size is None or size <= 0:
            return None
        remaining = 1 - max(0, min(float(fraction), 1)) if item['id'] == current_id else 1
        total += size * 1024 * 1024 * remaining
    return total / bytes_per_second


def pacific_midnight_after(now):
    """Next midnight in Los Angeles, including US daylight-saving transitions."""
    now = now.astimezone(UTC)
    def sundays(year, month):
        return [week[calendar.SUNDAY] for week in calendar.monthcalendar(year, month) if week[calendar.SUNDAY]]
    year = now.year
    start = datetime(year, 3, sundays(year, 3)[1], 10, tzinfo=UTC)
    end = datetime(year, 11, sundays(year, 11)[0], 9, tzinfo=UTC)
    local = now - timedelta(hours=7 if start <= now < end else 8)
    day = local.date() + timedelta(days=1)
    dst = (3 < day.month < 11 or
           day.month == 3 and day.day > sundays(day.year, 3)[1] or
           day.month == 11 and day.day <= sundays(day.year, 11)[0])
    return datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(hours=7 if dst else 8, minutes=5)


class UploadQueue:
    def __init__(self, history):
        self.history = history
        with history.connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS queue_items (
                id INTEGER PRIMARY KEY, row_json TEXT NOT NULL, channel_id TEXT NOT NULL,
                playlist_id TEXT NOT NULL, privacy TEXT NOT NULL, kids INTEGER NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending', error TEXT NOT NULL DEFAULT '',
                retry_at TEXT NOT NULL DEFAULT '', history_id INTEGER)''')
            db.execute("UPDATE queue_items SET state='interrupted', error='Kiểm tra lịch sử và YouTube Studio trước khi tiếp tục mục này.' WHERE state='running'")

    def add(self, rows, channel, playlist, privacy, kids):
        with self.history.connection() as db:
            active = {json.loads(x[0])['path'] for x in db.execute("SELECT row_json FROM queue_items WHERE state IN ('pending','running','waiting','interrupted')")}
            count = 0
            for row in rows:
                if row['path'] in active:
                    continue
                db.execute('INSERT INTO queue_items (row_json,channel_id,playlist_id,privacy,kids) VALUES (?,?,?,?,?)',
                           (json.dumps(row, ensure_ascii=False), channel, playlist, privacy, int(kids)))
                active.add(row['path'])
                count += 1
            return count

    def all(self):
        with self.history.connection() as db:
            return [dict(x) for x in db.execute('SELECT * FROM queue_items ORDER BY id')]

    def update(self, item_id, **values):
        if not values or not set(values) <= {'state', 'error', 'retry_at', 'history_id'}:
            raise ValueError('Invalid queue update')
        with self.history.connection() as db:
            db.execute('UPDATE queue_items SET ' + ','.join(k+'=?' for k in values) + ' WHERE id=?', (*values.values(), item_id))

    def remove(self, item_id):
        with self.history.connection() as db:
            db.execute("DELETE FROM queue_items WHERE id=? AND state != 'running'", (item_id,))

    def next(self, now=None):
        now = (now or datetime.now(UTC)).isoformat()
        with self.history.connection() as db:
            first = db.execute("SELECT * FROM queue_items WHERE state IN ('pending','waiting') ORDER BY id LIMIT 1").fetchone()
            if not first or first['retry_at'] and first['retry_at'] > now:
                return None
            return dict(first)

    def process(self, item, client, progress, now=None):
        if not client.channel or not client.channel_confirmed or client.channel['id'] != item['channel_id'] or client.playlist_id != item['playlist_id']:
            raise ValueError('Hàng đợi thuộc kênh hoặc playlist khác. Kết nối đúng trước khi tiếp tục.')
        self.update(item['id'], state='running', error='', retry_at='')
        try:
            result = client.upload(json.loads(item['row_json']), item['privacy'], bool(item['kids']), progress)
            self.update(item['id'], state='done' if result['state'] == 'Uploaded' and result['verified'] else 'attention',
                        error=result['error'], history_id=result['id'])
            return result
        except Exception as error:
            reason = error.reason if isinstance(error, QuotaWait) else quota_reason(error)
            if reason:
                now = now or datetime.now(UTC)
                retry = now + timedelta(hours=24) if reason == 'uploadLimitExceeded' else pacific_midnight_after(now)
                self.update(item['id'], state='waiting', error=f'Giới hạn YouTube: {reason}', retry_at=retry.isoformat())
                return None
            self.update(item['id'], state='attention', error=friendly_error(error))
            return None
