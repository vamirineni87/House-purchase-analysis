@echo off
REM Start PIPA server (no reload — Playwright-compatible)
cd /d "%~dp0"
python run_server.py
