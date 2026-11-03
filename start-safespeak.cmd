@echo off
rem Double-click to start SafeSpeak PES locally (backend + frontend). Close with Ctrl+C.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-safespeak.ps1" %*
