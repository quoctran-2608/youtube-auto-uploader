YOUTUBE AUTO UPLOADER v0.3 — WINDOWS

1. Giải nén TOÀN BỘ ZIP, mở YouTubeAutoUploader.exe, giữ nguyên _internal.
2. Lần đầu mở Cài đặt: nhập email Google và tên playlist, nhập OAuth JSON,
   kết nối YouTube, tự cấp quyền Google và xác nhận đúng kênh một lần.
3. Chọn thư mục video. App nhớ thư mục, kênh, playlist và mặc định.
4. Những lần sau chỉ MỞ APP: tự kết nối, kiểm tra kênh/playlist và quét lại thư mục.
   Chọn video > Upload > đọc hộp xác nhận video rồi đồng ý.
5. Mặc định: Unlisted, Not made for kids, playlist bạn đã cấu hình.
   Không đặt lịch công khai. Muốn đổi mặc định: sửa tùy chọn rồi Lưu mặc định.

Nâng cấp từ v0.2: dùng lại dữ liệu local, không cần nhập lại JSON.
Có thể cần xác nhận kênh một lần để lưu chế độ ghi nhớ mới.
OAuth Testing có thể cần chủ kênh cấp lại sau 7 ngày. Khi cần, vào Cài đặt >
Cấp quyền lại / đổi kênh. App không tự mở trình duyệt khi khởi động.

Playlist Pending: Lịch sử > Retry playlist; không upload lại.
Upload Unknown: đối chiếu YouTube Studio và Video ID; không upload lại.
Lịch sử chống trùng chỉ nằm trên từng máy. Không gửi token, credentials hay
thư mục AppData cho người khác. Người được mời Editor trong Studio chưa dùng
được YouTube API; xem SHARING.md để chọn cách cấp quyền phù hợp.

Đọc README.md và SHARING.md. Gói chưa ký số; giữ nguyên bảo vệ hệ thống nếu
bị chặn, dùng bản source hoặc nhờ quản trị viên kiểm tra.
Repo: https://github.com/quoctran-2608/youtube-auto-uploader
