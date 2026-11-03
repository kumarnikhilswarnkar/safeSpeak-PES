@echo off
rem Double-click to stop SafeSpeak PES started with start-safespeak.cmd.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-safespeak.ps1"
