# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine
from app.domain import models

from app.api import auth_router
from app.api import admin_router
from app.api import inventory_excel_router
from app.api import batch_router
from app.api import production_router
from app.api import report_router
from app.api import transfer_router as api_transfer_router

from app.routers import warehouse_router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="سیستم مدیریت هوشمند انبار",
    description="Warehouse SCM API",
    version="1.0.0",
)


# CORS امن‌تر برای اجرای لوکال و Streamlit
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# ساخت جدول‌ها بر اساس مدل اصلی پروژه
models.Base.metadata.create_all(bind=engine)

# Routers
app.include_router(auth_router.router)
app.include_router(admin_router.router)
app.include_router(inventory_excel_router.router)
app.include_router(warehouse_router.router)
app.include_router(batch_router.router)
app.include_router(api_transfer_router.router)
app.include_router(production_router.router)
app.include_router(report_router.router)


@app.get("/", tags=["General"])
def read_root():
    return {
        "status": "success",
        "message": "Warehouse SCM API is running"
    }


@app.get("/health", tags=["General"])
def health_check():
    return {
        "status": "ok"
    }