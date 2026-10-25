@echo off
rem Dublu-click: citeste contractele noi, verifica facturile si pregateste XML-urile pentru SAGA.
cd /d "%~dp0"
python -m saga_check --config config.toml
echo.
pause
