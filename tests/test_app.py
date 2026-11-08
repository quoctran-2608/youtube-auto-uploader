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
