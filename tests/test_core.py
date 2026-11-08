import tempfile
import unittest
from pathlib import Path
from core import preview, read_metadata, schedule_values, DEFAULT_CONFIG

class CoreTests(unittest.TestCase):
    def test_schedule(self):
        self.assertEqual(schedule_values('2026-11-12', ['19:00','08:00'], 3), [
            '2026-11-12 08:00', '2026-11-12 19:00', '2026-11-13 08:00'])

    def test_scan_and_metadata(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root)
            (p/'video 01.mp4').write_bytes(b'abc')
            (p/'other.txt').write_text('ignore')
            (p/'metadata.csv').write_text('filename,title,description,tags,publish_at\nvideo 01.mp4,Tiêu đề riêng,,tag1,2026-11-13 09:00\n',encoding='utf-8')
            cfg = dict(DEFAULT_CONFIG, start_date='2026-11-12')
            rows = preview(p, cfg, read_metadata(p/'metadata.csv'))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['title'], 'Tiêu đề riêng')
            self.assertEqual(rows[0]['publish_at'], '2026-11-13 09:00')

if __name__ == '__main__':
    unittest.main()
