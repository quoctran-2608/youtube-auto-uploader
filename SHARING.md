# Gửi app cho bạn bè để cùng upload kênh dùng chung

Kênh dùng chung: **kênh YouTube của bạn**. Chủ kênh tự nhập email và tên playlist qua **Cài đặt → Tài khoản & tên playlist**. `owner@example.com` trong hướng dẫn chỉ là ví dụ; không có tài khoản cá nhân được nhúng sẵn.

## Chọn cách phù hợp

| Cách | Bạn của bạn đăng nhập bằng gì? | Dùng app này? | Ai cấp quyền? |
| --- | --- | --- | --- |
| YouTube Studio | Gmail riêng, được mời Editor | Không; upload trong trình duyệt | Chủ kênh mời Editor một lần |
| App trên máy người bạn | OAuth của tài khoản chủ kênh, lưu riêng trên máy đó | Có, ba mặc định tự áp dụng | Chủ kênh tự đăng nhập/cấp OAuth trên máy đó; Testing có thể cần làm lại sau 7 ngày |
| App trên máy chủ kênh | Chủ kênh đã kết nối sẵn | Có | Người bạn gửi video/CSV; chủ kênh chọn và xác nhận upload |

Google ghi rõ người được mời qua tính năng quyền kênh chưa truy cập được **YouTube APIs**. Mời Editor/Manager trong Studio hoặc thêm Gmail bạn bè vào OAuth Test users không tự mở quyền API lên kênh này. [Nguồn Google](https://support.google.com/youtube/answer/9481328?hl=vi)

## Cách ít thiết lập nhất: người bạn dùng Studio

1. Chủ kênh mở YouTube Studio → **Settings → Permissions → Invite**.
2. Nhập Gmail của người bạn, chọn **Editor** (hoặc Editor limited nếu không cần xem doanh thu), gửi lời mời.
3. Người bạn chấp nhận lời mời, đăng nhập Gmail của họ và chọn đúng kênh trong Studio.
4. Tải video lên trong trình duyệt, chọn **Not made for kids**, **Unlisted** và đúng playlist trước khi hoàn tất.

Đây là cách được Google hỗ trợ để cộng tác bằng Gmail riêng, không chia sẻ tài khoản Google. Ba mặc định của app không áp dụng cho trình duyệt; người upload cần kiểm tra chúng trong Studio. Repo/app không tự mời người hoặc đổi quyền toàn kênh.

## Muốn dùng app trên máy bạn ấy: chuẩn bị một lần trên máy nhận

Chỉ chọn cách này với người và máy bạn tin cậy. Token trên máy đó cho app quyền YouTube của **chủ kênh**; scope Google rộng hơn một quyền chỉ upload. Không dùng cách này nếu bạn chỉ muốn cấp quyền Editor hạn chế.

### 1. Người nhận tải và mở app

1. Mở [Release mới nhất](https://github.com/quoctran-2608/youtube-auto-uploader/releases/latest).
2. Tải `youtube-auto-uploader-v0.3-windows-x64.zip`, giải nén toàn bộ, mở `YouTubeAutoUploader.exe`.
3. Giữ nguyên `_internal`, `config.json` và `metadata.csv` cạnh `.exe`; không chạy trong ZIP.

Gói Windows đã có Python/thư viện, không cần mở terminal hoặc cài Python. Gói source là lựa chọn khác cho người có kỹ thuật. Gói `.exe` chưa ký số; nếu hệ thống bảo vệ chặn, giữ nguyên bảo vệ và dùng bản source hoặc nhờ quản trị viên kiểm tra.

### 2. Chủ kênh tự chuẩn bị OAuth trên máy nhận

Bạn có thể ngồi tại máy đó hoặc dùng phiên hỗ trợ từ xa mà hai bên chủ động thiết lập. **Không gửi mật khẩu, OTP, token trong tin nhắn; không gửi file token từ máy bạn.**

1. Chính chủ kênh mở Chrome trên máy nhận, đăng nhập tài khoản Google chủ kênh của bạn và xử lý 2FA nếu Google yêu cầu.
2. Mở Google Cloud Console, chọn project YouTube Auto Uploader đã có. API đã bật thì dùng lại; không tạo billing hoặc project mới nếu không cần.
3. Trong Google Auth Platform, kiểm tra **External / Testing** và Test users có tài khoản chủ kênh.
4. Trong **Clients**, tạo OAuth Client **Desktop app** riêng cho máy nhận, đặt tên dễ nhận biết, ví dụ `Uploader - may ban A`. Tải JSON trực tiếp về thư mục local bảo mật trên máy nhận, ngoài thư mục repo/Drive.
5. Trong app, **Cài đặt → Nhập OAuth JSON** vừa tải → **Kết nối YouTube**.
6. Chính chủ kênh đọc quyền và xác nhận OAuth trong Google. Không cần cho người bạn biết mật khẩu.
7. Kiểm tra email, tên kênh, Channel ID và playlist. Xác nhận và ghi nhớ kênh một lần.
8. Sau khi app kết nối thành công, chủ kênh đăng xuất tài khoản Google khỏi Chrome trên máy nhận và không lưu mật khẩu trong trình duyệt. App giữ token riêng đã được cấp, không cần giữ phiên Gmail mở.

Credentials JSON là cấu hình client, không phải token quyền truy cập của chủ kênh; tuy vậy dự án này vẫn không đưa JSON đó vào GitHub/Drive/ZIP. Mỗi máy tự nhập cấu hình và tự tạo token qua sự đồng ý của chủ kênh. Gói app gửi bạn bè luôn sạch credentials/token.

### 3. Người bạn dùng hằng ngày

1. Mở app. App tự kết nối, kiểm tra kênh/playlist và quét thư mục đã lưu; không cần bấm Connect.
2. Kênh đã xác nhận và playlist đã chọn được ghi nhớ. Chỉ cần xử lý nếu app báo token hết hạn hoặc kênh/playlist thay đổi.
3. Chọn thư mục video local hoặc Drive đã tải offline → Quét → chọn một video.
4. Giữ mặc định **Unlisted / Not made for kids / playlist đã cấu hình**.
5. Kiểm tra tiêu đề/mô tả → bấm Upload → đọc hộp xác nhận → đồng ý.
6. Nếu Playlist Pending: retry riêng playlist. Nếu Upload Unknown: kiểm tra Studio và đối chiếu ID; không upload lại.

**Giới hạn Testing:** quyền/refresh token có thể hết hạn sau 7 ngày. Khi đó chủ kênh cần quay lại máy nhận và tự cấp quyền qua **Cài đặt → Cấp quyền lại / đổi kênh**. Không có cách bảo đảm “cấp một lần dùng mãi” trong cấu hình Testing này. Chuyển Production/phân phối công khai cần đánh giá yêu cầu OAuth/xác minh riêng; repo không tự thay đổi. [Nguồn Google](https://support.google.com/cloud/answer/15549945?hl=en)

### 4. Phân công để tránh trùng giữa nhiều máy

Lịch sử SQLite chỉ nằm trên từng máy. Ví dụ: máy A xử lý thư mục `DA_GIAO_CHO_A`, máy B xử lý `DA_GIAO_CHO_B`. Dùng bảng giao việc hoặc quy ước tên tệp, kiểm tra Studio trước khi upload lại tệp đã được người khác xử lý. Không gửi token/database để đồng bộ; app chưa có hàng đợi dùng chung.

### 5. Dừng quyền sử dụng

Chủ kênh kiểm tra [các kết nối bên thứ ba của Google](https://myaccount.google.com/connections) và thu hồi quyền app khi cần. Việc thu hồi có thể ảnh hưởng các máy khác đang dùng cùng ứng dụng/project; kiểm tra lại các máy của bạn. Đăng xuất Chrome đơn thuần không thu hồi token đã cấp cho app.

## Mẫu tin nhắn để bạn tự gửi

> Mình gửi app upload cho kênh dùng chung: https://github.com/quoctran-2608/youtube-auto-uploader/releases/latest
>
> Bạn tải bản Windows ZIP, giải nén toàn bộ rồi mở YouTubeAutoUploader.exe. Đọc README_FIRST.txt trước. Mình sẽ tự thiết lập OAuth trên máy bạn lần đầu; bạn không cần biết mật khẩu của mình và không dùng token từ máy mình.
>
> Sau khi kết nối, chọn video rồi upload từng tệp. Mặc định là Unlisted, Not made for kids và playlist đã cấu hình. Nếu có lỗi, gửi mã lỗi hoặc Video ID, không gửi token/credentials. Lưu ý chế độ Testing có thể cần mình cấp quyền lại sau 7 ngày.
