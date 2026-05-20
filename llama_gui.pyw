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

import tkinter as tk
from autoLLAma.app import LauncherApp
from autoLLAma.theme import apply_theme, THEMES


def main():
    root = tk.Tk()
    app = LauncherApp(root)

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
