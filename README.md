# LLM Server Launcher

GUI-лаунчер для локального LLM-сервера ([llama.cpp](https://github.com/ggerganov/llama.cpp)) с мониторингом ресурсов и API-тестером.

## Возможности

- 🚀 Запуск/остановка `llama-server.exe` из GUI
- 📊 Мониторинг CPU, RAM, GPU (VRAM) в реальном времени
- 🎨 Тёмная и светлая тема
- 💬 Встроенный API-тестер (`/v1/chat/completions`, `/v1/completions`)
- 💾 Автосохранение настроек (путь к exe, модель, тема)
- 🔍 Автоматический выбор файла при первом запуске

## Установка

### Требования

- Python 3.6+ (только стандартная библиотека)
- Windows 10/11
- [llama-server.exe](https://github.com/ggerganov/llama.cpp) — положите в папку `llama_server/`

### Структура проекта

```
llama-auto-run/
├── llama_gui.pyw              # Точка входа (GUI)
├── build.bat                  # Скрипт сборки в .exe
├── .gitignore
├── autoLLAma/                 # Пакет с модулями
│   ├── __init__.py
│   ├── app.py                 # Главное приложение (LauncherApp)
│   ├── utils.py               # Утилиты парсинга аргументов
│   ├── settings.py            # Загрузка/сохранение настроек
│   ├── monitor.py             # Мониторинг CPU/RAM/GPU
│   ├── threads.py             # Потоки (LogReader, Monitor)
│   ├── theme.py               # Система тем
│   └── api_client.py          # API-клиент для llama-server
├── llama_server/              # Папка для llama-server.exe
│   └── llama-server.exe
└── models/                    # Папка для моделей (.gguf)
```

## Использование

### Запуск из исходников

```powershell
# Двойной клик по llama_gui.pyw
# Или в консоли:
python llama_gui.pyw
```

### Сборка в .exe

```powershell
# Запустите build.bat
build.bat

# Или вручную:
pip install pyinstaller
pyinstaller --name "LLM-Launcher" --windowed --onefile ^
    --add-data "autoLLAma;autoLLAma" llama_gui.pyw
```

Готовый файл: `dist/LLM-Launcher.exe`

### Первый запуск

1. При первом запуске появится диалог выбора `llama-server.exe`
2. Выберите файл из папки `llama_server/`
3. Нажмите кнопку **"Выбрать модель"** и выберите `.gguf` файл
4. Нажмите **"Запуск"**

## Настройки

Настройки сохраняются в `launcher_settings.json` (игнорируется git):

```json
{
  "args": ["--model", "path/to/model.gguf", "--host", "127.0.0.1", ...],
  "exe_path": "C:\\path\\to\\llama-server.exe",
  "theme": "dark",
  "model": "C:\\path\\to\\model.gguf"
}
```

## API-тестер

Вкладка **"API-тестер"** позволяет отправлять запросы к запущенному серверу:

### Chat Completions

```json
POST /v1/chat/completions
{
  "model": "default",
  "messages": [{"role": "user", "content": "Привет!"}],
  "temperature": 0.7,
  "max_tokens": 512
}
```

### Completions (legacy)

```json
POST /v1/completions
{
  "model": "default",
  "prompt": "Привет!",
  "temperature": 0.7,
  "max_tokens": 512
}
```

**Горячая клавиша:** `Ctrl+Enter` — отправить сообщение

## Безопасность

- ⚠️ Сервер слушает `127.0.0.1` по умолчанию — недоступен из сети
- ⚠️ Не публикуйте llama-server в интернет без аутентификации
- ⚠️ Храните модели в надёжном месте — они могут содержать конфиденциальные данные

## Решение проблем

### Сервер не запускается

1. Проверьте путь к `llama-server.exe` (кнопка "Выбрать exe")
2. Убедитесь, что файл существует и не заблокирован антивирусом
3. Проверьте логи во вкладке **"Консоль"**

### Модель не загружается

1. Убедитесь, что файл `.gguf` не повреждён
2. Проверьте, что модель совместима с вашей версией llama.cpp
3. Посмотрите логи в консоли — там будет причина ошибки

### Мониторинг не работает

- **CPU/RAM** — работают на Windows без дополнительных зависимостей
- **GPU (VRAM)** — требует `nvidia-smi` (NVIDIA Driver + CUDA Toolkit)
- Если GPU не определяется, мониторинг покажет "—"

## Вклад

1. Форкните репозиторий
2. Создайте ветку для фичи (`git checkout -b feature/AmazingFeature`)
3. Закоммитьте изменения (`git commit -m 'feat: Add AmazingFeature'`)
4. Push в ветку (`git push origin feature/AmazingFeature`)
5. Откройте Pull Request

## Лицензия

MIT
