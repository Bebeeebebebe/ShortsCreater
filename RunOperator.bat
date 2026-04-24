@echo off
cd /d "%~dp0"

echo Starting FastAPI server...
uvicorn OperatorAPI:app --host 0.0.0.0 --port 8000

pause