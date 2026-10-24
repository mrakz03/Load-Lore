@echo off
REM Double-click this (from the scripts folder) on a Windows PC that has Python installed (python.org, tick "Add to PATH").
REM It creates the "LoadLore" folder with the .exe ready to share (like the portable .zip from a release).
cd /d "%~dp0.."
python -m pip install --upgrade pyinstaller || goto :err
python -m PyInstaller -y --onefile --windowed --name LoadLore --icon assets\icon.ico --add-data "assets/icon.png:." src\load_lore.py || goto :err
if exist LoadLore rmdir /s /q LoadLore
mkdir LoadLore
copy dist\LoadLore.exe LoadLore\ >nul
copy data\*.csv LoadLore\ >nul
del /q LoadLore\my_*.csv 2>nul
copy LICENSE LoadLore\LICENSE.txt >nul
copy LEGAL.md LoadLore\ >nul
echo.
echo Done! Zip up the LoadLore folder and send it. Double-click LoadLore.exe to run.
pause
exit /b 0
:err
echo Something went wrong - see the messages above.
pause
