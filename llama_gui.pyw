# -*- coding: utf-8 -*-
"""
GUI-лаунчер для локального LLM-сервера (llama-server.exe)
Стек: Python 3.6+, только стандартная библиотека
Запуск: двойной клик по llama_gui.pyw (или python llama_gui.py)

Добавлено:
- Мониторинг VRAM/CPU/RAM в реальном времени
- Автозагрузка последней модели при старте
- Тёмная/светлая тема
- Вкладка API-тестера (/v1/chat/completions)
"""

import os
import sys
import subprocess
import threading
import json
import time
import ctypes
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext

# ---------------------------------------------------------------------------
# Пути
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_EXE = os.path.join(_SCRIPT_DIR, "llama-server.exe")
_SETTINGS_FILE = os.path.join(_SCRIPT_DIR, "launcher_settings.json")

# ---------------------------------------------------------------------------
# Профиль запуска по умолчанию
# ---------------------------------------------------------------------------
DEFAULT_ARGS = [
    "--model", "models/your_model.gguf",
    "--host", "127.0.0.1",
    "--port", "8080",
    "--n-gpu-layers", "99",
    "--ctx-size", "4096",
    "--batch-size", "512",
    "--log-disable",
    "-cb",
]


# ===================================================================
# Утилиты
# ===================================================================

def _sanitize_args(args_list):
    clean = []
    for a in args_list:
        a = a.replace("^", " ").strip()
        if a:
            clean.append(a)
    return clean


def _args_list_to_string(args):
    parts = []
    for arg in args:
        if " " in arg or '"' in arg:
            parts.append(f'"{arg}"')
        else:
            parts.append(arg)
    return " ".join(parts)


def _string_to_args_list(text):
    text = text.replace("^", " ")
    tokens = []
    current = []
    in_quotes = False
    quote_char = None
    i = 0
    while i < len(text):
        ch = text[i]
        if in_quotes:
            if ch == quote_char:
                in_quotes = False
            else:
                current.append(ch)
        elif ch in ('"', "'"):
            in_quotes = True
            quote_char = ch
        elif ch == " ":
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(ch)
        i += 1
    if current:
        tokens.append("".join(current))
    return [t for t in tokens if t]


def _get_model_from_args(args_list):
    """Извлекает путь к модели из списка аргументов."""
    for i, a in enumerate(args_list):
        if a == "--model" and i + 1 < len(args_list):
            return args_list[i + 1]
    return None


def _load_settings():
    if not os.path.isfile(_SETTINGS_FILE):
        return None
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _save_settings(data):
    try:
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError:
        pass


# ===================================================================
# Мониторинг ресурсов (Windows, без внешних зависимостей)
# ===================================================================

def _get_windows_memory_info():
    """Возвращает (total, available) в байтах через ctypes."""
    try:
        kernel32 = ctypes.windll.kernel32
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        ms = MEMORYSTATUSEX()
        ms.dwLength = ctypes.sizeof(ms)
        kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
        return ms.ullTotalPhys, ms.ullAvailPhys
    except Exception:
        return None, None


def _get_cpu_usage():
    """Возвращает среднюю загрузку CPU в % через subprocess + wmic."""
    try:
        result = subprocess.run(
            ["wmic", "cpu", "get", "loadpercentage", "/format:list"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "=" in line:
                val = line.split("=")[1].strip()
                return int(val)
    except Exception:
        pass
    return None


def _get_gpu_memory():
    """Возвращает (used_mb, total_mb) через nvidia-smi."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total",
             "--format=csv,noheader,nounits", "-i", "0"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(",")
            if len(parts) == 2:
                return int(parts[0].strip()), int(parts[1].strip())
    except Exception:
        pass
    return None, None


def _format_bytes(b):
    if b is None:
        return "— МБ"
    gb = b / (1024 ** 3)
    if gb >= 1:
        return f"{gb:.1f} ГБ"
    return f"{b / 1024 / 1024:.0f} МБ"


# ===================================================================
# Потоки
# ===================================================================

class LogReaderThread(threading.Thread):
    def __init__(self, proc, log_widget, status_var, append_log_callback):
        super().__init__(daemon=True)
        self.proc = proc
        self.log_widget = log_widget
        self.status_var = status_var
        self.append_log = append_log_callback
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        try:
            for line in self.proc.stdout:
                if self._stop_event.is_set():
                    break
                try:
                    text = line.decode("utf-8", errors="replace").rstrip("\r\n")
                except Exception:
                    text = line.decode("latin-1", errors="replace").rstrip("\r\n")
                if text:
                    self.append_log(text)
            for line in self.proc.stderr:
                if self._stop_event.is_set():
                    break
                try:
                    text = line.decode("utf-8", errors="replace").rstrip("\r\n")
                except Exception:
                    text = line.decode("latin-1", errors="replace").rstrip("\r\n")
                if text:
                    self.append_log(text)
        except Exception:
            pass

        exit_code = self.proc.poll()
        if exit_code is None:
            exit_code = -1
        if self._stop_event.is_set():
            self.status_var.set("⏹ Завершил работу")
        elif exit_code != 0:
            self.status_var.set("❌ Ошибка")
        else:
            self.status_var.set("⏹ Завершил работу")


class MonitorThread(threading.Thread):
    """Фоновый поток мониторинга CPU/RAM/GPU каждые 2 секунды."""

    def __init__(self, update_callback, stop_event):
        super().__init__(daemon=True)
        self.update_callback = update_callback
        self._stop_event = stop_event

    def run(self):
        while not self._stop_event.is_set():
            try:
                cpu = _get_cpu_usage()
                ram_total, ram_avail = _get_windows_memory_info()
                gpu_used, gpu_total = _get_gpu_memory()
                self.update_callback(cpu, ram_total, ram_avail, gpu_used, gpu_total)
            except Exception:
                pass
            self._stop_event.wait(2)


# ===================================================================
# Тема
# ===================================================================

THEMES = {
    "dark": {
        "bg": "#1e1e1e", "fg": "#d4d4d4", "input_bg": "#3c3c3c", "input_fg": "#d4d4d4",
        "btn_bg": "#2d2d30", "btn_fg": "#cccccc", "btn_hover": "#3e3e42",
        "frame_bg": "#252526", "border": "#3c3c3c", "text_bg": "#1e1e1e",
        "entry_bg": "#3c3c3c", "entry_fg": "#d4d4d4", "label_fg": "#cccccc",
        "status_bg": "#007acc", "status_fg": "#ffffff",
        "code_bg": "#1e1e1e", "code_fg": "#d4d4d4",
        "chat_bg": "#1e1e1e", "chat_user_bg": "#0e639c", "chat_bot_bg": "#2d2d30",
        "tab_bg": "#2d2d30", "tab_fg": "#cccccc", "tab_selected": "#1e1e1e",
    },
    "light": {
        "bg": "#f5f5f5", "fg": "#333333", "input_bg": "#ffffff", "input_fg": "#333333",
        "btn_bg": "#e8e8e8", "btn_fg": "#333333", "btn_hover": "#d0d0d0",
        "frame_bg": "#fafafa", "border": "#d0d0d0", "text_bg": "#ffffff",
        "entry_bg": "#ffffff", "entry_fg": "#333333", "label_fg": "#333333",
        "status_bg": "#0078d4", "status_fg": "#ffffff",
        "code_bg": "#f5f5f5", "code_fg": "#333333",
        "chat_bg": "#f5f5f5", "chat_user_bg": "#0078d4", "chat_bot_bg": "#e8e8e8",
        "tab_bg": "#e8e8e8", "tab_fg": "#333333", "tab_selected": "#f5f5f5",
    },
}


def apply_theme(root, theme_name):
    colors = THEMES[theme_name]
    root.configure(bg=colors["bg"])

    style = ttk.Style()
    if theme_name == "dark":
        style.theme_use("clam")
    else:
        style.theme_use("clam")

    style.configure(".", background=colors["bg"], foreground=colors["fg"])
    style.configure("TFrame", background=colors["frame_bg"])
    style.configure("TLabel", background=colors["frame_bg"], foreground=colors["label_fg"])
    style.configure("TEntry", fieldbackground=colors["entry_bg"], foreground=colors["entry_fg"],
                    background=colors["entry_bg"])
    style.configure("TButton", background=colors["btn_bg"], foreground=colors["btn_fg"])
    style.map("TButton", background=[("active", colors["btn_hover"])])
    style.configure("TLabelFrame", background=colors["frame_bg"], foreground=colors["label_fg"])
    style.configure("TLabelFrame.Label", background=colors["frame_bg"], foreground=colors["label_fg"])
    style.configure("Treeview", background=colors["input_bg"], foreground=colors["fg"],
                    fieldbackground=colors["input_bg"])
    style.map("Treeview", background=[("selected", colors["btn_hover"])])

    # Применяем цвета ко всем существующим виджетам
    _recolor_widgets(root, colors)


def _recolor_widgets(widget, colors):
    for child in widget.winfo_children():
        try:
            wtype = child.winfo_class()
        except tk.TclError:
            continue
        if wtype in ("Text", "Entry", "Listbox", "Combobox"):
            try:
                child.configure(bg=colors["entry_bg"], fg=colors["entry_fg"],
                                insertbackground=colors["fg"])
            except Exception:
                pass
        elif wtype == "Label":
            try:
                child.configure(bg=colors["frame_bg"], fg=colors["label_fg"])
            except Exception:
                pass
        elif wtype == "Button" or wtype == "TButton":
            try:
                child.configure(bg=colors["btn_bg"], fg=colors["btn_fg"])
            except Exception:
                pass
        elif wtype == "Frame":
            try:
                child.configure(bg=colors["frame_bg"])
            except Exception:
                pass
        elif wtype == "Notebook":
            try:
                child.configure(bg=colors["tab_bg"])
            except Exception:
                pass
        _recolor_widgets(child, colors)


# ===================================================================
# API-клиент
# ===================================================================

class APIClient:
    """Клиент для отправки запросов к llama-server API (/v1/chat/completions)."""

    def __init__(self, host="127.0.0.1", port=8080, root=None):
        self.host = host
        self.port = port
        self.root = root

    def _url(self, path):
        return f"http://{self.host}:{self.port}{path}"

    def send_chat(self, messages, model="", temperature=0.7, max_tokens=512, stream=False):
        """Отправляет запрос к /v1/chat/completions. Возвращает (response_text, error)."""
        import urllib.request
        import urllib.error
        payload = {
            "model": model or "default",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url("/v1/chat/completions"),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                return content, None
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            return None, f"HTTP {e.code}: {body}"
        except urllib.error.URLError as e:
            return None, f"Не подключено: {e.reason}"
        except Exception as e:
            return None, str(e)

    def send_completion(self, prompt, model="", temperature=0.7, max_tokens=512):
        """Отправляет запрос к /v1/completions (legacy)."""
        import urllib.request
        import urllib.error
        payload = {
            "model": model or "default",
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url("/v1/completions"),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                content = result.get("choices", [{}])[0].get("text", "")
                return content, None
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            return None, f"HTTP {e.code}: {body}"
        except urllib.error.URLError as e:
            return None, f"Не подключено: {e.reason}"
        except Exception as e:
            return None, str(e)


# ===================================================================
# Главное приложение
# ===================================================================

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

        # Загружаем настройки
        settings = _load_settings()
        if settings and "args" in settings:
            self.current_args = _sanitize_args(settings["args"])
            self.current_exe = settings.get("exe_path", _DEFAULT_EXE)
            self.saved_theme = settings.get("theme", "dark")
            self.saved_model = _get_model_from_args(self.current_args)
        else:
            self.current_args = _sanitize_args(DEFAULT_ARGS)
            self.current_exe = _DEFAULT_EXE
            self.saved_theme = "dark"
            self.saved_model = _get_model_from_args(self.current_args)

        self.theme_name = self.saved_theme

        self._build_ui()
        self._update_button_states()

        if not os.path.isfile(self.current_exe):
            self.root.after(100, self._warn_missing_exe)

    # ======================== UI ========================

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # --- Верхняя панель кнопок ---
        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=10, pady=(8, 4))

        self.btn_start = ttk.Button(top_frame, text="▶ Запуск", command=self._on_start)
        self.btn_start.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_stop = ttk.Button(top_frame, text="■ Остановка", command=self._on_stop, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_save = ttk.Button(top_frame, text="💾 Сохранить", command=self._on_save)
        self.btn_save.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_browse = ttk.Button(top_frame, text="📁_exe", command=self._on_browse_exe)
        self.btn_browse.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_theme = ttk.Button(top_frame, text="🌙 Тёмная", command=self._toggle_theme)
        self.btn_theme.pack(side=tk.LEFT, padx=(0, 4))

        # --- Путь к exe ---
        exe_frame = ttk.Frame(self.root)
        exe_frame.pack(fill=tk.X, padx=10, pady=(0, 4))
        ttk.Label(exe_frame, text="llama-server.exe:").pack(side=tk.LEFT, padx=(0, 4))
        self.exe_var = tk.StringVar(value=os.path.basename(self.current_exe))
        ttk.Entry(exe_frame, textvariable=self.exe_var, width=45).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        # --- Параметры запуска ---
        ttk.Label(self.root, text="Параметры запуска:").pack(anchor=tk.W, padx=10, pady=(4, 2))
        args_frame = ttk.Frame(self.root)
        args_frame.pack(fill=tk.X, padx=10, pady=(0, 4))

        self.args_text = tk.Text(args_frame, height=3, wrap=tk.WORD, font=("Consolas", 10))
        self.args_text.insert("1.0", _args_list_to_string(self.current_args))
        args_scroll = ttk.Scrollbar(args_frame, orient=tk.VERTICAL, command=self.args_text.yview)
        self.args_text.configure(yscrollcommand=args_scroll.set)
        self.args_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        args_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Основной контент: табы + боковая панель мониторинга ---
        content_frame = ttk.Frame(self.root)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 0))
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)

        # Табы
        self.notebook = ttk.Notebook(content_frame)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        # Таб 1: Консоль
        console_tab = ttk.Frame(self.notebook)
        self.notebook.add(console_tab, text="  📟 Консоль  ")

        console_inner = ttk.Frame(console_tab)
        console_inner.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.log_text = tk.Text(console_inner, wrap=tk.NONE, font=("Consolas", 9),
                                bg="#1e1e1e", fg="#d4d4d4", insertbackground="white", state=tk.DISABLED)
        lv = ttk.Scrollbar(console_inner, orient=tk.VERTICAL, command=self.log_text.yview)
        lh = ttk.Scrollbar(console_inner, orient=tk.HORIZONTAL, command=self.log_text.xview)
        self.log_text.configure(yscrollcommand=lv.set, xscrollcommand=lh.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        lv.pack(side=tk.RIGHT, fill=tk.Y)
        lh.pack(side=tk.BOTTOM, fill=tk.X)

        ttk.Button(console_inner, text="🗑 Очистить", command=self._clear_logs).pack(side=tk.RIGHT, padx=(4, 0))

        # Таб 2: API-тестер
        api_tab = ttk.Frame(self.notebook)
        self.notebook.add(api_tab, text="  💬 API-тестер  ")

        self._build_api_tab(api_tab)

        # Боковая панель: мониторинг
        self._build_monitor_panel(content_frame)

        # --- Статус-бар ---
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
        """Боковая панель с мониторингом CPU/RAM/GPU."""
        panel = ttk.Frame(parent)
        panel.grid(row=0, column=1, sticky="ns", padx=(0, 0))
        panel.configure(width=180)
        panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 0))

        ttk.Label(panel, text="Мониторинг", font=("Segoe UI", 11, "bold")).pack(pady=(6, 4))

        # CPU
        f_cpu = ttk.LabelFrame(panel, text="CPU")
        f_cpu.pack(fill=tk.X, padx=4, pady=2)
        self.cpu_val = tk.StringVar(value="— %")
        ttk.Label(f_cpu, textvariable=self.cpu_val, font=("Consolas", 12)).pack(pady=2)
        self.cpu_bar = ttk.Progressbar(f_cpu, orient=tk.HORIZONTAL, length=160, maximum=100)
        self.cpu_bar.pack(padx=4, pady=(0, 4))

        # RAM
        f_ram = ttk.LabelFrame(panel, text="RAM")
        f_ram.pack(fill=tk.X, padx=4, pady=2)
        self.ram_val = tk.StringVar(value="— / —")
        ttk.Label(f_ram, textvariable=self.ram_val, font=("Consolas", 10)).pack(pady=2)
        self.ram_bar = ttk.Progressbar(f_ram, orient=tk.HORIZONTAL, length=160, maximum=100)
        self.ram_bar.pack(padx=4, pady=(0, 4))

        # GPU VRAM
        f_gpu = ttk.LabelFrame(panel, text="VRAM (GPU)")
        f_gpu.pack(fill=tk.X, padx=4, pady=2)
        self.gpu_val = tk.StringVar(value="— / —")
        ttk.Label(f_gpu, textvariable=self.gpu_val, font=("Consolas", 10)).pack(pady=2)
        self.gpu_bar = ttk.Progressbar(f_gpu, orient=tk.HORIZONTAL, length=160, maximum=100)
        self.gpu_bar.pack(padx=4, pady=(0, 4))

    def _build_api_tab(self, parent):
        """Вкладка API-тестера: чат-интерфейс + настройки запроса."""
        # Верхняя панель API
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

        # Тип запроса
        self.api_type_var = tk.StringVar(value="chat")
        ttk.Radiobutton(api_top, text="Chat", variable=self.api_type_var, value="chat").pack(side=tk.LEFT, padx=(8, 2))
        ttk.Radiobutton(api_top, text="Completion", variable=self.api_type_var, value="completion").pack(side=tk.LEFT, padx=(0, 4))

        # Кнопки
        self.btn_send = ttk.Button(api_top, text="📨 Отправить", command=self._api_send)
        self.btn_send.pack(side=tk.LEFT, padx=(8, 0))
        self.btn_clear_api = ttk.Button(api_top, text="🗑 Очистить", command=self._api_clear)
        self.btn_clear_api.pack(side=tk.LEFT, padx=(4, 0))

        # История чата
        chat_frame = ttk.Frame(parent)
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=(4, 4))

        self.api_chat_text = scrolledtext.ScrolledText(chat_frame, wrap=tk.WORD, font=("Consolas", 10),
                                                        state=tk.DISABLED)
        self.api_chat_text.pack(fill=tk.BOTH, expand=True)

        # Ввод сообщения
        input_frame = ttk.Frame(parent)
        input_frame.pack(fill=tk.X, padx=6, pady=(0, 6))
        self.api_input = tk.Text(input_frame, height=3, wrap=tk.WORD, font=("Consolas", 10))
        self.api_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self.api_input.bind("<Control-Return>", lambda e: self._api_send())
        ttk.Label(input_frame, text="Ctrl+Enter = отправить", foreground="#888").pack(side=tk.RIGHT, padx=(4, 0))

    # ======================== Мониторинг ========================

    def _update_monitor(self, cpu, ram_total, ram_avail, gpu_used, gpu_total):
        """Обновляет виджеты мониторинга через root.after()."""
        if cpu is not None:
            self.cpu_val.set(f"{cpu} %")
            self.cpu_bar.configure(value=cpu)
        if ram_total and ram_avail is not None:
            used = ram_total - ram_avail
            pct = (used / ram_total * 100) if ram_total > 0 else 0
            self.ram_val.set(f"{_format_bytes(used)} / {_format_bytes(ram_total)}")
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

    # ======================== Запуск / Остановка ========================

    def _on_start(self):
        if self._is_running:
            return

        raw_text = self.args_text.get("1.0", tk.END)
        args_list = _string_to_args_list(raw_text)
        if not args_list:
            messagebox.showwarning("Пустые параметры", "Укажите параметры запуска.")
            return

        exe_path = self.current_exe
        if not os.path.isabs(exe_path):
            exe_path = os.path.join(_SCRIPT_DIR, exe_path)

        if not os.path.isfile(exe_path):
            self.current_exe = exe_path
            self.exe_var.set(os.path.basename(exe_path))
            self.root.after(100, self._warn_missing_exe)
            return

        # Сохраняем настройки включая модель и тему
        saved_model = _get_model_from_args(args_list)
        _save_settings({
            "args": args_list,
            "exe_path": exe_path,
            "theme": self.theme_name,
            "model": saved_model,
        })

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
        self.status_var.set("⏹ Завершил работу")

    # ======================== API ========================

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
            self.api_chat_text.insert(tk.END, "\n▸ Вы: ", ("tag_user",))
            self.api_chat_text.insert(tk.END, text + "\n", ("tag_user_text",))
        elif role == "bot":
            self.api_chat_text.insert(tk.END, "\n▸ Бот: ", ("tag_bot",))
            self.api_chat_text.insert(tk.END, text + "\n", ("tag_bot_text",))
        elif role == "error":
            self.api_chat_text.insert(tk.END, f"\n⚠ {text}\n", ("tag_error",))
        self.api_chat_text.see(tk.END)
        self.api_chat_text.configure(state=tk.DISABLED)

    def _api_clear(self):
        self.api_chat_text.configure(state=tk.NORMAL)
        self.api_chat_text.delete("1.0", tk.END)
        self.api_chat_text.configure(state=tk.DISABLED)

    # ======================== Тема ========================

    def _toggle_theme(self):
        if self.theme_name == "dark":
            self.theme_name = "light"
            self.btn_theme.configure(text="☀ Светлая")
        else:
            self.theme_name = "dark"
            self.btn_theme.configure(text="🌙 Тёмная")

        # Сохраняем тему
        settings = _load_settings() or {}
        settings["theme"] = self.theme_name
        _save_settings(settings)

        apply_theme(self.root, self.theme_name)

        # Перекрашиваем элементы
        colors = THEMES[self.theme_name]
        self.log_text.configure(bg=colors["code_bg"], fg=colors["code_fg"], insertbackground=colors["fg"])
        self.args_text.configure(bg=colors["entry_bg"], fg=colors["entry_fg"], insertbackground=colors["fg"])
        self.api_chat_text.configure(bg=colors["chat_bg"], fg=colors["fg"], insertbackground=colors["fg"])
        self.api_input.configure(bg=colors["entry_bg"], fg=colors["entry_fg"], insertbackground=colors["fg"])

        # Теги для API-чата
        tag_map = {
            "tag_user": {"foreground": colors["chat_user_bg"], "background": colors["chat_bg"]},
            "tag_user_text": {"foreground": colors["fg"], "background": colors["chat_bg"]},
            "tag_bot": {"foreground": colors["chat_bot_bg"], "background": colors["chat_bg"]},
            "tag_bot_text": {"foreground": colors["fg"], "background": colors["chat_bg"]},
            "tag_error": {"foreground": "#ff6b6b", "background": colors["chat_bg"]},
        }
        for tag, opts in tag_map.items():
            self.api_chat_text.tag_configure(tag, **opts)

    # ======================== Вспомогательные ========================

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

    def _update_button_states(self):
        if self._is_running:
            self.btn_start.configure(state=tk.DISABLED)
            self.btn_stop.configure(state=tk.NORMAL)
            self.args_text.configure(state=tk.DISABLED)
        else:
            self.btn_start.configure(state=tk.NORMAL)
            self.btn_stop.configure(state=tk.DISABLED)
            self.args_text.configure(state=tk.NORMAL)

    def _update_timer(self):
        if self._is_running:
            elapsed = time.time() - self._start_time
            m, s = divmod(int(elapsed), 60)
            self.time_label.configure(text=f"Uptime: {m:02d}:{s:02d}")
        else:
            self.time_label.configure(text="")
        self.root.after(1000, self._update_timer)

    def _update_model_label(self):
        model = _get_model_from_args(self.current_args)
        if model:
            self.root.title(f"LLM Server Launcher — {os.path.basename(model)}")

    def _timestamp(self):
        return time.strftime("%H:%M:%S")

    def _warn_missing_exe(self):
        messagebox.showwarning(
            "Файл не найден",
            f"llama-server.exe не найден по пути:\n\n{self.current_exe}\n\n"
            f"Положите файл рядом со скриптом или нажмите 📁_exe для выбора."
        )

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
        args_list = _string_to_args_list(raw_text)
        saved_model = _get_model_from_args(args_list)
        _save_settings({
            "args": args_list,
            "exe_path": self.current_exe,
            "theme": self.theme_name,
            "model": saved_model,
        })
        messagebox.showinfo("Сохранено", "Профиль сохранён в launcher_settings.json")

    def _on_browse_exe(self):
        path = filedialog.askopenfilename(
            title="Выберите llama-server.exe",
            filetypes=[("Executable", "*.exe"), ("All", "*.*")],
        )
        if path:
            self.current_exe = path
            self.exe_var.set(os.path.basename(path))
            _save_settings({
                "args": _string_to_args_list(self.args_text.get("1.0", tk.END)),
                "exe_path": path,
                "theme": self.theme_name,
                "model": _get_model_from_args(_string_to_args_list(self.args_text.get("1.0", tk.END))),
            })


# ===================================================================
# Точка входа
# ===================================================================

def main():
    root = tk.Tk()
    app = LauncherApp(root)

    # Применяем сохранённую тему
    apply_theme(root, app.theme_name)
    colors = THEMES[app.theme_name]
    app.log_text.configure(bg=colors["code_bg"], fg=colors["code_fg"], insertbackground=colors["fg"])
    app.args_text.configure(bg=colors["entry_bg"], fg=colors["entry_fg"], insertbackground=colors["fg"])
    app.api_chat_text.configure(bg=colors["chat_bg"], fg=colors["fg"], insertbackground=colors["fg"])
    app.api_input.configure(bg=colors["entry_bg"], fg=colors["entry_fg"], insertbackground=colors["fg"])

    tag_map = {
        "tag_user": {"foreground": colors["chat_user_bg"], "background": colors["chat_bg"]},
        "tag_user_text": {"foreground": colors["fg"], "background": colors["chat_bg"]},
        "tag_bot": {"foreground": colors["chat_bot_bg"], "background": colors["chat_bg"]},
        "tag_bot_text": {"foreground": colors["fg"], "background": colors["chat_bg"]},
        "tag_error": {"foreground": "#ff6b6b", "background": colors["chat_bg"]},
    }
    for tag, opts in tag_map.items():
        app.api_chat_text.tag_configure(tag, **opts)

    root.mainloop()


if __name__ == "__main__":
    main()
