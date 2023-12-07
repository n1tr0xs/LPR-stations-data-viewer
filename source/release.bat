@echo off
cd dist\
del "LPR stations data viewer.zip"
7z a "LPR stations data viewer" -tzip
gh release create