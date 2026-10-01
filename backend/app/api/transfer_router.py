# app/api/transfer_router.py
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from typing import Optional, List

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.domain import models
from app import security


router = APIRouter(
    prefix="/transfers",
    tags=["Transfers & Ticketing"]
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="نشست کاربری نامعتبر یا منقضی شده است.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            security.SECRET_KEY,
            algorithms=[security.ALGORITHM]
        )
        username = payload.get("sub")
        if not username:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    user = db.query(models.User).filter(
        models.User.username == username,
        models.User.is_active == True
    ).first()

    if not user:
        raise credentials_exception

    return user


class TransferCreate(BaseModel):
    sender_warehouse_id: int
    receiver_warehouse_id: int
    product_id: int
    batch_id: int
    amount: float
    description: Optional[str] = None


class TransferPackagingPreviewRequest(BaseModel):
    sender_warehouse_id: int
    product_id: int
    amount: float

class TransferConfirm(BaseModel):
    received_amount: float


class TicketMessageCreate(BaseModel):
    message_text: str


class DisputeResolveRequest(BaseModel):
    resolution_notes: str
    action_taken: str


def _is_admin(user: models.User) -> bool:
    return user.role == "admin"


def _can_access_transfer(user: models.User, transfer: models.Transfer) -> bool:
    if _is_admin(user):
        return True

    return user.warehouse_id in [
        transfer.source_warehouse_id,
        transfer.destination_warehouse_id
    ]


def _require_source_access(user: models.User, warehouse_id: int):
    if not _is_admin(user) and user.warehouse_id != warehouse_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="شما مجاز به انجام عملیات روی انبار مبدأ نیستید."
        )


def _require_destination_access(user: models.User, warehouse_id: int):
    if not _is_admin(user) and user.warehouse_id != warehouse_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="شما مجاز به انجام عملیات روی انبار مقصد نیستید."
        )


def _get_inventory_for_update(
    db: Session,
    warehouse_id: int,
    product_id: int,
    batch_id: int
):
    return db.query(models.Inventory).filter(
        models.Inventory.warehouse_id == warehouse_id,
        models.Inventory.product_id == product_id,
        models.Inventory.batch_id == batch_id
    ).with_for_update().first()



def _get_packaging_inventory_for_update(
    db: Session,
    warehouse_id: int,
    material_id: int
):
    return db.query(models.PackagingInventory).filter(
        models.PackagingInventory.warehouse_id == warehouse_id,
        models.PackagingInventory.material_id == material_id
    ).with_for_update().first()


def _add_audit_log(
    db: Session,
    action: str,
    transfer_id: Optional[int],
    product_id: Optional[int],
    user_id: Optional[int],
    details: str
):
    db.add(models.AuditLog(
        action=action,
        transfer_id=transfer_id,
        product_id=product_id,
        user_id=user_id,
        details=details
    ))


def _release_reserved_quantity(
    db: Session,
    transfer: models.Transfer
):
    inventory = _get_inventory_for_update(
        db,
        transfer.source_warehouse_id,
        transfer.product_id,
        transfer.batch_id
    )

    if inventory:
        inventory.reserved_quantity = max(
            0.0,
            inventory.reserved_quantity - transfer.quantity
        )

    packaging_items = db.query(
        models.TransferPackagingItem
    ).filter(
        models.TransferPackagingItem.transfer_id == transfer.id
    ).with_for_update().all()

    for item in packaging_items:
        if (
            item.consumption_stage_snapshot == "dispatch"
            and item.reserved_quantity > 0
        ):
            packaging_inventory = (
                _get_packaging_inventory_for_update(
                    db=db,
                    warehouse_id=transfer.source_warehouse_id,
                    material_id=item.material_id
                )
            )

            if packaging_inventory:
                packaging_inventory.reserved_quantity = max(
                    0,
                    packaging_inventory.reserved_quantity
                    - item.reserved_quantity
                )

        item.reserved_quantity = 0
        item.status = "released"


def _transfer_to_decimal(value, field_name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid numeric value for {field_name}."
        ) from exc

    if not result.is_finite():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Non-finite numeric value for {field_name}."
        )

    return result


def _calculate_transfer_packaging_quantity(
    product_quantity,
    quantity_per_product,
    rounding_mode: str
) -> int:
    quantity = _transfer_to_decimal(
        product_quantity,
        "product_quantity"
    )
    ratio = _transfer_to_decimal(
        quantity_per_product,
        "quantity_per_product"
    )

    if quantity <= 0 or ratio <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Product quantity and packaging ratio "
                "must be greater than zero."
            )
        )

    calculated = quantity * ratio
    mode = (rounding_mode or "").strip().lower()

    if mode == "ceil":
        return int(
            calculated.to_integral_value(
                rounding=ROUND_CEILING
            )
        )

    if mode == "exact":
        integral = calculated.to_integral_value()

        if calculated != integral:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Exact packaging calculation produced "
                    "a fractional quantity."
                )
            )

        return int(integral)

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported packaging rounding mode: {rounding_mode}"
    )


def _build_transfer_packaging_plan(
    db: Session,
    source_warehouse_id: int,
    product: models.Product,
    amount,
    lock_inventory: bool = False
):
    product_quantity = _transfer_to_decimal(
        amount,
        "amount"
    )

    if product_quantity <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transfer amount must be greater than zero."
        )

    if product_quantity != product_quantity.to_integral_value():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Transfer amount must be a whole number "
                "because packaging is required."
            )
        )

    unit_weight = _transfer_to_decimal(
        product.unit_weight_grams or 0,
        "unit_weight_grams"
    )

    if unit_weight <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Product unit weight must be greater "
                "than zero."
            )
        )

    profile_query = db.query(
        models.PackagingProfile
    ).filter(
        models.PackagingProfile.product_id == product.id,
        models.PackagingProfile.is_active == True
    )

    if lock_inventory:
        profile_query = profile_query.with_for_update()

    profile = profile_query.first()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "An active packaging profile is required "
                "for product transfer."
            )
        )

    profile_items = sorted(
        profile.items,
        key=lambda item: item.id or 0
    )

    if not profile_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The active packaging profile has no items."
        )

    primary_items = [
        item
        for item in profile_items
        if item.is_primary
    ]

    if len(primary_items) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "The active packaging profile must have "
                "exactly one primary item."
            )
        )

    primary_material = primary_items[0].material

    if (
        primary_material is None
        or primary_material.material_type != "container"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Primary packaging must be a container."
        )

    if primary_material.capacity_grams is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Primary container capacity is not defined."
        )

    container_capacity = _transfer_to_decimal(
        primary_material.capacity_grams,
        "primary_container_capacity"
    )

    if container_capacity < unit_weight:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Primary container capacity is smaller "
                "than product unit weight."
            )
        )

    result_items = []
    all_dispatch_items_available = True

    for profile_item in profile_items:
        material = profile_item.material

        if material is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Packaging material was not found for "
                    f"profile item {profile_item.id}."
                )
            )

        required_quantity = (
            _calculate_transfer_packaging_quantity(
                product_quantity,
                profile_item.quantity_per_product,
                profile_item.rounding_mode
            )
        )

        available_quantity = None
        sufficient = True
        inventory_action = "embedded_in_finished_product"

        if profile_item.consumption_stage == "dispatch":
            inventory_query = db.query(
                models.PackagingInventory
            ).filter(
                models.PackagingInventory.warehouse_id
                == source_warehouse_id,
                models.PackagingInventory.material_id
                == profile_item.material_id
            )

            if lock_inventory:
                inventory_query = inventory_query.with_for_update()

            packaging_inventory = inventory_query.first()

            if packaging_inventory:
                available_quantity = (
                    packaging_inventory.quantity
                    - packaging_inventory.reserved_quantity
                )
            else:
                available_quantity = 0

            sufficient = (
                available_quantity >= required_quantity
            )

            inventory_action = "reserve_at_transfer"

            if not sufficient:
                all_dispatch_items_available = False

        elif profile_item.consumption_stage != "production":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Unsupported packaging consumption stage: "
                    f"{profile_item.consumption_stage}"
                )
            )

        result_items.append({
            "profile_item_id": profile_item.id,
            "material_id": material.id,
            "material_name": material.name,
            "material_sku": material.sku,
            "material_type": material.material_type,
            "quantity_per_product": float(
                profile_item.quantity_per_product
            ),
            "required_quantity": required_quantity,
            "consumption_stage": (
                profile_item.consumption_stage
            ),
            "rounding_mode": profile_item.rounding_mode,
            "is_primary": profile_item.is_primary,
            "inventory_action": inventory_action,
            "available_quantity": available_quantity,
            "sufficient": sufficient
        })

    return {
        "packaging_required": True,
        "product_id": product.id,
        "product_sku": product.sku,
        "product_quantity": float(product_quantity),
        "profile_id": profile.id,
        "profile_name": profile.name,
        "profile_version": profile.version,
        "items": result_items,
        "all_dispatch_items_available": (
            all_dispatch_items_available
        )
    }


@router.post("/packaging-preview")
def preview_transfer_packaging(
    request: TransferPackagingPreviewRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    _require_source_access(
        current_user,
        request.sender_warehouse_id
    )

    warehouse = db.query(models.Warehouse).filter(
        models.Warehouse.id == request.sender_warehouse_id,
        models.Warehouse.is_active == True
    ).first()

    if not warehouse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active source warehouse was not found."
        )

    product = db.query(models.Product).filter(
        models.Product.id == request.product_id
    ).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product was not found."
        )

    return _build_transfer_packaging_plan(
        db=db,
        source_warehouse_id=request.sender_warehouse_id,
        product=product,
        amount=request.amount,
        lock_inventory=False
    )


@router.post("/", status_code=status.HTTP_201_CREATED)
def initiate_transfer(
    request: TransferCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    _require_source_access(
        current_user,
        request.sender_warehouse_id
    )

    amount = _transfer_to_decimal(
        request.amount,
        "amount"
    )

    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transfer amount must be greater than zero."
        )

    if (
        request.sender_warehouse_id
        == request.receiver_warehouse_id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Source and destination warehouses "
                "must be different."
            )
        )

    try:
        source_warehouse = db.query(
            models.Warehouse
        ).filter(
            models.Warehouse.id
            == request.sender_warehouse_id,
            models.Warehouse.is_active == True
        ).first()

        if not source_warehouse:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Active source warehouse was not found."
            )

        destination_warehouse = db.query(
            models.Warehouse
        ).filter(
            models.Warehouse.id
            == request.receiver_warehouse_id,
            models.Warehouse.is_active == True
        ).first()

        if not destination_warehouse:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "Active destination warehouse "
                    "was not found."
                )
            )

        product = db.query(models.Product).filter(
            models.Product.id == request.product_id
        ).first()

        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product was not found."
            )

        batch = db.query(models.Batch).filter(
            models.Batch.id == request.batch_id,
            models.Batch.product_id == request.product_id
        ).first()

        if not batch:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Selected batch does not belong "
                    "to the selected product."
                )
            )

        inventory = _get_inventory_for_update(
            db=db,
            warehouse_id=request.sender_warehouse_id,
            product_id=request.product_id,
            batch_id=request.batch_id
        )

        if not inventory:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Product inventory for this batch "
                    "was not found in the source warehouse."
                )
            )

        free_quantity = (
            _transfer_to_decimal(
                inventory.quantity,
                "inventory_quantity"
            )
            - _transfer_to_decimal(
                inventory.reserved_quantity or 0,
                "reserved_quantity"
            )
        )

        if free_quantity < amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Insufficient free product inventory. "
                    f"Available: {free_quantity}"
                )
            )

        packaging_plan = _build_transfer_packaging_plan(
            db=db,
            source_warehouse_id=request.sender_warehouse_id,
            product=product,
            amount=amount,
            lock_inventory=True
        )

        if not packaging_plan[
            "all_dispatch_items_available"
        ]:
            shortages = [
                {
                    "material_sku": item["material_sku"],
                    "required_quantity": (
                        item["required_quantity"]
                    ),
                    "available_quantity": (
                        item["available_quantity"]
                    )
                }
                for item in packaging_plan["items"]
                if (
                    item["consumption_stage"] == "dispatch"
                    and not item["sufficient"]
                )
            ]

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": (
                        "Insufficient dispatch packaging "
                        "inventory."
                    ),
                    "shortages": shortages
                }
            )

        now = datetime.utcnow()

        inventory.reserved_quantity = float(
            _transfer_to_decimal(
                inventory.reserved_quantity or 0,
                "reserved_quantity"
            )
            + amount
        )

        transfer = models.Transfer(
            source_warehouse_id=request.sender_warehouse_id,
            destination_warehouse_id=(
                request.receiver_warehouse_id
            ),
            product_id=request.product_id,
            batch_id=request.batch_id,
            quantity=float(amount),
            status=(
                models.TransferStatus
                .PENDING_SOURCE_APPROVAL
                .value
            ),
            description=request.description,
            tracking_deadline=now + timedelta(hours=24),
            created_at=now,
            updated_at=now
        )

        db.add(transfer)
        db.flush()

        packaging_snapshot = []

        for item in packaging_plan["items"]:
            reserved_quantity = 0
            snapshot_status = "planned"

            if item["consumption_stage"] == "dispatch":
                packaging_inventory = (
                    _get_packaging_inventory_for_update(
                        db=db,
                        warehouse_id=request.sender_warehouse_id,
                        material_id=item["material_id"]
                    )
                )

                if not packaging_inventory:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "Dispatch packaging inventory "
                            "disappeared during reservation."
                        )
                    )

                available_quantity = (
                    packaging_inventory.quantity
                    - packaging_inventory.reserved_quantity
                )

                if (
                    available_quantity
                    < item["required_quantity"]
                ):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "Dispatch packaging inventory "
                            "changed during reservation."
                        )
                    )

                packaging_inventory.reserved_quantity += (
                    item["required_quantity"]
                )

                reserved_quantity = item["required_quantity"]
                snapshot_status = "reserved"

            snapshot = models.TransferPackagingItem(
                transfer_id=transfer.id,
                packaging_profile_id=(
                    packaging_plan["profile_id"]
                ),
                material_id=item["material_id"],
                material_name_snapshot=item["material_name"],
                material_sku_snapshot=item["material_sku"],
                profile_version_snapshot=(
                    packaging_plan["profile_version"]
                ),
                quantity_per_product=(
                    item["quantity_per_product"]
                ),
                consumption_stage_snapshot=(
                    item["consumption_stage"]
                ),
                rounding_mode_snapshot=(
                    item["rounding_mode"]
                ),
                required_quantity=item["required_quantity"],
                reserved_quantity=reserved_quantity,
                issued_quantity=0,
                received_quantity=0,
                damaged_quantity=0,
                missing_quantity=0,
                status=snapshot_status
            )

            db.add(snapshot)

            packaging_snapshot.append({
                "material_id": item["material_id"],
                "material_sku": item["material_sku"],
                "material_type": item["material_type"],
                "required_quantity": (
                    item["required_quantity"]
                ),
                "consumption_stage": (
                    item["consumption_stage"]
                ),
                "reserved_quantity": reserved_quantity,
                "status": snapshot_status
            })

        _add_audit_log(
            db=db,
            action="TRANSFER_INIT",
            transfer_id=transfer.id,
            product_id=request.product_id,
            user_id=current_user.id,
            details=(
                f"Transfer created by "
                f"{current_user.username}; "
                f"quantity={amount}; "
                f"packaging_profile="
                f"{packaging_plan['profile_id']}; "
                f"profile_version="
                f"{packaging_plan['profile_version']}."
            )
        )

        db.commit()
        db.refresh(transfer)

        return {
            "status": "success",
            "message": (
                "Transfer was created and required "
                "inventory was reserved."
            ),
            "transfer_id": transfer.id,
            "transfer_status": transfer.status,
            "tracking_deadline": transfer.tracking_deadline,
            "packaging_profile_id": (
                packaging_plan["profile_id"]
            ),
            "packaging_profile_version": (
                packaging_plan["profile_version"]
            ),
            "packaging_items": packaging_snapshot
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while creating transfer."
        ) from exc


@router.post("/{transfer_id}/source-approve", status_code=status.HTTP_200_OK)
def source_warehouse_approve(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    transfer = db.query(models.Transfer).filter(
        models.Transfer.id == transfer_id,
        models.Transfer.status
        == models.TransferStatus.PENDING_SOURCE_APPROVAL.value
    ).with_for_update().first()

    if not transfer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Transfer awaiting source approval "
                "was not found."
            )
        )

    _require_source_access(
        current_user,
        transfer.source_warehouse_id
    )

    try:
        if (
            transfer.tracking_deadline
            and datetime.utcnow() > transfer.tracking_deadline
        ):
            _release_reserved_quantity(
                db=db,
                transfer=transfer
            )

            transfer.status = (
                models.TransferStatus.EXPIRED.value
            )
            transfer.updated_at = datetime.utcnow()

            _add_audit_log(
                db=db,
                action="TRANSFER_EXPIRED",
                transfer_id=transfer.id,
                product_id=transfer.product_id,
                user_id=current_user.id,
                details=(
                    "Transfer expired before source approval; "
                    "all reservations were released."
                )
            )

            db.commit()

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "The source-approval deadline "
                    "has expired."
                )
            )

        inventory = _get_inventory_for_update(
            db=db,
            warehouse_id=transfer.source_warehouse_id,
            product_id=transfer.product_id,
            batch_id=transfer.batch_id
        )

        if not inventory:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source product inventory was not found."
            )

        transfer_quantity = _transfer_to_decimal(
            transfer.quantity,
            "transfer_quantity"
        )

        product_quantity = _transfer_to_decimal(
            inventory.quantity,
            "inventory_quantity"
        )

        product_reserved = _transfer_to_decimal(
            inventory.reserved_quantity or 0,
            "reserved_quantity"
        )

        if product_reserved < transfer_quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Reserved product quantity is insufficient "
                    "for this transfer."
                )
            )

        if product_quantity < transfer_quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Physical product inventory is insufficient "
                    "for source approval."
                )
            )

        packaging_items = db.query(
            models.TransferPackagingItem
        ).filter(
            models.TransferPackagingItem.transfer_id
            == transfer.id
        ).order_by(
            models.TransferPackagingItem.material_id.asc()
        ).with_for_update().all()

        product = db.get(
            models.Product,
            transfer.product_id
        )

        if (
            product
            and product.product_type == "finished_good"
            and not packaging_items
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Packaging snapshot is missing for "
                    "this finished-product transfer."
                )
            )

        packaging_result = []

        for item in packaging_items:
            required_quantity = int(
                item.required_quantity
            )

            if required_quantity < 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Invalid required packaging quantity "
                        "in transfer snapshot."
                    )
                )

            stage = (
                item.consumption_stage_snapshot
                or ""
            ).strip().lower()

            if stage == "production":
                # Already consumed during production.
                # It physically travels as part of the product.
                item.reserved_quantity = 0
                item.issued_quantity = required_quantity
                item.status = "issued"

            elif stage == "dispatch":
                reserved_quantity = int(
                    item.reserved_quantity or 0
                )

                if reserved_quantity < required_quantity:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "Reserved dispatch packaging is "
                            "insufficient for source approval."
                        )
                    )

                packaging_inventory = (
                    _get_packaging_inventory_for_update(
                        db=db,
                        warehouse_id=(
                            transfer.source_warehouse_id
                        ),
                        material_id=item.material_id
                    )
                )

                if not packaging_inventory:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "Dispatch packaging inventory "
                            "was not found."
                        )
                    )

                if (
                    packaging_inventory.reserved_quantity
                    < required_quantity
                ):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "Warehouse packaging reservation "
                            "is insufficient."
                        )
                    )

                if (
                    packaging_inventory.quantity
                    < required_quantity
                ):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "Physical dispatch packaging "
                            "inventory is insufficient."
                        )
                    )

                packaging_inventory.quantity -= (
                    required_quantity
                )

                packaging_inventory.reserved_quantity -= (
                    required_quantity
                )

                item.reserved_quantity = 0
                item.issued_quantity = required_quantity
                item.status = "issued"

                db.add(models.PackagingAdjustment(
                    warehouse_id=(
                        transfer.source_warehouse_id
                    ),
                    material_id=item.material_id,
                    quantity=required_quantity,
                    action_type="transfer_issue",
                    reference_type="transfer",
                    reference_id=transfer.id,
                    reason=(
                        f"Dispatch packaging issued for "
                        f"transfer {transfer.id}."
                    ),
                    user_id=current_user.id
                ))

            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Unsupported packaging consumption "
                        f"stage: {stage}"
                    )
                )

            packaging_result.append({
                "material_id": item.material_id,
                "material_sku": (
                    item.material_sku_snapshot
                ),
                "consumption_stage": stage,
                "required_quantity": required_quantity,
                "issued_quantity": item.issued_quantity,
                "status": item.status
            })

        inventory.quantity = float(
            product_quantity - transfer_quantity
        )

        inventory.reserved_quantity = float(
            product_reserved - transfer_quantity
        )

        transfer.status = (
            models.TransferStatus.PENDING_DESTINATION.value
        )
        transfer.source_approved_at = datetime.utcnow()
        transfer.updated_at = datetime.utcnow()

        _add_audit_log(
            db=db,
            action="SOURCE_APPROVE",
            transfer_id=transfer.id,
            product_id=transfer.product_id,
            user_id=current_user.id,
            details=(
                f"Source approved transfer {transfer.id}; "
                f"product quantity={transfer_quantity}; "
                f"packaging items={len(packaging_items)}."
            )
        )

        db.commit()

        return {
            "status": "success",
            "message": (
                "Product and accompanying packaging "
                "were issued from the source warehouse."
            ),
            "transfer_id": transfer.id,
            "transfer_status": transfer.status,
            "packaging_items": packaging_result
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Unexpected error during source approval."
            )
        ) from exc


@router.post("/{transfer_id}/confirm", status_code=status.HTTP_200_OK)
def confirm_transfer_endpoint(
    transfer_id: int,
    request: TransferConfirm,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    transfer = db.query(models.Transfer).filter(
        models.Transfer.id == transfer_id,
        models.Transfer.status
        == models.TransferStatus.PENDING_DESTINATION.value
    ).with_for_update().first()

    if not transfer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Transfer awaiting destination confirmation "
                "was not found."
            )
        )

    _require_destination_access(
        current_user,
        transfer.destination_warehouse_id
    )

    received_amount = _transfer_to_decimal(
        request.received_amount,
        "received_amount"
    )

    sent_amount = _transfer_to_decimal(
        transfer.quantity,
        "transfer_quantity"
    )

    if received_amount < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Received quantity cannot be negative."
        )

    if received_amount > sent_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Received quantity cannot exceed "
                "the issued quantity."
            )
        )

    product = db.get(
        models.Product,
        transfer.product_id
    )

    if not product:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Transferred product was not found."
        )

    if (
        product.product_type == "finished_good"
        and received_amount
        != received_amount.to_integral_value()
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Received finished-product quantity "
                "must be a whole number."
            )
        )

    try:
        destination_warehouse = db.query(
            models.Warehouse
        ).filter(
            models.Warehouse.id
            == transfer.destination_warehouse_id
        ).with_for_update().first()

        if not destination_warehouse:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Destination warehouse was not found."
            )

        packaging_items = db.query(
            models.TransferPackagingItem
        ).filter(
            models.TransferPackagingItem.transfer_id
            == transfer.id
        ).order_by(
            models.TransferPackagingItem.material_id.asc()
        ).with_for_update().all()

        if (
            product.product_type == "finished_good"
            and not packaging_items
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Packaging snapshot is missing for "
                    "this finished-product transfer."
                )
            )

        packaging_result = []

        for item in packaging_items:
            stage = (
                item.consumption_stage_snapshot
                or ""
            ).strip().lower()

            if stage not in {"production", "dispatch"}:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Unsupported packaging consumption "
                        f"stage: {stage}"
                    )
                )

            issued_quantity = int(
                item.issued_quantity or 0
            )

            if received_amount == 0:
                calculated_received = 0
            else:
                calculated_received = (
                    _calculate_transfer_packaging_quantity(
                        received_amount,
                        item.quantity_per_product,
                        item.rounding_mode_snapshot
                    )
                )

            received_packaging = min(
                issued_quantity,
                calculated_received
            )

            missing_packaging = max(
                0,
                issued_quantity - received_packaging
            )

            item.received_quantity = received_packaging
            item.missing_quantity = missing_packaging
            item.damaged_quantity = 0

            if missing_packaging > 0:
                item.status = "disputed"
            else:
                item.status = "received"

            if (
                stage == "dispatch"
                and received_packaging > 0
            ):
                destination_packaging_inventory = (
                    _get_packaging_inventory_for_update(
                        db=db,
                        warehouse_id=(
                            transfer.destination_warehouse_id
                        ),
                        material_id=item.material_id
                    )
                )

                if destination_packaging_inventory:
                    destination_packaging_inventory.quantity += (
                        received_packaging
                    )
                else:
                    destination_packaging_inventory = (
                        models.PackagingInventory(
                            warehouse_id=(
                                transfer.destination_warehouse_id
                            ),
                            material_id=item.material_id,
                            quantity=received_packaging,
                            reserved_quantity=0
                        )
                    )

                    db.add(destination_packaging_inventory)

                db.add(models.PackagingAdjustment(
                    warehouse_id=(
                        transfer.destination_warehouse_id
                    ),
                    material_id=item.material_id,
                    quantity=received_packaging,
                    action_type="transfer_receive",
                    reference_type="transfer",
                    reference_id=transfer.id,
                    reason=(
                        f"Dispatch packaging received for "
                        f"transfer {transfer.id}."
                    ),
                    user_id=current_user.id
                ))

            packaging_result.append({
                "material_id": item.material_id,
                "material_sku": (
                    item.material_sku_snapshot
                ),
                "consumption_stage": stage,
                "issued_quantity": issued_quantity,
                "received_quantity": received_packaging,
                "missing_quantity": missing_packaging,
                "status": item.status
            })

        if received_amount > 0:
            receiver_inventory = _get_inventory_for_update(
                db=db,
                warehouse_id=(
                    transfer.destination_warehouse_id
                ),
                product_id=transfer.product_id,
                batch_id=transfer.batch_id
            )

            if receiver_inventory:
                receiver_inventory.quantity = float(
                    _transfer_to_decimal(
                        receiver_inventory.quantity,
                        "destination_inventory_quantity"
                    )
                    + received_amount
                )
            else:
                receiver_inventory = models.Inventory(
                    warehouse_id=(
                        transfer.destination_warehouse_id
                    ),
                    product_id=transfer.product_id,
                    batch_id=transfer.batch_id,
                    quantity=float(received_amount),
                    reserved_quantity=0.0
                )

                db.add(receiver_inventory)

        missing_product = sent_amount - received_amount
        now = datetime.utcnow()

        if missing_product > 0:
            dispute = models.Dispute(
                transfer_id=transfer.id,
                reported_quantity=float(received_amount),
                missing_amount=float(missing_product),
                status="OPEN",
                reason=(
                    "Product shortage during destination "
                    "confirmation."
                )
            )

            db.add(dispute)

            transfer.status = (
                models.TransferStatus.DISPUTED.value
            )
            transfer.dispute_deadline = (
                now + timedelta(hours=24)
            )
            transfer.updated_at = now

            ticket = models.TransferTicket(
                transfer_id=transfer.id,
                status=models.TicketStatus.OPEN.value,
                title=f"Transfer discrepancy {transfer.id}"
            )

            db.add(ticket)
            db.flush()

            db.add(models.TicketMessage(
                ticket_id=ticket.id,
                sender_role="admin",
                sender_name="system",
                message_text=(
                    f"Transfer discrepancy registered. "
                    f"Issued product quantity: {sent_amount}; "
                    f"received product quantity: "
                    f"{received_amount}; "
                    f"missing product quantity: "
                    f"{missing_product}."
                )
            ))

            _add_audit_log(
                db=db,
                action="DISPUTE_CREATED",
                transfer_id=transfer.id,
                product_id=transfer.product_id,
                user_id=current_user.id,
                details=(
                    f"Destination reported shortage for "
                    f"transfer {transfer.id}; "
                    f"missing product={missing_product}."
                )
            )

            db.commit()

            return {
                "status": "disputed",
                "message": (
                    "Received quantities were registered "
                    "and a discrepancy ticket was created."
                ),
                "transfer_id": transfer.id,
                "ticket_id": ticket.id,
                "missing_amount": float(missing_product),
                "packaging_items": packaging_result
            }

        transfer.status = (
            models.TransferStatus.CONFIRMED.value
        )
        transfer.updated_at = now

        _add_audit_log(
            db=db,
            action="CONFIRM_SUCCESS",
            transfer_id=transfer.id,
            product_id=transfer.product_id,
            user_id=current_user.id,
            details=(
                f"Destination confirmed complete receipt "
                f"of transfer {transfer.id}; "
                f"product quantity={received_amount}; "
                f"packaging items={len(packaging_items)}."
            )
        )

        db.commit()

        return {
            "status": "success",
            "message": (
                "Product and accompanying packaging "
                "were received successfully."
            ),
            "transfer_id": transfer.id,
            "transfer_status": transfer.status,
            "received_amount": float(received_amount),
            "packaging_items": packaging_result
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Unexpected error during destination "
                "confirmation."
            )
        ) from exc


@router.post("/tickets/{ticket_id}/messages", status_code=status.HTTP_201_CREATED)
def send_ticket_message(
    ticket_id: int,
    request: TicketMessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    ticket = db.query(models.TransferTicket).filter(
        models.TransferTicket.id == ticket_id
    ).with_for_update().first()

    if not ticket:
        raise HTTPException(status_code=404, detail="تیکت یافت نشد.")

    transfer = db.query(models.Transfer).filter(
        models.Transfer.id == ticket.transfer_id
    ).first()

    if not transfer or not _can_access_transfer(current_user, transfer):
        raise HTTPException(status_code=403, detail="شما مجاز به گفتگو در این تیکت نیستید.")

    cleaned_message = request.message_text.strip()

    if not cleaned_message:
        raise HTTPException(status_code=400, detail="متن پیام نمی‌تواند خالی باشد.")

    if len(cleaned_message) > 2000:
        raise HTTPException(status_code=400, detail="متن پیام بیش از حد مجاز است.")

    try:
        if (
            ticket.status == models.TicketStatus.OPEN.value
            and transfer.dispute_deadline
            and datetime.utcnow() > transfer.dispute_deadline
        ):
            ticket.status = models.TicketStatus.ESCALATED_TO_ADMIN.value

        sender_role = "admin"
        if current_user.role != "admin":
            sender_role = (
                "source_warehouse"
                if current_user.warehouse_id == transfer.source_warehouse_id
                else "destination_warehouse"
            )

        db.add(models.TicketMessage(
            ticket_id=ticket.id,
            sender_role=sender_role,
            sender_name=current_user.username,
            message_text=cleaned_message
        ))

        ticket.updated_at = datetime.utcnow()
        db.commit()

        return {
            "status": "success",
            "ticket_status": ticket.status,
            "message": "پیام ثبت شد."
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="???? ????? ????.")


@router.get("/tickets/{ticket_id}/history")
def get_ticket_chat_history(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    ticket = db.query(models.TransferTicket).filter(
        models.TransferTicket.id == ticket_id
    ).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="تیکت یافت نشد.")

    transfer = db.query(models.Transfer).filter(
        models.Transfer.id == ticket.transfer_id
    ).first()

    if not transfer or not _can_access_transfer(current_user, transfer):
        raise HTTPException(status_code=403, detail="شما به این تیکت دسترسی ندارید.")

    messages = db.query(models.TicketMessage).filter(
        models.TicketMessage.ticket_id == ticket_id
    ).order_by(models.TicketMessage.created_at.asc()).all()

    return {
        "ticket_id": ticket.id,
        "title": ticket.title,
        "status": ticket.status,
        "chat_history": [
            {
                "sender": msg.sender_role,
                "name": msg.sender_name or "system",
                "text": msg.message_text,
                "time": msg.created_at.strftime("%Y-%m-%d %H:%M:%S") if msg.created_at else None
            }
            for msg in messages
        ]
    }


@router.post("/disputes/{dispute_id}/resolve", status_code=status.HTTP_200_OK)
def resolve_dispute(
    dispute_id: int,
    request: DisputeResolveRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an administrator can resolve disputes."
        )

    action = (request.action_taken or "").strip().lower()
    notes = (request.resolution_notes or "").strip()

    allowed_actions = {
        "accept_shortage",
        "receive_missing",
    }

    if action not in allowed_actions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Unsupported dispute action.",
                "allowed_actions": sorted(allowed_actions)
            }
        )

    if not notes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resolution notes are required."
        )

    dispute = db.query(models.Dispute).filter(
        models.Dispute.id == dispute_id
    ).with_for_update().first()

    if not dispute:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dispute was not found."
        )

    if dispute.status == "RESOLVED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This dispute has already been resolved."
        )

    transfer = db.query(models.Transfer).filter(
        models.Transfer.id == dispute.transfer_id
    ).with_for_update().first()

    if not transfer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The related transfer was not found."
        )

    if transfer.status != models.TransferStatus.DISPUTED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The related transfer is not in disputed status."
        )

    try:
        packaging_items = db.query(
            models.TransferPackagingItem
        ).filter(
            models.TransferPackagingItem.transfer_id
            == transfer.id
        ).order_by(
            models.TransferPackagingItem.material_id.asc()
        ).with_for_update().all()

        product_inventory_added = 0.0
        dispatch_packaging_added = []

        if action == "receive_missing":
            missing_product = _transfer_to_decimal(
                dispute.missing_amount or 0,
                "missing_product_quantity"
            )

            if missing_product <= 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="There is no missing product quantity to receive."
                )

            destination_inventory = _get_inventory_for_update(
                db=db,
                warehouse_id=transfer.destination_warehouse_id,
                product_id=transfer.product_id,
                batch_id=transfer.batch_id
            )

            if destination_inventory:
                destination_inventory.quantity = float(
                    _transfer_to_decimal(
                        destination_inventory.quantity,
                        "destination_inventory_quantity"
                    )
                    + missing_product
                )
            else:
                destination_inventory = models.Inventory(
                    warehouse_id=transfer.destination_warehouse_id,
                    product_id=transfer.product_id,
                    batch_id=transfer.batch_id,
                    quantity=float(missing_product),
                    reserved_quantity=0.0
                )
                db.add(destination_inventory)

            product_inventory_added = float(missing_product)

            for item in packaging_items:
                missing_packaging = int(
                    item.missing_quantity or 0
                )

                if missing_packaging <= 0:
                    continue

                stage = (
                    item.consumption_stage_snapshot
                    or ""
                ).strip().lower()

                if stage == "dispatch":
                    destination_packaging_inventory = (
                        _get_packaging_inventory_for_update(
                            db=db,
                            warehouse_id=(
                                transfer.destination_warehouse_id
                            ),
                            material_id=item.material_id
                        )
                    )

                    if destination_packaging_inventory:
                        destination_packaging_inventory.quantity += (
                            missing_packaging
                        )
                    else:
                        destination_packaging_inventory = (
                            models.PackagingInventory(
                                warehouse_id=(
                                    transfer.destination_warehouse_id
                                ),
                                material_id=item.material_id,
                                quantity=missing_packaging,
                                reserved_quantity=0
                            )
                        )
                        db.add(destination_packaging_inventory)

                    db.add(models.PackagingAdjustment(
                        warehouse_id=(
                            transfer.destination_warehouse_id
                        ),
                        material_id=item.material_id,
                        quantity=missing_packaging,
                        action_type="dispute_receive",
                        reference_type="transfer",
                        reference_id=transfer.id,
                        reason=(
                            "Missing dispatch packaging received "
                            f"during resolution of dispute {dispute.id}."
                        ),
                        user_id=current_user.id
                    ))

                    dispatch_packaging_added.append({
                        "material_id": item.material_id,
                        "material_sku": (
                            item.material_sku_snapshot
                        ),
                        "quantity": missing_packaging
                    })

                elif stage != "production":
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "Unsupported packaging consumption "
                            f"stage: {stage}"
                        )
                    )

                item.received_quantity += missing_packaging
                item.missing_quantity = 0
                item.status = "received"

            dispute.reported_quantity = float(
                _transfer_to_decimal(
                    dispute.reported_quantity,
                    "reported_quantity"
                )
                + missing_product
            )
            dispute.missing_amount = 0.0

        dispute.status = "RESOLVED"
        dispute.reason = (
            f"action={action} | notes={notes}"
        )

        transfer.status = (
            models.TransferStatus.CONFIRMED.value
        )
        transfer.updated_at = datetime.utcnow()

        ticket = db.query(
            models.TransferTicket
        ).filter(
            models.TransferTicket.transfer_id == transfer.id
        ).with_for_update().first()

        if ticket:
            ticket.status = (
                models.TicketStatus.RESOLVED.value
            )
            ticket.updated_at = datetime.utcnow()

            db.add(models.TicketMessage(
                ticket_id=ticket.id,
                sender_role="admin",
                sender_name=current_user.username,
                message_text=(
                    f"Dispute resolved. Action: {action}. "
                    f"Notes: {notes}"
                )
            ))

        _add_audit_log(
            db=db,
            action="DISPUTE_RESOLVED",
            transfer_id=transfer.id,
            product_id=transfer.product_id,
            user_id=current_user.id,
            details=(
                f"Dispute {dispute.id} resolved by "
                f"{current_user.username}; action={action}; "
                f"product_added={product_inventory_added}."
            )
        )

        db.commit()

        return {
            "status": "success",
            "message": "Dispute was resolved successfully.",
            "transfer_id": transfer.id,
            "transfer_status": transfer.status,
            "action_taken": action,
            "confirmed_quantity": dispute.reported_quantity,
            "remaining_missing_quantity": (
                dispute.missing_amount
            ),
            "product_inventory_added": (
                product_inventory_added
            ),
            "dispatch_packaging_added": (
                dispatch_packaging_added
            )
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while resolving dispute."
        ) from exc


@router.get("/disputes/open", response_model=List[dict])
def get_open_disputes(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="این گزارش فقط برای مدیر ارشد است.")

    disputes = db.query(models.Dispute).filter(
        models.Dispute.status == "OPEN"
    ).order_by(models.Dispute.created_at.desc()).all()

    result = []
    for dispute in disputes:
        transfer = db.query(models.Transfer).filter(
            models.Transfer.id == dispute.transfer_id
        ).first()

        result.append({
            "dispute_id": dispute.id,
            "transfer_id": dispute.transfer_id,
            "source_warehouse_id": transfer.source_warehouse_id if transfer else None,
            "destination_warehouse_id": transfer.destination_warehouse_id if transfer else None,
            "product_id": transfer.product_id if transfer else None,
            "batch_id": transfer.batch_id if transfer else None,
            "reported_quantity": dispute.reported_quantity,
            "missing_amount": dispute.missing_amount,
            "status": dispute.status,
            "created_at": dispute.created_at.strftime("%Y-%m-%d %H:%M:%S") if dispute.created_at else None
        })

    return result


@router.get("/my-warehouse/{warehouse_id}")
def get_my_warehouse_transfers(
    warehouse_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if (
        not _is_admin(current_user)
        and current_user.warehouse_id != warehouse_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You are not allowed to view transfers "
                "for this warehouse."
            )
        )

    transfers = db.query(models.Transfer).filter(
        (
            models.Transfer.source_warehouse_id
            == warehouse_id
        )
        |
        (
            models.Transfer.destination_warehouse_id
            == warehouse_id
        )
    ).order_by(
        models.Transfer.created_at.desc()
    ).all()

    result = []

    for transfer in transfers:
        packaging_items = sorted(
            transfer.packaging_items or [],
            key=lambda item: item.id or 0
        )

        result.append({
            "transfer_id": transfer.id,
            "source_warehouse_id": (
                transfer.source_warehouse_id
            ),
            "destination_warehouse_id": (
                transfer.destination_warehouse_id
            ),
            "product_id": transfer.product_id,
            "batch_id": transfer.batch_id,
            "quantity": transfer.quantity,
            "status": transfer.status,
            "description": transfer.description,
            "role_in_transfer": (
                "sender"
                if transfer.source_warehouse_id
                == warehouse_id
                else "receiver"
            ),
            "created_at": (
                transfer.created_at.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                if transfer.created_at
                else None
            ),
            "packaging_items": [
                {
                    "id": item.id,
                    "material_id": item.material_id,
                    "material_name": (
                        item.material_name_snapshot
                    ),
                    "material_sku": (
                        item.material_sku_snapshot
                    ),
                    "profile_id": (
                        item.packaging_profile_id
                    ),
                    "profile_version": (
                        item.profile_version_snapshot
                    ),
                    "quantity_per_product": float(
                        item.quantity_per_product
                    ),
                    "consumption_stage": (
                        item.consumption_stage_snapshot
                    ),
                    "rounding_mode": (
                        item.rounding_mode_snapshot
                    ),
                    "required_quantity": (
                        item.required_quantity
                    ),
                    "reserved_quantity": (
                        item.reserved_quantity
                    ),
                    "issued_quantity": (
                        item.issued_quantity
                    ),
                    "received_quantity": (
                        item.received_quantity
                    ),
                    "damaged_quantity": (
                        item.damaged_quantity
                    ),
                    "missing_quantity": (
                        item.missing_quantity
                    ),
                    "status": item.status
                }
                for item in packaging_items
            ]
        })

    return {
        "warehouse_id": warehouse_id,
        "total_transfers_accessible": len(result),
        "transfers": result
    }

