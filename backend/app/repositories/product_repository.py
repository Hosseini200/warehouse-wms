# app/repositories/product_repository.py
from sqlalchemy.orm import Session
from typing import Optional
from app.domain.models import Product
from app.schemas import schemas  # اصلاح نحوه ایمپورت برای هماهنگی با نسخه متمرکز اسکیماها

class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, product_in: schemas.ProductCreate) -> Product:
        """
        یک محصول جدید در دیتابیس ایجاد می‌کند.
        از model_dump() برای تبدیل اسکیمای Pydantic به دیکشنری مناسب برای مدل SQLAlchemy استفاده می‌شود.
        """
        db_product = Product(**product_in.model_dump())
        self.db.add(db_product)
        self.db.commit()
        self.db.refresh(db_product)
        return db_product
        
    def get_by_sku(self, sku: str) -> Optional[Product]:
        """
        یک محصول را بر اساس شناسه یکتای SKU آن جستجو می‌کند.
        این متد با سیستم بارگذاری اکسل و ردیابی زنجیره تامین کاملاً هماهنگ است.
        """
        return self.db.query(Product).filter(Product.sku == sku).first()