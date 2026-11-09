"""Windows UI lifecycle tests with isolated local state and no Google access."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app import UploaderApp
from storage import Settings


@unittest.skipUnless(os.name == 'nt', 'Windows desktop app')
class StartupTests(unittest.TestCase):
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
                    return {'id': len(app.client.upload.call_args_list), 'video_id': 'abcdefghijk',
                            'state': 'Uploaded', 'verified': 'yes', 'error': ''}
                app.client.upload = MagicMock(side_effect=upload)
                with patch('app.messagebox.askyesno', return_value=True) as confirm:
                    app.upload_selected()
                    self.pump(app, lambda: len(app.upload_queue.all()) == 2 and all(x['state'] == 'done' for x in app.upload_queue.all()))
                    confirm.assert_called_once()
                self.assertEqual([call.args[0]['title'] for call in app.client.upload.call_args_list], ['one', 'two'])
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
