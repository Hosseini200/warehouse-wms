@echo off
cd /d C:\warehouse\backend
"C:\warehouse\backend\venv_new\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >> "C:\warehouse\logs\backend.log" 2>&1
