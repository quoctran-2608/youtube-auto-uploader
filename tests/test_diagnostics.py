import tempfile
import unittest
from pathlib import Path

from diagnostics import copy_for_inspection, delete_uploaded_files, find_uploaded_files
from storage import History, fingerprint


class CopyTests(unittest.TestCase):
    def test_auto_find_recurses_and_matches_content_after_rename_without_deleting(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            history = History(root)
            source = root / 'original.mp4'
            source.write_bytes(b'good content')
            record = history.claim('channel', fingerprint(source), {'path': str(source), 'title': 'Original'}, 'playlist', 'unlisted', False)
            history.update(record, state='Uploaded', video_id='abcdefghijk', verified='yes')
            folder = root / 'videos'
            (folder / 'nested').mkdir(parents=True)
            renamed = folder / 'nested' / 'renamed.mp4'
            renamed.write_bytes(source.read_bytes())
            other = folder / 'not-uploaded.mp4'
            other.write_bytes(b'not uploaded')
            matches, count, failures = find_uploaded_files(folder, history, 'channel')
            self.assertEqual([row['path'] for row in matches], [str(renamed)])
            self.assertEqual(count, 2)
            self.assertFalse(failures)
            self.assertTrue(renamed.exists())
            self.assertTrue(other.exists())
            self.assertEqual(find_uploaded_files(folder, history, 'other-channel')[0], [])

    def test_delete_requires_verified_matching_content_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / 'clip.mp4'
            path.write_bytes(b'uploaded')
            row = {'path': str(path), 'title': 'Clip'}
            history = History(root)
            record_id = history.claim('channel', fingerprint(path), row, 'playlist', 'unlisted', False)
            deleted, failures = delete_uploaded_files([row], history, 'channel')
            self.assertFalse(deleted)
            self.assertTrue(failures)
            self.assertTrue(path.exists())
            history.update(record_id, state='Uploaded', video_id='abcdefghijk', verified='yes')
            path.write_bytes(b'replaced content')
            self.assertFalse(delete_uploaded_files([row], history, 'channel')[0])
            self.assertTrue(path.exists())
            path.write_bytes(b'uploaded')
            self.assertFalse(delete_uploaded_files([row], history, 'other-channel')[0])
            deleted, failures = delete_uploaded_files([row], history, 'channel')
            self.assertEqual(deleted, [str(path)])
            self.assertFalse(failures)
            self.assertFalse(path.exists())
            self.assertEqual(history.get(record_id)['video_id'], 'abcdefghijk')

    def test_copies_do_not_overwrite_same_names_or_originals(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for folder in ('a', 'b', 'out'):
                (root / folder).mkdir()
            first, second = root / 'a' / 'clip.mp4', root / 'b' / 'clip.mp4'
            first.write_bytes(b'first')
            second.write_bytes(b'second')
            output = root / 'out'
            (output / 'clip.mp4').write_bytes(b'existing')
            copied, failures = copy_for_inspection([{'path': str(first)}, {'path': str(second)}], output)
            self.assertFalse(failures)
            self.assertEqual([Path(p).read_bytes() for p in copied], [b'first', b'second'])
            self.assertEqual((output / 'clip.mp4').read_bytes(), b'existing')
            self.assertEqual(first.read_bytes(), b'first')
            self.assertEqual(second.read_bytes(), b'second')
