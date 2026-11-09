import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from storage import History
from upload_queue import UploadQueue, pacific_midnight_after
from youtube_client import QuotaWait

UTC = timezone.utc


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.history = History(Path(self.temp.name))
        self.queue = UploadQueue(self.history)
        self.client = MagicMock(channel={'id': 'channel'}, channel_confirmed=True, playlist_id='list')
        self.rows = [{'path': 'a.mp4', 'title': 'A'}, {'path': 'b.mp4', 'title': 'B'}]
        self.queue.add(self.rows, 'channel', 'list', 'unlisted', False)

    def test_persists_sequence_and_does_not_duplicate_pending_items(self):
        self.assertEqual(self.queue.add(self.rows, 'channel', 'list', 'unlisted', False), 0)
        self.client.upload.return_value = {'id': 1, 'state': 'Uploaded', 'verified': 'yes', 'error': ''}
        self.queue.process(self.queue.next(), self.client, lambda *args: None)
        restored = UploadQueue(self.history)
        self.assertEqual(json.loads(restored.next()['row_json'])['title'], 'B')
        self.assertEqual(restored.all()[0]['state'], 'done')

    def test_quota_waits_until_pacific_midnight_and_survives_restart(self):
        now = datetime(2026, 7, 1, 12, tzinfo=UTC)
        self.client.upload.side_effect = QuotaWait('quotaExceeded')
        self.queue.process(self.queue.next(now), self.client, lambda *args: None, now)
        restored = UploadQueue(self.history)
        self.assertIsNone(restored.next(now))
        self.assertEqual(restored.all()[0]['retry_at'], '2026-07-02T07:05:00+00:00')
        self.assertIsNotNone(restored.next(datetime(2026, 7, 2, 7, 6, tzinfo=UTC)))

    def test_channel_limit_waits_24_hours(self):
        now = datetime(2026, 11, 9, 12, tzinfo=UTC)
        self.client.upload.side_effect = QuotaWait('uploadLimitExceeded')
        self.queue.process(self.queue.next(now), self.client, lambda *args: None, now)
        self.assertEqual(self.queue.all()[0]['retry_at'], '2026-11-10T12:00:00+00:00')

    def test_interrupted_is_never_automatically_uploaded_again(self):
        self.queue.update(self.queue.next()['id'], state='running')
        restored = UploadQueue(self.history)
        self.assertEqual(restored.all()[0]['state'], 'interrupted')
        self.assertEqual(json.loads(restored.next()['row_json'])['title'], 'B')

    def test_wrong_channel_never_uploads(self):
        self.client.channel = {'id': 'other'}
        with self.assertRaises(ValueError):
            self.queue.process(self.queue.next(), self.client, lambda *args: None)
        self.client.upload.assert_not_called()

    def test_pacific_midnight_dst_transitions(self):
        cases = [((2026, 3, 8, 9), (2026, 3, 9, 7)), ((2026, 11, 1, 8), (2026, 11, 2, 8)),
                 ((2026, 3, 7, 12), (2026, 3, 8, 8)), ((2026, 10, 31, 12), (2026, 11, 1, 7))]
        for source, target in cases:
            expected = datetime(*target, 5, tzinfo=UTC)
            self.assertEqual(pacific_midnight_after(datetime(*source, tzinfo=UTC)), expected)
