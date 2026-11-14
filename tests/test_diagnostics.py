import tempfile
import unittest
from pathlib import Path

from diagnostics import copy_for_inspection


class CopyTests(unittest.TestCase):
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
