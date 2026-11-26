@echo off
setlocal
set "PYW=pythonw.exe"
if exist "%~dp0.env" (
  for /f "usebackq tokens=1,* delims==" %%A in ("%~dp0.env") do (
    if /i "%%A"=="GRIMOIRE_PYTHONW" set "PYW=%%~B"
  )
)
"%PYW%" "%~dp0run.py" --host 0.0.0.0 --port 7940
