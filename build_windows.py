"""Build a Windows portable folder with an explicit, credential-free ZIP manifest."""
from pathlib import Path
import os
import subprocess
import sys
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent


def build():
    if os.name != 'nt':
        raise RuntimeError('Build Windows trên Windows.')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
        '--onedir', '--windowed', '--name', 'YouTubeAutoUploader',
        '--collect-data', 'googleapiclient', '--collect-data', 'certifi',
        '--distpath', str(ROOT / 'dist' / 'windows'),
        '--workpath', str(ROOT / 'build' / 'windows'),
        '--specpath', str(ROOT / 'build'), str(ROOT / 'app.py')], cwd=ROOT, check=True)
    folder = ROOT / 'dist' / 'windows' / 'YouTubeAutoUploader'
    import shutil
    for name in ['config.json', 'metadata.csv', 'README.md', 'SHARING.md', 'README_FIRST.txt']:
        shutil.copyfile(ROOT / name, folder / name)
    # PyInstaller output is generated in its own directory; never copy AppData.
    archive_path = ROOT / 'dist' / 'youtube-auto-uploader-v0.8-windows-x64.zip'
    with ZipFile(archive_path, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                archive.write(path, Path('YouTubeAutoUploader') / path.relative_to(folder))
    return archive_path


if __name__ == '__main__':
    print(build())
