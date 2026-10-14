@echo off
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onefile --windowed ^
  --name "PNG压缩工具" ^
  --icon "assets\icon.ico" ^
  --add-binary "assets\pngquant.exe;." ^
  --add-data "assets\icon256.png;." ^
  --add-data "assets\icon.ico;." ^
  --collect-all customtkinter ^
  --collect-all tkinterdnd2 ^
  app.py
echo BUILD_EXIT=%ERRORLEVEL%
