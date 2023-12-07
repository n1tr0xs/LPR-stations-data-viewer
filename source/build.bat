@echo off
pyinstaller --noconfirm --clean --log-level FATAL --onedir --name "LPR stations data viewer" --contents-directory "." --noconsole --icon "icon.ico" --add-data "icon.ico";"." "main.py"