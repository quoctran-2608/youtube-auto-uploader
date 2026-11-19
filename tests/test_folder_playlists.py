import tempfile
import unittest
from pathlib import Path

from folder_playlists import Mp3Index, plan_history


class FolderPlaylistTests(unittest.TestCase):
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
