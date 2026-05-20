@echo off
echo Building LLM-Launcher.exe...
pip install pyinstaller --quiet
pyinstaller --name "LLM-Launcher" --windowed --onefile --add-data "autoLLAma;autoLLAma" llama_gui.pyw
if %errorlevel% equ 0 (
    echo.
    echo Build successful!
    echo Executable: dist\LLM-Launcher.exe
) else (
    echo.
    echo Build failed!
    pause
    exit /b 1
)
pause
