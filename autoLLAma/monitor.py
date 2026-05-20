import subprocess
import ctypes
import sys


def get_windows_memory_info():
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


def get_cpu_usage():
    try:
        result = subprocess.run(
            ["wmic", "cpu", "get", "loadpercentage", "/format:list"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        for line in result.stdout.splitlines():
            if "=" in line:
                val = line.split("=")[1].strip()
                return int(val)
    except Exception:
        pass
    return None


def get_gpu_memory():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total",
             "--format=csv,noheader,nounits", "-i", "0"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(",")
            if len(parts) == 2:
                return int(parts[0].strip()), int(parts[1].strip())
    except Exception:
        pass
    return None, None


def format_bytes(b):
    if b is None:
        return "— МБ"
    gb = b / (1024 ** 3)
    if gb >= 1:
        return f"{gb:.1f} ГБ"
    return f"{b / 1024 / 1024:.0f} МБ"
