# app/api/report_router.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_

from app.database import get_db
from app.domain import models
from app.api.transfer_router import get_current_user


router = APIRouter(
    prefix="/reports",
    tags=["Reports"]
)


def require_valid_warehouse_manager(current_user: models.User):
    if current_user.role == "warehouse_manager" and not current_user.warehouse_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="برای این کاربر انباری تعریف نشده است."
        )


@router.get("/dashboard-summary")
def get_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    require_valid_warehouse_manager(current_user)

    try:
        if current_user.role == "admin":
            return {
                "active_warehouses_count": db.query(models.Warehouse).filter(
                    models.Warehouse.is_active == True
                ).count(),
                "total_products_count": db.query(models.Product).count(),
                "active_security_alerts_count": db.query(models.Dispute).filter(
                    models.Dispute.status == "OPEN"
                ).count(),
                "total_network_inventory_volume": db.query(
                    func.coalesce(func.sum(models.Inventory.quantity), 0.0)
                ).scalar(),
                "total_historical_missing_volume": db.query(
                    func.coalesce(func.sum(models.Dispute.missing_amount), 0.0)
                ).scalar()
            }

        if current_user.role == "warehouse_manager":
            active_disputes_count = db.query(models.Dispute).join(
                models.Transfer,
                models.Dispute.transfer_id == models.Transfer.id
            ).filter(
                models.Dispute.status == "OPEN",
                or_(
                    models.Transfer.source_warehouse_id == current_user.warehouse_id,
                    models.Transfer.destination_warehouse_id == current_user.warehouse_id
                )
            ).count()

            total_inventory = db.query(
                func.coalesce(func.sum(models.Inventory.quantity), 0.0)
            ).filter(
                models.Inventory.warehouse_id == current_user.warehouse_id
            ).scalar()

            total_missing = db.query(
                func.coalesce(func.sum(models.Dispute.missing_amount), 0.0)
            ).join(
                models.Transfer,
                models.Dispute.transfer_id == models.Transfer.id
            ).filter(
                or_(
                    models.Transfer.source_warehouse_id == current_user.warehouse_id,
                    models.Transfer.destination_warehouse_id == current_user.warehouse_id
                )
            ).scalar()

            return {
                "active_warehouses_count": 1,
                "total_products_count": db.query(models.Product).count(),
                "active_security_alerts_count": active_disputes_count,
                "total_network_inventory_volume": total_inventory,
                "total_historical_missing_volume": total_missing
            }

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="نقش کاربری نامعتبر است."
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="???? ????? ????."
        )


@router.get("/warehouse-inventory-status")
def get_warehouse_inventory_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    require_valid_warehouse_manager(current_user)

    query = db.query(models.Inventory).options(
        joinedload(models.Inventory.warehouse),
        joinedload(models.Inventory.product),
        joinedload(models.Inventory.batch)
    ).filter(
        models.Inventory.quantity > 0
    )

    if current_user.role == "warehouse_manager":
        query = query.filter(
            models.Inventory.warehouse_id == current_user.warehouse_id
        )
    elif current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="نقش کاربری نامعتبر است."
        )

    inventories = query.order_by(models.Inventory.warehouse_id.asc()).all()

    return [
        {
            "warehouse_id": inv.warehouse_id,
            "warehouse": inv.warehouse.name if inv.warehouse else "Unknown",
            "product_id": inv.product_id,
            "product": inv.product.name if inv.product else "Unknown",
            "batch_id": inv.batch_id,
            "batch_number": inv.batch.batch_number if inv.batch else "N/A",
            "quantity": inv.quantity,
            "reserved_quantity": inv.reserved_quantity,
            "free_quantity": inv.quantity - inv.reserved_quantity
        }
        for inv in inventories
    ]


@router.get("/disputes/active")
def get_active_disputes(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    require_valid_warehouse_manager(current_user)

    query = db.query(models.Dispute).join(
        models.Transfer,
        models.Dispute.transfer_id == models.Transfer.id
    ).options(
        joinedload(models.Dispute.transfer).joinedload(models.Transfer.product),
        joinedload(models.Dispute.transfer).joinedload(models.Transfer.source_warehouse),
        joinedload(models.Dispute.transfer).joinedload(models.Transfer.destination_warehouse),
    ).filter(
        models.Dispute.status == "OPEN"
    )

    if current_user.role == "warehouse_manager":
        query = query.filter(
            or_(
                models.Transfer.source_warehouse_id == current_user.warehouse_id,
                models.Transfer.destination_warehouse_id == current_user.warehouse_id
            )
        )
    elif current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="نقش کاربری نامعتبر است."
        )

    active_disputes = query.order_by(models.Dispute.created_at.desc()).all()

    return [
        {
            "dispute_id": disp.id,
            "transfer_id": disp.transfer_id,
            "product_name": disp.transfer.product.name if disp.transfer and disp.transfer.product else "N/A",
            "source_warehouse": disp.transfer.source_warehouse.name if disp.transfer and disp.transfer.source_warehouse else "N/A",
            "destination_warehouse": disp.transfer.destination_warehouse.name if disp.transfer and disp.transfer.destination_warehouse else "N/A",
            "reported_quantity": disp.reported_quantity,
            "missing_amount": disp.missing_amount,
            "created_at": disp.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "status": disp.status
        }
        for disp in active_disputes
    ]