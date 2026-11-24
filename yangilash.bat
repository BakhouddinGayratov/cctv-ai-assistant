@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem GitHub'dan yangi versiyani oladi va serverni qayta yoqadi (ishga_tushirish.bat 10 soniyada o'zi yoqadi).
git pull || (echo Yangilab bo'lmadi. & pause & exit /b 1)
python -m pip install --disable-pip-version-check -q -r requirements.txt
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | ?{ $_.CommandLine -match 'main\.py' -and (Get-Process -Id $_.ProcessId).Path -and $_.CommandLine -notmatch 'manage\.py' } | %%{ Stop-Process -Id $_.ProcessId -Force }"
echo Yangilandi. Server 10-30 soniyada qayta ishga tushadi.
pause
