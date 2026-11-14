YOUTUBE AUTO UPLOADER v0.6 — WINDOWS

1. Giải nén TOÀN BỘ ZIP, mở YouTubeAutoUploader.exe, giữ nguyên _internal.
2. Lần đầu mở Cài đặt: nhập email Google và tên playlist, nhập OAuth JSON,
   kết nối YouTube, tự cấp quyền Google và xác nhận đúng kênh một lần.
3. Chọn thư mục video. App quét luôn các thư mục con và nhớ thư mục, kênh, playlist và mặc định.
4. Những lần sau chỉ MỞ APP: tự kết nối, kiểm tra kênh/playlist và quét lại thư mục.
   Giữ Ctrl/Shift chọn nhiều video hoặc Chọn tất cả > Thêm video vào hàng đợi.
   Xác nhận một lần. App tải lần lượt; mở Hàng đợi để xem, tạm dừng hoặc xóa.
   Cột trạng thái: ✓ xanh hoàn tất, ✕ đỏ cần kiểm tra, ● vàng đang tải/chờ.
   Thời gian dự kiến tính từ tốc độ tải thực tế và có thể thay đổi.
5. Mặc định: Unlisted, Not made for kids, playlist bạn đã cấu hình.
   Không đặt lịch công khai. Muốn đổi mặc định: sửa tùy chọn rồi Lưu mặc định.

Nâng cấp từ v0.2/v0.3: dùng lại dữ liệu local, không cần nhập lại JSON.
Có thể cần xác nhận kênh một lần để lưu chế độ ghi nhớ mới.
OAuth Testing có thể cần chủ kênh cấp lại sau 7 ngày. Khi cần, vào Cài đặt >
Cấp quyền lại / đổi kênh. App không tự mở trình duyệt khi khởi động.

Playlist Pending: Lịch sử > Retry playlist; không upload lại.
Chuột phải vào clip > Xem lỗi để đọc lý do và hướng xử lý.
Thử lại / hoàn tất: nếu đã có Video ID, chỉ hoàn tất playlist và xác minh.
Chuột phải > Sao chép hoặc Gom tất cả clip đỏ để kiểm tra trong thư mục riêng.
Lịch sử giữ nguyên khi đổi folder; kiểm tra SHA-256 nhận ra cả tệp đổi tên.
Tìm cùng tiêu đề trên kênh chỉ đưa ra gợi ý để tự đối chiếu.
Upload Unknown: đối chiếu YouTube Studio và Video ID; không upload lại.
Hàng đợi lưu trên máy và tiếp tục khi mở app; không chạy khi app đóng hoặc máy ngủ.
Giữ nguyên đường dẫn tệp. Nếu YouTube báo hết quota, app chờ rồi thử lại.
Lịch sử chống trùng chỉ nằm trên từng máy. Không gửi token, credentials hay
thư mục AppData cho người khác. Người được mời Editor trong Studio chưa dùng
được YouTube API; xem SHARING.md để chọn cách cấp quyền phù hợp.

Đọc README.md và SHARING.md. Gói chưa ký số; giữ nguyên bảo vệ hệ thống nếu
bị chặn, dùng bản source hoặc nhờ quản trị viên kiểm tra.
Repo: https://github.com/quoctran-2608/youtube-auto-uploader
