# app/schemas/schemas.py
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import date

# ==========================================
# Batch Schemas (سری ساخت)
# ==========================================
class BatchBase(BaseModel):
    batch_number: str
    production_date: Optional[date] = None
    expiry_date: date  # تاریخ انقضا در سیستم دارویی/غذایی اجباری است

class BatchCreate(BatchBase):
    product_id: int

class BatchResponse(BatchBase):
    id: int
    product_id: int

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Product Schemas (محصولات)
# ==========================================
class ProductBase(BaseModel):
    name: str
    sku: str  # اصلاح فیلد برای پایداری با دیتابیس و انبارداری توزیع
    base_unit: str
    is_composite: bool = False
    product_type: Optional[str] = "finished_good"  # مقادیر مجاز: raw_material یا finished_good

class ProductCreate(ProductBase):
    pass

class ProductResponse(ProductBase):
    id: int
    batches: List[BatchResponse] = []  # نمایش لیست سری ساخت‌های هر محصول در پاسخ

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Transfer Schemas (انتقالات و تراکنش‌ها)
# ==========================================
class TransferCreate(BaseModel):
    sender_warehouse_id: int
    receiver_warehouse_id: int
    product_id: int
    batch_id: int  # الزامی شدن شناسه بچ برای پایداری زنجیره تامین و ردیابی بار
    amount: float
    packaging_id: Optional[int] = None
    description: Optional[str] = None

class TransferConfirm(BaseModel):
    received_amount: float  # مقداری که انبار مقصد واقعاً تحویل گرفته است


# ==========================================
# Recipe & BOM Schemas (فرمولاسیون مواد ترکیبی)
# ==========================================
class RecipeIngredient(BaseModel):
    ingredient_id: int
    quantity_required: float  # مقدار مورد نیاز از ماده اولیه برای تولید یک واحد کالا

class RecipeCreate(BaseModel):
    final_product_id: int
    ingredients: List[RecipeIngredient]

class RecipeResponse(BaseModel):
    id: int
    final_product_id: int
    ingredient_id: int
    quantity_required: float

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Production Schemas (عملیات دستور ساخت و تولید)
# ==========================================
class ProductionRequest(BaseModel):
    warehouse_id: int
    final_product_id: int
    produce_quantity: float
    new_batch_number: str  # شماره بچ محصول نهایی که تولید می‌شود

    # ==========================================
# Dispute Resolution Schemas (حل مغایرت)
# ==========================================
class DisputeResolveRequest(BaseModel):
    resolution_notes: str  # یادداشت بازرس درباره نحوه حل پرونده
    action_taken: str      # اقدامی که انجام شد (مثلاً: "جریمه راننده"، "تایید خسارت بیمه")