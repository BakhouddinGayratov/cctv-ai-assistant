@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem CCTV serverini ishga tushiradi va to'xtab qolsa 10 soniyadan keyin qayta yoqadi.
rem Kompyuter yonganda avtomatik ishlashi uchun Vazifalar rejalashtiruvchisiga qo'shing (README.md, "O'rnatish").
:loop
echo [%date% %time%] server ishga tushdi>> server_restart.log
python -X faulthandler main.py >> server.log 2>> server.err.log
echo [%date% %time%] server to'xtadi, 10 soniyadan keyin qayta yoqiladi>> server_restart.log
timeout /t 10 /nobreak >nul
goto loop
