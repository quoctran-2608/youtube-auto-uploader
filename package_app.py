"""Build a source-only ZIP; never walks local credentials, videos or environments."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent
FILES = ['app.py', 'core.py', 'storage.py', 'youtube_client.py', 'upload_queue.py', 'config.json',
         'metadata.csv', 'README.md', 'START.bat', 'requirements.txt',
         'requirements-lock.txt', '.gitignore', 'package_app.py',
         'SHARING.md', 'README_FIRST.txt', 'build_windows.py', 'requirements-build.txt', 'smoke_check.py',
         'tests/__init__.py', 'tests/test_core.py', 'tests/test_youtube.py', 'tests/test_app.py', 'tests/test_queue.py']


def package():
    for name in FILES:
        path = ROOT / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f'Missing or unsafe source file: {name}')
    destination = ROOT / 'dist' / 'youtube-auto-uploader-v0.5.zip'
    destination.parent.mkdir(exist_ok=True)
    with ZipFile(destination, 'w', ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(ROOT / name, f'youtube-auto-uploader-v0.5/{name}')
    return destination


if __name__ == '__main__':
    print(package())
