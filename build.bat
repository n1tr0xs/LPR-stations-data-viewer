@echo off
pyinstaller --noconfirm --clean --log-level FATAL --onedir --name "LPR stations data viewer" --noconsole --icon "icon.ico" "main.py"