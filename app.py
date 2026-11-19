"""YouTube Auto Uploader v0.3 — scan, OAuth, and one confirmed upload."""
from __future__ import annotations

import sys
import json
import time
import queue
import threading
import webbrowser
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from core import preview, read_config, read_metadata, save_preview
from storage import History, InstanceLock, SecretStore, Settings, local_directory
from youtube_client import YouTubeClient, friendly_error, quota_reason
from upload_queue import UploadQueue, STATUS, estimate_remaining, pacific_midnight_after
from diagnostics import error_advice, copy_for_inspection, delete_uploaded_files, find_uploaded_files
from folder_playlists import folder_title, Mp3Index, plan_history, PlaylistBatch
from storage import fingerprint

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
        self.upload_queue = UploadQueue(self.history)
        self.playlist_batch = PlaylistBatch(self.local)
        self.client = YouTubeClient(SecretStore(self.local), self.settings, self.history)
        self.busy = False
        self.events = queue.Queue()
        self.actions = []
        self.video_url = ''
        self.deleted_local = set()
        self.current_item = None
        self.current_started = None
        self.current_fraction = 0.0
        self.transfer_samples = []
        super().__init__()
        self.folder.set(self.settings.data.get('last_folder', ''))
        self.title('YouTube Auto Uploader · v0.9.3')
        self.geometry('1040x700')
        self.minsize(880, 620)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.drain)
        self.after(300, self.startup)
        self.queue_timer = self.after(1500, self.queue_tick)

    def action(self, parent, text, command, **pack):
        button = ttk.Button(parent, text=text, command=command)
        button.pack(**pack)
        self.actions.append(button)
        return button

    def _setup(self):
        style = ttk.Style(self)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), background='#f3f6fa')
        style.configure('TButton', padding=(10, 6))
        style.configure('Treeview', background='white', fieldbackground='white', rowheight=29)
        style.configure('Treeview.Heading', font=('Segoe UI', 10, 'bold'))
        style.configure('Upload.TButton', background='#175bc0', foreground='white', padding=(18, 9))
        style.map('Upload.TButton', background=[('active', '#104a9e'), ('disabled', '#a0afc5')])
        container = ttk.Frame(self, padding=18)
        container.pack(fill='both', expand=True)
        header = ttk.Frame(container)
        header.pack(fill='x')
        ttk.Label(header, text='YouTube Auto Uploader', font=('Segoe UI', 19, 'bold')).pack(side='left')
        self.action(header, 'Cài đặt', self.show_settings, side='right')
        self.action(header, 'Lịch sử', self.show_history, side='right', padx=8)
        self.action(header, 'Hàng đợi', self.show_queue, side='right')
        self.action(header, 'Sắp playlist video cũ…', self.organize_history, side='right', padx=8)
        self.connection = tk.StringVar(value='Đang chuẩn bị kết nối…')
        ttk.Label(container, textvariable=self.connection, wraplength=960, foreground='#285b8d').pack(anchor='w', pady=(8, 3))
        self.playlist = tk.StringVar(value=self.playlist_title)
        ttk.Label(container, textvariable=self.playlist, wraplength=960, foreground='#576779').pack(anchor='w', pady=(0, 12))
        self.reconnect = self.action(container, 'Kết nối YouTube', self.connect, anchor='w', pady=(0, 8))
        self.reconnect.pack_forget()
        source = ttk.Frame(container)
        source.pack(fill='x', pady=(0, 10))
        ttk.Label(source, text='Thư mục video').pack(side='left')
        ttk.Entry(source, textvariable=self.folder).pack(side='left', fill='x', expand=True, padx=8)
        self.action(source, 'Chọn thư mục', self.choose_folder, side='left')
        self.action(source, 'Làm mới', self.scan, side='left', padx=(8, 0))
        self.action(source, 'Chọn tất cả', lambda: self.table.selection_set(self.table.get_children()), side='left', padx=(8, 0))
        self.count = ttk.Label(container, text='0 video')
        self.count.pack(anchor='w', pady=(0, 5))
        frame = ttk.Frame(container)
        frame.pack(fill='both', expand=True)
        columns = ('number', 'filename', 'title', 'size_mb', 'state')
        self.table = ttk.Treeview(frame, columns=columns, show='headings', selectmode='extended', height=8)
        for key, title, width in [('number', 'STT', 55), ('filename', 'Tệp video', 275), ('title', 'Tiêu đề', 300), ('size_mb', 'MB', 65), ('state', 'Trạng thái', 160)]:
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=60, stretch=key != 'size_mb')
        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        for tag, color in [('waiting', '#9a6700'), ('done', '#18733e'), ('error', '#b42318')]:
            self.table.tag_configure(tag, foreground=color)
        self.table.tag_configure('deleted', foreground='#687383')
        self.details = tk.StringVar(value='Giữ Ctrl hoặc Shift để chọn nhiều video; Ctrl+A chọn tất cả.')
        ttk.Label(container, textvariable=self.details, wraplength=960).pack(anchor='w', pady=(10, 6))
        options = ttk.Frame(container)
        options.pack(fill='x')
        ttk.Label(options, text='Chế độ xem').pack(side='left')
        self.privacy = tk.StringVar(value=self.settings.data['privacy_status'])
        self.privacy_box = ttk.Combobox(options, textvariable=self.privacy, values=('unlisted', 'private', 'public'), state='readonly', width=11)
        self.privacy_box.pack(side='left', padx=(8, 18))
        self.kids = tk.BooleanVar(value=self.settings.data['made_for_kids'])
        self.kids_check = ttk.Checkbutton(options, text='Dành cho trẻ em', variable=self.kids)
        self.kids_check.pack(side='left')
        self.by_folder = tk.BooleanVar(value=self.settings.data.get('playlist_by_folder', False))
        ttk.Checkbutton(options, text='Playlist theo thư mục', variable=self.by_folder,
                        command=self.save_playlist_mode).pack(side='left', padx=12)
        self.action(options, 'Nguồn MP3…', self.configure_mp3_source, side='left')
        self.action(options, 'Lưu mặc định', self.save_defaults, side='right')
        cleanup = ttk.Frame(container)
        cleanup.pack(fill='x', pady=(6, 0))
        self.action(cleanup, 'Tự tìm & xóa clip đã tải…', self.find_and_delete_uploaded, side='left')
        self.delete_button = self.action(cleanup, 'Xóa clip đã chọn…', self.delete_selected, side='left', padx=8)
        footer = ttk.Frame(container)
        footer.pack(fill='x', pady=(12, 0))
        self.upload_button = self.action(footer, 'Thêm video vào hàng đợi…', self.upload_selected, side='left')
        self.upload_button.configure(style='Upload.TButton')
        self.action(footer, 'Mở video', self.open_result, side='left', padx=8)
        self.progress = ttk.Progressbar(footer, maximum=100)
        self.progress.pack(side='left', fill='x', expand=True, padx=(8, 0))
        self.result = tk.StringVar(value='')
        ttk.Label(container, textvariable=self.result, wraplength=960).pack(anchor='w', pady=(7, 0))
        self.eta = tk.StringVar(value='Dự kiến hoàn thành: chưa có hàng đợi.')
        ttk.Label(container, textvariable=self.eta, wraplength=960, foreground='#285b8d').pack(anchor='w', pady=(5, 0))
        self.playlist_notice = tk.StringVar(value='')
        self.playlist_notice_label = ttk.Label(container, textvariable=self.playlist_notice, wraplength=960, foreground='#285b8d')
        ttk.Label(container, textvariable=self.info, wraplength=960, foreground='#576779').pack(anchor='w', pady=(5, 0))
        self.table.bind('<<TreeviewSelect>>', self.selection_changed)
        self.table.bind('<Control-a>', lambda event: self.table.selection_set(self.table.get_children()))
        self.table.bind('<Button-3>', self.clip_menu)
        self.table.bind('<Double-1>', lambda event: self.show_clip_details())
        self.settings_window = tk.Toplevel(self)
        self.settings_window.withdraw()
        self.settings_window.title('Cài đặt YouTube Auto Uploader')
        self.settings_window.protocol('WM_DELETE_WINDOW', self.settings_window.withdraw)
        settings = ttk.Frame(self.settings_window, padding=18)
        settings.pack(fill='both', expand=True)
        ttk.Label(settings, text='Thiết lập một lần trên máy này', font=('Segoe UI', 14, 'bold')).pack(anchor='w', pady=(0, 12))
        ttk.Label(settings, text='Cấu hình email và playlist, nhập OAuth JSON, rồi kết nối.\nCác lần sau app tự kết nối và kiểm tra kênh đã lưu.', wraplength=570).pack(anchor='w', pady=(0, 12))
        ttk.Label(settings, textvariable=self.connection, wraplength=570, foreground='#285b8d').pack(anchor='w', pady=(0, 8))
        self.action(settings, 'Tài khoản & tên playlist', self.configure_account, fill='x', pady=3)
        self.action(settings, 'Nhập OAuth JSON', self.import_credentials, fill='x', pady=3)
        self.settings_connect = self.action(settings, 'Kết nối YouTube', self.connect, fill='x', pady=3)
        self.settings_reauthorize = self.action(settings, 'Cấp quyền lại / đổi kênh', lambda: self.connect(True), fill='x', pady=3)
        self.action(settings, 'Chọn playlist trùng tên', self.choose_playlist, fill='x', pady=3)
        self.action(settings, 'Xuất CSV xem trước', self.export_csv, fill='x', pady=3)
        self.confirmed = tk.BooleanVar(value=False)
        self.confirm_check = ttk.Checkbutton(settings, variable=self.confirmed, command=self.confirm_channel)
        self.defaults_label = tk.StringVar()
        ttk.Label(settings, textvariable=self.defaults_label, wraplength=570).pack(anchor='w', pady=12)
        ttk.Label(settings, text=f'Dữ liệu chỉ lưu trên máy này:\n{self.local}', wraplength=570, foreground='#576779').pack(anchor='w')
        self.show_defaults()
        self.update_controls()

    def show_settings(self):
        self.update_controls()
        self.settings_window.geometry(f'620x550+{max(0, self.winfo_x() + 50)}+{max(0, self.winfo_y() + 50)}')
        self.settings_window.deiconify()
        self.settings_window.lift()

    def update_controls(self):
        quota_wait = self.connection_quota_wait_until()
        if quota_wait:
            self.show_connection_quota_wait()
        for button in (self.settings_connect, self.settings_reauthorize):
            button.configure(state='disabled' if self.busy or quota_wait else 'normal')
        if hasattr(self, 'upload_button'):
            ready = self.client.channel_confirmed and (self.client.playlist_id or self.by_folder.get()) and not self.busy and bool(self.table.selection()) and all(row['path'] not in self.deleted_local for row in self.selected_rows())
            self.upload_button.configure(state='normal' if ready else 'disabled')
        if hasattr(self, 'delete_button'):
            eligible = not self.busy and any('done' in self.table.item(item, 'tags') for item in self.table.selection())
            self.delete_button.configure(state='normal' if eligible else 'disabled')

    def startup(self):
        if self.settings.data.get('expected_email') and self.client.secrets.read('credentials') and self.client.secrets.read('token'):
            if self.show_connection_quota_wait():
                self.after(100, self.scan_saved_folder)
            else:
                self.auto_connect()
        else:
            self.connection.set('Thiết lập lần đầu trong Cài đặt để bắt đầu.')
            self.reconnect.pack(anchor='w', pady=(0, 8), before=self.count)
            self.show_settings()
            self.after(100, self.scan_saved_folder)

    def connection_quota_wait_until(self):
        retry = self.settings.data.get('connection_quota_retry_at')
        if retry:
            retry_at = datetime.fromisoformat(retry)
            if retry_at > datetime.now(timezone.utc):
                return retry_at
        return None

    def show_connection_quota_wait(self):
        retry = self.connection_quota_wait_until()
        if not retry:
            return False
        local = retry.astimezone().strftime('%d/%m %H:%M')
        self.connection.set(f'Chờ hạn mức YouTube API đến {local} (giờ máy). App sẽ tự kết nối lại.')
        self.reconnect.pack_forget()
        return True

    def auto_connect(self):
        if self.settings.data.pop('connection_quota_retry_at', None):
            self.settings.save()
        self.connection.set('Đang kết nối và kiểm tra kênh đã lưu…')
        self.run_task(lambda: self.client.connect(interactive=False), self.connected, silent=True)

    def scan_saved_folder(self):
        if self.folder.get() and not self.busy:
            self.scan()

    @property
    def playlist_title(self):
        return self.settings.data['playlist_title']

    def show_defaults(self):
        data = self.settings.data
        audience = 'Made for kids' if data['made_for_kids'] else 'Not made for kids'
        self.defaults_label.set(f"Mặc định đã lưu: Audience = {audience} · Visibility = {data['privacy_status'].title()} · Không đặt lịch công khai")

    def run_task(self, function, callback, silent=False):
        if self.busy:
            return
        self.busy = True
        self.silent_task = silent
        self.scan_after_failure = callback == self.connected
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
                self.events.put(('error', friendly_error(error), quota_reason(error)))
        threading.Thread(target=worker, daemon=True).start()

    def drain(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'progress':
                    self.progress['value'] = event[1]
                    self.info.set(event[2])
                    if self.current_item and event[2].startswith('Đang upload'):
                        self.current_fraction = min(max(event[1] / 100, 0), 1)
                        self.refresh_eta()
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
                elif self.scan_after_failure and event[2] in ('quotaExceeded', 'dailyLimitExceeded'):
                    self.settings.data['connection_quota_retry_at'] = pacific_midnight_after(datetime.now(timezone.utc)).isoformat()
                    self.settings.save()
                    self.confirmed.set(False)
                    self.update_playlist()
                    self.show_connection_quota_wait()
                    self.info.set('YouTube đã dùng hết hạn mức API. Bạn có thể đóng app và mở lại sau giờ thử lại.')
                    self.after(100, self.scan_saved_folder)
                else:
                    self.info.set(event[1])
                    self.confirmed.set(self.client.channel_confirmed)
                    if self.scan_after_failure:
                        self.connection.set(f'Kết nối YouTube không thành công. {event[1]}')
                    elif not self.client.channel:
                        self.connection.set('Chưa kết nối / kết nối thất bại')
                    self.update_playlist()
                    self.reconnect.pack(anchor='w', pady=(0, 8), before=self.count)
                    if not self.silent_task:
                        messagebox.showerror('Chưa hoàn tất', event[1], parent=self)
                    elif self.scan_after_failure:
                        self.after(100, self.scan_saved_folder)
                self.update_controls()
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
        self.update_controls()

    def import_credentials(self):
        path = filedialog.askopenfilename(title='OAuth JSON loại Desktop app', filetypes=[('JSON', '*.json')])
        if path:
            self.run_task(lambda: self.client.import_credentials(path), self.credentials_imported)

    def credentials_imported(self, project):
        self.confirmed.set(False)
        self.connection.set('Chưa kết nối YouTube')
        self.update_playlist()
        self.update_controls()
        self.info.set(f'Đã nhập credentials project {project}; bản lưu local được mã hóa Windows DPAPI. Bấm Connect YouTube.')

    def connect(self, new_login=False):
        if self.busy or self.show_connection_quota_wait():
            return
        email_label = self.settings.data.get('expected_email') or '(email đã cấu hình)'
        request_consent = new_login or not self.client.secrets.read('token')
        if request_consent and not messagebox.askokcancel('Quyền truy cập OAuth',
            f'Đăng nhập {email_label} và tự cấp quyền trong trình duyệt.\n\n'
            'youtube.force-ssl: đọc kênh/playlist, upload, tạo playlist và quản lý mục trong playlist theo xác nhận của bạn. '
            'Google cũng cho quyền này khả năng sửa/xóa video, bình luận và phụ đề; app chỉ dùng các thao tác nêu trên.\n\n'
            'openid + email: kiểm tra địa chỉ email đã xác minh. Token được mã hóa bằng Windows DPAPI, '
            'lưu ngoài thư mục dự án/Drive. Chưa upload video khi kết nối.\n\nTiếp tục mở kết nối?', parent=self):
            return
        self.confirmed.set(False)
        self.connection.set('Đang kết nối YouTube… Nếu trình duyệt mở, hãy hoàn tất cấp quyền ở đó.')
        self.info.set('Đang kết nối. Bạn tự chọn tài khoản, kênh và cấp quyền trong trình duyệt. Chờ tối đa 5 phút.')
        self.run_task(lambda: self.client.connect(new_login), self.connected)

    def connected(self, channel):
        if self.settings.data.pop('connection_quota_retry_at', None):
            self.settings.save()
        self.connection.set(f"Đã kết nối: {channel['snippet']['title']}")
        self.reconnect.pack_forget()
        if not self.client.channel_confirmed:
            approved = self.settings.data.get('approved_channel_id') == channel['id'] and self.settings.data.get('approved_email') == self.settings.data.get('expected_email')
            if not approved:
                if messagebox.askyesno('Xác nhận kênh lần đầu',
                    f"Kênh: {channel['snippet']['title']}\nChannel ID: {channel['id']}\n\nDùng và ghi nhớ kênh này trên máy?", parent=self):
                    self.client.approve_channel()
            else:
                self.client.channel_confirmed = True
        self.confirmed.set(self.client.channel_confirmed)
        self.update_playlist()
        if self.client.channel_confirmed and self.by_folder.get():
            self.info.set('Sẵn sàng. Video mới sẽ dùng playlist theo thư mục.')
            self.settings_window.withdraw()
        elif not self.client.playlists:
            self.info.set('Không tìm thấy playlist đúng tên trên kênh này. Kiểm tra trong Cài đặt.')
        elif not self.client.playlist_id:
            self.choose_playlist()
        elif self.client.channel_confirmed:
            self.info.set('Sẵn sàng. Chọn một video để upload.')
            self.settings_window.withdraw()
        else:
            self.info.set('Kênh chưa được chấp nhận. Mở Cài đặt để kết nối lại.')
        self.update_controls()
        self.after(100, self.scan_saved_folder)

    def confirm_channel(self):
        if self.client.channel and self.confirmed.get():
            self.client.approve_channel()

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
                self.update_controls()
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
            if len(selected) > 1:
                self.details.set(f'Đã chọn {len(selected)} video. Tải lần lượt theo thứ tự trong danh sách.')
            else:
                error, video_id = self.clip_diagnostic(row)
                if error:
                    self.details.set(f"{row['title']}\n{error[:220]} · Nhấp đúp hoặc chuột phải → Xem lỗi để đọc đầy đủ.")
            if row['path'] in self.deleted_local:
                self.details.set(f"{row['title']} · Đã xoá trong máy. Lịch sử upload được giữ; dòng này sẽ mất khi quét lại thư mục.")
        self.update_controls()

    def selected_rows(self):
        return [self.rows[self.table.index(item)] for item in self.table.selection()]

    def clip_diagnostic(self, row):
        channel = self.client.channel['id'] if self.client.channel else None
        records = [r for r in self.history.recent(channel) if r['path'] == row['path']] if channel else []
        items = [i for i in self.upload_queue.all() if i['channel_id'] == channel and json.loads(i['row_json'])['path'] == row['path']]
        if items and items[-1]['history_id']:
            records = [self.history.get(items[-1]['history_id'])]
        record = records[0] if records else {}
        errors = list(dict.fromkeys(e for e in ((items[-1]['error'] if items else ''), record.get('error', '')) if e))
        return '\n'.join(errors), record.get('video_id', '')

    def clip_menu(self, event):
        item = self.table.identify_row(event.y)
        if not item:
            return
        if item not in self.table.selection():
            self.table.selection_set(item)
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label='Xem lỗi / hướng xử lý', command=self.show_clip_details)
        menu.add_command(label='Thử lại / hoàn tất video đã chọn…', command=self.upload_selected, state='disabled' if self.busy else 'normal')
        menu.add_separator()
        menu.add_command(label='Sao chép clip đã chọn sang thư mục…', command=self.copy_selected, state='disabled' if self.busy else 'normal')
        menu.add_command(label='Gom tất cả clip đỏ sang thư mục…', command=lambda: self.copy_selected(True), state='disabled' if self.busy else 'normal')
        menu.add_command(label='Xóa clip đã tải khỏi máy…', command=self.delete_selected, state='disabled' if self.busy else 'normal')
        menu.add_separator()
        menu.add_command(label='Kiểm tra lịch sử bằng nội dung SHA-256', command=self.check_local_content, state='disabled' if self.busy else 'normal')
        menu.add_command(label='Tìm video cùng tiêu đề trên kênh', command=self.check_channel_title, state='disabled' if self.busy else 'normal')
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def text_dialog(self, title, text):
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.geometry('850x440')
        frame = ttk.Frame(dialog)
        frame.pack(fill='both', expand=True)
        box = tk.Text(frame, wrap='word', font=('Segoe UI', 10), padx=14, pady=14)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=box.yview)
        box.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        box.pack(side='left', fill='both', expand=True)
        box.insert('1.0', text)
        box.configure(state='disabled')
        ttk.Button(dialog, text='Đóng', command=dialog.destroy).pack(pady=8)
        return dialog

    def delete_selected(self):
        if self.busy:
            return
        rows = [self.rows[self.table.index(item)] for item in self.table.selection()
                if 'done' in self.table.item(item, 'tags') and self.rows[self.table.index(item)]['path'] not in self.deleted_local]
        if not rows:
            messagebox.showinfo('Xóa clip trên máy', 'Chọn clip đã tải thành công (dấu tích xanh) trước.', parent=self)
            return
        channel = self.client.channel['id'] if self.client.channel else self.settings.data.get('channel_id', '')
        self.confirm_delete_rows(rows, channel)

    def find_and_delete_uploaded(self):
        if self.busy:
            return
        folder = self.folder.get().strip()
        if not folder:
            messagebox.showinfo('Tìm clip đã tải', 'Chọn thư mục video cần dọn trước.', parent=self)
            return
        channel = self.client.channel['id'] if self.client.channel else self.settings.data.get('channel_id', '')
        def found(result):
            rows, scanned, failures = result
            summary = f'Đã kiểm tra {scanned} clip trong thư mục và thư mục con; tìm thấy {len(rows)} clip đã tải thành công.'
            self.info.set(summary)
            if not rows:
                self.text_dialog('Kết quả tìm clip đã tải', summary + ('\n\nKhông đọc được:\n' + '\n'.join(failures) if failures else ''))
                return
            summary += f"\nDung lượng có thể giải phóng: {sum(row['size_mb'] for row in rows):,.1f} MB."
            if failures:
                summary += f'\nCó {len(failures)} tệp không đọc được; các tệp này sẽ được bỏ qua.'
            self.confirm_delete_rows(rows, channel, summary)
        self.run_task(lambda: find_uploaded_files(folder, self.history, channel,
            lambda value, text: self.events.put(('progress', value, text))), found)

    def confirm_delete_rows(self, rows, channel, summary=''):
        file_list = '\n'.join(row['path'] for row in rows[:10])
        if len(rows) > 10:
            file_list += f'\n… và {len(rows) - 10} tệp khác trong lựa chọn.'
        if not messagebox.askyesno('Xác nhận xóa vĩnh viễn tệp trên máy',
            (summary + '\n\n' if summary else '') + f'Bạn sắp XÓA VĨNH VIỄN {len(rows)} tệp trên máy (không vào Thùng rác):\n\n{file_list}\n\n'
            'App sẽ kiểm tra nội dung khớp lịch sử tải thành công trước khi xóa. '
            'Video trên YouTube và lịch sử upload được giữ nguyên. Dòng clip vẫn hiện đến khi quét lại thư mục. '
            'Nếu tệp nằm trong thư mục đồng bộ, việc xóa có thể đồng bộ sang Drive/OneDrive.\n\nĐồng ý xóa?', parent=self):
            return
        def done(result):
            deleted, failures = result
            self.deleted_local.update(deleted)
            known_paths = {row['path'] for row in self.rows}
            for row in rows:
                if row['path'] in deleted and row['path'] not in known_paths:
                    self.rows.append(row)
                    known_paths.add(row['path'])
                    self.table.insert('', 'end', values=(len(self.rows), row['filename'], row['title'], round(row['size_mb'], 2), 'Đã xoá trong máy'))
            self.count.configure(text=f'{len(self.rows)} video')
            self.refresh_statuses()
            self.update_controls()
            self.info.set(f'Đã xóa {len(deleted)} tệp trên máy. Dòng clip được giữ đến khi quét lại thư mục.')
            if failures:
                self.text_dialog('Một số tệp chưa được xóa', '\n\n'.join(failures))
        self.run_task(lambda: delete_uploaded_files(rows, self.history, channel), done)

    def show_clip_details(self):
        rows = self.selected_rows()
        if not rows:
            return
        sections = []
        for row in rows:
            error, video_id = self.clip_diagnostic(row)
            sections.append(f"{row['title']}\nTệp: {row['path']}\nVideo ID: {video_id or 'chưa có / chưa đối chiếu nội dung'}\n\nChi tiết:\n{error or 'Chưa có lỗi ghi nhận cho đường dẫn này.'}\n\nCách xử lý:\n{error_advice(error, video_id)}")
        self.text_dialog('Chi tiết clip / lỗi đã lưu', '\n\n────────\n\n'.join(sections))

    def copy_selected(self, all_errors=False):
        if self.busy:
            return
        rows = [self.rows[self.table.index(item)] for item in self.table.get_children() if 'error' in self.table.item(item, 'tags')] if all_errors else self.selected_rows()
        if not rows:
            messagebox.showinfo('Sao chép', 'Chưa có clip được chọn hoặc clip đỏ trong danh sách hiện tại.', parent=self)
            return
        destination = filedialog.askdirectory(title='Chọn thư mục gom bản sao để kiểm tra')
        if not destination:
            return
        def done(result):
            copied, failures = result
            self.text_dialog('Kết quả sao chép', f'Đã sao chép {len(copied)} clip.\nTệp gốc được giữ nguyên.\n\n' + '\n'.join(copied + failures))
        self.run_task(lambda: copy_for_inspection(rows, destination), done)

    def check_local_content(self):
        rows = self.selected_rows()
        if self.busy or not rows or not self.ready():
            return
        channel = self.client.channel['id']
        def work():
            lines = []
            for row in rows:
                digest = fingerprint(Path(row['path']))
                record = self.history.find(channel, digest)
                lines.append(f"{row['title']}\n" + (f"Đã có nội dung trong lịch sử: {record['state']}\nVideo ID: {record['video_id'] or 'chưa rõ kết quả'}\nĐường dẫn cũ: {record['path']}\n{record['error']}" if record else 'Chưa có SHA-256 này trong lịch sử máy này. Điều đó không đảm bảo kênh chưa có video.'))
            return '\n\n'.join(lines)
        self.run_task(work, lambda result: self.text_dialog('Kiểm tra nội dung / lịch sử', result))

    def check_channel_title(self):
        rows = self.selected_rows()
        if self.busy or not rows or not self.ready():
            return
        row = rows[0]
        def done(matches):
            text = f"Tiêu đề: {row['title']}\n\n" + '\n'.join(f"{m['title']}\nhttps://www.youtube.com/watch?v={m['video_id']}" for m in matches)
            text += '\n\n' + ('Các kết quả cùng tiêu đề cần mở đối chiếu nội dung trong Studio.' if matches else 'Không thấy tiêu đề trùng. Video đã đổi tiêu đề vẫn có thể tồn tại trên kênh.')
            text += '\nTra cứu tiêu đề không chứng minh hai tệp có cùng nội dung. Kết quả không tự gắn vào lịch sử hoặc tải video.'
            self.text_dialog('Kết quả tra cứu trên kênh', text)
        self.run_task(lambda: self.client.matching_channel_titles(row['title'], lambda value, text: self.events.put(('progress', value, text))), done)

    def choose_folder(self):
        folder = filedialog.askdirectory(title='Chọn thư mục video', initialdir=self.folder.get() or None)
        if folder:
            self.folder.set(folder)
            self.settings.data['last_folder'] = folder
            self.settings.save()
            self.scan()

    def scan(self):
        if self.busy or not self.folder.get().strip():
            return
        folder = Path(self.folder.get()).expanduser()
        self.settings.data['last_folder'] = str(folder)
        self.settings.save()
        self.rows = []
        self.table.delete(*self.table.get_children())
        def work():
            config = read_config(ROOT / 'config.json')
            config['scan_subfolders'] = True
            path = Path(config.get('metadata_csv', 'metadata.csv'))
            return preview(folder, config, read_metadata(path if path.is_absolute() else ROOT / path))
        def done(rows):
            self.rows = rows
            self.deleted_local.clear()
            self.table.delete(*self.table.get_children())
            for index, row in enumerate(rows, 1):
                self.table.insert('', 'end', values=(index, row['filename'], row['title'], row['size_mb'], ''))
            self.count.configure(text=f'{len(rows)} video')
            self.refresh_statuses()
            self.info.set(f'Đã quét {len(rows)} video. Chọn một video để upload.' if self.client.channel_confirmed and self.client.playlist_id else 'Đã quét thư mục. Hoàn tất kết nối trong Cài đặt để upload.')
        self.run_task(work, done, silent=True)

    def save_defaults(self):
        self.settings.data.update(privacy_status=self.privacy.get(), made_for_kids=self.kids.get())
        self.settings.save()
        self.show_defaults()
        self.info.set('Đã lưu Audience và Visibility cho lần chạy sau. Playlist được lưu theo Channel ID.')

    def save_playlist_mode(self):
        self.settings.data['playlist_by_folder'] = self.by_folder.get()
        self.settings.save()
        self.update_controls()

    def configure_mp3_source(self):
        current = self.settings.data.get('mp3_source', '')
        action = messagebox.askyesnocancel('Nguồn tên playlist khi tải video mới',
            f"Nguồn hiện tại: {current or 'thư mục chứa MP4'}\n\nCó: chọn thư mục MP3 để đối chiếu tên MP4.\nKhông: dùng thư mục chứa MP4.\nHủy: giữ lựa chọn hiện tại.", parent=self)
        if action is None:
            return
        folder = filedialog.askdirectory(title='Chọn thư mục gốc chứa MP3', initialdir=current or None, parent=self) if action else ''
        if action and not folder:
            return
        self.settings.data['mp3_source'] = folder
        self.by_folder.set(True)
        self.save_playlist_mode()
        self.info.set(f"Nguồn tên playlist: {folder or 'thư mục chứa MP4'}")

    def organize_history(self):
        if self.busy:
            return
        batch = self.playlist_batch.read()
        if batch and any(item['state'] == 'pending' for item in batch['items']):
            self.show_playlist_batch(batch)
            return
        if not self.ready(require_playlist=False):
            return
        dialog = tk.Toplevel(self)
        dialog.title('Sắp playlist video cũ')
        dialog.transient(self)
        panel = ttk.Frame(dialog, padding=16)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='Chọn nguồn tên thư mục để lập danh sách chuyển.', wraplength=520).pack(anchor='w', pady=(0, 10))

        def start(use_mp3):
            if self.busy:
                return
            folder = filedialog.askdirectory(title='Chọn thư mục gốc chứa MP3', parent=dialog) if use_mp3 else None
            if use_mp3 and not folder:
                return
            channel = self.client.channel['id']
            dialog.destroy()
            self.info.set('Đang lập danh sách playlist đề xuất…')
            self.run_task(lambda: plan_history(self.history.recent(channel), Mp3Index(folder) if folder else None),
                          self.review_playlist_plan)

        ttk.Button(panel, text='Dùng thư mục từng lưu trong lịch sử', command=lambda: start(False)).pack(fill='x', pady=4)
        ttk.Button(panel, text='Chọn thư mục MP3 để đối chiếu tên', command=lambda: start(True)).pack(fill='x', pady=4)
        if batch:
            ttk.Button(panel, text='Xem kết quả đợt trước', command=lambda: self.show_playlist_batch(batch)).pack(fill='x', pady=4)
        dialog.grab_set()

    def review_playlist_plan(self, proposals):
        if not proposals:
            messagebox.showinfo('Sắp playlist video cũ', 'Kênh này chưa có Video ID trong lịch sử trên máy.', parent=self)
            return
        dialog = tk.Toplevel(self)
        self.playlist_review = dialog
        dialog.title('Xem trước playlist cho video cũ')
        dialog.geometry('1100x570')
        dialog.transient(self)
        panel = ttk.Frame(dialog, padding=12)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='Bấm vào dòng để chọn hoặc bỏ chọn. Tên gần giống cần chọn thủ công sau khi kiểm tra.',
                  wraplength=1000).pack(anchor='w', pady=(0, 8))
        frame = ttk.Frame(panel)
        frame.pack(fill='both', expand=True)
        tree = ttk.Treeview(frame, columns=('use', 'title', 'target', 'detail'), show='headings', selectmode='browse')
        for key, label, width in [('use', 'Dùng', 58), ('title', 'Video', 320), ('target', 'Playlist đích', 280), ('detail', 'Căn cứ', 290)]:
            tree.heading(key, text=label)
            tree.column(key, width=width, stretch=key != 'use')
        scroll = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        chosen = set()
        for i, item in enumerate(proposals):
            if item['automatic'] and item['target']:
                chosen.add(i)
            tree.insert('', 'end', iid=str(i), values=('✓' if i in chosen else '—', item['record']['title'],
                                                      item['target'], item['detail']))
        detail = tk.StringVar(value='Chọn một dòng để xem đường dẫn dùng để đối chiếu.')
        ttk.Label(panel, textvariable=detail, wraplength=1020).pack(anchor='w', pady=8)
        remove_old = tk.BooleanVar(value=True)
        ttk.Checkbutton(panel, text='Gỡ khỏi playlist cũ ghi trong lịch sử sau khi thêm và xác minh playlist đích',
                        variable=remove_old).pack(anchor='w')
        buttons = ttk.Frame(panel)
        buttons.pack(fill='x', pady=(8, 0))

        def mark(i, enabled):
            if enabled:
                chosen.add(i)
            else:
                chosen.discard(i)
            tree.set(str(i), 'use', '✓' if enabled else '—')
            apply.configure(text=f'Áp dụng cho {len(chosen)} video…', state='normal' if chosen else 'disabled')

        def toggle(event):
            iid = tree.identify_row(event.y)
            if iid:
                i = int(iid)
                item = proposals[i]
                detail.set(f"{item['record']['video_id']} · {item['source']}")
                if item['target']:
                    mark(i, i not in chosen)

        def select_suggestions():
            for i, item in enumerate(proposals):
                if item['target'] and not item['detail'].startswith('Gần giống'):
                    mark(i, True)

        def clear_suggestions():
            for i in tuple(chosen):
                mark(i, False)

        def execute():
            if self.busy or not chosen or not self.ready(require_playlist=False):
                return
            picked = [proposals[i] for i in sorted(chosen)]
            move = remove_old.get()
            action = 'Chuyển playlist' if move else 'Thêm vào playlist đích'
            if not messagebox.askyesno(action, f'{action} cho {len(picked)} video?\n'
                'Playlist mới ở chế độ Riêng tư. App lưu đợt này và tự tiếp tục sau khi hạn mức được cấp lại.', parent=dialog):
                return
            self.playlist_batch.start(self.client.channel['id'], picked, move)
            dialog.destroy()
            self.run_playlist_batch(show_result=True)

        tree.bind('<ButtonRelease-1>', toggle)
        ttk.Button(buttons, text='Chọn tất cả đề xuất rõ ràng', command=select_suggestions).pack(side='left')
        ttk.Button(buttons, text='Bỏ chọn hết', command=clear_suggestions).pack(side='left', padx=8)
        apply = ttk.Button(buttons, text=f'Áp dụng cho {len(chosen)} video…', command=execute,
                           state='normal' if chosen else 'disabled')
        apply.pack(side='right')
        dialog.grab_set()

    def playlist_batch_summary(self, batch):
        from datetime import datetime
        done = sum(item['state'] == 'done' for item in batch['items'])
        errors = sum(item['state'] == 'error' for item in batch['items'])
        pending = sum(item['state'] == 'pending' for item in batch['items'])
        summary = f'Sắp playlist — {done} hoàn tất · {pending} còn chờ · {errors} cần kiểm tra'
        if batch['retry_at']:
            retry = datetime.fromisoformat(batch['retry_at']).astimezone().strftime('%d/%m %H:%M')
            summary += f'. Chờ hạn mức YouTube đến {retry} (giờ máy).'
        elif pending and batch['reason']:
            summary += '. Đợt đang tạm dừng, mở “Sắp playlist video cũ” để tiếp tục.'
        return summary

    def update_playlist_notice(self, batch):
        if batch:
            self.playlist_notice.set(self.playlist_batch_summary(batch))
            self.playlist_notice_label.pack(anchor='w', pady=(4, 0))

    def run_playlist_batch(self, show_result=False):
        def done(batch):
            self.update_playlist_notice(batch)
            self.info.set(batch['reason'] or 'Đã xử lý xong đợt sắp playlist.')
            self.progress['value'] = 100 * sum(item['state'] != 'pending' for item in batch['items']) / len(batch['items'])
            if show_result:
                self.show_playlist_batch(batch)
        self.info.set('Đang sắp playlist…')
        self.playlist_notice.set('Đang xử lý đợt sắp playlist đã lưu.')
        self.playlist_notice_label.pack(anchor='w', pady=(4, 0))
        self.run_task(lambda: self.playlist_batch.run(self.client,
            lambda value, text: self.events.put(('progress', value, text))), done)

    def show_playlist_batch(self, batch):
        existing = getattr(self, 'playlist_batch_window', None)
        if existing and existing.winfo_exists():
            existing.destroy()
        pending = any(item['state'] == 'pending' for item in batch['items'])
        reason = '\n' + batch['reason'] if batch['reason'] else ''
        lines = [self.playlist_batch_summary(batch) + reason]
        if pending and batch['retry_at']:
            lines.append('App tự chạy tiếp khi đến giờ, app đang mở và đúng kênh đã kết nối.')
        for item in batch['items']:
            symbol = {'done': '✓', 'error': '✕', 'pending': '●', 'cancelled': '—'}[item['state']]
            lines.append(f"{symbol} {item['record']['title']} → {item['target']}" + ('\n' + item['detail'] if item['detail'] else ''))
        dialog = self.text_dialog('Kết quả sắp playlist', '\n\n'.join(lines))
        self.playlist_batch_window = dialog
        if not pending:
            return

        def resume():
            current = self.playlist_batch.read()
            if self.busy or not self.ready(require_playlist=False):
                return
            if current['channel'] != self.client.channel['id']:
                messagebox.showinfo('Kênh của đợt sắp playlist', 'Kết nối lại đúng kênh đã dùng để tạo đợt này.', parent=dialog)
                return
            if not self.playlist_batch.due(current):
                messagebox.showinfo('Chờ hạn mức', self.playlist_batch_summary(current), parent=dialog)
                return
            dialog.destroy()
            self.run_playlist_batch(show_result=True)

        def cancel():
            if self.busy or not messagebox.askyesno('Bỏ các mục còn chờ',
                'Bỏ các mục chưa xử lý trong đợt này? Các mục đã hoàn tất sẽ được giữ.', parent=dialog):
                return
            if self.busy or not dialog.winfo_exists():
                return
            current = self.playlist_batch.read()
            for item in current['items']:
                if item['state'] == 'pending':
                    item.update(state='cancelled', detail='Đã bỏ khỏi đợt')
            current.update(retry_at='', reason='')
            self.playlist_batch.save(current)
            self.update_playlist_notice(current)
            dialog.destroy()

        actions = ttk.Frame(dialog)
        actions.pack(fill='x', padx=12, pady=(0, 8))
        ttk.Button(actions, text='Chạy tiếp đợt này', command=resume).pack(side='left')
        ttk.Button(actions, text='Bỏ các mục còn chờ…', command=cancel).pack(side='right')

    def ready(self, require_playlist=True):
        if not self.client.channel or not self.client.channel_confirmed or (require_playlist and not self.client.playlist_id):
            message = 'Hãy kết nối YouTube và xác nhận đúng kênh.'
            if require_playlist:
                message += ' Chọn playlist mặc định trong Cài đặt nếu chưa có.'
            messagebox.showinfo('Chưa sẵn sàng', message, parent=self)
            return False
        return True

    def upload_selected(self):
        by_folder = self.by_folder.get()
        if self.busy or not self.ready(require_playlist=not by_folder):
            return
        selected = self.table.selection()
        if not selected:
            messagebox.showinfo('Chọn video', 'Chọn đúng một video trong danh sách.', parent=self)
            return
        rows = [dict(self.rows[self.table.index(item)]) for item in sorted(selected, key=self.table.index)]
        if any(row['path'] in self.deleted_local for row in rows):
            messagebox.showinfo('Tệp đã xóa', 'Bỏ chọn các dòng Đã xoá trong máy hoặc quét lại thư mục.', parent=self)
            return
        privacy, kids = self.privacy.get(), self.kids.get()
        mp3_root = self.settings.data.get('mp3_source', '') if by_folder else ''
        if mp3_root:
            def match_rows():
                index = Mp3Index(mp3_root)
                matched, uncertain = [], []
                for row in rows:
                    path, reason = index.match(row['path'])
                    if reason == 'Tên khớp' and folder_title(str(path)):
                        matched.append(dict(row, folder_playlist=folder_title(str(path))))
                    else:
                        uncertain.append(f"{row['filename']} · {reason}")
                return matched, uncertain

            def review_matches(result):
                matched, uncertain = result
                if uncertain:
                    self.text_dialog('Video chưa ghép được với MP3',
                        'Các video sau cần đối chiếu lại tên MP3 trước khi đưa vào hàng đợi.\n\n' + '\n'.join(uncertain))
                if matched and self.ready(require_playlist=False):
                    self.enqueue_rows(matched, privacy, kids, True, len(uncertain))

            self.run_task(match_rows, review_matches)
            return
        if by_folder:
            for row in rows:
                row['folder_playlist'] = folder_title(row['path'])
        self.enqueue_rows(rows, privacy, kids, by_folder)

    def enqueue_rows(self, rows, privacy, kids, by_folder, skipped=0):
        playlist_info = f'Playlist cố định: {self.playlist_title}'
        if by_folder:
            if any(not row['folder_playlist'] or len(row['folder_playlist']) > 150 for row in rows):
                messagebox.showerror('Tên playlist', 'Một số video thiếu tên thư mục chứa hợp lệ hoặc tên dài quá 150 ký tự.', parent=self)
                return
            titles = sorted({row['folder_playlist'] for row in rows})
            playlist_info = f'{len(titles)} playlist theo thư mục: ' + ', '.join(titles[:8])
            if len(titles) > 8:
                playlist_info += f' và {len(titles) - 8} playlist khác'
            playlist_info += '. Playlist tạo mới ở chế độ Riêng tư.'
        if skipped:
            playlist_info += f' Bỏ qua {skipped} video chưa khớp tên MP3.'
        audience = 'Made for kids' if kids else 'Not made for kids'
        if not messagebox.askyesno('Xác nhận hàng đợi upload',
            f"Số video: {len(rows)}\n"
            f"Kênh: {self.client.channel['snippet']['title']}\nChannel ID: {self.client.channel['id']}\n"
            f'{playlist_info}\n'
            f'Audience: {audience}\nVisibility: {privacy.upper()}\nKhông đặt lịch công khai.\n\n'
            'Tải tuần tự; khi mở lại app, hàng đợi sẽ tiếp tục.\n'
            'Nếu nội dung đã có Video ID trong lịch sử: chỉ hoàn tất và xác minh theo cài đặt lần tải trước, không đổi Audience/Visibility.\n\nĐồng ý bắt đầu?', parent=self):
            return
        self.progress['value'] = 0
        self.video_url = ''
        count = self.upload_queue.add(rows, self.client.channel['id'], '' if by_folder else self.client.playlist_id, privacy, kids)
        self.settings.data['queue_paused'] = False
        self.settings.save()
        self.result.set(f'Đã thêm {count} video vào hàng đợi. Xem tiến trình trong Hàng đợi.')
        self.refresh_statuses()
        self.refresh_queue()
        self.kick_queue()

    def kick_queue(self):
        self.after_cancel(self.queue_timer)
        self.queue_timer = self.after(100, self.queue_tick)

    def refresh_statuses(self):
        if not hasattr(self, 'table'):
            return
        channel = self.client.channel['id'] if self.client.channel else None
        states = {}
        if channel:
            for record in reversed(self.history.recent(channel)):
                label = ('✓ Đã tải (lịch sử)', 'done') if record['state'] == 'Uploaded' and record['verified'] else ('✕ Cần kiểm tra', 'error')
                states[record['path']] = label
            for item in self.upload_queue.all():
                if item['channel_id'] == channel:
                    states[json.loads(item['row_json'])['path']] = STATUS.get(item['state'], ('', ''))
        for index, tree_id in enumerate(self.table.get_children()):
            if index >= len(self.rows):
                break
            label, tag = states.get(self.rows[index]['path'], ('— Chưa thêm', ''))
            if self.rows[index]['path'] in self.deleted_local:
                label, tag = 'Đã xoá trong máy', 'deleted'
            self.table.set(tree_id, 'state', label)
            self.table.item(tree_id, tags=(tag,))

    def refresh_eta(self):
        from datetime import datetime, timedelta, timezone
        items = self.upload_queue.all()
        active = [item for item in items if item['state'] in ('pending', 'running', 'waiting')]
        if not active:
            attention = any(item['state'] in ('attention', 'interrupted') for item in items)
            text = 'Hàng đợi đã hết mục chờ.' + (' Có mục cần kiểm tra.' if attention else '') if items else 'Chưa có hàng đợi.'
        elif self.settings.data.get('queue_paused'):
            text = 'Đã tạm dừng; chưa thể ước tính giờ hoàn thành.'
        elif not self.client.channel_confirmed:
            text = 'Chưa kết nối; chưa thể ước tính giờ hoàn thành.'
        elif any(item['channel_id'] != self.client.channel['id'] or (item['playlist_id'] and item['playlist_id'] != self.client.playlist_id) for item in active):
            text = 'Có video thuộc kênh hoặc playlist khác; chưa thể ước tính.'
        elif active[0]['state'] == 'waiting' and active[0]['retry_at'] and datetime.fromisoformat(active[0]['retry_at']) > datetime.now(timezone.utc):
            retry = datetime.fromisoformat(active[0]['retry_at']).astimezone().strftime('%d/%m %H:%M')
            text = f'Chờ hạn mức; thử lại sau {retry}. Chưa thể dự đoán giờ hoàn thành.'
        else:
            bytes_done = sum(sample[0] for sample in self.transfer_samples)
            seconds = sum(sample[1] for sample in self.transfer_samples)
            if self.current_item and self.current_started and self.current_fraction > 0:
                elapsed = time.monotonic() - self.current_started
                size = json.loads(self.current_item['row_json']).get('size_mb', 0) * 1024 * 1024
                if elapsed > 0 and size > 0:
                    bytes_done += size * self.current_fraction
                    seconds += elapsed
            speed = bytes_done / seconds if seconds > 0 else None
            remaining = estimate_remaining(active, self.current_item['id'] if self.current_item else None, self.current_fraction, speed)
            if remaining is None:
                text = 'Đang chờ dữ liệu tốc độ tải để ước tính.'
            elif remaining < 1 and self.current_item:
                text = 'Đang hoàn tất và xác minh video cuối.'
            else:
                finish = (datetime.now().astimezone() + timedelta(seconds=remaining)).strftime('%d/%m %H:%M')
                minutes = max(1, round(remaining / 60))
                text = f'Khoảng {minutes // 60} giờ {minutes % 60:02} phút nữa · khoảng {finish} (giờ máy).'
        self.eta.set('Dự kiến hoàn thành: ' + text)


    def queue_tick(self):
        review = getattr(self, 'playlist_review', None)
        reviewing = review and review.winfo_exists()
        if not self.busy and self.settings.data.get('connection_quota_retry_at') and not self.show_connection_quota_wait():
            self.auto_connect()
        if not self.busy:
            batch = self.playlist_batch.read()
            self.update_playlist_notice(batch)
            if (batch and batch['retry_at'] and self.playlist_batch.due(batch) and not reviewing
                    and self.client.channel and self.client.channel_confirmed and self.client.channel['id'] == batch['channel']):
                dialog = getattr(self, 'playlist_batch_window', None)
                if dialog and dialog.winfo_exists():
                    dialog.destroy()
                self.run_playlist_batch()
        if not self.busy and not self.settings.data.get('queue_paused', False) and not reviewing:
            item = self.upload_queue.next()
            if item and self.client.channel_confirmed:
                if self.client.channel['id'] != item['channel_id'] or (item['playlist_id'] and self.client.playlist_id != item['playlist_id']):
                    self.info.set('Hàng đợi thuộc kênh hoặc playlist khác; kết nối đúng để tiếp tục.')
                else:
                    row = json.loads(item['row_json'])
                    self.current_item = item
                    self.current_started = time.monotonic()
                    self.current_fraction = 0.0
                    self.result.set(f"Đang tải: {row['title']}")
                    self.run_task(lambda: self.upload_queue.process(item, self.client,
                        lambda value, text: self.events.put(('progress', value, text))), self.queue_finished, silent=True)
                    self.after(250, self.refresh_queue)
        self.refresh_statuses()
        self.refresh_eta()
        self.queue_timer = self.after(5000, self.queue_tick)

    def queue_finished(self, row):
        if row and self.current_item and self.current_started and self.current_fraction > 0:
            size = json.loads(self.current_item['row_json']).get('size_mb', 0) * 1024 * 1024
            elapsed = time.monotonic() - self.current_started
            if size > 0 and elapsed > 0:
                self.transfer_samples = (self.transfer_samples + [(size, elapsed)])[-5:]
        self.current_item = None
        self.current_started = None
        self.current_fraction = 0.0
        if row:
            self.upload_finished(row)
        else:
            self.info.set('Một mục đang chờ hoặc cần kiểm tra. Mở Hàng đợi để xem chi tiết.')
        self.refresh_queue()
        self.refresh_statuses()
        self.refresh_eta()
        self.kick_queue()

    def show_queue(self):
        if getattr(self, 'queue_window', None) and self.queue_window.winfo_exists():
            self.queue_window.lift()
            self.refresh_queue()
            return
        self.queue_window = tk.Toplevel(self)
        self.queue_window.title('Hàng đợi upload')
        self.queue_window.geometry('1040x420')
        frame = ttk.Frame(self.queue_window, padding=12)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Tải tuần tự khi app đang mở. Mục bị gián đoạn cần kiểm tra Lịch sử / YouTube Studio.').pack(anchor='w')
        self.queue_table = ttk.Treeview(frame, columns=('number','title','state','retry','error'), show='headings', selectmode='extended')
        for key, label, width in [('number','STT',55), ('title','Video',300), ('state','Trạng thái',160), ('retry','Thử lại sau (giờ máy)',180), ('error','Chi tiết',400)]:
            self.queue_table.heading(key, text=label)
            self.queue_table.column(key, width=width)
        self.queue_table.pack(fill='both', expand=True, pady=8)
        for tag, color in [('waiting', '#9a6700'), ('done', '#18733e'), ('error', '#b42318')]:
            self.queue_table.tag_configure(tag, foreground=color)
        ttk.Label(frame, textvariable=self.eta, foreground='#285b8d').pack(anchor='w', pady=(0, 6))
        bar = ttk.Frame(frame)
        bar.pack(fill='x')
        ttk.Button(bar, text='Tạm dừng / tiếp tục', command=self.toggle_queue).pack(side='left')
        ttk.Button(bar, text='Xóa mục đã chọn khỏi hàng đợi', command=self.remove_queue).pack(side='left', padx=8)
        self.queue_status = tk.StringVar()
        ttk.Label(bar, textvariable=self.queue_status).pack(side='left')
        self.refresh_queue()

    def refresh_queue(self):
        if not getattr(self, 'queue_window', None) or not self.queue_window.winfo_exists():
            return
        from datetime import datetime
        self.queue_table.delete(*self.queue_table.get_children())
        for index, item in enumerate(self.upload_queue.all(), 1):
            retry = datetime.fromisoformat(item['retry_at']).astimezone().strftime('%d/%m/%Y %H:%M') if item['retry_at'] else ''
            label, tag = STATUS.get(item['state'], (item['state'], ''))
            row = json.loads(item['row_json'])
            description = item['error'] or (f"Playlist đích: {row['folder_playlist']}" if row.get('folder_playlist') else '')
            self.queue_table.insert('', 'end', iid=str(item['id']), values=(index, row['title'], label, retry, description), tags=(tag,))
        self.queue_status.set('Đã tạm dừng' if self.settings.data.get('queue_paused') else 'Đang hoạt động')

    def toggle_queue(self):
        self.settings.data['queue_paused'] = not self.settings.data.get('queue_paused', False)
        self.settings.save()
        self.refresh_queue()
        self.refresh_eta()
        self.kick_queue()

    def remove_queue(self):
        for item in self.queue_table.selection():
            self.upload_queue.remove(int(item))
        self.refresh_queue()
        self.refresh_statuses()
        self.refresh_eta()

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
        if not self.ready(require_playlist=False):
            return
        row = self.selected_history()
        if row:
            if not row['video_id']:
                messagebox.showinfo('Chưa rõ kết quả', 'Kiểm tra Studio và dùng Đối chiếu Video ID. App sẽ không upload lại.', parent=self)
                return
            self.run_task(lambda: self.client.finish(row['id']), self.upload_finished)

    def reconcile(self):
        if not self.ready(require_playlist=False):
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
