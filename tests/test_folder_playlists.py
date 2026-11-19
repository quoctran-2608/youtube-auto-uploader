import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from googleapiclient.errors import HttpError
from folder_playlists import Mp3Index, PlaylistBatch, plan_history


class FolderPlaylistTests(unittest.TestCase):
    def test_quota_checkpoints_failed_and_unattempted_moves_until_reset(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            batch = PlaylistBatch(root)
            proposals = [dict(record=dict(id=i, video_id=str(i), playlist_id='old', title=str(i)), target='New') for i in range(4)]
            batch.start('channel', proposals, True)
            error = HttpError(SimpleNamespace(status=403, reason='Forbidden'),
                              b'{"error":{"errors":[{"reason":"quotaExceeded"}]}}')
            client = MagicMock(channel={'id': 'channel'}, channel_confirmed=True)
            client.organize_video.side_effect = [None, ValueError('old playlist unavailable'), error]
            progress = MagicMock()
            before = datetime(2026, 11, 19, 12, tzinfo=timezone.utc)
            batch.run(client, progress, before)
            reopened = PlaylistBatch(root)
            saved = reopened.read()
            self.assertEqual([item['state'] for item in saved['items']], ['done', 'error', 'pending', 'pending'])
            self.assertIn('quotaExceeded', saved['reason'])
            client.organize_video.reset_mock(side_effect=True)
            reopened.run(client, progress, before)
            client.organize_video.assert_not_called()
            reopened.run(client, progress, datetime(2026, 11, 20, 8, 6, tzinfo=timezone.utc))
            self.assertEqual([call.args[0]['id'] for call in client.organize_video.call_args_list], [2, 3])
            self.assertEqual([item['state'] for item in reopened.read()['items']], ['done', 'error', 'done', 'done'])

    def test_saved_windows_parent_works_without_original_file(self):
        record = dict(video_id='video', path=r'D:\Old\Topic\clip.mp4')
        proposal, = plan_history([record])
        self.assertEqual(proposal['target'], 'Topic')

    def test_exact_near_and_ambiguous_mp3_matches(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / 'Topic'
            second = root / 'Other'
            first.mkdir()
            second.mkdir()
            long_name = 'Mot ten video du dai de kiem tra chuoi gan giong 1234567890'
            for folder, name in ((first, 'Bài giảng'), (first, 'Trùng'), (second, 'Trùng'), (first, long_name)):
                (folder / f'{name}.mp3').touch()
            records = [dict(video_id=str(i), path=f'D:/Exports/{name}.mp4') for i, name in
                       enumerate(('BÀI-GIẢNG', 'Trùng', long_name[:-1] + '1', 'Missing'))]
            exact, ambiguous, near, missing = plan_history(records, Mp3Index(root))
            self.assertEqual(exact['target'], 'Topic')
            self.assertTrue(exact['automatic'])
            self.assertEqual(near['target'], 'Topic')
            self.assertFalse(near['automatic'])
            self.assertTrue(near['detail'].startswith('Gần giống'))
            self.assertEqual(ambiguous['target'], '')
            self.assertEqual(missing['target'], '')
