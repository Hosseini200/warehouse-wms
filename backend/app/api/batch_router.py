# app/api/batch_router.py
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.domain import models
from app.api.transfer_router import get_current_user


router = APIRouter(
    prefix="/batches",
    tags=["Batches"]
)


class BatchCreateRequest(BaseModel):
    product_id: int
    batch_number: str
    production_date: Optional[datetime] = None
    expiry_date: datetime


def require_admin(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="فقط مدیر ارشد مجاز به ثبت سری ساخت است."
        )
    return current_user


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_batch(
    request: BatchCreateRequest,
    db: Session = Depends(get_db),
    _=Depends(require_admin)
):
    product = db.query(models.Product).filter(
        models.Product.id == request.product_id
    ).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="محصول انتخاب‌شده یافت نشد."
        )

    existing_batch = db.query(models.Batch).filter(
        models.Batch.batch_number == request.batch_number
    ).first()

    if existing_batch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="سری ساخت با این شماره بچ از قبل وجود دارد."
        )

    if request.expiry_date <= datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="تاریخ انقضا باید بعد از زمان فعلی باشد."
        )

    new_batch = models.Batch(
        product_id=request.product_id,
        batch_number=request.batch_number,
        production_date=request.production_date or datetime.utcnow(),
        expiry_date=request.expiry_date
    )

    try:
        db.add(new_batch)
        db.commit()
        db.refresh(new_batch)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="خطا در ثبت سری ساخت. شماره بچ یا اطلاعات محصول را بررسی کنید."
        )

    return {
        "id": new_batch.id,
        "product_id": new_batch.product_id,
        "batch_number": new_batch.batch_number,
        "production_date": new_batch.production_date,
        "expiry_date": new_batch.expiry_date
    }


@router.get("/product/{product_id}")
def get_batches_by_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    product = db.query(models.Product).filter(
        models.Product.id == product_id
    ).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="محصول یافت نشد."
        )

    batches = db.query(models.Batch).filter(
        models.Batch.product_id == product_id
    ).order_by(models.Batch.id.desc()).all()

    return [
        {
            "id": batch.id,
            "product_id": batch.product_id,
            "batch_number": batch.batch_number,
            "production_date": batch.production_date,
            "expiry_date": batch.expiry_date
        }
        for batch in batches
    ]


@router.get("/")
def get_all_batches(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    batches = db.query(models.Batch).order_by(
        models.Batch.id.desc()
    ).all()

    return [
        {
            "id": batch.id,
            "product_id": batch.product_id,
            "product_name": batch.product.name if batch.product else "Unknown",
            "batch_number": batch.batch_number,
            "production_date": batch.production_date,
            "expiry_date": batch.expiry_date
        }
        for batch in batches
    ]