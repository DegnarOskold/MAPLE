@echo off
title IBKR Client Portal Gateway
echo ============================================================
echo           Starting IBKR Client Portal Gateway...
echo ============================================================
cd /d "%~dp0clientportal"
call "bin\run.bat" root\conf.yaml
pause
