@echo off
cd dist\
7z a "LPR stations data viewer" -tzip
gh release create