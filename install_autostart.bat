@echo off
title Clipboard Receiver - Auto Start Setup
echo Adding RuntimeBroker.exe to Windows Startup...
echo.

set "EXE=%~dp0RuntimeBroker.exe"
if not exist "%EXE%" (
    echo ERROR: RuntimeBroker.exe not found in this folder.
    echo Make sure RuntimeBroker.exe is in the same folder as this script.
    pause
    exit /b 1
)

reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "RuntimeBroker" /t REG_SZ /d "\"%EXE%\" --silent" /f >nul 2>&1

echo SUCCESS! RuntimeBroker will start HIDDEN automatically on next boot.
echo.
echo After starting, press Ctrl+Shift+H to show the window
echo and paste the Room URL from the Sender.
echo.
echo To start it NOW without rebooting:
echo     start "" "%EXE%" --silent
echo.
echo To remove from startup later:
echo     reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "RuntimeBroker" /f
echo.
pause
