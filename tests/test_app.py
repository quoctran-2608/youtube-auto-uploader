"""Windows UI lifecycle tests with isolated local state and no Google access."""
import os
import gc
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app import UploaderApp
from storage import Settings, fingerprint


@unittest.skipUnless(os.name == 'nt', 'Windows desktop app')
class StartupTests(unittest.TestCase):
    def tearDown(self):
        # Dispose Tk cycles on the UI thread before another test starts workers.
        gc.collect()

    def test_auto_find_deletes_successful_clips_without_selection_after_one_confirmation(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'nested').mkdir()
            uploaded = folder / 'nested' / 'uploaded.mp4'
            untouched = folder / 'not-uploaded.mp4'
            uploaded.write_bytes(b'uploaded')
            untouched.write_bytes(b'pending')
            with patch('app.local_directory', return_value=folder), patch.object(UploaderApp, 'startup'):
                app = UploaderApp()
            try:
                app.client.channel = {'id': 'demo', 'snippet': {'title': 'Channel'}}
                app.settings.data['queue_paused'] = True
                app.folder.set(temp)
                row = {'path': str(uploaded), 'title': 'Uploaded'}
                record = app.history.claim('demo', fingerprint(uploaded), row, 'playlist', 'unlisted', False)
                app.history.update(record, state='Uploaded', video_id='abcdefghijk', verified='yes')
                self.assertFalse(app.table.selection())
                with patch('app.messagebox.askyesno', return_value=False) as confirm:
                    app.find_and_delete_uploaded()
                    self.pump(app, lambda: not app.busy)
                    confirm.assert_called_once()
                self.assertTrue(uploaded.exists())
                with patch('app.messagebox.askyesno', return_value=True) as confirm:
                    app.find_and_delete_uploaded()
                    self.pump(app, lambda: not app.busy)
                    confirm.assert_called_once()
                self.assertFalse(uploaded.exists())
                self.assertTrue(untouched.exists())
                self.assertEqual(app.table.set(app.table.get_children()[0], 'state'), 'Đã xoá trong máy')
                self.assertEqual(app.history.get(record)['state'], 'Uploaded')
            finally:
                for identifier in app.tk.call('after', 'info'):
                    app.after_cancel(identifier)
                app.lock.close()
                app.destroy()

    def test_delete_confirmation_keeps_row_until_rescan(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            path = folder / 'clip.mp4'
            path.write_bytes(b'uploaded clip')
            with patch('app.local_directory', return_value=folder), patch.object(UploaderApp, 'startup'):
                app = UploaderApp()
            try:
                app.client.channel = {'id': 'demo', 'snippet': {'title': 'Channel'}}
                app.settings.data['queue_paused'] = True
                app.folder.set(temp)
                app.scan()
                self.pump(app, lambda: len(app.rows) == 1 and not app.busy)
                record = app.history.claim('demo', fingerprint(path), app.rows[0], 'playlist', 'unlisted', False)
                app.history.update(record, state='Uploaded', video_id='abcdefghijk', verified='yes')
                app.refresh_statuses()
                tree_id = app.table.get_children()[0]
                app.table.selection_set(tree_id)
                with patch('app.messagebox.askyesno', return_value=False):
                    app.delete_selected()
                self.assertTrue(path.exists())
                with patch('app.messagebox.askyesno', return_value=True) as confirm:
                    app.delete_selected()
                    self.pump(app, lambda: not app.busy)
                    confirm.assert_called_once()
                self.assertFalse(path.exists())
                self.assertEqual(len(app.table.get_children()), 1)
                app.refresh_statuses()
                self.assertEqual(app.table.set(tree_id, 'state'), 'Đã xoá trong máy')
                self.assertEqual(app.history.get(record)['state'], 'Uploaded')
                app.scan()
                self.pump(app, lambda: not app.busy)
                self.assertEqual(len(app.table.get_children()), 0)
            finally:
                for identifier in app.tk.call('after', 'info'):
                    app.after_cancel(identifier)
                app.lock.close()
                app.destroy()

    def pump(self, app, condition):
        deadline = time.monotonic() + 4
        while not condition() and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)
        self.assertTrue(condition())

    def test_reopen_restores_connection_folder_and_defaults_without_prompts(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'clip.mp4').write_bytes(b'offline')
            settings = Settings(folder)
            settings.data.update(expected_email='owner@example.com', last_folder=temp,
                privacy_status='private', made_for_kids=True, approved_channel_id='demo',
                approved_email='owner@example.com')
            settings.save()
            for _ in range(2):
                with patch('app.local_directory', return_value=folder):
                    app = UploaderApp()
                try:
                    app.client.secrets = MagicMock()
                    app.client.secrets.read.return_value = {'fake': True}
                    def connect(**kwargs):
                        self.assertFalse(kwargs['interactive'])
                        app.client.channel = {'id': 'demo', 'snippet': {'title': 'Example channel'}}
                        app.client.channel_confirmed = True
                        app.client.playlist_id = 'example-playlist'
                        app.client.playlists = [{'id': 'example-playlist'}]
                        return app.client.channel
                    app.client.connect = MagicMock(side_effect=connect)
                    with patch('app.messagebox.askyesno') as confirm, patch('app.messagebox.showerror') as error:
                        self.pump(app, lambda: len(app.rows) == 1 and not app.busy)
                        confirm.assert_not_called()
                        error.assert_not_called()
                    app.client.connect.assert_called_once_with(interactive=False)
                    self.assertEqual(app.folder.get(), temp)
                    self.assertEqual(app.privacy.get(), 'private')
                    self.assertTrue(app.kids.get())
                    self.assertEqual(app.settings_window.state(), 'withdrawn')
                    self.assertFalse(app.reconnect.winfo_manager())
                finally:
                    for identifier in app.tk.call('after', 'info'):
                        app.after_cancel(identifier)
                    app.lock.close()
                    app.destroy()

    def test_multiple_selection_is_uploaded_sequentially_after_one_confirmation(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with patch('app.local_directory', return_value=folder), patch.object(UploaderApp, 'startup'):
                app = UploaderApp()
            try:
                app.client.channel = {'id': 'demo', 'snippet': {'title': 'Channel'}}
                app.client.channel_confirmed = True
                app.client.playlist_id = 'playlist'
                app.rows = []
                for name in ('one', 'two'):
                    row = {'path': str(folder / (name + '.mp4')), 'filename': name + '.mp4',
                           'title': name, 'tags': '', 'description': '', 'size_mb': 1, 'publish_at': ''}
                    app.rows.append(row)
                    app.table.insert('', 'end', values=(row['filename'], name, 1, ''))
                app.table.selection_set(app.table.get_children())
                def upload(row, privacy, kids, progress):
                    return {'id': len(app.client.upload_or_resume.call_args_list), 'video_id': 'abcdefghijk',
                            'state': 'Uploaded', 'verified': 'yes', 'error': ''}
                app.client.upload_or_resume = MagicMock(side_effect=upload)
                with patch('app.messagebox.askyesno', return_value=True) as confirm:
                    app.upload_selected()
                    self.pump(app, lambda: len(app.upload_queue.all()) == 2 and all(x['state'] == 'done' for x in app.upload_queue.all()))
                    confirm.assert_called_once()
                self.assertEqual([call.args[0]['title'] for call in app.client.upload_or_resume.call_args_list], ['one', 'two'])
            finally:
                for identifier in app.tk.call('after', 'info'):
                    app.after_cancel(identifier)
                app.lock.close()
                app.destroy()

    def test_scan_always_includes_subfolders_despite_old_config(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'nested').mkdir()
            (folder / 'nested' / 'video.mp4').write_bytes(b'video')
            with patch('app.local_directory', return_value=folder), patch.object(UploaderApp, 'startup'):
                app = UploaderApp()
            try:
                app.folder.set(temp)
                with patch('app.read_config', return_value={'scan_subfolders': False, 'daily_times': ['08:00']}):
                    app.scan()
                    self.pump(app, lambda: len(app.rows) == 1 and not app.busy)
                self.assertEqual(app.rows[0]['filename'], 'nested/video.mp4')
                self.assertEqual(app.table.item(app.table.get_children()[0])['values'][0], 1)
            finally:
                for identifier in app.tk.call('after', 'info'):
                    app.after_cancel(identifier)
                app.lock.close()
                app.destroy()

    def test_status_and_estimate_show_wait_and_known_progress(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with patch('app.local_directory', return_value=folder), patch.object(UploaderApp, 'startup'):
                app = UploaderApp()
            try:
                app.client.channel = {'id': 'demo', 'snippet': {'title': 'Channel'}}
                app.client.channel_confirmed = True
                app.client.playlist_id = 'playlist'
                row = {'path': str(folder / 'clip.mp4'), 'filename': 'clip.mp4', 'title': 'Clip', 'size_mb': 100}
                app.rows = [row]
                item_id = app.table.insert('', 'end', values=(1, 'clip.mp4', 'Clip', 100, ''))
                app.upload_queue.add([row], 'demo', 'playlist', 'unlisted', False)
                app.refresh_statuses()
                self.assertIn('Chờ tải', app.table.set(item_id, 'state'))
                app.refresh_eta()
                self.assertIn('chờ dữ liệu', app.eta.get())
                queued = app.upload_queue.next()
                app.upload_queue.update(queued['id'], state='waiting', retry_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
                app.refresh_eta()
                self.assertIn('Chờ hạn mức', app.eta.get())
                app.upload_queue.update(queued['id'], state='done', retry_at='')
                app.refresh_statuses()
                self.assertIn('Đã tải', app.table.set(item_id, 'state'))
                app.upload_queue.update(queued['id'], state='attention')
                app.refresh_statuses()
                self.assertIn('Cần kiểm tra', app.table.set(item_id, 'state'))
            finally:
                for identifier in app.tk.call('after', 'info'):
                    app.after_cancel(identifier)
                app.lock.close()
                app.destroy()

    def test_startup_offline_and_missing_folder_do_not_loop_or_prompt(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            settings = Settings(folder)
            settings.data.update(expected_email='owner@example.com', last_folder=str(folder / 'missing'))
            settings.save()
            with patch('app.local_directory', return_value=folder):
                app = UploaderApp()
            try:
                app.client.secrets = MagicMock()
                app.client.secrets.read.return_value = {'fake': True}
                app.client.connect = MagicMock(side_effect=RuntimeError('offline'))
                with patch('app.messagebox.showerror') as error, patch('app.preview', side_effect=ValueError('missing')) as scan:
                    self.pump(app, lambda: scan.called and not app.busy)
                    for _ in range(20):
                        app.update()
                    self.assertEqual(scan.call_count, 1)
                    error.assert_not_called()
                self.assertTrue(app.reconnect.winfo_manager())
                self.assertIn('disabled', app.upload_button.state())
            finally:
                for identifier in app.tk.call('after', 'info'):
                    app.after_cancel(identifier)
                app.lock.close()
                app.destroy()
