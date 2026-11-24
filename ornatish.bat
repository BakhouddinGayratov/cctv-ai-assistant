@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem CCTV AI ni shu kompyuterga o'rnatadi. Sichqonchaning o'ng tugmasi -> "Administrator sifatida ishga tushirish".

net session >nul 2>&1 || (echo Administrator sifatida ishga tushiring. & pause & exit /b 1)

echo [1/6] Python tekshirilmoqda...
python --version >nul 2>&1 || (
  echo Python topilmadi, o'rnatilmoqda...
  winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
  echo Python o'rnatildi. Oynani yopib, ornatish.bat ni qaytadan ishga tushiring.
  pause & exit /b 1
)

echo [2/6] ffmpeg tekshirilmoqda...
ffmpeg -version >nul 2>&1 || (
  winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
  echo ffmpeg o'rnatildi. Oynani yopib, ornatish.bat ni qaytadan ishga tushiring.
  pause & exit /b 1
)

if not exist ".env" (
  copy .env.example .env >nul
  echo .env yaratildi. Kalit va parollarni to'ldiring ^(README, "O'rnatish"^), saqlang va ornatish.bat ni qayta ishga tushiring.
  notepad .env
  pause & exit /b 1
)

echo [3/6] Kutubxonalar va modellar o'rnatilmoqda (bir necha daqiqa)...
rem onnxruntime yangi Visual C++ kutubxonasini talab qiladi, eski bo'lsa server qulaydi
winget install -e --id Microsoft.VCRedist.2015+.x64 --accept-package-agreements --accept-source-agreements >nul 2>&1
python -m pip install --disable-pip-version-check -r requirements.txt || (echo Kutubxonalar o'rnatilmadi. & pause & exit /b 1)
if not exist "models" mkdir models
if not exist "models\w600k_r50.onnx" (
  echo Yuz tanish modeli yuklanmoqda ^(288 MB, bir marta^)...
  curl.exe -L --fail --retry 20 --retry-all-errors -C - -o "%TEMP%\buffalo_l.zip" https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip
  tar -xf "%TEMP%\buffalo_l.zip" -C models w600k_r50.onnx || echo DIQQAT: yuz tanish modeli olinmadi, oddiyroq model ishlatiladi.
)
if not exist "..\yolov8n.pt" curl.exe -L --fail --retry 10 -o "..\yolov8n.pt" https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.pt

echo [4/6] Port tekshirilmoqda...
for /f "tokens=2 delims==" %%p in ('findstr /b "PORT=" .env') do set PORT=%%p
powershell -NoProfile -Command "$p=%PORT%; $busy=(netsh interface ipv4 show excludedportrange protocol=tcp) -match '^\s+\d' | %%{ $a=$_.Trim() -split '\s+'; if($p -ge [int]$a[0] -and $p -le [int]$a[1]){$_} }; if($busy){ Write-Host ('DIQQAT: port '+$p+' Windows tomonidan band. .env dagi PORT ni boshqa raqamga o''zgartiring.') -ForegroundColor Red }"
netsh advfirewall firewall add rule name="CCTV AI" dir=in action=allow protocol=TCP localport=%PORT% profile=private >nul

echo [5/6] Kompyuter yonganda avtomatik ishga tushish sozlanmoqda...
schtasks /Create /F /TN "CCTV AI" /SC ONLOGON /RL HIGHEST /TR "wscript.exe \"%~dp0yashirin_ishga_tushirish.vbs\"" >nul
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0

echo [6/6] Server ishga tushirilmoqda...
wscript.exe "%~dp0yashirin_ishga_tushirish.vbs"
timeout /t 30 /nobreak >nul
for /f "tokens=*" %%i in ('powershell -NoProfile -Command "(Get-NetIPConfiguration | ?{$_.IPv4DefaultGateway} | select -First 1).IPv4Address.IPAddress"') do set IP=%%i
echo.
echo Tayyor. Shu kompyuterda: http://127.0.0.1:%PORT%
echo Ofis tarmog'idagi boshqa qurilmalardan: http://%IP%:%PORT%
pause
