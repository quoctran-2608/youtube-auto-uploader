YOUTUBE AUTO UPLOADER v0.2 — WINDOWS

1. Giải nén TOÀN BỘ ZIP vào một thư mục local (không chạy ngay trong ZIP).
2. Mở YouTubeAutoUploader.exe. Giữ nguyên thư mục _internal đi kèm.
3. Lần đầu, CHỦ KÊNH phải tự nhập OAuth JSON và Connect YouTube trên máy này.
   Bấm Cấu hình tài khoản để lưu email chủ kênh và tên playlist trên máy này.
   Đăng nhập Gmail riêng với quyền Editor trong Studio KHÔNG đủ dùng YouTube API.
4. Xác nhận đúng kênh YouTube của bạn và playlist.
5. Chọn thư mục video đã tải offline > Quét video > chọn một video > Upload.
6. Đọc hộp xác nhận rồi mới đồng ý. Mặc định: Unlisted, Not made for kids,
   playlist đã cấu hình; không đặt lịch công khai.

Lần sau mở lại: Connect YouTube dùng token đã lưu. OAuth Testing có thể yêu cầu
CHỦ KÊNH cấp quyền lại sau 7 ngày. Không gửi mật khẩu, OTP, token hoặc thư mục
AppData cho người khác. Đọc SHARING.md để thiết lập cho máy bạn bè.

Nếu thấy Playlist Pending: dùng Lịch sử / Retry playlist, không upload lại.
Nếu thấy Upload Unknown: đối chiếu Studio rồi gắn Video ID, không upload lại.

README.md: hướng dẫn đầy đủ. SHARING.md: cách chia sẻ và cấp quyền đúng.
Repo: https://github.com/quoctran-2608/youtube-auto-uploader

Gói Windows chưa có chữ ký số. Chỉ chạy bản bạn tin cậy từ repo này; nếu Windows
hoặc phần mềm bảo vệ chặn, giữ nguyên bảo vệ và dùng bản source hoặc nhờ người
quản trị kiểm tra. Không cần tắt antivirus hay thay đổi thiết lập bảo mật.
