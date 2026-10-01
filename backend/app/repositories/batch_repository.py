from sqlalchemy.orm import Session
from typing import List, Optional
from app.domain.models import Batch
from app.schemas import BatchCreate

class BatchRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, batch_in: BatchCreate) -> Batch:
        """
        ایجاد یک سری ساخت (Batch) جدید در دیتابیس.
        استفاده از model_dump برای تبدیل خودکار فیلدهای Pydantic به SQLAlchemy.
        """
        db_batch = Batch(**batch_in.model_dump())
        self.db.add(db_batch)
        self.db.commit()
        self.db.refresh(db_batch)
        return db_batch

    def get_by_batch_number(self, batch_number: str) -> Optional[Batch]:
        """
        جستجوی یک سری ساخت بر اساس شماره بچ (Batch Number).
        از آنجا که شماره بچ یکتاست، از first() استفاده می‌کنیم.
        """
        return self.db.query(Batch).filter(Batch.batch_number == batch_number).first()

    def get_by_product_id(self, product_id: int) -> List[Batch]:
        """
        دریافت تمام سری ساخت‌های مرتبط با یک محصول خاص (با استفاده از شناسه محصول).
        """
        return self.db.query(Batch).filter(Batch.product_id == product_id).all()
