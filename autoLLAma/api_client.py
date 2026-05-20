import json
import urllib.request
import urllib.error


class APIClient:
    def __init__(self, host="127.0.0.1", port=8080, root=None):
        self.host = host
        self.port = port
        self.root = root

    def _url(self, path):
        return f"http://{self.host}:{self.port}{path}"

    def send_chat(self, messages, model="", temperature=0.7, max_tokens=512, stream=False):
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
