"""Offline checks for the packaged Windows runtime; never loads real credentials."""
import json
import tempfile
from pathlib import Path


def run_check(root: Path, result_path: Path):
    import tkinter as tk
    from google.auth.credentials import AnonymousCredentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from core import read_config
    from storage import History, SecretStore
    from youtube_client import youtube_http

    window = tk.Tk()
    window.withdraw()
    window.update_idletasks()
    window.destroy()
    read_config(root / 'config.json')
    assert (root / 'metadata.csv').exists()
    http = youtube_http(AnonymousCredentials())
    assert 308 not in http.http.redirect_codes
    api = build('youtube', 'v3', http=http, cache_discovery=False)
    assert api.videos() and api.playlistItems()
    # Construct a flow without opening a browser or contacting Google.
    flow = InstalledAppFlow.from_client_config({'installed': {
        'client_id': 'offline-check', 'client_secret': 'offline-check',
        'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
        'token_uri': 'https://oauth2.googleapis.com/token'}}, scopes=['openid'])
    assert flow.client_config['client_id'] == 'offline-check'
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        store = SecretStore(folder)
        store.write('test', {'offline': True})
        assert store.read('test') == {'offline': True}
        assert History(folder).recent() == []
    http.http.close()
    result_path.write_text(json.dumps({'tkinter': True, 'youtube_sdk': True,
        'oauth_sdk': True, 'resume_308': True, 'dpapi': True, 'sqlite': True,
        'external_config': True}), encoding='utf-8')
