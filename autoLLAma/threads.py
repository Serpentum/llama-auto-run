import threading


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
    def __init__(self, update_callback, stop_event):
        super().__init__(daemon=True)
        self.update_callback = update_callback
        self._stop_event = stop_event

    def run(self):
        while not self._stop_event.is_set():
            try:
                self.update_callback()
            except Exception:
                pass
            self._stop_event.wait(2)
