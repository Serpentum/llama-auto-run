import tkinter as tk
from tkinter import ttk

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
