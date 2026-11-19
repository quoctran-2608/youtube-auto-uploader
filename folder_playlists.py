"""Build a local, reviewable playlist plan before changing YouTube."""
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path, PureWindowsPath
from datetime import datetime, timezone
import json
import re
import unicodedata

from google.auth.exceptions import GoogleAuthError

from storage import atomic_write
from upload_queue import pacific_midnight_after
from youtube_client import friendly_error, quota_reason


def source_path(value):
    return PureWindowsPath(value) if '\\' in value or re.match(r'^[A-Za-z]:', value) else Path(value)


def folder_title(value):
    parent = source_path(value).parent.name.strip()
    return parent if parent and parent not in ('.', '..') else ''


def normalized_stem(value):
    name = unicodedata.normalize('NFC', source_path(value).stem).casefold()
    return ' '.join(re.findall(r'[^\W_]+', name))


class Mp3Index:
    def __init__(self, root):
        root = Path(root)
        if not root.is_dir():
            raise ValueError('Không tìm thấy thư mục MP3.')
        self.by_name = defaultdict(list)
        self.by_length = defaultdict(list)
        for path in sorted(root.rglob('*')):
            if path.suffix.casefold() == '.mp3' and path.is_file():
                name = normalized_stem(path.name)
                if name:
                    if name not in self.by_name:
                        self.by_length[len(name)].append(name)
                    self.by_name[name].append(path)
        if not self.by_name:
            raise ValueError('Không tìm thấy tệp MP3 trong thư mục đã chọn.')

    def match(self, filename):
        key = normalized_stem(filename)
        if key in self.by_name:
            matches = self.by_name[key]
            return (matches[0], 'Tên khớp') if len(matches) == 1 else (None, 'Trùng tên MP3')
        if len(key) < 12:
            return None, 'Không tìm thấy MP3 khớp'
        matches = []
        for length in range((len(key) * 98 + 101) // 102, len(key) * 102 // 98 + 1):
            for name in self.by_length.get(length, ()):
                ratio = SequenceMatcher(None, key, name, autojunk=False).ratio()
                if ratio >= .98:
                    matches.extend((path, ratio) for path in self.by_name[name])
        if len(matches) == 1:
            path, ratio = matches[0]
            return path, f'Gần giống {ratio:.1%} · cần chọn thủ công'
        return None, 'Nhiều MP3 gần giống' if matches else 'Không tìm thấy MP3 khớp'


def plan_history(records, mp3_index=None):
    proposals = []
    seen = set()
    ambiguous_ids = {vid for vid, count in _video_counts(records).items() if count > 1}
    for record in records:
        video_id = record['video_id']
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        source = record['path']
        detail = 'Thư mục trong lịch sử'
        automatic = False
        if video_id in ambiguous_ids:
            target, detail = '', 'Video ID có nhiều bản ghi lịch sử'
        elif mp3_index is not None:
            matched, detail = mp3_index.match(source)
            target = folder_title(str(matched)) if matched else ''
            automatic = detail == 'Tên khớp'
            if matched:
                source = str(matched)
        else:
            target = folder_title(source)
            if not target:
                detail = 'Thiếu thư mục trong lịch sử'
        proposals.append(dict(record=record, target=target, source=source, detail=detail, automatic=automatic))
    return proposals


def _video_counts(records):
    counts = defaultdict(int)
    for record in records:
        counts[record['video_id']] += 1
    return counts


class PlaylistBatch:
    """Checkpoint each approved move and retry only unfinished work."""

    def __init__(self, folder):
        self.path = folder / 'playlist-batch.json'

    def read(self):
        if self.path.exists():
            return json.loads(self.path.read_text(encoding='utf-8'))
        return None

    def save(self, batch):
        atomic_write(self.path, json.dumps(batch, ensure_ascii=False).encode('utf-8'))

    def start(self, channel, proposals, remove_old):
        items = [{'record': {key: item['record'][key] for key in ('id', 'video_id', 'playlist_id', 'title')},
                  'target': item['target'], 'state': 'pending', 'detail': ''} for item in proposals]
        self.save({'channel': channel, 'remove_old': remove_old, 'items': items, 'retry_at': '', 'reason': ''})

    def due(self, batch, now=None):
        return not batch['retry_at'] or datetime.fromisoformat(batch['retry_at']) <= (now or datetime.now(timezone.utc))

    def run(self, client, progress, now=None):
        batch = self.read()
        if not batch or not client.channel or not client.channel_confirmed or client.channel['id'] != batch['channel']:
            raise ValueError('Hãy kết nối đúng kênh của đợt sắp playlist.')
        if not self.due(batch, now):
            return batch
        batch.update(retry_at='', reason='')
        for index, item in enumerate(batch['items'], 1):
            if item['state'] != 'pending':
                continue
            progress((index - 1) * 100 / len(batch['items']), f"Đang sắp playlist {index}/{len(batch['items'])}…")
            try:
                client.organize_video(item['record'], item['target'], batch['remove_old'])
            except Exception as error:
                detail = friendly_error(error)
                status = getattr(getattr(error, 'resp', None), 'status', 0) or 0
                if quota_reason(error) in ('quotaExceeded', 'dailyLimitExceeded'):
                    batch['retry_at'] = pacific_midnight_after(now or datetime.now(timezone.utc)).isoformat()
                    batch['reason'] = detail
                elif not client.channel_confirmed or isinstance(error, (OSError, GoogleAuthError)) or status in (401, 429) or status >= 500:
                    batch['reason'] = detail
                else:
                    item.update(state='error', detail=detail)
                    self.save(batch)
                    continue
                self.save(batch)
                break
            else:
                item.update(state='done', detail='')
                self.save(batch)
        return batch
