"""Local-only settings, Windows DPAPI secrets, and durable upload history."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import sqlite3
import subprocess
from contextlib import contextmanager
from pathlib import Path

PLAYLIST_TITLE = 'Video uploads'
DEFAULTS = {'playlist_title': PLAYLIST_TITLE, 'privacy_status': 'unlisted',
            'made_for_kids': False, 'expected_email': '', 'channel_id': '', 'playlist_id': ''}


def local_directory() -> Path:
    base = Path(os.environ['LOCALAPPDATA']) if os.name == 'nt' else Path.home() / '.local' / 'share'
    folder = base / 'YouTubeAutoUploader'
    folder.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        # Remove inherited access and grant only the current Windows identity.
        sid = subprocess.check_output(['whoami', '/user', '/fo', 'csv', '/nh'],
                                      text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        import csv
        identity = next(csv.reader([sid.strip()]))[1]
        subprocess.run(['icacls', str(folder), '/inheritance:r', '/grant:r',
                        f'*{identity}:(OI)(CI)F'], check=True, capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        folder.chmod(0o700)
    return folder


def atomic_write(path: Path, data: bytes):
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)


def _dpapi(data: bytes, decrypt=False) -> bytes:
    if os.name != 'nt':
        raise RuntimeError('Lưu token yêu cầu Windows DPAPI; không lưu token dạng rõ.')
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    source_buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    api = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        ok = api.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1,
                                   ctypes.byref(target))
    else:
        ok = api.CryptProtectData(ctypes.byref(source), 'YouTube Auto Uploader', None,
                                 None, None, 1, ctypes.byref(target))
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


class Settings:
    def __init__(self, folder: Path):
        self.path = folder / 'settings.json'
        self.data = dict(DEFAULTS)
        if self.path.exists():
            self.data.update(json.loads(self.path.read_text(encoding='utf-8')))
        if self.data['privacy_status'] not in ('private', 'unlisted', 'public'):
            raise ValueError('Visibility không hợp lệ trong settings.json')
        if type(self.data['made_for_kids']) is not bool:
            raise ValueError('made_for_kids phải là true hoặc false')

    def save(self):
        atomic_write(self.path, json.dumps(self.data, ensure_ascii=False, indent=2).encode('utf-8'))

    def bind_channel(self, channel_id):
        if self.data['channel_id'] != channel_id:
            self.data.update(channel_id=channel_id, playlist_id='')
        self.save()


class SecretStore:
    def __init__(self, folder: Path):
        self.folder = folder

    def write(self, name: str, value: dict):
        atomic_write(self.folder / (name + '.bin'), _dpapi(json.dumps(value).encode('utf-8')))

    def read(self, name: str):
        path = self.folder / (name + '.bin')
        return json.loads(_dpapi(path.read_bytes(), decrypt=True)) if path.exists() else None


def fingerprint(path: Path, progress=lambda value: None) -> str:
    before = path.stat()
    digest = hashlib.sha256()
    done = 0
    with path.open('rb') as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
            done += len(block)
            progress(done / max(before.st_size, 1))
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('Tệp thay đổi trong khi đọc. Hãy dùng bản đã tải offline và ổn định.')
    return digest.hexdigest()


class History:
    def __init__(self, folder: Path):
        self.path = folder / 'history.sqlite3'
        with self.connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY, channel_id TEXT NOT NULL, sha256 TEXT NOT NULL,
                path TEXT NOT NULL, title TEXT NOT NULL, playlist_id TEXT NOT NULL,
                privacy TEXT NOT NULL, kids INTEGER NOT NULL, state TEXT NOT NULL,
                video_id TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
                verified TEXT NOT NULL DEFAULT '',
                updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(channel_id, sha256))''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def find(self, channel, digest):
        with self.connection() as db:
            row = db.execute('SELECT * FROM uploads WHERE channel_id=? AND sha256=?',
                             (channel, digest)).fetchone()
            return dict(row) if row else None

    def get(self, record_id):
        with self.connection() as db:
            row = db.execute('SELECT * FROM uploads WHERE id=?', (record_id,)).fetchone()
            if not row:
                raise ValueError('Không tìm thấy bản ghi upload')
            return dict(row)

    def claim(self, channel, digest, row, playlist, privacy, kids):
        with self.connection() as db:
            cursor = db.execute('''INSERT INTO uploads
                (channel_id,sha256,path,title,playlist_id,privacy,kids,state)
                VALUES (?,?,?,?,?,?,?,'Uploading')''',
                (channel, digest, row['path'], row['title'], playlist, privacy, int(kids)))
            return cursor.lastrowid

    def update(self, record_id, **values):
        allowed = {'state', 'video_id', 'error', 'verified'}
        if not values or not set(values) <= allowed:
            raise ValueError('Trường lịch sử không hợp lệ')
        with self.connection() as db:
            fields = ','.join(f'{key}=?' for key in values)
            db.execute(f'UPDATE uploads SET {fields},updated=CURRENT_TIMESTAMP WHERE id=?',
                       (*values.values(), record_id))

    def recent(self, channel=None):
        with self.connection() as db:
            if channel:
                rows = db.execute('SELECT * FROM uploads WHERE channel_id=? ORDER BY id DESC', (channel,))
            else:
                rows = db.execute('SELECT * FROM uploads ORDER BY id DESC')
            return [dict(row) for row in rows]


class InstanceLock:
    """Prevent two app processes from mutating the same local state."""
    def __init__(self, folder: Path):
        self.stream = (folder / 'app.lock').open('a+b')
        self.stream.write(b'0')
        self.stream.flush()
        self.stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                self.stream.close()
                raise RuntimeError('Ứng dụng đang mở ở cửa sổ khác.') from None

    def close(self):
        self.stream.close()
