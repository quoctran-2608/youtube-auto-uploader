# YouTube Auto Uploader — v0.7

Ứng dụng Windows để quét video, đọc metadata CSV và upload nhiều video tuần tự lên kênh YouTube của bạn. Mặc định: **Unlisted**, **Not made for kids**, playlist đã cấu hình. Không tự đặt lịch Public.

## Bắt đầu nhanh — không cần cài Python

1. Mở [Releases](https://github.com/quoctran-2608/youtube-auto-uploader/releases/latest).
2. Tải **youtube-auto-uploader-v0.7-windows-x64.zip** trong phần Assets. Đây là gói Windows có `.exe`; nút **Code → Download ZIP** chỉ tải mã nguồn.
3. Giải nén toàn bộ vào thư mục local, ví dụ `D:\YouTubeAutoUploader`. Không chạy ngay trong ZIP, không tách `.exe` khỏi thư mục `_internal`.
4. Mở **YouTubeAutoUploader.exe**. Lần đầu, chủ kênh phải thiết lập OAuth trên máy này theo [SHARING.md](SHARING.md).
5. Lần đầu mở **Cài đặt**: nhập email/tên playlist, nhập OAuth JSON rồi kết nối YouTube và xác nhận đúng kênh một lần.
6. Từ lần sau: app tự kết nối bằng token lưu sẵn, làm mới token nếu còn dùng được, kiểm tra đúng kênh/playlist và tự quét thư mục lần trước. Không cần bấm Connect, xác nhận lại kênh hay chọn lại playlist. Nếu phải chọn giữa playlist trùng tên, app ghi nhớ ID đã chọn.
7. Chọn thư mục video đã tải offline. App quét cả các thư mục con ở mọi cấp, hiển thị đường dẫn tương đối. Giữ **Ctrl** hoặc **Shift** để chọn nhiều video, hoặc bấm **Chọn tất cả**.
8. Kiểm tra Audience và Visibility áp dụng cho các video được chọn → **Thêm video vào hàng đợi…** → xác nhận một lần.
9. App tải tuần tự. Mở **Hàng đợi** để xem từng mục, tạm dừng sau video hiện tại, tiếp tục hoặc xóa mục. Để app mở và máy không ngủ trong khi tải; nếu đóng app, mở lại để tự tiếp tục. Đợi video hiện tại kết thúc trước khi đóng.

Danh sách video và hàng đợi có cột **STT** và **Trạng thái**: dấu ✓ xanh là hoàn tất và đã xác minh; dấu ✕ đỏ là cần kiểm tra, có thể đã tải nhưng chưa xác minh xong; chấm vàng là đang tải hoặc đang chờ. Trạng thái theo lịch sử chỉ đối chiếu đường dẫn tại máy này, không chứng minh tệp chưa bị thay thế; app kiểm tra nội dung bằng SHA-256 trước khi tải để chặn trùng. Trạng thái không đồng bộ giữa các máy.

Dòng **Dự kiến hoàn thành** ước tính từ dữ liệu tiến độ/tốc độ trong lần mở app hiện tại và tổng dung lượng còn lại. Sau khi có tiến độ tải, con số cập nhật theo tốc độ thực tế, bao gồm thời gian đã dùng để kiểm tra tệp hiện tại; tốc độ mạng, thời gian xử lý từng video và giới hạn YouTube có thể làm kết quả thay đổi đáng kể. Khi đang chờ hạn mức hoặc thiếu dữ liệu tốc độ, app không đưa ra giờ hoàn thành. Đây là thời gian tải và xác minh hàng đợi, không phải thời gian YouTube xử lý xong video.

Hàng đợi lưu trên máy, gắn với đúng kênh, playlist, quyền riêng tư và đối tượng lúc xác nhận. Tệp phải vẫn ở nguyên đường dẫn và sẵn sàng offline. Khi gặp quota API, app chờ đến sau nửa đêm giờ Thái Bình Dương; giới hạn riêng của kênh không công bố giờ reset nên app chờ 24 giờ rồi thử lại, có thể phải chờ lâu hơn. Hàng đợi chỉ chạy khi app mở, có mạng, token còn hiệu lực và máy không ngủ; không tự chạy nền khi app đã đóng. Mục gián đoạn hoặc có kết quả không chắc chắn cần kiểm tra trong **Lịch sử** và YouTube Studio; app không tự tải lại mục đó. Mục khác vẫn tiếp tục.

Theo [Google](https://developers.google.com/youtube/v3/determine_quota_cost), quota mặc định hiện là 100 lệnh `videos.insert` mỗi ngày cho dự án, dùng chung với ứng dụng khác cùng dự án; giới hạn thực tế có thể khác. YouTube cũng áp dụng [giới hạn upload riêng cho từng kênh](https://developers.google.com/youtube/data/reference/rest/v3/errors), không có một con số chung được đảm bảo. App dựa vào lỗi thực tế thay vì dự đoán số còn lại.

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
6. Trong app: **Cài đặt → Nhập OAuth JSON → Kết nối YouTube**. Chủ kênh tự đăng nhập và cấp quyền Google; không gửi thông tin đăng nhập qua chat.
7. Xác nhận tên kênh/Channel ID một lần. App lưu xác nhận theo email và Channel ID, chỉ hỏi lại khi chúng thay đổi. Playlist và thư mục được nhớ cho các lần sau.

Bấm **Cài đặt → Tài khoản & tên playlist** để nhập email Google và tên playlist chính xác. Các giá trị này chỉ lưu local trong settings.json, không nằm trong repo. `owner@example.com` là ví dụ, không phải tài khoản mặc định. Khi đổi kênh, app xác nhận lại playlist bằng API.

`youtube.force-ssl` đáp ứng upload, đọc kênh/playlist và thêm video vào playlist; `youtube.upload` riêng lẻ không đủ thêm playlist. Google cấp scope này cả khả năng sửa/xóa video, đánh giá, bình luận và phụ đề. App chỉ gọi các thao tác upload/đọc/thêm playlist nêu trên. `openid` và `userinfo.email` dùng để kiểm tra đúng email đã xác minh.

**Testing có giới hạn 7 ngày:** Google có thể yêu cầu chủ kênh cấp quyền lại sau bảy ngày. Dùng **Cài đặt → Cấp quyền lại / đổi kênh** khi cần. Khi mở app, token không còn dùng được sẽ hiện nút kết nối lại; không tự mở trình duyệt hoặc hỏi lặp lại. Repo này không tự chuyển Production hoặc gửi xác minh.

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

`config.json` giữ cấu hình xem trước: `start_date`, `daily_times`, `timezone`, `metadata_csv`, `default_description`, `default_tags`. App upload luôn quét thư mục con ngay cả khi `scan_subfolders` trong cấu hình cũ là false. **Lịch trong CSV chỉ để tham khảo và không được gửi lên YouTube.**

## Lỗi và chống upload trùng

**Xóa nhanh clip đã tải trên máy:** chọn một hoặc nhiều clip tích xanh → bấm **Xóa clip đã tải khỏi máy…** (hoặc chuột phải chọn cùng lệnh). Hộp cảnh báo liệt kê số tệp và yêu cầu xác nhận xóa vĩnh viễn, không vào Thùng rác. Trước khi xóa, app đọc SHA-256 để kiểm tra nội dung có bản ghi `Uploaded`, Video ID và xác minh đầy đủ trên kênh này; clip chưa đủ điều kiện hoặc đã bị thay thế sẽ không được xóa. Chỉ các clip tích xanh trong lựa chọn được đưa vào thao tác.

Sau khi xóa thành công, dòng vẫn nằm trong danh sách chính với trạng thái màu xám **Đã xoá trong máy**; app không cho thêm dòng này vào hàng đợi. Bấm **Làm mới**, chọn lại thư mục hoặc mở lại app để quét thư mục thì tệp đã xóa không còn trong danh sách. Lịch sử và video YouTube không bị xóa. Xóa tệp trong thư mục Drive/OneDrive đồng bộ có thể đồng bộ thao tác xóa lên dịch vụ đó. Nếu có tệp bị khóa hoặc không đủ quyền, app báo tệp chưa được xóa.

**Chuột phải vào clip** trong danh sách chính:

- **Xem lỗi / hướng xử lý** (hoặc nhấp đúp): mở chi tiết lỗi đã lưu, Video ID nếu có và hướng xử lý. Chọn một clip cũng hiển thị tóm tắt lỗi dưới bảng. Ảnh chụp chỉ có chữ “Cần kiểm tra” không đủ xác định nguyên nhân; cần đọc chi tiết trên máy đã tải.
- **Thử lại / hoàn tất**: thêm lại mục để kiểm tra SHA-256. Nếu đã có Video ID, app chỉ hoàn tất playlist và xác minh theo cấu hình của lần tải gốc. Nếu kết quả tải trước chưa rõ và chưa có ID, app vẫn chặn tải mới; mở Lịch sử, kiểm tra Studio rồi đối chiếu ID. Lỗi tệp/metadata trước khi bắt đầu upload có thể thử lại sau khi sửa và quét lại.
- **Sao chép clip đã chọn** hoặc **Gom tất cả clip đỏ**: chọn thư mục đích. App giữ nguyên tệp gốc, tự thêm số khi trùng tên, báo tệp không sao chép được. “Tất cả” áp dụng cho danh sách thư mục đang quét. Bản sao vẫn có cùng SHA-256 nên không dùng để ép tải lại.
- **Kiểm tra lịch sử bằng nội dung SHA-256**: đọc nội dung tệp rồi tìm trong toàn bộ lịch sử của kênh trên máy này, kể cả khi đã đổi thư mục hoặc tên tệp.
- **Tìm video cùng tiêu đề trên kênh**: tra cứu clip đầu tiên đang chọn trong danh sách upload của kênh, hiển thị link các kết quả để tự đối chiếu. Tiêu đề khác vẫn có thể là cùng video; tiêu đề giống cũng có thể khác nội dung. App không tự gắn ID hay tự xác nhận trùng từ tên. Cách đọc danh sách upload dùng [channels.list](https://developers.google.com/youtube/v3/docs/channels/list) và [playlistItems.list](https://developers.google.com/youtube/v3/docs/playlistItems/list), phân trang đến hết và có thể cần thời gian/quota khi kênh nhiều video.

**Lịch sử không bị xóa khi đổi thư mục.** Database nằm ở `%LOCALAPPDATA%\YouTubeAutoUploader\history.sqlite3`, độc lập với thư mục video và thư mục giải nén app. Nội dung giống hệt được nhận ra qua SHA-256, kể cả đổi tên hoặc chép sang chỗ khác. Tệp đã biên tập hoặc mã hóa lại sẽ có SHA-256 khác. Hai máy có lịch sử độc lập; app không có đối chiếu tự động toàn bộ nội dung video trên YouTube.

| Trạng thái | Cách xử lý |
| --- | --- |
| `Uploaded` | API đã xác nhận video trong playlist; xem cột Audience/Visibility để biết xác minh riêng |
| `Playlist Pending` | Đã có Video ID. Mở **Lịch sử / Retry playlist**, chọn bản ghi và bấm **Retry playlist / kiểm tra**; không upload lại |
| `Upload Unknown` hoặc `Uploading` sau khi bị tắt đột ngột | Kiểm tra Studio. Nếu video đã có, dùng **Đối chiếu Video ID từ Studio** và nhập ID đúng 11 ký tự; không upload lại |
| Token hết hạn / bị thu hồi | **Cài đặt → Cấp quyền lại / đổi kênh**, để chủ kênh tự cấp quyền lại |
| Không thấy playlist | Kiểm tra đúng kênh và đúng tên. App không tự tạo playlist |
| HTTP 403 | Kiểm tra API đã bật, scope, test user và quota; xem mã lỗi trong lịch sử |

Upload theo chunk 8 MiB bằng resumable upload, xử lý `308 Resume Incomplete` qua transport chuẩn của Google. SHA-256 chống trùng theo từng Channel ID kể cả khi đổi tên/đường dẫn. Video ID được lưu trước bước playlist. Trước khi thêm playlist, kiểm tra membership; sau khi thêm, chờ đọc xác minh nếu YouTube cập nhật chậm. Nếu app khởi động lại giữa upload, không tự mở phiên upload mới cho cùng nội dung.

**Chống trùng chỉ dựa vào lịch sử local trên máy đó.** Hai máy không chia sẻ database nên có thể upload cùng tệp. Khi nhiều người cùng làm, phân công người/tệp rõ ràng và kiểm tra Studio trước; app chưa có hàng đợi dùng chung.

## Nâng cấp từ bản trước

Tải bản Windows v0.7 và giải nén toàn bộ vào thư mục mới, mở `.exe` mới. Không cần chép token hoặc nhập lại credentials: app tiếp tục dùng dữ liệu ở `%LOCALAPPDATA%\YouTubeAutoUploader`. Lần đầu chuyển từ v0.2 có thể cần xác nhận kênh một lần để lưu chế độ ghi nhớ mới; các lần sau hoàn toàn tự khôi phục. Dữ liệu cá nhân chỉ nằm local, không nhúng vào gói phát hành.

Hộp xác nhận áp dụng cho toàn bộ nhóm video đã chọn. Cài đặt kết nối không lặp lại khi token/kênh/playlist vẫn hợp lệ.

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

- `build_windows.py`: gói Windows tại `dist/youtube-auto-uploader-v0.7-windows-x64.zip`, không kèm credentials/token/lịch sử/video.
- `package_app.py`: ZIP mã nguồn theo danh sách cho phép; báo cáo thiết lập cá nhân `SETUP_STATUS.md` không được publish.
- `YouTubeAutoUploader.exe --self-check output.json`: kiểm tra offline runtime, Tkinter, SDK, DPAPI, SQLite và transport 308; không đăng nhập hoặc upload video.

Kiểm thử tự động/máy chủ HTTP loopback không thay thế upload thật. OAuth, kênh, playlist, Audience/Visibility của lần dùng trước đã được kiểm tra bằng API thật; không upload lại video chỉ để thử bản đóng gói.

## Tài liệu chính thức

- [Quyền kênh và giới hạn YouTube API](https://support.google.com/youtube/answer/9481328?hl=vi)
- [OAuth Testing và giới hạn bảy ngày](https://support.google.com/cloud/answer/15549945?hl=en)
- [OAuth Desktop](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Upload video](https://developers.google.com/youtube/v3/docs/videos/insert)
- [Thêm video vào playlist](https://developers.google.com/youtube/v3/docs/playlistItems/insert)
