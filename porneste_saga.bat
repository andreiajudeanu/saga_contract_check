@echo off
rem Porneste SAGA C dupa ce verifica facturile noi: rezultatele sunt gata in import_saga cand se deschide SAGA.
rem Folositi acest fisier (sau scurtatura lui de pe Desktop) in loc de iconita SAGA.
cd /d "%~dp0"
echo Verific contractele si facturile noi...
python -m saga_check --config config.toml
if errorlevel 1 (
  echo.
  echo A aparut o eroare - vezi mesajul de mai sus. SAGA se deschide oricum.
  pause
)
set "SAGA_EXE=C:\SAGA C.3.0\sc.exe"
if not exist "%SAGA_EXE%" (
  echo Nu gasesc %SAGA_EXE% - modificati calea in porneste_saga.bat
  pause
  exit /b 1
)
start "" /D "C:\SAGA C.3.0" "%SAGA_EXE%"
