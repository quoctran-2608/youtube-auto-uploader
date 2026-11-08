"""YouTube Auto Uploader v0.3 — scan, OAuth, and one confirmed upload."""
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
        self.title('YouTube Auto Uploader · v0.3')
        self.geometry('1040x700')
        self.minsize(880, 620)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.drain)
        self.after(300, self.startup)

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
        self.count = ttk.Label(container, text='0 video')
        self.count.pack(anchor='w', pady=(0, 5))
        frame = ttk.Frame(container)
        frame.pack(fill='both', expand=True)
        columns = ('filename', 'title', 'size_mb', 'publish_at')
        self.table = ttk.Treeview(frame, columns=columns, displaycolumns=('filename', 'title', 'size_mb'), show='headings', selectmode='browse', height=8)
        for key, title, width in [('filename', 'Tệp video', 340), ('title', 'Tiêu đề', 440), ('size_mb', 'MB', 75)]:
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=60, stretch=key != 'size_mb')
        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        self.details = tk.StringVar(value='Chọn một video để xem metadata và upload.')
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
        self.action(options, 'Lưu mặc định', self.save_defaults, side='right')
        footer = ttk.Frame(container)
        footer.pack(fill='x', pady=(12, 0))
        self.upload_button = self.action(footer, 'Upload video đã chọn…', self.upload_selected, side='left')
        self.upload_button.configure(style='Upload.TButton')
        self.action(footer, 'Mở video', self.open_result, side='left', padx=8)
        self.progress = ttk.Progressbar(footer, maximum=100)
        self.progress.pack(side='left', fill='x', expand=True, padx=(8, 0))
        self.result = tk.StringVar(value='')
        ttk.Label(container, textvariable=self.result, wraplength=960).pack(anchor='w', pady=(7, 0))
        ttk.Label(container, textvariable=self.info, wraplength=960, foreground='#576779').pack(anchor='w', pady=(5, 0))
        self.table.bind('<<TreeviewSelect>>', self.selection_changed)
        self.settings_window = tk.Toplevel(self)
        self.settings_window.withdraw()
        self.settings_window.title('Cài đặt YouTube Auto Uploader')
        self.settings_window.protocol('WM_DELETE_WINDOW', self.settings_window.withdraw)
        settings = ttk.Frame(self.settings_window, padding=18)
        settings.pack(fill='both', expand=True)
        ttk.Label(settings, text='Thiết lập một lần trên máy này', font=('Segoe UI', 14, 'bold')).pack(anchor='w', pady=(0, 12))
        ttk.Label(settings, text='Cấu hình email và playlist, nhập OAuth JSON, rồi kết nối.\nCác lần sau app tự kết nối và kiểm tra kênh đã lưu.', wraplength=570).pack(anchor='w', pady=(0, 12))
        for title, command in [('Tài khoản & tên playlist', self.configure_account), ('Nhập OAuth JSON', self.import_credentials), ('Kết nối YouTube', self.connect), ('Cấp quyền lại / đổi kênh', lambda: self.connect(True)), ('Chọn playlist trùng tên', self.choose_playlist), ('Xuất CSV xem trước', self.export_csv)]:
            self.action(settings, title, command, fill='x', pady=3)
        self.confirmed = tk.BooleanVar(value=False)
        self.confirm_check = ttk.Checkbutton(settings, variable=self.confirmed, command=self.confirm_channel)
        self.defaults_label = tk.StringVar()
        ttk.Label(settings, textvariable=self.defaults_label, wraplength=570).pack(anchor='w', pady=12)
        ttk.Label(settings, text=f'Dữ liệu chỉ lưu trên máy này:\n{self.local}', wraplength=570, foreground='#576779').pack(anchor='w')
        self.show_defaults()
        self.update_controls()

    def show_settings(self):
        self.settings_window.geometry(f'620x510+{max(0, self.winfo_x() + 50)}+{max(0, self.winfo_y() + 50)}')
        self.settings_window.deiconify()
        self.settings_window.lift()

    def update_controls(self):
        if hasattr(self, 'upload_button'):
            ready = self.client.channel_confirmed and bool(self.client.playlist_id) and not self.busy and bool(self.table.selection())
            self.upload_button.configure(state='normal' if ready else 'disabled')

    def startup(self):
        if self.settings.data.get('expected_email') and self.client.secrets.read('credentials') and self.client.secrets.read('token'):
            self.connection.set('Đang kết nối và kiểm tra kênh đã lưu…')
            self.run_task(lambda: self.client.connect(interactive=False), self.connected, silent=True)
        else:
            self.connection.set('Thiết lập lần đầu trong Cài đặt để bắt đầu.')
            self.reconnect.pack(anchor='w', pady=(0, 8), before=self.count)
            self.show_settings()
            self.after(100, self.scan_saved_folder)

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
        if self.busy:
            return
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
        if not self.client.playlists:
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
        self.update_controls()

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
            path = Path(config.get('metadata_csv', 'metadata.csv'))
            return preview(folder, config, read_metadata(path if path.is_absolute() else ROOT / path))
        def done(rows):
            self.rows = rows
            self.table.delete(*self.table.get_children())
            for row in rows:
                self.table.insert('', 'end', values=(row['filename'], row['title'], row['size_mb'], row['publish_at']))
            self.count.configure(text=f'{len(rows)} video')
            self.info.set(f'Đã quét {len(rows)} video. Chọn một video để upload.' if self.client.channel_confirmed and self.client.playlist_id else 'Đã quét thư mục. Hoàn tất kết nối trong Cài đặt để upload.')
        self.run_task(work, done, silent=True)

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
