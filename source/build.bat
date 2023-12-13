@echo off
pyinstaller --noconfirm --clean --log-level FATAL --onedir --name %name% --contents-directory "." --noconsole --icon "icon.ico" --add-data "icon.ico";"." "main.py"