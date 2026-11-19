"""Build a local, reviewable playlist plan before changing YouTube."""
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path, PureWindowsPath
import re
import unicodedata


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
