# app/schemas/batch.py
from pydantic import BaseModel, ConfigDict
from datetime import date

class BatchBase(BaseModel):
    product_id: int
    batch_number: str
    production_date: date
    expiry_date: date

class BatchCreate(BatchBase):
    pass

class BatchResponse(BatchBase):
    id: int

    # این تنظیم برای Pydantic v2 است تا بتواند داده‌های دیتابیس را مستقیماً بخواند
    model_config = ConfigDict(from_attributes=True)
