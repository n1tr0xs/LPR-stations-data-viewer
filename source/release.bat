@echo off
cd dist\
del *.zip
7z a %name% -tzip
gh release create