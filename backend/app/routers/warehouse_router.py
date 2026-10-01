from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.domain import models
from app.api.transfer_router import get_current_user


router = APIRouter(
    prefix="/warehouses",
    tags=["Warehouses"]
)


@router.get("/")
def get_all_warehouses(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    لیست انبارها.
    ادمین: همه انبارهای فعال
    انباردار: فقط انبار خودش
    """

    if current_user.role == "admin":
        return db.query(models.Warehouse).filter(
            models.Warehouse.is_active == True
        ).order_by(models.Warehouse.id.asc()).all()

    if current_user.role == "warehouse_manager":
        if not current_user.warehouse_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="برای این کاربر انباری تعریف نشده است."
            )

        warehouse = db.query(models.Warehouse).filter(
            models.Warehouse.id == current_user.warehouse_id,
            models.Warehouse.is_active == True
        ).first()

        if not warehouse:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="انبار مرتبط با این کاربر یافت نشد."
            )

        return [warehouse]

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="نقش کاربری نامعتبر است."
    )

@router.get("/destinations")
def get_destination_warehouses(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    لیست انبارهای مقصد برای ثبت حواله.
    ادمین: همه انبارهای فعال
    انباردار: همه انبارهای فعال به‌جز انبار خودش
    """

    if current_user.role == "admin":
        warehouses = db.query(models.Warehouse).filter(
            models.Warehouse.is_active == True
        ).order_by(models.Warehouse.id.asc()).all()

    elif current_user.role == "warehouse_manager":
        if not current_user.warehouse_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="برای این کاربر انباری تعریف نشده است."
            )

        warehouses = db.query(models.Warehouse).filter(
            models.Warehouse.is_active == True,
            models.Warehouse.id != current_user.warehouse_id
        ).order_by(models.Warehouse.id.asc()).all()

    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="نقش کاربری نامعتبر است."
        )

    return [
        {
            "id": warehouse.id,
            "name": warehouse.name,
            "location": warehouse.location,
            "is_active": warehouse.is_active
        }
        for warehouse in warehouses
    ]

@router.post("/")
def create_warehouse(
    name: str,
    location: str = "",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    ساخت انبار جدید.
    فقط ادمین مجاز است.
    """

    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="فقط مدیر ارشد مجاز به ساخت انبار است."
        )

    existing = db.query(models.Warehouse).filter(
        models.Warehouse.name == name
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="انباری با این نام از قبل وجود دارد."
        )

    new_warehouse = models.Warehouse(
        name=name,
        location=location,
        is_active=True
    )

    db.add(new_warehouse)
    db.commit()
    db.refresh(new_warehouse)

    return {
        "message": "انبار با موفقیت ساخته شد",
        "warehouse_id": new_warehouse.id
    }