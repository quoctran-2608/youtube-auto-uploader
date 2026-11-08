# YouTube Auto Uploader — v0.2

Ứng dụng Windows để quét video, đọc metadata CSV và upload **từng video** lên kênh **kênh YouTube của bạn**. Mặc định: **Unlisted**, **Not made for kids**, playlist **playlist đã cấu hình**. Không tự đặt lịch Public và không upload hàng loạt.

## Bắt đầu nhanh — không cần cài Python

1. Mở [Releases](https://github.com/quoctran-2608/youtube-auto-uploader/releases/latest).
2. Tải **youtube-auto-uploader-v0.2-windows-x64.zip** trong phần Assets. Đây là gói Windows có `.exe`; nút **Code → Download ZIP** chỉ tải mã nguồn.
3. Giải nén toàn bộ vào thư mục local, ví dụ `D:\YouTubeAutoUploader`. Không chạy ngay trong ZIP, không tách `.exe` khỏi thư mục `_internal`.
4. Mở **YouTubeAutoUploader.exe**. Lần đầu, chủ kênh phải thiết lập OAuth trên máy này theo [SHARING.md](SHARING.md).
5. Bấm **Cấu hình tài khoản**, nhập email của bạn và tên playlist chính xác; sau đó bấm **Connect YouTube**. Đăng nhập email bạn đã cấu hình nếu Google yêu cầu; kiểm tra tên kênh và Channel ID, rồi đánh dấu xác nhận.
6. Kiểm tra playlist đã được xác nhận bằng API; nếu trùng tên, chọn đúng ID. App không tự tạo playlist.
7. Chọn thư mục video đã tải offline → **Quét video** → chọn một video.
8. Kiểm tra metadata, Audience và Visibility → **Upload video đã chọn…** → đọc hộp xác nhận rồi đồng ý.
9. App hiển thị tiến độ, lưu Video ID, thêm playlist và kiểm tra trạng thái. Dùng **Mở video vừa upload** để xem; YouTube có thể cần thêm thời gian xử lý nội dung.

**Muốn gửi cho bạn bè?** Gửi link Release hoặc gói Windows ZIP sạch. Đọc [hướng dẫn chia sẻ cùng kênh](SHARING.md): lời mời Editor/Manager trong Studio chưa dùng được với YouTube API. Không gửi mật khẩu, OTP, token hoặc thư mục AppData.

## Dùng bản source

Cần Windows 64-bit, Python 3.11+ có Tkinter, và Internet.

```powershell
git clone https://github.com/quoctran-2608/youtube-auto-uploader.git
cd youtube-auto-uploader
.\START.bat
```

Hoặc **Code → Download ZIP**, giải nén, nhấp đúp `START.bat`. Lần đầu script tạo `.venv` và cài phiên bản thư viện đã kiểm tra trong `requirements-lock.txt`; lần sau dùng lại. Gói `.exe` đã kèm Python và thư viện nên không cần bước này.

## Kết nối OAuth lần đầu

Chủ kênh thực hiện trên từng máy được tin cậy:

1. Trong [Google Cloud Console](https://console.cloud.google.com/), chọn project đã dành cho app; không cần billing.
2. Bật **YouTube Data API v3** nếu chưa bật.
3. **Google Auth Platform → Audience**: giữ **External / Testing**, thêm tài khoản chủ kênh vào Test users. Không cần thêm Gmail của người bạn nếu OAuth vẫn dùng tài khoản chủ kênh.
4. **Data Access**: cấu hình `youtube.force-ssl`, `openid`, `userinfo.email`.
5. **Clients → Create client → Desktop app**: tạo client cho máy nhận, tải JSON vào thư mục local bảo mật trên máy đó.
6. Trong app: **Nhập OAuth JSON → Connect YouTube**. Chủ kênh tự đăng nhập và cấp quyền Google; không gửi thông tin đăng nhập qua chat.
7. Kiểm tra email, tên kênh, Channel ID, playlist và ba mặc định trước lần upload đầu.

Bấm **Cấu hình tài khoản** để nhập email Google và tên playlist chính xác. Các giá trị này chỉ lưu local trong settings.json, không nằm trong repo. `owner@example.com` là ví dụ, không phải tài khoản mặc định. Khi đổi kênh, app xác nhận lại playlist bằng API.

`youtube.force-ssl` đáp ứng upload, đọc kênh/playlist và thêm video vào playlist; `youtube.upload` riêng lẻ không đủ thêm playlist. Google cấp scope này cả khả năng sửa/xóa video, đánh giá, bình luận và phụ đề. App chỉ gọi các thao tác upload/đọc/thêm playlist nêu trên. `openid` và `userinfo.email` dùng để kiểm tra đúng email đã xác minh.

**Testing có giới hạn 7 ngày:** Google có thể yêu cầu chủ kênh cấp quyền lại sau bảy ngày. Dùng **Đổi tài khoản / kênh** khi cần. Repo này không tự chuyển Production hoặc gửi xác minh.

## Mặc định và metadata

| Thiết lập | Mặc định |
| --- | --- |
| Playlist | playlist đã cấu hình; ID được tìm bằng `playlists.list(mine=true)` và gắn với Channel ID |
| Audience | Not made for kids (`selfDeclaredMadeForKids=false`) |
| Visibility | Unlisted (`privacyStatus="unlisted"`) |
| Lịch công khai | Không gửi `publishAt` |

Có thể đổi Audience/Visibility cho video đang chọn. Chỉ **Lưu làm mặc định** mới thay đổi mặc định cho các lần sau. Khi chọn video khác, app nạp lại mặc định đã lưu.

`metadata.csv` tùy chọn:

```csv
filename,title,description,tags,publish_at
clip-01.mp4,Tiêu đề tùy chỉnh,Mô tả video,tag1;tag2,2026-11-15 08:00
folder/clip-02.mp4,Tiêu đề khác,Mô tả khác,,
```

Không có dòng CSV thì dùng tên tệp làm tiêu đề; mô tả mặc định trống. App không tạo metadata bằng AI. Dùng đường dẫn tương đối để phân biệt tệp trùng basename. Tiêu đề tối đa 100 ký tự.

`config.json` giữ cấu hình quét của v0.1: `scan_subfolders`, `start_date`, `daily_times`, `timezone`, `metadata_csv`, `default_description`, `default_tags`. **Lịch trong bảng/CSV chỉ để tham khảo và không được gửi lên YouTube.**

## Lỗi và chống upload trùng

| Trạng thái | Cách xử lý |
| --- | --- |
| `Uploaded` | API đã xác nhận video trong playlist; xem cột Audience/Visibility để biết xác minh riêng |
| `Playlist Pending` | Đã có Video ID. Mở **Lịch sử / Retry playlist**, chọn bản ghi và bấm **Retry playlist / kiểm tra**; không upload lại |
| `Upload Unknown` hoặc `Uploading` sau khi bị tắt đột ngột | Kiểm tra Studio. Nếu video đã có, dùng **Đối chiếu Video ID từ Studio** và nhập ID đúng 11 ký tự; không upload lại |
| Token hết hạn / bị thu hồi | **Đổi tài khoản / kênh**, để chủ kênh tự cấp quyền lại |
| Không thấy playlist | Kiểm tra đúng kênh và đúng tên. App không tự tạo playlist |
| HTTP 403 | Kiểm tra API đã bật, scope, test user và quota; xem mã lỗi trong lịch sử |

Upload theo chunk 8 MiB bằng resumable upload, xử lý `308 Resume Incomplete` qua transport chuẩn của Google. SHA-256 chống trùng theo từng Channel ID kể cả khi đổi tên/đường dẫn. Video ID được lưu trước bước playlist. Trước khi thêm playlist, kiểm tra membership; sau khi thêm, chờ đọc xác minh nếu YouTube cập nhật chậm. Nếu app khởi động lại giữa upload, không tự mở phiên upload mới cho cùng nội dung.

**Chống trùng chỉ dựa vào lịch sử local trên máy đó.** Hai máy không chia sẻ database nên có thể upload cùng tệp. Khi nhiều người cùng làm, phân công người/tệp rõ ràng và kiểm tra Studio trước; app chưa có hàng đợi dùng chung.

## Dữ liệu riêng nằm ở đâu?

`%LOCALAPPDATA%\YouTubeAutoUploader`:

- `settings.json`: mặc định, thư mục đã chọn và Channel ID/Playlist ID.
- `credentials.bin`, `token.bin`: mã hóa Windows DPAPI cho tài khoản Windows hiện tại.
- `history.sqlite3`: SHA-256, Video ID, trạng thái và lỗi.
- `app.lock`: ngăn hai tiến trình app cùng dùng dữ liệu local.

Không gửi thư mục này cho người khác; token DPAPI không dùng được dưới tài khoản Windows khác. Credentials JSON gốc phải nằm ở thư mục local được bảo vệ, ngoài Drive/GitHub và ngoài các gói phân phối. Không xóa lịch sử nếu muốn giữ khả năng chống trùng. Không đưa database/token lên repo để đồng bộ nhiều máy.

## Kiểm thử và đóng gói

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe build_windows.py
.\.venv\Scripts\python.exe package_app.py
```

- `build_windows.py`: gói Windows tại `dist/youtube-auto-uploader-v0.2-windows-x64.zip`, không kèm credentials/token/lịch sử/video.
- `package_app.py`: ZIP mã nguồn theo danh sách cho phép; báo cáo thiết lập cá nhân `SETUP_STATUS.md` không được publish.
- `YouTubeAutoUploader.exe --self-check output.json`: kiểm tra offline runtime, Tkinter, SDK, DPAPI, SQLite và transport 308; không đăng nhập hoặc upload video.

Kiểm thử tự động/máy chủ HTTP loopback không thay thế upload thật. OAuth, kênh, playlist, Audience/Visibility của lần dùng trước đã được kiểm tra bằng API thật; không upload lại video chỉ để thử bản đóng gói.

## Tài liệu chính thức

- [Quyền kênh và giới hạn YouTube API](https://support.google.com/youtube/answer/9481328?hl=vi)
- [OAuth Testing và giới hạn bảy ngày](https://support.google.com/cloud/answer/15549945?hl=en)
- [OAuth Desktop](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Upload video](https://developers.google.com/youtube/v3/docs/videos/insert)
- [Thêm video vào playlist](https://developers.google.com/youtube/v3/docs/playlistItems/insert)
