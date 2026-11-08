"""YouTube Auto Uploader v0.2 — scan, OAuth, and one confirmed upload."""
from __future__ import annotations

import sys
import queue
import threading
import webbrowser
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from core import preview, read_config, read_metadata, save_preview
from storage import History, InstanceLock, SecretStore, Settings, local_directory
from youtube_client import YouTubeClient, friendly_error

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent


class PreviewApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('YouTube Auto Uploader · v0.1 (Preview Only)')
        self.geometry('1050x640')
        self.minsize(780, 500)
        self.folder = tk.StringVar()
        self.info = tk.StringVar(value='Chọn thư mục video rồi bấm Quét video. Không có video nào được upload.')
        self.rows = []
        self._setup()

    def _setup(self):
        style = ttk.Style(self)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        container = ttk.Frame(self, padding=20)
        container.pack(fill='both', expand=True)
        ttk.Label(container, text='YouTube Auto Uploader', font=('Segoe UI', 18, 'bold')).pack(anchor='w')
        ttk.Label(container, text='BƯỚC 1 / BẢN 0.1 · Quét thư mục và xem trước dữ liệu. Chưa kết nối YouTube.', foreground='#666').pack(anchor='w', pady=(3, 16))
        source = ttk.Frame(container)
        source.pack(fill='x')
        ttk.Label(source, text='Thư mục video (local / Google Drive):').pack(side='left')
        ttk.Entry(source, textvariable=self.folder).pack(side='left', fill='x', expand=True, padx=10)
        ttk.Button(source, text='Chọn thư mục', command=self.choose_folder).pack(side='left')
        buttons = ttk.Frame(container)
        buttons.pack(fill='x', pady=(14, 12))
        ttk.Button(buttons, text='Quét video & xem lịch', command=self.scan).pack(side='left', padx=(0, 8))
        ttk.Button(buttons, text='Xuất CSV xem trước', command=self.export_csv).pack(side='left')
        self.count = ttk.Label(buttons, text='0 video', font=('Segoe UI', 10, 'bold'))
        self.count.pack(side='right')
        table_frame = ttk.Frame(container)
        table_frame.pack(fill='both', expand=True)
        columns = ('filename', 'title', 'size_mb', 'publish_at')
        self.table = ttk.Treeview(table_frame, columns=columns, show='headings', selectmode='browse')
        for key, name, width in [
            ('filename', 'Tệp video', 280), ('title', 'Tiêu đề YouTube', 340),
            ('size_mb', 'MB', 85), ('publish_at', 'Lịch dự kiến', 160)]:
            self.table.heading(key, text=name)
            self.table.column(key, width=width, minwidth=75, stretch=key in ('filename', 'title'))
        scroll_y = ttk.Scrollbar(table_frame, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scroll_y.set)
        self.table.pack(side='left', fill='both', expand=True)
        scroll_y.pack(side='right', fill='y')
        ttk.Label(container, textvariable=self.info, wraplength=900, foreground='#555').pack(anchor='w', pady=(12, 6))
        ttk.Label(container, text='Cấu hình: config.json · Metadata riêng: metadata.csv · Chỉ đọc, không thay đổi file gốc.', foreground='#777').pack(anchor='w')

    def choose_folder(self):
        folder = filedialog.askdirectory(title='Chọn thư mục video')
        if folder:
            self.folder.set(folder)

    def scan(self):
        try:
            if not self.folder.get().strip():
                raise ValueError('Hãy chọn thư mục video trước.')
            folder = Path(self.folder.get()).expanduser()
            config = read_config(ROOT / 'config.json')
            metadata_name = config.get('metadata_csv', 'metadata.csv')
            metadata_path = Path(metadata_name)
            if not metadata_path.is_absolute():
                metadata_path = ROOT / metadata_path
            self.rows = preview(folder, config, read_metadata(metadata_path))
            for item in self.table.get_children():
                self.table.delete(item)
            for row in self.rows:
                self.table.insert('', 'end', values=(row['filename'], row['title'], row['size_mb'], row['publish_at']))
            self.count.configure(text=f'{len(self.rows)} video')
            self.info.set(f'Đã quét {len(self.rows)} video · Múi giờ dự kiến: {config.get("timezone", "Asia/Ho_Chi_Minh")} · KHÔNG upload.')
        except Exception as e:
            messagebox.showerror('Lỗi khi quét', str(e))
            self.info.set('Có lỗi khi quét. Kiểm tra đường dẫn, config.json hoặc metadata.csv.')

    def export_csv(self):
        if not self.rows:
            messagebox.showinfo('Chưa có dữ liệu', 'Hãy quét video trước khi xuất CSV.')
            return
        location = filedialog.asksaveasfilename(title='Lưu CSV xem trước', defaultextension='.csv',
                                                initialfile='upload-preview.csv',
                                                filetypes=[('CSV', '*.csv')])
        if not location:
            return
        try:
            save_preview(self.rows, Path(location))
            messagebox.showinfo('Hoàn tất', f'Đã xuất {len(self.rows)} dòng. Chưa có video nào được upload.')
        except Exception as e:
            messagebox.showerror('Không thể xuất CSV', str(e))


class UploaderApp(PreviewApp):
    def __init__(self):
        self.local = local_directory()
        self.lock = InstanceLock(self.local)
        self.settings = Settings(self.local)
        self.settings.save()
        self.history = History(self.local)
        self.client = YouTubeClient(SecretStore(self.local), self.settings, self.history)
        self.busy = False
        self.events = queue.Queue()
        self.actions = []
        self.video_url = ''
        super().__init__()
        self.folder.set(self.settings.data.get('last_folder', ''))
        self.title('YouTube Auto Uploader · v0.2')
        self.geometry('1160x790')
        self.minsize(1000, 730)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.drain)

    def action(self, parent, text, command, **pack):
        button = ttk.Button(parent, text=text, command=command)
        button.pack(**pack)
        self.actions.append(button)
        return button

    def _setup(self):
        super()._setup()
        container = self.winfo_children()[0]
        children = container.winfo_children()
        children[1].configure(text='v0.2 · Quét thư mục, xác nhận kênh và upload từng video.', foreground='#555')
        # Retain the original scan table and CSV flow.
        for button in children[3].winfo_children():
            if isinstance(button, ttk.Button):
                self.actions.append(button)
        children[3].winfo_children()[0].configure(text='Quét video')
        self.table.heading('publish_at', text='Lịch tham khảo')
        self.table.configure(height=6)
        children[-1].configure(text=f'Dữ liệu local bảo mật: {self.local}')
        connection = ttk.LabelFrame(container, text='YouTube · Kết nối & mặc định', padding=10)
        connection.pack(fill='x', pady=(0, 12), before=children[2])
        bar = ttk.Frame(connection)
        bar.pack(fill='x')
        self.action(bar, 'Cấu hình tài khoản', self.configure_account, side='left', padx=(0, 6))
        self.action(bar, 'Nhập OAuth JSON', self.import_credentials, side='left')
        self.action(bar, 'Connect YouTube', self.connect, side='left', padx=6)
        self.action(bar, 'Đổi tài khoản / kênh', lambda: self.connect(True), side='left')
        self.connection = tk.StringVar(value='Chưa kết nối YouTube')
        ttk.Label(connection, textvariable=self.connection, wraplength=1050).pack(anchor='w', pady=(8, 3))
        self.confirmed = tk.BooleanVar(value=False)
        self.confirm_check = ttk.Checkbutton(connection, text='Tôi xác nhận đúng tên kênh và Channel ID ở trên',
            variable=self.confirmed, command=self.confirm_channel, state='disabled')
        self.confirm_check.pack(anchor='w')
        self.playlist = tk.StringVar(value=f'{self.playlist_title} · chưa xác nhận bằng API')
        playlist_bar = ttk.Frame(connection)
        playlist_bar.pack(fill='x', pady=4)
        ttk.Label(playlist_bar, textvariable=self.playlist, wraplength=850).pack(side='left')
        self.action(playlist_bar, 'Chọn playlist', self.choose_playlist, side='right')
        self.defaults_label = tk.StringVar()
        ttk.Label(connection, textvariable=self.defaults_label, foreground='#17604a').pack(anchor='w')
        self.show_defaults()

        bottom = ttk.Frame(container)
        bottom.pack(fill='x', before=children[-2], pady=(10, 0))
        self.details = tk.StringVar(value='Chọn một video. Metadata và lịch gốc vẫn được giữ để xem trước.')
        ttk.Label(bottom, textvariable=self.details, wraplength=1050).pack(anchor='w')
        options = ttk.LabelFrame(bottom, text='Cấu hình riêng cho video đang chọn', padding=8)
        options.pack(fill='x', pady=6)
        ttk.Label(options, text='Visibility:').pack(side='left')
        self.privacy = tk.StringVar(value=self.settings.data['privacy_status'])
        self.privacy_box = ttk.Combobox(options, textvariable=self.privacy,
            values=('unlisted', 'private', 'public'), state='readonly', width=12)
        self.privacy_box.pack(side='left', padx=(6, 12))
        self.kids = tk.BooleanVar(value=self.settings.data['made_for_kids'])
        self.kids_check = ttk.Checkbutton(options, text='Made for kids (bỏ chọn = Not made for kids)', variable=self.kids)
        self.kids_check.pack(side='left')
        self.action(options, 'Lưu làm mặc định', self.save_defaults, side='right')
        bar = ttk.Frame(bottom)
        bar.pack(fill='x')
        self.action(bar, 'Upload video đã chọn…', self.upload_selected, side='left')
        self.action(bar, 'Lịch sử / Retry playlist', self.show_history, side='left', padx=6)
        self.action(bar, 'Mở video vừa upload', self.open_result, side='left')
        self.progress = ttk.Progressbar(bar, maximum=100)
        self.progress.pack(side='left', fill='x', expand=True, padx=(10, 0))
        self.result = tk.StringVar(value='Chưa upload video trong phiên này.')
        ttk.Label(bottom, textvariable=self.result, wraplength=1050).pack(anchor='w', pady=6)
        self.table.bind('<<TreeviewSelect>>', self.selection_changed)

    @property
    def playlist_title(self):
        return self.settings.data['playlist_title']

    def show_defaults(self):
        data = self.settings.data
        audience = 'Made for kids' if data['made_for_kids'] else 'Not made for kids'
        self.defaults_label.set(f"Mặc định đã lưu: Audience = {audience} · Visibility = {data['privacy_status'].title()} · Không đặt lịch công khai")

    def run_task(self, function, callback):
        if self.busy:
            return
        self.busy = True
        for button in self.actions:
            if button.winfo_exists():
                button.configure(state='disabled')
        self.confirm_check.configure(state='disabled')
        self.kids_check.configure(state='disabled')
        self.privacy_box.configure(state='disabled')

        def worker():
            try:
                self.events.put(('done', callback, function()))
            except Exception as error:
                self.events.put(('error', friendly_error(error)))
        threading.Thread(target=worker, daemon=True).start()

    def drain(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'progress':
                    self.progress['value'] = event[1]
                    self.info.set(event[2])
                    continue
                self.busy = False
                for button in self.actions:
                    if button.winfo_exists():
                        button.configure(state='normal')
                self.privacy_box.configure(state='readonly')
                self.kids_check.configure(state='normal')
                self.confirm_check.configure(state='normal' if self.client.channel else 'disabled')
                if event[0] == 'done':
                    event[1](event[2])
                else:
                    self.info.set(event[1])
                    self.confirmed.set(self.client.channel_confirmed)
                    if not self.client.channel:
                        self.connection.set('Chưa kết nối / kết nối thất bại')
                    self.update_playlist()
                    messagebox.showerror('Chưa hoàn tất', event[1], parent=self)
                if getattr(self, 'history_window', None) and self.history_window.winfo_exists():
                    self.refresh_history()
        except queue.Empty:
            pass
        finally:
            self.after(100, self.drain)

    def configure_account(self):
        email = simpledialog.askstring('Cấu hình local', 'Email Google dùng OAuth trên máy này:',
            initialvalue=self.settings.data.get('expected_email', ''), parent=self)
        if email is None:
            return
        email = email.strip().casefold()
        if '@' not in email or ' ' in email:
            messagebox.showerror('Cấu hình', 'Nhập email hợp lệ.', parent=self)
            return
        title = simpledialog.askstring('Cấu hình local', 'Tên playlist chính xác trên kênh:',
            initialvalue=self.settings.data['playlist_title'], parent=self)
        if title is None or not title.strip():
            return
        if email != self.settings.data.get('expected_email') or title.strip() != self.settings.data['playlist_title']:
            self.settings.data.update(expected_email=email, playlist_title=title.strip(), playlist_id='')
            self.settings.save()
            self.client.channel_confirmed = False
            self.client.channel = None
            self.client.playlist_id = ''
            self.client.playlists = []
            self.confirmed.set(False)
            self.connection.set('Cấu hình đã lưu local. Hãy kết nối lại YouTube.')
            self.update_playlist()

    def import_credentials(self):
        path = filedialog.askopenfilename(title='OAuth JSON loại Desktop app', filetypes=[('JSON', '*.json')])
        if path:
            self.run_task(lambda: self.client.import_credentials(path), self.credentials_imported)

    def credentials_imported(self, project):
        self.confirmed.set(False)
        self.connection.set('Chưa kết nối YouTube')
        self.update_playlist()
        self.info.set(f'Đã nhập credentials project {project}; bản lưu local được mã hóa Windows DPAPI. Bấm Connect YouTube.')

    def connect(self, new_login=False):
        email_label = self.settings.data.get('expected_email') or '(email đã cấu hình)'
        request_consent = new_login or not self.client.secrets.read('token')
        if request_consent and not messagebox.askokcancel('Quyền truy cập OAuth',
            f'Đăng nhập {email_label} và tự cấp quyền trong trình duyệt.\n\n'
            'youtube.force-ssl: đọc kênh/playlist, upload và thêm video vào playlist. '
            'Google cũng cho quyền này khả năng sửa/xóa video, bình luận và phụ đề; app chỉ dùng các thao tác nêu trên.\n\n'
            'openid + email: kiểm tra địa chỉ email đã xác minh. Token được mã hóa bằng Windows DPAPI, '
            'lưu ngoài thư mục dự án/Drive. Chưa upload video khi kết nối.\n\nTiếp tục mở kết nối?', parent=self):
            return
        self.confirmed.set(False)
        self.info.set('Đang kết nối. Bạn tự chọn tài khoản, kênh và cấp quyền trong trình duyệt. Chờ tối đa 5 phút.')
        self.run_task(lambda: self.client.connect(new_login), self.connected)

    def connected(self, channel):
        self.connection.set(f"Đã kết nối {self.client.email} · Kênh: {channel['snippet']['title']} · Channel ID: {channel['id']}")
        self.confirmed.set(False)
        self.update_playlist()
        self.info.set('Kiểm tra tên kênh / Channel ID và đánh dấu xác nhận. Chưa upload video.')
        if not self.client.playlists:
            messagebox.showwarning('Không tìm thấy playlist', f'Không có playlist khớp chính xác “{self.playlist_title}” trên kênh này. App không tự tạo playlist.', parent=self)
        elif not self.client.playlist_id:
            self.choose_playlist()

    def confirm_channel(self):
        self.client.channel_confirmed = bool(self.client.channel and self.confirmed.get())

    def update_playlist(self):
        self.playlist.set(f"{self.playlist_title} · {self.client.playlist_id or 'chưa chọn / không tìm thấy'}")

    def choose_playlist(self):
        choices = self.client.playlists
        if not choices:
            messagebox.showinfo('Playlist', 'Kết nối YouTube để tìm playlist chính xác trên kênh.', parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title('Chọn đúng một playlist')
        dialog.geometry(f'780x270+{max(0, self.winfo_x() + 30)}+{max(0, self.winfo_y() + 80)}')
        dialog.transient(self)
        ttk.Label(dialog, text='Chọn theo Playlist ID và số video:', padding=12).pack(anchor='w')
        box = tk.Listbox(dialog, font=('Segoe UI', 10), exportselection=False)
        box.pack(fill='both', expand=True, padx=12)
        for item in choices:
            box.insert('end', f"{item['id']} · {item.get('contentDetails', {}).get('itemCount', '?')} video · {item['snippet'].get('description', '')[:60]}")

        def choose():
            selected = box.curselection()
            if selected:
                self.client.select_playlist(choices[selected[0]]['id'])
                self.update_playlist()
                dialog.destroy()
        ttk.Button(dialog, text='Dùng playlist đã chọn', command=choose).pack(pady=10)
        dialog.grab_set()

    def selection_changed(self, event=None):
        selected = self.table.selection()
        if selected:
            row = self.rows[self.table.index(selected[0])]
            self.privacy.set(self.settings.data['privacy_status'])
            self.kids.set(self.settings.data['made_for_kids'])
            self.details.set(f"{row['title']} · Tags: {row['tags'] or '(trống)'}\nMô tả: {row['description'][:180] or '(trống)'}")

    def scan(self):
        if not self.busy:
            super().scan()
            if self.rows:
                self.settings.data['last_folder'] = self.folder.get()
                self.settings.save()
                self.info.set(f'Đã quét {len(self.rows)} video. Lịch tham khảo không được gửi lên YouTube. Chưa upload.')

    def save_defaults(self):
        self.settings.data.update(privacy_status=self.privacy.get(), made_for_kids=self.kids.get())
        self.settings.save()
        self.show_defaults()
        self.info.set('Đã lưu Audience và Visibility cho lần chạy sau. Playlist được lưu theo Channel ID.')

    def ready(self):
        if not self.client.channel or not self.client.channel_confirmed or not self.client.playlist_id:
            messagebox.showinfo('Chưa sẵn sàng', 'Hãy kết nối, xác nhận đúng kênh và chọn playlist đã kiểm tra bằng API.', parent=self)
            return False
        return True

    def upload_selected(self):
        if not self.ready():
            return
        selected = self.table.selection()
        if not selected:
            messagebox.showinfo('Chọn video', 'Chọn đúng một video trong danh sách.', parent=self)
            return
        row = dict(self.rows[self.table.index(selected[0])])
        privacy, kids = self.privacy.get(), self.kids.get()
        audience = 'Made for kids' if kids else 'Not made for kids'
        if not messagebox.askyesno('Đồng ý upload video này?',
            f"Tệp: {row['filename']}\nTiêu đề: {row['title']}\n"
            f"Kênh: {self.client.channel['snippet']['title']}\nChannel ID: {self.client.channel['id']}\n"
            f'Playlist: {self.playlist_title}\nPlaylist ID: {self.client.playlist_id}\n'
            f'Audience: {audience}\nVisibility: {privacy.upper()}\nKhông đặt lịch công khai.\n\n'
            'Bạn đồng ý upload duy nhất video này?', parent=self):
            return
        self.progress['value'] = 0
        self.video_url = ''
        self.result.set('Đang xử lý video đã được bạn xác nhận…')
        self.run_task(lambda: self.client.upload(row, privacy, kids,
            lambda value, text: self.events.put(('progress', value, text))), self.upload_finished)

    def upload_finished(self, row):
        self.video_url = f"https://www.youtube.com/watch?v={row['video_id']}"
        verified = 'đã xác minh' if row['verified'] else 'CHƯA xác minh'
        self.result.set(f"Video ID: {row['video_id']} · Playlist: {row['state']} · Audience/Visibility: {verified}\n{self.video_url}")
        self.info.set(row['error'] or 'Đã xác nhận bằng API: video nằm trong playlist, Audience và Visibility đúng yêu cầu.')
        self.update_playlist()

    def show_history(self):
        if getattr(self, 'history_window', None) and self.history_window.winfo_exists():
            self.history_window.lift()
            return
        self.history_window = tk.Toplevel(self)
        self.history_window.title('Lịch sử · Retry playlist không upload lại')
        self.history_window.geometry(f'1100x420+{max(0, self.winfo_x() + 20)}+{max(0, self.winfo_y() + 80)}')
        frame = ttk.Frame(self.history_window, padding=12)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Bản ghi Upload Unknown cần đối chiếu Studio; app chặn upload lại để tránh trùng.').pack(anchor='w', pady=(0, 8))
        columns = ('title', 'state', 'video_id', 'verified', 'error')
        self.history_table = ttk.Treeview(frame, columns=columns, show='headings', selectmode='browse')
        for key, label, width in [('title', 'Tiêu đề', 230), ('state', 'Trạng thái', 140),
            ('video_id', 'Video ID', 120), ('verified', 'Audience / Visibility', 140), ('error', 'Lỗi', 400)]:
            self.history_table.heading(key, text=label)
            self.history_table.column(key, width=width)
        self.history_table.pack(fill='both', expand=True)
        bar = ttk.Frame(frame)
        bar.pack(fill='x', pady=(8, 0))
        self.action(bar, 'Retry playlist / kiểm tra', self.retry, side='left')
        self.action(bar, 'Đối chiếu Video ID từ Studio', self.reconcile, side='left', padx=6)
        self.action(bar, 'Mở video', self.open_history, side='left')
        self.refresh_history()

    def refresh_history(self):
        self.history_table.delete(*self.history_table.get_children())
        for row in self.history.recent(self.client.channel['id'] if self.client.channel else None):
            state = 'Upload Unknown' if row['state'] == 'Uploading' else row['state']
            self.history_table.insert('', 'end', iid=str(row['id']), values=(row['title'], state,
                row['video_id'], 'Đã xác minh' if row['verified'] else 'Chưa xác minh', row['error']))

    def selected_history(self):
        selected = self.history_table.selection()
        if not selected:
            messagebox.showinfo('Lịch sử', 'Chọn một bản ghi trước.', parent=self.history_window)
            return None
        return self.history.get(int(selected[0]))

    def retry(self):
        if not self.ready():
            return
        row = self.selected_history()
        if row:
            if not row['video_id']:
                messagebox.showinfo('Chưa rõ kết quả', 'Kiểm tra Studio và dùng Đối chiếu Video ID. App sẽ không upload lại.', parent=self)
                return
            self.run_task(lambda: self.client.finish(row['id']), self.upload_finished)

    def reconcile(self):
        if not self.ready():
            return
        row = self.selected_history()
        if row:
            video_id = simpledialog.askstring('Đối chiếu thủ công',
                f"Bản ghi: {row['title']}\nChỉ tiếp tục sau khi đã đối chiếu đúng tệp trong Studio.\n"
                'Nhập Video ID (11 ký tự). App kiểm tra kênh và thêm video đó vào playlist; không upload tệp.', parent=self.history_window)
            if video_id:
                self.run_task(lambda: self.client.reconcile(row['id'], video_id.strip()), self.upload_finished)

    def open_history(self):
        row = self.selected_history()
        if row and row['video_id']:
            webbrowser.open(f"https://www.youtube.com/watch?v={row['video_id']}")

    def open_result(self):
        if self.video_url:
            webbrowser.open(self.video_url)

    def close(self):
        if self.busy:
            messagebox.showinfo('Đang xử lý', 'Đợi tác vụ hoàn tất trước khi đóng để giữ kết quả upload.', parent=self)
            return
        self.lock.close()
        self.destroy()


if __name__ == '__main__':
    try:
        if len(sys.argv) == 3 and sys.argv[1] == '--self-check':
            from smoke_check import run_check
            run_check(ROOT, Path(sys.argv[2]))
            sys.exit(0)
        UploaderApp().mainloop()
    except Exception as e:
        if sys.stderr is not None:
            print(friendly_error(e), file=sys.stderr)
        else:
            messagebox.showerror('YouTube Auto Uploader', friendly_error(e))
        sys.exit(1)
