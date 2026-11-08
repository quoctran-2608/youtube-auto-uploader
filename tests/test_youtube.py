import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

from storage import History, Settings, PLAYLIST_TITLE, fingerprint
from youtube_client import YouTubeClient, video_body, youtube_http, SCOPES


class YouTubeTests(unittest.TestCase):
    def test_account_configuration_is_local_and_playlist_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            settings = Settings(folder)
            self.assertEqual(settings.data['expected_email'], '')
            settings.data.update(expected_email='owner@example.com', playlist_title='My private playlist')
            settings.save()
            loaded = Settings(folder)
            self.assertEqual(loaded.data['expected_email'], 'owner@example.com')
            self.assertEqual(loaded.data['playlist_title'], 'My private playlist')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.settings = Settings(self.folder)
        self.settings.data['expected_email'] = 'owner@example.com'
        self.history = History(self.folder)
        self.api = MagicMock()
        self.client = YouTubeClient(None, self.settings, self.history, self.api)
        self.channel = {'id': 'channel-a', 'snippet': {'title': 'My channel'}}
        self.playlist = {'id': 'playlist-a', 'snippet': {'title': PLAYLIST_TITLE, 'channelId': 'channel-a'}}
        self.api.channels.return_value.list.return_value.execute.return_value = {'items': [self.channel]}
        self.api.playlists.return_value.list.return_value.execute.return_value = {'items': [self.playlist]}
        self.client.identify()
        self.client.channel_confirmed = True
        self.path = self.folder / 'clip.mp4'
        self.path.write_bytes(b'offline-test-video')
        self.row = {'path': str(self.path), 'title': 'Title', 'description': 'Description', 'tags': 'one;two',
                    'publish_at': '2026-11-12 08:00'}
        self.video_id = 'abcdefghijk'
        self.api.videos.return_value.list.return_value.execute.return_value = {'items': [{
            'snippet': {'channelId': 'channel-a'},
            'status': {'privacyStatus': 'unlisted', 'selfDeclaredMadeForKids': False}}]}

    def upload_response(self):
        self.api.videos.return_value.insert.return_value.next_chunk.return_value = (None, {'id': self.video_id})

    def record(self):
        key = self.history.claim('channel-a', fingerprint(self.path), self.row, 'playlist-a', 'unlisted', False)
        self.history.update(key, video_id=self.video_id, state='Playlist Pending')
        return key

    def test_defaults_never_send_schedule(self):
        body = video_body(self.row)
        self.assertEqual(body['status'], {'privacyStatus': 'unlisted', 'selfDeclaredMadeForKids': False})
        self.assertNotIn('publishAt', json.dumps(body))
        self.assertEqual(video_body(self.row, 'private', True)['status']['selfDeclaredMadeForKids'], True)

    def test_playlist_failure_persists_id_retry_does_not_upload(self):
        self.upload_response()
        self.api.playlistItems.return_value.list.return_value.execute.return_value = {'items': []}
        self.api.playlistItems.return_value.insert.return_value.execute.side_effect = OSError('offline')
        result = self.client.upload(self.row)
        self.assertEqual(result['state'], 'Playlist Pending')
        self.assertEqual(result['video_id'], self.video_id)
        self.assertTrue(result['error'])
        self.assertEqual(self.api.videos.return_value.insert.call_count, 1)
        # A lost response may have succeeded server-side. List first on retry.
        self.api.playlistItems.return_value.list.return_value.execute.return_value = {'items': [{'id': 'existing'}]}
        result = self.client.finish(result['id'])
        self.assertEqual(result['state'], 'Uploaded')
        self.assertTrue(result['verified'])
        self.assertEqual(self.api.videos.return_value.insert.call_count, 1)
        self.assertEqual(self.api.playlistItems.return_value.insert.call_count, 1)

    def test_upload_success_checks_membership_and_status(self):
        self.upload_response()
        self.api.playlistItems.return_value.list.return_value.execute.side_effect = [
            {'items': []}, {'items': [{'id': 'new-item'}]}]
        result = self.client.upload(self.row)
        self.assertEqual(result['state'], 'Uploaded')
        self.assertTrue(result['verified'])
        self.assertEqual(result['error'], '')
        arguments = self.api.videos.return_value.insert.call_args.kwargs
        self.assertEqual(arguments['body']['status']['privacyStatus'], 'unlisted')
        self.assertFalse(arguments['notifySubscribers'])

    def test_playlist_index_lag_retries_only_reads(self):
        record_id = self.record()
        self.api.playlistItems.return_value.list.return_value.execute.side_effect = [
            {'items': []}, {'items': []}, {'items': []}, {'items': [{'id': 'new-item'}]}]
        with patch('youtube_client.time.sleep') as sleep:
            result = self.client.finish(record_id)
        self.assertEqual(result['state'], 'Uploaded')
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(self.api.playlistItems.return_value.insert.call_count, 1)
        self.api.videos.return_value.insert.assert_not_called()

    def test_duplicate_content_after_rename_blocked(self):
        self.record()
        renamed = self.folder / 'renamed.mp4'
        renamed.write_bytes(self.path.read_bytes())
        with self.assertRaisesRegex(ValueError, 'lịch sử'):
            self.client.upload(dict(self.row, path=str(renamed)))
        self.api.videos.return_value.insert.assert_not_called()

    def test_unknown_upload_never_restarts(self):
        self.api.videos.return_value.insert.return_value.next_chunk.side_effect = OSError('connection lost')
        with self.assertRaisesRegex(RuntimeError, 'chặn upload lại'):
            self.client.upload(self.row)
        self.assertEqual(self.history.recent()[0]['state'], 'Upload Unknown')
        # Restarting the history/client cannot clear the content reservation.
        self.client.history = History(self.folder)
        with self.assertRaisesRegex(ValueError, 'chưa rõ kết quả'):
            self.client.upload(self.row)
        self.assertEqual(self.api.videos.return_value.insert.call_count, 1)

    def test_playlist_exact_match_and_pagination(self):
        other = {'id': 'wrong', 'snippet': {'title': PLAYLIST_TITLE + ' ', 'channelId': 'channel-a'}}
        self.api.playlists.return_value.list.return_value.execute.side_effect = [
            {'items': [other], 'nextPageToken': 'next'}, {'items': [self.playlist]}]
        self.client.identify()
        self.assertEqual(self.client.playlist_id, 'playlist-a')
        calls = self.api.playlists.return_value.list.call_args_list
        self.assertTrue(calls[-1].kwargs['mine'])
        self.assertEqual(calls[-1].kwargs['pageToken'], 'next')

    def test_duplicate_titles_require_selection_and_persist_choice(self):
        self.settings.data['playlist_id'] = ''
        self.api.playlists.return_value.list.return_value.execute.return_value = {
            'items': [self.playlist, dict(self.playlist, id='playlist-b')]}
        self.client.identify()
        self.assertEqual(self.client.playlist_id, '')
        self.client.select_playlist('playlist-b')
        self.client.identify()
        self.assertEqual(self.client.playlist_id, 'playlist-b')

    def test_changed_channel_clears_playlist(self):
        new = {'id': 'channel-b', 'snippet': {'title': 'Other channel'}}
        self.api.channels.return_value.list.return_value.execute.return_value = {'items': [new]}
        self.client.identify()
        self.assertEqual(self.client.playlist_id, '')
        self.assertEqual(Settings(self.folder).data['playlist_id'], '')
        self.assertFalse(self.client.channel_confirmed)

    def test_wrong_playlist_owner_blocks_before_upload(self):
        self.api.playlists.return_value.list.return_value.execute.return_value = {'items': [{
            'snippet': {'title': PLAYLIST_TITLE, 'channelId': 'different'}}]}
        with self.assertRaisesRegex(ValueError, 'đúng kênh'):
            self.client.upload(self.row)
        self.api.videos.return_value.insert.assert_not_called()

    def test_actual_privacy_mismatch_is_not_passed(self):
        record_id = self.record()
        self.api.videos.return_value.list.return_value.execute.return_value = {'items': [{
            'snippet': {'channelId': 'channel-a'},
            'status': {'privacyStatus': 'private', 'selfDeclaredMadeForKids': False}}]}
        result = self.client.verify_video(record_id)
        self.assertFalse(result['verified'])
        self.assertIn('chưa khớp', result['error'])
        self.api.videos.return_value.update.assert_not_called()

    def test_rejected_upload_is_not_verified(self):
        record_id = self.record()
        self.api.videos.return_value.list.return_value.execute.return_value = {'items': [{
            'snippet': {'channelId': 'channel-a'}, 'status': {'uploadStatus': 'rejected',
            'privacyStatus': 'unlisted', 'selfDeclaredMadeForKids': False}}]}
        result = self.client.verify_video(record_id)
        self.assertFalse(result['verified'])
        self.assertIn('từ chối', result['error'])

    def test_defaults_persist(self):
        self.settings.data.update(privacy_status='private', made_for_kids=True)
        self.settings.save()
        loaded = Settings(self.folder)
        self.assertEqual(loaded.data['privacy_status'], 'private')
        self.assertTrue(loaded.data['made_for_kids'])

    def test_oauth_wrong_email_does_not_save_token_or_connect(self):
        secrets = MagicMock()
        secrets.read.side_effect = [{'installed': {'client_id': 'offline-test'}}, None]
        self.client.secrets = secrets
        credentials = MagicMock()
        credentials.has_scopes.return_value = True
        credentials.granted_scopes = list(SCOPES)
        flow = MagicMock()
        flow.run_local_server.return_value = credentials
        session = MagicMock()
        session.get.return_value.json.return_value = {'email': 'wrong@example.com', 'email_verified': True}
        with patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_config', return_value=flow), \
             patch('google.auth.transport.requests.AuthorizedSession', return_value=session):
            with self.assertRaisesRegex(ValueError, 'đúng owner'):
                self.client.connect()
        secrets.write.assert_not_called()
        self.assertIsNone(self.client.service)
        self.assertIsNone(self.client.channel)
        self.assertFalse(self.client.channel_confirmed)

    def test_missing_oauth_scope_does_not_connect(self):
        secrets = MagicMock()
        secrets.read.side_effect = [{'installed': {'client_id': 'offline-test'}}, None]
        self.client.secrets = secrets
        credentials = MagicMock()
        credentials.has_scopes.return_value = True
        credentials.granted_scopes = ['openid']
        flow = MagicMock()
        flow.run_local_server.return_value = credentials
        with patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_config', return_value=flow):
            with self.assertRaisesRegex(ValueError, 'Chưa cấp đủ quyền'):
                self.client.connect()
        secrets.write.assert_not_called()

    def test_wrong_reconcile_owner_blocked(self):
        record_id = self.history.claim('channel-a', fingerprint(self.path), self.row, 'playlist-a', 'unlisted', False)
        self.api.videos.return_value.list.return_value.execute.return_value = {'items': [{
            'snippet': {'channelId': 'different'}}]}
        with self.assertRaisesRegex(ValueError, 'không thuộc'):
            self.client.reconcile(record_id, self.video_id)
        self.assertEqual(self.history.get(record_id)['video_id'], '')

    def test_real_http_transport_handles_308_resumable_chunks(self):
        from google.auth.credentials import AnonymousCredentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        received = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200)
                self.send_header('Location', f'http://127.0.0.1:{self.server.server_port}/session')
                self.send_header('Content-Length', '0')
                self.end_headers()

            def do_PUT(self):
                received.append(self.rfile.read(int(self.headers['Content-Length'])))
                first = len(received) == 1
                data = b'' if first else b'{"id":"abcdefghijk"}'
                self.send_response(308 if first else 200)
                if first:
                    # Intentionally NO Location: this is Resume Incomplete.
                    self.send_header('Range', 'bytes=0-7')
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        transport = youtube_http(AnonymousCredentials())
        self.assertNotIn(308, transport.http.redirect_codes)
        self.assertIn(301, transport.http.redirect_codes)
        api = build('youtube', 'v3', http=transport, cache_discovery=False)
        self.path.write_bytes(b'1234567890abcdef')
        media = MediaFileUpload(str(self.path), chunksize=8, resumable=True)
        try:
            request = api.videos().insert(part='snippet,status', body=video_body(self.row), media_body=media)
            request.uri = f'http://127.0.0.1:{server.server_port}/start'
            status, body = request.next_chunk()
            self.assertEqual(status.progress(), 0.5)
            self.assertIsNone(body)
            _, body = request.next_chunk()
            self.assertEqual(body['id'], self.video_id)
            self.assertEqual(received, [b'12345678', b'90abcdef'])
        finally:
            media.stream().close()
            transport.http.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
