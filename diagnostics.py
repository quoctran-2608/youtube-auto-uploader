"""Local diagnostics and non-destructive copies for inspection."""
import shutil
from pathlib import Path
from storage import fingerprint


def error_advice(error, video_id=''):
    if 'quotaExceeded' in error or 'uploadLimitExceeded' in error:
        return 'YouTube đang giới hạn lượt tải. Giữ mục trong hàng đợi và chờ thời điểm thử lại.'
    if video_id:
        return 'Đã có Video ID. Dùng Thử lại / hoàn tất để kiểm tra video và playlist; app không gửi lại tệp.'
    if any(word in error for word in ('chưa rõ', 'chưa chắc chắn', 'Unknown', 'gián đoạn')):
        return 'Kiểm tra YouTube Studio. Nếu video đã có, mở Lịch sử và Đối chiếu Video ID. Không đổi tên hoặc chép tệp để ép tải lại.'
    if any(word in error for word in ('invalidTitle', 'invalidDescription', 'invalidTags')):
        return 'Kiểm tra tiêu đề, mô tả và tags trong metadata.csv rồi quét lại thư mục.'
    return 'Kiểm tra đường dẫn tệp, mạng và kết nối YouTube. Thử lại sẽ kiểm tra SHA-256 trước; nếu đã có Video ID thì chỉ hoàn tất các bước còn thiếu.'


def copy_for_inspection(rows, destination):
    """Exclusive creation avoids overwriting originals or same-name copies."""
    destination = Path(destination)
    copied, failures = [], []
    for row in rows:
        source = Path(row['path'])
        target = None
        try:
            with source.open('rb') as incoming:
                for index in range(10000):
                    candidate = destination / (source.name if index == 0 else f'{source.stem} ({index}){source.suffix}')
                    try:
                        outgoing = candidate.open('xb')
                        target = candidate
                        break
                    except FileExistsError:
                        continue
                else:
                    raise ValueError('Quá nhiều tệp trùng tên tại thư mục đích.')
                with outgoing:
                    shutil.copyfileobj(incoming, outgoing, 8 * 1024 * 1024)
            copied.append(str(target))
        except Exception as error:
            if target is not None:
                target.unlink(missing_ok=True)
            failures.append(f'{source}: {type(error).__name__}')
    return copied, failures


def delete_uploaded_files(rows, history, channel):
    """Delete only exact file contents with a verified successful local record."""
    deleted, failures = [], []
    for row in rows:
        path = Path(row['path'])
        try:
            if not channel or path.is_symlink() or not path.is_file():
                raise ValueError('Tệp không tồn tại, là liên kết hoặc chưa xác định kênh.')
            before = path.stat()
            record = history.find(channel, fingerprint(path))
            if not record or record['state'] != 'Uploaded' or not record['video_id'] or not record['verified'] or record['error']:
                raise ValueError('Nội dung tệp chưa có bản ghi tải thành công và xác minh đầy đủ trên kênh này.')
            after = path.stat()
            if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                raise ValueError('Tệp đã thay đổi trong lúc kiểm tra; chưa xóa.')
            path.unlink()
            deleted.append(str(path))
        except Exception as error:
            failures.append(f'{path}: {error if isinstance(error, ValueError) else type(error).__name__}')
    return deleted, failures
