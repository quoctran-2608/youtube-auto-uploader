"""Core logic for YouTube Auto Uploader preview (v0.1, no API calls)."""
from __future__ import annotations

import csv
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

SUPPORTED_EXTS = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v'}
DEFAULT_CONFIG = {
    'scan_subfolders': True,
    'start_date': '',
    'daily_times': ['08:00', '19:00'],
    'timezone': 'Asia/Ho_Chi_Minh',
    'default_description': '',
    'default_tags': '',
    'metadata_csv': 'metadata.csv',
}


def read_config(config_path: Path) -> dict:
    config = dict(DEFAULT_CONFIG)
    if config_path.exists():
        data = json.loads(config_path.read_text(encoding='utf-8-sig'))
        if not isinstance(data, dict):
            raise ValueError('config.json phải là một JSON object')
        config.update(data)
    return config


def read_metadata(csv_path: Path) -> dict[str, dict]:
    if not csv_path.exists():
        return {}
    output = {}
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or 'filename' not in reader.fieldnames:
            raise ValueError('metadata.csv phải có cột filename')
        for row in reader:
            key = str(row.get('filename') or '').strip().replace('\\', '/').casefold()
            if key:
                if key in output:
                    raise ValueError(f'Tên filename bị trùng trong CSV: {key}')
                output[key] = row
    return output


def scan_files(folder: Path, recursive: bool = True) -> list[Path]:
    if not folder.is_dir():
        raise ValueError('Thư mục video không tồn tại hoặc chưa được tải offline')
    files = folder.rglob('*') if recursive else folder.iterdir()
    return sorted((p for p in files if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS),
                  key=lambda p: str(p.relative_to(folder)).casefold())


def schedule_values(start: str, times: list[str], count: int) -> list[str]:
    if not start:
        start_day = date.today() + timedelta(days=1)
    else:
        start_day = date.fromisoformat(start)
    if not isinstance(times, list) or not times:
        raise ValueError('daily_times phải chứa ít nhất một giờ, ví dụ ["08:00"]')
    parsed_times = []
    for t in times:
        tm = datetime.strptime(t, '%H:%M').time()
        canonical = tm.strftime('%H:%M')
        if canonical not in parsed_times:
            parsed_times.append(canonical)
    parsed_times.sort()
    return [f'{(start_day + timedelta(days=i // len(parsed_times))).isoformat()} {parsed_times[i % len(parsed_times)]}' for i in range(count)]


def preview(folder: Path, config: dict, metadata: dict) -> list[dict]:
    paths = scan_files(folder, bool(config['scan_subfolders']))
    schedule = schedule_values(config.get('start_date', ''), config['daily_times'], len(paths))
    basename_counts = {}
    for path in paths:
        key = path.name.casefold()
        basename_counts[key] = basename_counts.get(key, 0) + 1
    result = []
    for i, path in enumerate(paths):
        relative = path.relative_to(folder).as_posix()
        row = metadata.get(relative.casefold())
        if row is None and basename_counts[path.name.casefold()] == 1:
            row = metadata.get(path.name.casefold())
        row = row or {}
        title = (row.get('title') or path.stem).strip()
        if len(title) > 100:
            title = title[:100].rstrip()
        custom_schedule = (row.get('publish_at') or '').strip()
        if custom_schedule:
            datetime.strptime(custom_schedule, '%Y-%m-%d %H:%M')
        result.append({
            'filename': relative,
            'path': str(path),
            'title': title,
            'description': (row.get('description') or config.get('default_description', '')).strip(),
            'tags': (row.get('tags') or config.get('default_tags', '')).strip(),
            'publish_at': custom_schedule or schedule[i],
            'size_mb': round(path.stat().st_size / (1024 * 1024), 2),
        })
    return result


def save_preview(rows: list[dict], file: Path) -> None:
    cols = ['filename', 'title', 'description', 'tags', 'publish_at', 'size_mb', 'path']
    with file.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows([{k: row.get(k, '') for k in cols} for row in rows])
