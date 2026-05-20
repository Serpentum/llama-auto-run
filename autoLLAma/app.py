import os
import sys
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext

from autoLLAma.utils import sanitize_args, args_list_to_string, string_to_args_list, get_model_from_args
from autoLLAma.settings import load_settings, save_settings
from autoLLAma.monitor import get_cpu_usage, get_windows_memory_info, get_gpu_memory, format_bytes
from autoLLAma.threads import LogReaderThread, MonitorThread
from autoLLAma.theme import apply_theme, THEMES
from autoLLAma.api_client import APIClient


DEFAULT_ARGS = [
    "--fit", "on",
    "--fit-ctx", "128000",
    "--fit-target", "256",
    "-np", "1",
    "-fa", "on",
    "--no-mmap",
    "--mlock",
    "-b", "2048",
    "-ub", "2048",
    "-ctk", "q8_0",
    "-ctv", "q8_0",
    "--temp", "0.6",
    "--top-p", "0.95",
    "--top-k", "20",
    "--min-p", "0.0",
    "--presence-penalty", "0.0",
    "--repeat-penalty", "1.0",
    "--reasoning-budget", "-1",
    "--chat-template-kwargs", '{"preserve_thinking": true}',
    "--host", "0.0.0.0",
    "--port", "8033",
]


class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("LLM Server Launcher")
        self.root.geometry("900x650")
        self.root.minsize(650, 500)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.proc = None
        self.log_thread = None
        self.monitor_thread = None
        self._monitor_stop = threading.Event()
        self._is_running = False

        self.status_var = tk.StringVar(value="⏸ Ожидание")

        settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "launcher_settings.json")
        _DEFAULT_EXE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "llama_server", "llama-server.exe")

        settings = load_settings(settings_file)
        if settings and "args" in settings:
            self.current_args = sanitize_args(settings["args"])
            self.current_exe = settings.get("exe_path", _DEFAULT_EXE)
            self.saved_theme = settings.get("theme", "dark")
            self.saved_model = get_model_from_args(self.current_args)
        else:
            self.current_args = sanitize_args(DEFAULT_ARGS)
            self.current_exe = _DEFAULT_EXE
            self.saved_theme = "dark"
            self.saved_model = get_model_from_args(self.current_args)

        self.theme_name = self.saved_theme

        self._build_ui()
        self._update_button_states()

        if not os.path.isfile(self.current_exe):
            self.root.after(100, self._warn_missing_exe)

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=10, pady=(8, 4))

        self.btn_start = ttk.Button(top_frame, text="Запуск", command=self._on_start)
        self.btn_start.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_stop = ttk.Button(top_frame, text="Остановка", command=self._on_stop, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_save = ttk.Button(top_frame, text="Сохранить", command=self._on_save)
        self.btn_save.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_browse = ttk.Button(top_frame, text="Выбрать exe", command=self._on_browse_exe)
        self.btn_browse.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_theme = ttk.Button(top_frame, text="Тёмная", command=self._toggle_theme)
        self.btn_theme.pack(side=tk.LEFT, padx=(0, 4))

        exe_frame = ttk.Frame(self.root)
        exe_frame.pack(fill=tk.X, padx=10, pady=(0, 4))
        ttk.Label(exe_frame, text="llama-server.exe:").pack(side=tk.LEFT, padx=(0, 4))
        self.exe_var = tk.StringVar(value=os.path.basename(self.current_exe))
        ttk.Entry(exe_frame, textvariable=self.exe_var, width=45, state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        model_frame = ttk.Frame(self.root)
        model_frame.pack(fill=tk.X, padx=10, pady=(0, 4))
        ttk.Label(model_frame, text="Модель:").pack(side=tk.LEFT, padx=(0, 4))
        self.model_var = tk.StringVar(value=self.saved_model or "")
        self.model_entry = ttk.Entry(model_frame, textvariable=self.model_var, width=45, state="readonly")
        self.model_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        ttk.Button(model_frame, text="Выбрать модель", command=self._on_browse_model).pack(side=tk.LEFT, padx=(4, 0))

        self.model_warning = ttk.Label(model_frame, text="", foreground="#ff4444", font=("Segoe UI", 9))
        self.model_warning.pack(anchor=tk.W, padx=(140, 0), pady=(2, 0))

        ttk.Label(self.root, text="Параметры запуска:").pack(anchor=tk.W, padx=10, pady=(4, 2))
        args_frame = ttk.Frame(self.root)
        args_frame.pack(fill=tk.X, padx=10, pady=(0, 4))

        self.args_text = tk.Text(args_frame, height=3, wrap=tk.WORD, font=("Consolas", 10))
        self.args_text.insert("1.0", args_list_to_string(self.current_args))
        args_scroll = ttk.Scrollbar(args_frame, orient=tk.VERTICAL, command=self.args_text.yview)
        self.args_text.configure(yscrollcommand=args_scroll.set)
        self.args_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        args_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._check_model()

        content_frame = ttk.Frame(self.root)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 0))
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(content_frame)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        console_tab = ttk.Frame(self.notebook)
        self.notebook.add(console_tab, text="Консоль")

        console_inner = ttk.Frame(console_tab)
        console_inner.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.log_text = tk.Text(console_inner, wrap=tk.NONE, font=("Consolas", 9),
                                bg="#1e1e1e", fg="#d4d4d4", insertbackground="white", state=tk.DISABLED)
        self.log_text.bind("<Control-c>", self._copy_log_text)
        self.log_text.bind("<Control-C>", self._copy_log_text)
        self.log_text.bind("<Button-3>", self._show_copy_menu)
        lv = ttk.Scrollbar(console_inner, orient=tk.VERTICAL, command=self.log_text.yview)
        lh = ttk.Scrollbar(console_inner, orient=tk.HORIZONTAL, command=self.log_text.xview)
        self.log_text.configure(yscrollcommand=lv.set, xscrollcommand=lh.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        lv.pack(side=tk.RIGHT, fill=tk.Y)
        lh.pack(side=tk.BOTTOM, fill=tk.X)

        ttk.Button(console_inner, text="Очистить", command=self._clear_logs).pack(side=tk.RIGHT, padx=(4, 0))

        api_tab = ttk.Frame(self.notebook)
        self.notebook.add(api_tab, text="API-тестер")

        self._build_api_tab(api_tab)

        self._build_monitor_panel(content_frame)

        bar_frame = ttk.Frame(self.root)
        bar_frame.pack(fill=tk.X, padx=10, pady=(4, 6))

        self.status_label = ttk.Label(bar_frame, textvariable=self.status_var,
                                      font=("Segoe UI", 10), foreground="#555")
        self.status_label.pack(side=tk.LEFT)

        self.time_label = ttk.Label(bar_frame, text="", font=("Segoe UI", 9), foreground="#888")
        self.time_label.pack(side=tk.RIGHT, padx=(10, 0))

        self._update_timer()
        self._update_model_label()

    def _build_monitor_panel(self, parent):
        panel = ttk.Frame(parent)
        panel.configure(width=180)
        panel.grid(row=0, column=1, sticky="ns", padx=(6, 0))

        ttk.Label(panel, text="Мониторинг", font=("Segoe UI", 11, "bold")).pack(pady=(6, 4))

        f_cpu = ttk.LabelFrame(panel, text="CPU")
        f_cpu.pack(fill=tk.X, padx=4, pady=2)
        self.cpu_val = tk.StringVar(value="%")
        ttk.Label(f_cpu, textvariable=self.cpu_val, font=("Consolas", 12)).pack(pady=2)
        self.cpu_bar = ttk.Progressbar(f_cpu, orient=tk.HORIZONTAL, length=160, maximum=100)
        self.cpu_bar.pack(padx=4, pady=(0, 4))

        f_ram = ttk.LabelFrame(panel, text="RAM")
        f_ram.pack(fill=tk.X, padx=4, pady=2)
        self.ram_val = tk.StringVar(value="/ ")
        ttk.Label(f_ram, textvariable=self.ram_val, font=("Consolas", 10)).pack(pady=2)
        self.ram_bar = ttk.Progressbar(f_ram, orient=tk.HORIZONTAL, length=160, maximum=100)
        self.ram_bar.pack(padx=4, pady=(0, 4))

        f_gpu = ttk.LabelFrame(panel, text="VRAM (GPU)")
        f_gpu.pack(fill=tk.X, padx=4, pady=2)
        self.gpu_val = tk.StringVar(value="/ ")
        ttk.Label(f_gpu, textvariable=self.gpu_val, font=("Consolas", 10)).pack(pady=2)
        self.gpu_bar = ttk.Progressbar(f_gpu, orient=tk.HORIZONTAL, length=160, maximum=100)
        self.gpu_bar.pack(padx=4, pady=(0, 4))

    def _build_api_tab(self, parent):
        api_top = ttk.Frame(parent)
        api_top.pack(fill=tk.X, padx=6, pady=4)

        ttk.Label(api_top, text="Host:").pack(side=tk.LEFT, padx=(0, 2))
        self.api_host_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(api_top, textvariable=self.api_host_var, width=14).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Label(api_top, text="Port:").pack(side=tk.LEFT, padx=(0, 2))
        self.api_port_var = tk.StringVar(value="8080")
        ttk.Entry(api_top, textvariable=self.api_port_var, width=6).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Label(api_top, text="Model:").pack(side=tk.LEFT, padx=(0, 2))
        self.api_model_var = tk.StringVar(value=self.saved_model or "")
        ttk.Entry(api_top, textvariable=self.api_model_var, width=20).pack(side=tk.LEFT, padx=(0, 4))

        ttk.Label(api_top, text="Temp:").pack(side=tk.LEFT, padx=(6, 2))
        self.api_temp_var = tk.DoubleVar(value=0.7)
        ttk.Spinbox(api_top, from_=0.0, to=2.0, increment=0.1, textvariable=self.api_temp_var,
                    width=5).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Label(api_top, text="MaxTok:").pack(side=tk.LEFT, padx=(0, 2))
        self.api_max_var = tk.IntVar(value=512)
        ttk.Spinbox(api_top, from_=1, to=4096, textvariable=self.api_max_var, width=5).pack(side=tk.LEFT, padx=(0, 4))

        self.api_type_var = tk.StringVar(value="chat")
        ttk.Radiobutton(api_top, text="Chat", variable=self.api_type_var, value="chat").pack(side=tk.LEFT, padx=(8, 2))
        ttk.Radiobutton(api_top, text="Completion", variable=self.api_type_var, value="completion").pack(side=tk.LEFT, padx=(0, 4))

        self.btn_send = ttk.Button(api_top, text="Отправить", command=self._api_send)
        self.btn_send.pack(side=tk.LEFT, padx=(8, 0))
        self.btn_clear_api = ttk.Button(api_top, text="Очистить", command=self._api_clear)
        self.btn_clear_api.pack(side=tk.LEFT, padx=(4, 0))

        chat_frame = ttk.Frame(parent)
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=(4, 4))

        self.api_chat_text = scrolledtext.ScrolledText(chat_frame, wrap=tk.WORD, font=("Consolas", 10),
                                                        state=tk.DISABLED)
        self.api_chat_text.pack(fill=tk.BOTH, expand=True)

        input_frame = ttk.Frame(parent)
        input_frame.pack(fill=tk.X, padx=6, pady=(0, 6))
        self.api_input = tk.Text(input_frame, height=3, wrap=tk.WORD, font=("Consolas", 10))
        self.api_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self.api_input.bind("<Control-Return>", lambda e: self._api_send())
        ttk.Label(input_frame, text="Ctrl+Enter = отправить", foreground="#888").pack(side=tk.RIGHT, padx=(4, 0))

    def _update_monitor(self):
        cpu = get_cpu_usage()
        ram_total, ram_avail = get_windows_memory_info()
        gpu_used, gpu_total = get_gpu_memory()

        self.root.after(0, self._apply_monitor, cpu, ram_total, ram_avail, gpu_used, gpu_total)

    def _apply_monitor(self, cpu, ram_total, ram_avail, gpu_used, gpu_total):
        if cpu is not None:
            self.cpu_val.set(f"{cpu} %")
            self.cpu_bar.configure(value=cpu)
        if ram_total and ram_avail is not None:
            used = ram_total - ram_avail
            pct = (used / ram_total * 100) if ram_total > 0 else 0
            self.ram_val.set(f"{format_bytes(used)} / {format_bytes(ram_total)}")
            self.ram_bar.configure(value=min(pct, 100))
        if gpu_total and gpu_used is not None:
            pct = (gpu_used / gpu_total * 100) if gpu_total > 0 else 0
            self.gpu_val.set(f"{gpu_used} МБ / {gpu_total} МБ")
            self.gpu_bar.configure(value=min(pct, 100))

    def _start_monitor(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            return
        self._monitor_stop.clear()
        self.monitor_thread = MonitorThread(self._update_monitor, self._monitor_stop)
        self.monitor_thread.start()

    def _stop_monitor(self):
        self._monitor_stop.set()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=3)
            self.monitor_thread = None

    def _on_start(self):
        if self._is_running:
            return

        if not self.model_var.get().strip():
            messagebox.showwarning("Модель не выбрана", "Выберите модель (.gguf) перед запуском сервера.")
            self._check_model()
            return

        raw_text = self.args_text.get("1.0", tk.END)
        args_list = string_to_args_list(raw_text)
        if not args_list:
            messagebox.showwarning("Пустые параметры", "Укажите параметры запуска.")
            return

        exe_path = self.current_exe
        if not os.path.isabs(exe_path):
            exe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", exe_path)

        if not os.path.isfile(exe_path):
            self.current_exe = exe_path
            self.exe_var.set(os.path.basename(exe_path))
            self.root.after(100, self._warn_missing_exe)
            return

        saved_model = get_model_from_args(args_list)
        if not saved_model:
            messagebox.showerror("Ошибка", "В аргументах нет --model!\n\nНажмите 'Выбрать модель' чтобы указать путь.")
            return
        
        import os.path as osp
        abs_path = osp.abspath(saved_model)
        self._append_log_safe(f"[DEBUG] saved_model: {repr(saved_model)}")
        self._append_log_safe(f"[DEBUG] abs_path: {repr(abs_path)}")
        self._append_log_safe(f"[DEBUG] exists: {osp.exists(abs_path)}, isfile: {osp.isfile(abs_path)}")
        self._append_log_safe(f"[DEBUG] model_var: {repr(self.model_var.get())}")
        self._append_log_safe(f"[DEBUG] model_var exists: {osp.exists(self.model_var.get())}")
        self._append_log_safe(f"[DEBUG] model_var isfile: {osp.isfile(self.model_var.get())}")
        self._append_log_safe(f"[DEBUG] model_var abspath exists: {osp.exists(osp.abspath(self.model_var.get()))}")
        
        if not osp.isfile(abs_path):
            messagebox.showerror("Модель не найдена", f"Файл модели не существует:\n\n{abs_path}\n\nПроверьте путь и нажмите 'Выбрать модель'.")
            return
        settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "launcher_settings.json")
        save_settings({
            "args": args_list,
            "exe_path": exe_path,
            "theme": self.theme_name,
            "model": saved_model,
        }, settings_file)

        try:
            self.proc = subprocess.Popen(
                [exe_path] + args_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except FileNotFoundError as e:
            messagebox.showerror("Не найдено", f"llama-server.exe не найден:\n{exe_path}\n\n{e}")
            return
        except Exception as e:
            messagebox.showerror("Ошибка запуска", f"Не удалось запустить процесс:\n{e}")
            return

        self._is_running = True
        self._start_time = time.time()
        self._update_button_states()
        self._update_model_label()
        self._start_monitor()

        self.log_thread = LogReaderThread(
            self.proc, self.log_text, self.status_var, self._append_log_safe
        )
        self.log_thread.start()

        self._append_log_safe(f"[{self._timestamp()}] Процесс запущен: PID={self.proc.pid}")
        self.root.after(3000, self._check_process_alive)

    def _check_process_alive(self):
        if self.proc and self.proc.poll() is not None:
            exit_code = self.proc.poll()
            self._is_running = False
            self._update_button_states()
            self._stop_monitor()
            self.status_var.set("❌ Ошибка")
            self._append_log_safe(f"[{self._timestamp()}] Процесс завершился с кодом {exit_code}")
            model_info = f"\nМодель: {self.saved_model}" if getattr(self, 'saved_model', None) else ""
            messagebox.showerror("Ошибка сервера", f"llama-server.exe завершился с кодом {exit_code}{model_info}\n\nПроверьте путь к модели и файлу.")
            self.proc = None
            self.log_thread = None

    def _on_stop(self):
        if not self._is_running or self.proc is None:
            return

        self._append_log_safe(f"[{self._timestamp()}] Остановка процесса (PID={self.proc.pid})...")

        if self.log_thread:
            self.log_thread.stop()

        self.proc.terminate()

        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self._append_log_safe("[{}] Таймаут, принудительное завершение (kill)...".format(self._timestamp()))
            self.proc.kill()
            try:
                self.proc.wait(timeout=2)
            except Exception:
                pass

        self._stop_monitor()
        self._is_running = False
        self.proc = None
        self.log_thread = None
        self._update_button_states()
        self.status_var.set("Завершил работу")

    def _api_send(self):
        if not self._is_running:
            messagebox.showwarning("Не подключено", "Сначала запустите сервер.")
            return

        user_msg = self.api_input.get("1.0", tk.END).strip()
        if not user_msg:
            return

        host = self.api_host_var.get() or "127.0.0.1"
        port = int(self.api_port_var.get() or 8080)
        model = self.api_model_var.get()
        temp = float(self.api_temp_var.get() or 0.7)
        max_tok = int(self.api_max_var.get() or 512)
        api_type = self.api_type_var.get()

        client = APIClient(host=host, port=port, root=self.root)

        self._api_insert("user", user_msg)
        self.api_input.delete("1.0", tk.END)

        self.btn_send.configure(state=tk.DISABLED)

        def _do_request():
            try:
                if api_type == "chat":
                    messages = [{"role": "user", "content": user_msg}]
                    reply, err = client.send_chat(messages, model=model, temperature=temp, max_tokens=max_tok)
                else:
                    reply, err = client.send_completion(user_msg, model=model, temperature=temp, max_tokens=max_tok)

                if err:
                    self._api_insert("error", f"Ошибка: {err}")
                else:
                    self._api_insert("bot", reply if reply else "(пустой ответ)")
            except Exception as e:
                self._api_insert("error", f"Ошибка: {e}")
            finally:
                self.root.after(0, lambda: self.btn_send.configure(state=tk.NORMAL))

        threading.Thread(target=_do_request, daemon=True).start()

    def _api_insert(self, role, text):
        self.api_chat_text.configure(state=tk.NORMAL)
        if role == "user":
            self.api_chat_text.insert(tk.END, "\nВы: ", ("tag_user",))
            self.api_chat_text.insert(tk.END, text + "\n", ("tag_user_text",))
        elif role == "bot":
            self.api_chat_text.insert(tk.END, "\nБот: ", ("tag_bot",))
            self.api_chat_text.insert(tk.END, text + "\n", ("tag_bot_text",))
        elif role == "error":
            self.api_chat_text.insert(tk.END, f"\n⚠ {text}\n", ("tag_error",))
        self.api_chat_text.see(tk.END)
        self.api_chat_text.configure(state=tk.DISABLED)

    def _api_clear(self):
        self.api_chat_text.configure(state=tk.NORMAL)
        self.api_chat_text.delete("1.0", tk.END)
        self.api_chat_text.configure(state=tk.DISABLED)

    def _toggle_theme(self):
        if self.theme_name == "dark":
            self.theme_name = "light"
            self.btn_theme.configure(text="Светлая")
        else:
            self.theme_name = "dark"
            self.btn_theme.configure(text="Тёмная")

        settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "launcher_settings.json")
        settings = load_settings(settings_file) or {}
        settings["theme"] = self.theme_name
        save_settings(settings, settings_file)

        apply_theme(self.root, self.theme_name)

        colors = THEMES[self.theme_name]
        self.log_text.configure(bg=colors["code_bg"], fg=colors["code_fg"], insertbackground=colors["fg"])
        self.args_text.configure(bg=colors["entry_bg"], fg=colors["entry_fg"], insertbackground=colors["fg"])
        self.api_chat_text.configure(bg=colors["chat_bg"], fg=colors["fg"], insertbackground=colors["fg"])
        self.api_input.configure(bg=colors["entry_bg"], fg=colors["entry_fg"], insertbackground=colors["fg"])

        tag_map = {
            "tag_user": {"foreground": colors["chat_user_bg"], "background": colors["chat_bg"]},
            "tag_user_text": {"foreground": colors["fg"], "background": colors["chat_bg"]},
            "tag_bot": {"foreground": colors["chat_bot_bg"], "background": colors["chat_bg"]},
            "tag_bot_text": {"foreground": colors["fg"], "background": colors["chat_bg"]},
            "tag_error": {"foreground": "#ff6b6b", "background": colors["chat_bg"]},
        }
        for tag, opts in tag_map.items():
            self.api_chat_text.tag_configure(tag, **opts)

    def _append_log_safe(self, text):
        self.root.after(0, lambda: self._append_log(text))

    def _append_log(self, text):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_logs(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _copy_log_text(self, event=None):
        try:
            text = self.log_text.selection_get()
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()
        except tk.TclError:
            pass
        return "break"

    def _show_copy_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Копировать", command=self._copy_log_text)
        menu.post(event.x_root, event.y_root)

    def _update_button_states(self):
        has_model = bool(self.model_var.get().strip())
        if self._is_running:
            self.btn_start.configure(state=tk.DISABLED)
            self.btn_stop.configure(state=tk.NORMAL)
            self.args_text.configure(state=tk.DISABLED)
        else:
            self.btn_start.configure(state=tk.NORMAL if has_model else tk.DISABLED)
            self.btn_stop.configure(state=tk.DISABLED)
            self.args_text.configure(state=tk.NORMAL)

    def _check_model(self):
        has_model = bool(self.model_var.get().strip())
        if has_model:
            self.model_warning.configure(text="")
            self.model_entry.configure(style="TEntry")
        else:
            self.model_warning.configure(text="⚠ Выберите модель (.gguf) перед запуском")
        self._update_button_states()

    def _update_timer(self):
        if self._is_running:
            elapsed = time.time() - self._start_time
            m, s = divmod(int(elapsed), 60)
            self.time_label.configure(text=f"Uptime: {m:02d}:{s:02d}")
        else:
            self.time_label.configure(text="")
        self.root.after(1000, self._update_timer)

    def _update_model_label(self):
        model = get_model_from_args(self.current_args)
        if model:
            self.root.title(f"LLM Server Launcher — {os.path.basename(model)}")

    def _timestamp(self):
        return time.strftime("%H:%M:%S")

    def _warn_missing_exe(self):
        path = filedialog.askopenfilename(
            title="Выберите llama-server.exe",
            filetypes=[("Executable", "*.exe"), ("All", "*.*")],
        )
        if path:
            self.current_exe = path
            self.exe_var.set(os.path.basename(path))
            settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "launcher_settings.json")
            save_settings({
                "args": string_to_args_list(self.args_text.get("1.0", tk.END)),
                "exe_path": path,
                "theme": self.theme_name,
                "model": get_model_from_args(string_to_args_list(self.args_text.get("1.0", tk.END))),
            }, settings_file)
        else:
            messagebox.showwarning(
                "Файл не найден",
                f"llama-server.exe не найден по пути:\n\n{self.current_exe}\n\n"
                f"Положите файл рядом со скриптом или нажмите Выбрать exe для выбора."
            )

    def _warn_missing_model(self):
        path = filedialog.askopenfilename(
            title="Выберите модель (.gguf)",
            filetypes=[("GGUF Model", "*.gguf"), ("All", "*.*")],
        )
        if path:
            self.model_var.set(path)
            args_text = self.args_text.get("1.0", tk.END)
            args_list = string_to_args_list(args_text)
            for i, a in enumerate(args_list):
                if a == "--model":
                    args_list[i + 1] = path
                    break
            else:
                args_list.extend(["--model", path])
            self.args_text.delete("1.0", tk.END)
            self.args_text.insert("1.0", args_list_to_string(args_list))
            settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "launcher_settings.json")
            save_settings({
                "args": args_list,
                "exe_path": self.current_exe,
                "theme": self.theme_name,
                "model": path,
            }, settings_file)
            self._check_model()
        else:
            messagebox.showwarning(
                "Модель не найдена",
                f"Модель не найдена по пути:\n\n{self.saved_model}\n\n"
                f"Нажмите Выбрать модель для выбора."
            )

    def _on_browse_model(self):
        path = filedialog.askopenfilename(
            title="Выберите модель (.gguf)",
            filetypes=[("GGUF Model", "*.gguf"), ("All", "*.*")],
        )
        if path:
            self.model_var.set(path)
            args_text = self.args_text.get("1.0", tk.END)
            args_list = string_to_args_list(args_text)
            for i, a in enumerate(args_list):
                if a == "--model":
                    args_list[i + 1] = path
                    break
            else:
                args_list.extend(["--model", path])
            self.args_text.delete("1.0", tk.END)
            self.args_text.insert("1.0", args_list_to_string(args_list))
            settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "launcher_settings.json")
            save_settings({
                "args": args_list,
                "exe_path": self.current_exe,
                "theme": self.theme_name,
                "model": path,
            }, settings_file)
            self._check_model()

    def _on_close(self):
        if self._is_running:
            try:
                if messagebox.askyesno("Выход", "Сервер запущен. Остановить и выйти?"):
                    self._on_stop()
                    self.root.destroy()
            except tk.TclError:
                pass
        else:
            self.root.destroy()

    def _on_save(self):
        raw_text = self.args_text.get("1.0", tk.END)
        args_list = string_to_args_list(raw_text)
        saved_model = get_model_from_args(args_list)
        settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "launcher_settings.json")
        save_settings({
            "args": args_list,
            "exe_path": self.current_exe,
            "theme": self.theme_name,
            "model": saved_model,
        }, settings_file)
        messagebox.showinfo("Сохранено", "Профиль сохранён в launcher_settings.json")

    def _on_browse_exe(self):
        path = filedialog.askopenfilename(
            title="Выберите llama-server.exe",
            filetypes=[("Executable", "*.exe"), ("All", "*.*")],
        )
        if path:
            self.current_exe = path
            self.exe_var.set(os.path.basename(path))
            settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "launcher_settings.json")
            save_settings({
                "args": string_to_args_list(self.args_text.get("1.0", tk.END)),
                "exe_path": path,
                "theme": self.theme_name,
                "model": get_model_from_args(string_to_args_list(self.args_text.get("1.0", tk.END))),
            }, settings_file)
