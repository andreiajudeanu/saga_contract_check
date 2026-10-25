@echo off
rem Verifica din nou TOATE facturile din folderul e-Factura si rescrie fisierele din folderul de import.
rem Util cand ai schimbat un contract sau ai sters fisierele din "Import verificat".
cd /d "%~dp0"
python -m saga_check --config config.toml --reproceseaza
echo.
pause
