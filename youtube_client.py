"""OAuth and one-video uploads. Never changes channel or existing video settings."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from storage import fingerprint

SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl',
          'openid', 'https://www.googleapis.com/auth/userinfo.email']


def friendly_error(error):
    # Do not log HTTP URLs, headers, credentials or resumable session URIs.
    status = getattr(getattr(error, 'resp', None), 'status', None)
    if status:
        reason = 'API error'
        try:
            body = json.loads(error.content)
            reason = body['error']['errors'][0]['reason']
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            pass
        return f'YouTube API HTTP {status}: {reason}'
    if isinstance(error, (ValueError, RuntimeError, FileNotFoundError)):
        return str(error)
    return f'{type(error).__name__}: thao tác thất bại; kiểm tra mạng, OAuth và thử lại.'


def video_body(row, privacy='unlisted', kids=False):
    if privacy not in ('unlisted', 'private', 'public') or type(kids) is not bool:
        raise ValueError('Visibility hoặc Audience không hợp lệ')
    title = str(row['title']).strip()
    description = str(row.get('description', ''))
    if not title or len(title) > 100 or '<' in title or '>' in title:
        raise ValueError('Tiêu đề phải có 1–100 ký tự và không chứa < >.')
    if len(description.encode('utf-8')) > 5000 or '<' in description or '>' in description:
        raise ValueError('Mô tả tối đa 5000 byte và không chứa < >.')
    snippet = {'title': title, 'description': description, 'categoryId': '22'}
    tags = [t.strip() for t in row.get('tags', '').split(';') if t.strip()]
    if tags:
        snippet['tags'] = tags
    return {'snippet': snippet, 'status': {'privacyStatus': privacy,
                                         'selfDeclaredMadeForKids': kids}}


def youtube_http(credentials):
    from googleapiclient.http import build_http
    from google_auth_httplib2 import AuthorizedHttp
    # Google's transport excludes 308 from redirects: YouTube uses it for
    # Resume Incomplete with a Range header, not a Location header.
    transport = build_http()
    transport.timeout = 60
    return AuthorizedHttp(credentials, http=transport)


class YouTubeClient:
    def __init__(self, secrets, settings, history, service=None):
        self.secrets, self.settings, self.history = secrets, settings, history
        self.service = service
        self.channel = None
        self.email = ''
        self.channel_confirmed = False
        self.playlists = []
        self.playlist_id = ''

    def import_credentials(self, path):
        config = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        client = config.get('installed', {})
        if (not client.get('client_id') or not client.get('client_secret') or
                client.get('auth_uri') != 'https://accounts.google.com/o/oauth2/auth' or
                client.get('token_uri') != 'https://oauth2.googleapis.com/token'):
            raise ValueError('Cần JSON OAuth Client loại Desktop app tải từ Google Cloud.')
        self.secrets.write('credentials', config)
        self.service = None
        self.channel = None
        self.channel_confirmed = False
        self.playlist_id = ''
        # Old tokens belong to a different OAuth client and must not be reused.
        self.secrets.write('token', {})
        return client.get('project_id', '')

    def connect(self, new_login=False, interactive=True):
        from google.auth.transport.requests import Request, AuthorizedSession
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        self.channel_confirmed = False
        self.channel = None
        self.playlist_id = ''
        self.service = None
        expected_email = self.settings.data.get('expected_email', '').strip().casefold()
        if not expected_email:
            raise ValueError('Hãy cấu hình email tài khoản và tên playlist trên máy này trước.')
        config = self.secrets.read('credentials')
        if not config:
            raise ValueError('Hãy nhập OAuth credentials JSON loại Desktop app trước.')
        token = None if new_login else self.secrets.read('token')
        creds = Credentials.from_authorized_user_info(token) if token else None
        if creds and not creds.has_scopes(SCOPES):
            creds = None
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                raise RuntimeError('Token hết hạn hoặc bị thu hồi. Chọn Đổi tài khoản / kênh để cấp quyền lại.') from None
        if not creds or not creds.valid:
            if not interactive:
                raise RuntimeError('Cần cấp quyền lại. Mở Cài đặt và chọn Kết nối YouTube.')
            flow = InstalledAppFlow.from_client_config(config, SCOPES, autogenerate_code_verifier=True)
            chrome_paths = [Path(os.environ.get(env, '')) / suffix for env, suffix in (
                ('PROGRAMFILES', 'Google/Chrome/Application/chrome.exe'),
                ('PROGRAMFILES(X86)', 'Google/Chrome/Application/chrome.exe'),
                ('LOCALAPPDATA', 'Google/Chrome/Application/chrome.exe'))]
            chrome = next((p for p in chrome_paths if p.is_file()), None) if os.name == 'nt' else None
            creds = flow.run_local_server(host='127.0.0.1', port=0, open_browser=True,
                browser=f'"{chrome}" %s' if chrome else None,
                timeout_seconds=300, prompt='consent select_account', login_hint=expected_email,
                authorization_prompt_message='', success_message='Đã nhận OAuth. Bạn có thể quay về YouTube Auto Uploader.')
        granted = creds.granted_scopes
        if not creds.has_scopes(SCOPES) or (granted is not None and not set(SCOPES) <= set(granted)):
            raise ValueError('Chưa cấp đủ quyền YouTube và email. Hãy kết nối lại.')
        session = AuthorizedSession(creds)
        try:
            response = session.get('https://openidconnect.googleapis.com/v1/userinfo', timeout=30)
            response.raise_for_status()
            user = response.json()
        finally:
            session.close()
        if user.get('email', '').casefold() != expected_email or not user.get('email_verified'):
            raise ValueError(f'Cần đăng nhập đúng {expected_email}; chưa chấp nhận tài khoản hiện tại.')
        self.secrets.write('token', json.loads(creds.to_json()))
        self.email = user['email']
        self.service = build('youtube', 'v3', http=youtube_http(creds),
                             cache_discovery=False)
        return self.identify()

    def identify(self):
        self.channel_confirmed = False
        self.playlist_id = ''
        channels = self.service.channels().list(part='snippet', mine=True, maxResults=50).execute()
        items = channels.get('items', [])
        if len(items) != 1:
            raise ValueError('Không xác định được duy nhất một kênh. Kết nối lại và chọn đúng kênh YouTube.')
        self.channel = items[0]
        self.settings.bind_channel(self.channel['id'])
        self.playlists = []
        token = None
        while True:
            response = self.service.playlists().list(part='snippet,contentDetails', mine=True,
                                                     maxResults=50, pageToken=token).execute()
            self.playlists.extend(p for p in response.get('items', [])
                                  if p['snippet']['title'] == self.settings.data['playlist_title'] and
                                  p['snippet']['channelId'] == self.channel['id'])
            token = response.get('nextPageToken')
            if not token:
                break
        saved = self.settings.data.get('playlist_id')
        matches = [p for p in self.playlists if p['id'] == saved]
        if len(self.playlists) == 1:
            self.select_playlist(self.playlists[0]['id'])
        elif matches:
            self.select_playlist(saved)
        else:
            self.settings.data['playlist_id'] = ''
            self.settings.save()
        self.channel_confirmed = (self.settings.data.get('approved_channel_id') == self.channel['id']
            and self.settings.data.get('approved_email') == self.settings.data.get('expected_email')
            and bool(self.playlist_id))
        return self.channel

    def approve_channel(self):
        if not self.channel:
            raise ValueError('Chưa kết nối kênh.')
        self.settings.data.update(approved_channel_id=self.channel['id'],
            approved_email=self.settings.data['expected_email'])
        self.settings.save()
        self.channel_confirmed = True

    def select_playlist(self, playlist_id):
        if not any(p['id'] == playlist_id for p in self.playlists):
            raise ValueError('Playlist không thuộc danh sách đã xác nhận của kênh này.')
        self.playlist_id = playlist_id
        self.settings.data['playlist_id'] = playlist_id
        if self.channel and self.settings.data.get('approved_channel_id') == self.channel['id'] and self.settings.data.get('approved_email') == self.settings.data.get('expected_email'):
            self.channel_confirmed = True
        self.settings.save()

    def validate_context(self, playlist_id):
        if not self.channel or not self.channel_confirmed:
            raise ValueError('Hãy xác nhận tên kênh và Channel ID trong giao diện trước.')
        channels = self.service.channels().list(part='id', mine=True).execute().get('items', [])
        if len(channels) != 1 or channels[0]['id'] != self.channel['id']:
            self.channel_confirmed = False
            raise ValueError('Kênh OAuth đã thay đổi. Hãy kết nối và xác nhận lại.')
        playlists = self.service.playlists().list(part='snippet', id=playlist_id).execute().get('items', [])
        if (len(playlists) != 1 or playlists[0]['snippet']['channelId'] != self.channel['id'] or
                playlists[0]['snippet']['title'] != self.settings.data['playlist_title']):
            self.playlist_id = ''
            self.settings.data['playlist_id'] = ''
            self.settings.save()
            raise ValueError('Playlist đã đổi tên, bị xóa hoặc không thuộc đúng kênh. Kết nối lại.')

    def membership(self, playlist_id, video_id):
        response = self.service.playlistItems().list(part='id', playlistId=playlist_id,
                                                   videoId=video_id, maxResults=50).execute()
        return bool(response.get('items'))

    def add_playlist(self, record_id):
        row = self.history.get(record_id)
        if not row['video_id']:
            raise ValueError('Chưa có Video ID; không được retry playlist bằng cách upload lại.')
        if not self.channel or row['channel_id'] != self.channel['id']:
            raise ValueError('Lịch sử này thuộc kênh khác. Hãy kết nối đúng kênh.')
        self.history.update(record_id, state='Playlist Pending', error='')
        try:
            self.validate_context(row['playlist_id'])
            if not self.membership(row['playlist_id'], row['video_id']):
                self.service.playlistItems().insert(part='snippet', body={'snippet': {
                    'playlistId': row['playlist_id'],
                    'resourceId': {'kind': 'youtube#video', 'videoId': row['video_id']}}}).execute()
            # Playlist reads can lag a successful insert. Retry only reads here.
            for attempt in range(4):
                if self.membership(row['playlist_id'], row['video_id']):
                    break
                if attempt < 3:
                    time.sleep(2 ** attempt)
            else:
                raise RuntimeError('YouTube chưa xác nhận video nằm trong playlist. Hãy retry playlist sau.')
            self.history.update(record_id, state='Uploaded', error='')
        except Exception as error:
            self.history.update(record_id, state='Playlist Pending', error=friendly_error(error))
        return self.history.get(record_id)

    def verify_video(self, record_id):
        row = self.history.get(record_id)
        try:
            items = self.service.videos().list(part='snippet,status', id=row['video_id']).execute().get('items', [])
            if len(items) != 1 or items[0]['snippet']['channelId'] != row['channel_id']:
                raise RuntimeError('Chưa đọc được video trên đúng kênh. Hãy kiểm tra lại sau.')
            actual = items[0]['status']
            if actual.get('uploadStatus') in ('failed', 'rejected', 'deleted'):
                raise RuntimeError('YouTube báo video thất bại/bị từ chối/đã xóa. Kiểm tra Studio; app không upload lại.')
            if (actual.get('privacyStatus') != row['privacy'] or
                    actual.get('selfDeclaredMadeForKids') is not bool(row['kids']) or actual.get('publishAt')):
                raise RuntimeError('Audience/Visibility thực tế chưa khớp yêu cầu. Xem YouTube Studio; app không tự sửa.')
            self.history.update(record_id, verified=json.dumps(actual), error='')
        except Exception as error:
            self.history.update(record_id, verified='', error=friendly_error(error))
        return self.history.get(record_id)

    def finish(self, record_id):
        row = self.add_playlist(record_id)
        playlist_error = row['error']
        verified = self.verify_video(record_id)
        errors = [e for e in (playlist_error, verified['error']) if e]
        self.history.update(record_id, error=' | '.join(errors))
        return self.history.get(record_id)

    def upload(self, row, privacy='unlisted', kids=False, progress=lambda value, text: None):
        from googleapiclient.http import MediaFileUpload
        if not self.playlist_id:
            raise ValueError('Chưa xác nhận playlist mặc định. Không upload.')
        body = video_body(row, privacy, kids)
        self.validate_context(self.playlist_id)
        path = Path(row['path'])
        if not path.is_file() or not path.stat().st_size:
            raise ValueError('Video không tồn tại, rỗng hoặc chưa tải offline.')
        stat = path.stat()
        digest = fingerprint(path, lambda fraction: progress(0, f'Đang kiểm tra SHA-256: {fraction:.0%}'))
        existing = self.history.find(self.channel['id'], digest)
        if existing:
            if existing['video_id']:
                raise ValueError(f"Video đã có trong lịch sử: {existing['video_id']}. Chỉ dùng Retry playlist / kiểm tra.")
            raise ValueError('Tệp đã có phiên upload chưa rõ kết quả. Đối chiếu YouTube Studio trước; không upload lại tự động.')
        media = MediaFileUpload(str(path), mimetype='application/octet-stream',
                                chunksize=8 * 1024 * 1024, resumable=True)
        try:
            if (stat.st_size, stat.st_mtime_ns) != (path.stat().st_size, path.stat().st_mtime_ns):
                raise ValueError('Tệp đã thay đổi sau khi kiểm tra; không upload.')
            request = self.service.videos().insert(part='snippet,status', body=body,
                                                   media_body=media, notifySubscribers=False)
            record_id = self.history.claim(self.channel['id'], digest, row, self.playlist_id, privacy, kids)
            try:
                response = None
                while response is None:
                    status, response = request.next_chunk(num_retries=5)
                    if status:
                        progress(status.progress() * 100, f'Đang upload {status.progress():.0%}')
                video_id = response.get('id', '')
                if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
                    raise RuntimeError('Phản hồi không có Video ID hợp lệ. Cần đối chiếu YouTube Studio.')
                # Persist ID BEFORE any progress/UI, playlist or verification requests.
                self.history.update(record_id, video_id=video_id, state='Playlist Pending', error='')
            except Exception as error:
                self.history.update(record_id, state='Upload Unknown', error=friendly_error(error))
                raise RuntimeError('Upload dừng, kết quả chưa chắc chắn. Đã chặn upload lại tệp này; kiểm tra YouTube Studio.') from None
        finally:
            media.stream().close()
        progress(100, f'Đã nhận Video ID: {video_id}; đang xác minh playlist và trạng thái.')
        return self.finish(record_id)

    def reconcile(self, record_id, video_id):
        """Manually attach a Studio-confirmed Video ID after an interrupted response."""
        row = self.history.get(record_id)
        if row['video_id'] or row['state'] not in ('Upload Unknown', 'Uploading'):
            raise ValueError('Chỉ đối chiếu bản ghi chưa có Video ID.')
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
            raise ValueError('Video ID cần đúng 11 ký tự (không phải URL).')
        self.validate_context(row['playlist_id'])
        items = self.service.videos().list(part='snippet', id=video_id).execute().get('items', [])
        if not items or items[0]['snippet']['channelId'] != row['channel_id']:
            raise ValueError('Video ID không thuộc kênh của bản ghi này.')
        self.history.update(record_id, video_id=video_id, state='Playlist Pending', error='')
        return self.finish(record_id)
