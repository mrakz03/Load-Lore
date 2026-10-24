@echo off
REM Double-click this (from the scripts folder) on a Windows PC that has Python installed (python.org, tick "Add to PATH").
REM It creates the "CartridgeCalculator" folder with the .exe ready to share (like the portable .zip from a release).
cd /d "%~dp0.."
python -m pip install --upgrade pyinstaller || goto :err
python -m PyInstaller -y --onefile --windowed --name CartridgeCalculator --icon assets\icon.ico --add-data "assets/icon.png:." src\cartridge_calculator.py || goto :err
if exist CartridgeCalculator rmdir /s /q CartridgeCalculator
mkdir CartridgeCalculator
copy dist\CartridgeCalculator.exe CartridgeCalculator\ >nul
copy data\*.csv CartridgeCalculator\ >nul
del /q CartridgeCalculator\my_*.csv 2>nul
copy LICENSE CartridgeCalculator\LICENSE.txt >nul
copy LEGAL.md CartridgeCalculator\ >nul
echo.
echo Done! Zip up the CartridgeCalculator folder and send it. Double-click CartridgeCalculator.exe to run.
pause
exit /b 0
:err
echo Something went wrong - see the messages above.
pause
