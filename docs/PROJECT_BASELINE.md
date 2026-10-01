# Warehouse WMS - Project Baseline

## Project Information

Project Name:
Warehouse WMS

Baseline Version:
v1.0

Baseline Date:
2026-10-01

Repository:
https://github.com/Hosseini200/warehouse-wms.git


---

# Production Environment

## Server

Environment:
Production

OS:
Windows Server

Deployment Access:
RDP


---

# Backend

Path:

C:\warehouse\backend


Framework:

FastAPI


Runtime:

Python Virtual Environment

C:\warehouse\backend\venv_new


Startup Method:

Windows Task Scheduler


Task Name:

WarehouseBackend


Entry Point:

run_backend_service.py


Application Server:

Uvicorn


API Port:

8000


---

# Frontend

Framework:

React + Vite + PWA


Source Path:

C:\warehouse\builds\warehouse-pwa_20260722_114050


Production URL:

https://wms.daroo100.com/


Deployment:

Plesk Virtual Host


Deploy Path:

C:\inetpub\vhosts\daroo100.com\wms.daroo100.com


---

# Database

Database Engine:

PostgreSQL 16


Service:

postgresql-x64-16


Migration Location:

C:\warehouse\migrations


Migration Type:

Manual SQL Migration Files


---

# Git Workflow

Branches:

main:
Production stable version


develop:
Development integration branch


feature/*:
Individual feature development


---

# Deployment Rules

1. Never modify production directly.

2. Every change must start from develop.

3. Every feature must have its own branch.

4. Test before merging.

5. Merge tested changes into develop.

6. Deploy only approved versions to production.


---

# Current Baseline Commit

Commit:

d8f2636

Message:

Production Baseline v1 - 2026-10-01