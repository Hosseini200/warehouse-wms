# app/api/admin_router.py
from typing import List, Optional
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.domain import models
from app.api.transfer_router import get_current_user


router = APIRouter(
    prefix="/admin-panel",
    tags=["Admin - Master Data Management"]
)


def require_admin(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="فقط مدیر ارشد مجاز به انجام این عملیات است."
        )
    return current_user


class WarehouseCreate(BaseModel):
    name: str
    location: Optional[str] = None
    manager_name: Optional[str] = None


class ProductCreate(BaseModel):
    name: str
    sku: str
    base_unit: str
    is_composite: bool = False
    product_type: Optional[str] = "finished_good"
    unit_weight_grams: Optional[float] = 0.0
    packaging_material_id: Optional[int] = None


class PackagingMaterialCreate(BaseModel):
    name: str
    sku: str
    capacity_grams: Optional[float] = None
    description: Optional[str] = None
    material_type: str = "container"


class PackagingProfileItemCreate(BaseModel):
    material_id: int
    quantity_per_product: float
    consumption_stage: str = "production"
    rounding_mode: str = "exact"
    is_primary: bool = False


class PackagingProfileCreate(BaseModel):
    product_id: int
    name: str
    items: List[PackagingProfileItemCreate]

class InventorySetRequest(BaseModel):
    warehouse_id: int
    product_id: int
    batch_id: int
    quantity: float
    reserved_quantity: Optional[float] = 0.0

class PackagingInventorySetRequest(BaseModel):
    warehouse_id: int
    material_id: int
    quantity: int
    reserved_quantity: Optional[int] = 0
    reason: Optional[str] = None


class PackagingAdjustmentRequest(BaseModel):
    warehouse_id: int
    material_id: int
    quantity: int
    action_type: str  # damaged, lost, manual_decrease, manual_increase
    reason: Optional[str] = None

class RecipeComponent(BaseModel):
    ingredient_id: int
    percentage: float


class RecipeCreate(BaseModel):
    final_product_id: int
    components: List[RecipeComponent]


@router.post("/warehouses", status_code=status.HTTP_201_CREATED)
def create_warehouse(
    request: WarehouseCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    if not request.name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="نام انبار الزامی است."
        )

    existing = db.query(models.Warehouse).filter(
        models.Warehouse.name == request.name.strip()
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="انباری با این نام از قبل وجود دارد."
        )

    new_wh = models.Warehouse(
        name=request.name.strip(),
        location=request.location,
        manager_name=request.manager_name,
        is_active=True
    )

    try:
        db.add(new_wh)
        db.commit()
        db.refresh(new_wh)

        return {
            "message": f"انبار '{new_wh.name}' با موفقیت ثبت شد.",
            "warehouse_id": new_wh.id
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="???? ????? ????."
        )


@router.post("/packaging-materials", status_code=status.HTTP_201_CREATED)
def create_packaging_material(
    request: PackagingMaterialCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    material_type = (request.material_type or "container").strip().lower()

    allowed_material_types = {
        "container",
        "lid",
        "label",
        "inner_box",
        "carton",
        "pallet",
        "other"
    }

    if material_type not in allowed_material_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid packaging material type."
        )

    if request.capacity_grams is not None and request.capacity_grams <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Packaging capacity must be greater than zero."
        )

    if not request.name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="نام ملزومات بسته‌بندی الزامی است."
        )

    if not request.sku.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="کد ملزومات بسته‌بندی الزامی است."
        )

    existing = db.query(models.PackagingMaterial).filter(
        models.PackagingMaterial.sku == request.sku.strip()
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ملزومات بسته‌بندی با این کد از قبل وجود دارد."
        )

    new_material = models.PackagingMaterial(
        name=request.name.strip(),
        sku=request.sku.strip(),
        capacity_grams=request.capacity_grams,
        description=request.description,
        material_type=material_type
    )

    try:
        db.add(new_material)
        db.commit()
        db.refresh(new_material)

        return {
            "message": f"ملزومات بسته‌بندی '{new_material.name}' ثبت شد.",
            "material_id": new_material.id
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="???? ????? ????."
        )


@router.get("/packaging-materials")
def get_packaging_materials(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    materials = db.query(
        models.PackagingMaterial
    ).order_by(
        models.PackagingMaterial.id.asc()
    ).all()

    return [
        {
            "id": material.id,
            "name": material.name,
            "sku": material.sku,
            "capacity_grams": material.capacity_grams,
            "description": material.description,
            "material_type": material.material_type
        }
        for material in materials
    ]

@router.post("/products", status_code=status.HTTP_201_CREATED)
def create_product(
    request: ProductCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    try:
        name = request.name.strip()
        sku = request.sku.strip()
        base_unit = request.base_unit.strip()

        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="نام محصول الزامی است."
            )

        if not sku:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="کد کالا الزامی است."
            )

        if not base_unit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="واحد پایه الزامی است."
            )

        existing = db.query(models.Product).filter(
            models.Product.sku == sku
        ).first()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="محصولی با این کد کالا از قبل وجود دارد."
            )

        if request.packaging_material_id:
            material = db.query(models.PackagingMaterial).filter(
                models.PackagingMaterial.id == request.packaging_material_id
            ).first()

            if not material:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="ملزومات بسته‌بندی انتخاب‌شده یافت نشد."
                )

        new_prod = models.Product(
            name=name,
            sku=sku,
            base_unit=base_unit,
            is_composite=bool(request.is_composite),
            product_type=request.product_type or "finished_good",
            unit_weight_grams=request.unit_weight_grams or 0.0,
            packaging_material_id=request.packaging_material_id
        )

        db.add(new_prod)
        db.commit()
        db.refresh(new_prod)

        db.add(models.AuditLog(
            action="PRODUCT_CREATE",
            product_id=new_prod.id,
            user_id=current_user.id,
            details=f"محصول {new_prod.name} با کد {new_prod.sku} ساخته شد."
        ))
        db.commit()

        return {
            "message": f"محصول '{new_prod.name}' با موفقیت تعریف شد.",
            "product_id": new_prod.id
        }

    except HTTPException:
        raise

    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"خطا در ثبت محصول. احتمالاً کد کالا تکراری است یا فیلد اجباری ناقص است. جزئیات: {str(e.orig)}"
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="???? ????? ????."
        )


@router.get("/products")
def get_products(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    products = db.query(models.Product).order_by(models.Product.id.asc()).all()

    return [
        {
            "id": p.id,
            "name": p.name,
            "sku": p.sku,
            "base_unit": p.base_unit,
            "is_composite": p.is_composite,
            "product_type": p.product_type,
            "unit_weight_grams": p.unit_weight_grams,
            "packaging_material_id": p.packaging_material_id
        }
        for p in products
    ]


@router.post("/recipes", status_code=status.HTTP_201_CREATED)
def create_product_recipe(
    request: RecipeCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    final_product = db.query(models.Product).filter(
        models.Product.id == request.final_product_id
    ).first()

    if not final_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="محصول نهایی یافت نشد."
        )

    total_percentage = sum(c.percentage for c in request.components)

    if abs(total_percentage - 100.0) > 0.01:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"مجموع درصدهای فرمولاسیون باید دقیقاً ۱۰۰ باشد. مقدار فعلی: {total_percentage}"
        )

    for component in request.components:
        ingredient = db.query(models.Product).filter(
            models.Product.id == component.ingredient_id
        ).first()

        if not ingredient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ماده اولیه با شناسه {component.ingredient_id} یافت نشد."
            )

    try:
        db.query(models.Recipe).filter(
            models.Recipe.final_product_id == request.final_product_id
        ).delete()

        for component in request.components:
            db_recipe = models.Recipe(
                final_product_id=request.final_product_id,
                ingredient_id=component.ingredient_id,
                percentage=component.percentage
            )
            db.add(db_recipe)

        final_product.is_composite = True
        db.commit()

        return {
            "message": "فرمولاسیون محصول با موفقیت ثبت شد."
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="???? ????? ????."
        )

@router.post("/packaging-inventory/set", status_code=status.HTTP_200_OK)
def set_packaging_inventory_quantity(
    request: PackagingInventorySetRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    if request.quantity < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="موجودی بسته‌بندی نمی‌تواند منفی باشد."
        )

    if request.reserved_quantity is None:
        request.reserved_quantity = 0

    if request.reserved_quantity < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="موجودی رزروشده بسته‌بندی نمی‌تواند منفی باشد."
        )

    if request.reserved_quantity > request.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="موجودی رزروشده بسته‌بندی نمی‌تواند بیشتر از موجودی کل باشد."
        )

    warehouse = db.query(models.Warehouse).filter(
        models.Warehouse.id == request.warehouse_id,
        models.Warehouse.is_active == True
    ).first()

    if not warehouse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="انبار فعال یافت نشد."
        )

    material = db.query(models.PackagingMaterial).filter(
        models.PackagingMaterial.id == request.material_id
    ).first()

    if not material:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ملزومات بسته‌بندی یافت نشد."
        )

    try:
        packaging_inventory = db.query(models.PackagingInventory).filter(
            models.PackagingInventory.warehouse_id == request.warehouse_id,
            models.PackagingInventory.material_id == request.material_id
        ).with_for_update().first()

        if packaging_inventory:
            packaging_inventory.quantity = request.quantity
            packaging_inventory.reserved_quantity = request.reserved_quantity
        else:
            packaging_inventory = models.PackagingInventory(
                warehouse_id=request.warehouse_id,
                material_id=request.material_id,
                quantity=request.quantity,
                reserved_quantity=request.reserved_quantity
            )
            db.add(packaging_inventory)

        db.add(models.PackagingAdjustment(
            warehouse_id=request.warehouse_id,
            material_id=request.material_id,
            quantity=request.quantity,
            action_type="manual_set",
            reference_type="admin_adjustment",
            reference_id=None,
            reason=request.reason or "تنظیم دستی موجودی بسته‌بندی توسط مدیر",
            user_id=current_user.id
        ))

        db.add(models.AuditLog(
            action="PACKAGING_INVENTORY_SET",
            user_id=current_user.id,
            details=(
                f"موجودی بسته‌بندی {request.material_id} در انبار "
                f"{request.warehouse_id} روی {request.quantity} تنظیم شد."
            )
        ))

        db.commit()
        db.refresh(packaging_inventory)

        return {
            "message": "موجودی بسته‌بندی با موفقیت ثبت/به‌روزرسانی شد.",
            "packaging_inventory_id": packaging_inventory.id,
            "warehouse_id": packaging_inventory.warehouse_id,
            "material_id": packaging_inventory.material_id,
            "quantity": packaging_inventory.quantity,
            "reserved_quantity": packaging_inventory.reserved_quantity
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="???? ????? ????."
        )

@router.post("/packaging-inventory/adjust", status_code=status.HTTP_200_OK)
def adjust_packaging_inventory(
    request: PackagingAdjustmentRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    allowed_actions = {
        "damaged",
        "lost",
        "manual_decrease",
        "manual_increase"
    }

    if request.action_type not in allowed_actions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="نوع عملیات بسته‌بندی معتبر نیست."
        )

    if request.quantity <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="تعداد باید بزرگتر از صفر باشد."
        )

    warehouse = db.query(models.Warehouse).filter(
        models.Warehouse.id == request.warehouse_id,
        models.Warehouse.is_active == True
    ).first()

    if not warehouse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="انبار فعال یافت نشد."
        )

    material = db.query(models.PackagingMaterial).filter(
        models.PackagingMaterial.id == request.material_id
    ).first()

    if not material:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ملزومات بسته‌بندی یافت نشد."
        )

    try:
        packaging_inventory = db.query(models.PackagingInventory).filter(
            models.PackagingInventory.warehouse_id == request.warehouse_id,
            models.PackagingInventory.material_id == request.material_id
        ).with_for_update().first()

        if not packaging_inventory:
            if request.action_type == "manual_increase":
                packaging_inventory = models.PackagingInventory(
                    warehouse_id=request.warehouse_id,
                    material_id=request.material_id,
                    quantity=0,
                    reserved_quantity=0
                )
                db.add(packaging_inventory)
                db.flush()
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="برای این ملزومات بسته‌بندی در این انبار موجودی ثبت نشده است."
                )

        free_quantity = packaging_inventory.quantity - packaging_inventory.reserved_quantity

        if request.action_type in {"damaged", "lost", "manual_decrease"}:
            if free_quantity < request.quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"موجودی آزاد بسته‌بندی کافی نیست. موجودی آزاد: {free_quantity}"
                )

            packaging_inventory.quantity -= request.quantity

        elif request.action_type == "manual_increase":
            packaging_inventory.quantity += request.quantity

        db.add(models.PackagingAdjustment(
            warehouse_id=request.warehouse_id,
            material_id=request.material_id,
            quantity=request.quantity,
            action_type=request.action_type,
            reference_type="admin_adjustment",
            reference_id=None,
            reason=request.reason,
            user_id=current_user.id
        ))

        db.add(models.AuditLog(
            action=f"PACKAGING_{request.action_type.upper()}",
            user_id=current_user.id,
            details=(
                f"عملیات {request.action_type} برای ملزومات بسته‌بندی "
                f"{request.material_id} در انبار {request.warehouse_id} "
                f"به تعداد {request.quantity} ثبت شد."
            )
        ))

        db.commit()
        db.refresh(packaging_inventory)

        return {
            "message": "عملیات بسته‌بندی با موفقیت ثبت شد.",
            "warehouse_id": packaging_inventory.warehouse_id,
            "material_id": packaging_inventory.material_id,
            "quantity": packaging_inventory.quantity,
            "reserved_quantity": packaging_inventory.reserved_quantity,
            "action_type": request.action_type,
            "adjusted_quantity": request.quantity
        }

    except HTTPException:
        db.rollback()
        raise

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="???? ????? ????."
        )
    

@router.post("/inventory/set", status_code=status.HTTP_200_OK)
def set_inventory_quantity(
    request: InventorySetRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    if request.quantity < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="موجودی نمی‌تواند منفی باشد."
        )

    if request.reserved_quantity is None:
        request.reserved_quantity = 0.0

    if request.reserved_quantity < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="موجودی رزروشده نمی‌تواند منفی باشد."
        )

    if request.reserved_quantity > request.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="موجودی رزروشده نمی‌تواند بیشتر از موجودی کل باشد."
        )

    warehouse = db.query(models.Warehouse).filter(
        models.Warehouse.id == request.warehouse_id,
        models.Warehouse.is_active == True
    ).first()

    if not warehouse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="انبار یافت نشد یا غیرفعال است."
        )

    product = db.query(models.Product).filter(
        models.Product.id == request.product_id
    ).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="محصول یافت نشد."
        )

    batch = db.query(models.Batch).filter(
        models.Batch.id == request.batch_id,
        models.Batch.product_id == request.product_id
    ).first()

    if not batch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="بچ انتخاب‌شده با محصول انتخاب‌شده همخوانی ندارد."
        )

    try:
        inventory = db.query(models.Inventory).filter(
            models.Inventory.warehouse_id == request.warehouse_id,
            models.Inventory.product_id == request.product_id,
            models.Inventory.batch_id == request.batch_id
        ).with_for_update().first()

        if inventory:
            inventory.quantity = request.quantity
            inventory.reserved_quantity = request.reserved_quantity
        else:
            inventory = models.Inventory(
                warehouse_id=request.warehouse_id,
                product_id=request.product_id,
                batch_id=request.batch_id,
                quantity=request.quantity,
                reserved_quantity=request.reserved_quantity
            )
            db.add(inventory)

        db.add(models.AuditLog(
            action="INVENTORY_SET",
            product_id=request.product_id,
            user_id=current_user.id,
            details=f"موجودی کالا {request.product_id} در انبار {request.warehouse_id} روی {request.quantity} تنظیم شد."
        ))

        db.commit()
        db.refresh(inventory)

        return {
            "message": "موجودی با موفقیت ثبت/به‌روزرسانی شد.",
            "inventory_id": inventory.id,
            "warehouse_id": inventory.warehouse_id,
            "product_id": inventory.product_id,
            "batch_id": inventory.batch_id,
            "quantity": inventory.quantity,
            "reserved_quantity": inventory.reserved_quantity
        }

    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"خطا در ثبت موجودی. احتمالاً رکورد تکراری یا ناسازگار است. جزئیات: {str(e.orig)}"
        )

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="???? ????? ????."
        )

def _serialize_packaging_profile(profile):
    return {
        "id": profile.id,
        "product_id": profile.product_id,
        "product_name": (
            profile.product.name
            if profile.product is not None
            else None
        ),
        "product_sku": (
            profile.product.sku
            if profile.product is not None
            else None
        ),
        "name": profile.name,
        "version": profile.version,
        "is_active": profile.is_active,
        "effective_from": profile.effective_from,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
        "items": [
            {
                "id": item.id,
                "material_id": item.material_id,
                "material_name": (
                    item.material.name
                    if item.material is not None
                    else None
                ),
                "material_sku": (
                    item.material.sku
                    if item.material is not None
                    else None
                ),
                "material_type": (
                    item.material.material_type
                    if item.material is not None
                    else item.component_type
                ),
                "capacity_grams": (
                    item.material.capacity_grams
                    if item.material is not None
                    else None
                ),
                "quantity_per_product": float(
                    item.quantity_per_product
                ),
                "component_type": item.component_type,
                "consumption_stage": item.consumption_stage,
                "rounding_mode": item.rounding_mode,
                "is_primary": item.is_primary
            }
            for item in sorted(
                profile.items,
                key=lambda row: row.id or 0
            )
        ]
    }


@router.get("/packaging-dashboard")
def get_packaging_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    warehouses = db.query(
        models.Warehouse
    ).filter(
        models.Warehouse.is_active == True
    ).order_by(
        models.Warehouse.id.asc()
    ).all()

    products = db.query(
        models.Product
    ).order_by(
        models.Product.id.asc()
    ).all()

    materials = db.query(
        models.PackagingMaterial
    ).order_by(
        models.PackagingMaterial.id.asc()
    ).all()

    inventories = db.query(
        models.PackagingInventory
    ).order_by(
        models.PackagingInventory.warehouse_id.asc(),
        models.PackagingInventory.material_id.asc()
    ).all()

    profiles = db.query(
        models.PackagingProfile
    ).order_by(
        models.PackagingProfile.product_id.asc(),
        models.PackagingProfile.version.desc()
    ).all()

    warehouse_names = {
        warehouse.id: warehouse.name
        for warehouse in warehouses
    }

    material_names = {
        material.id: material
        for material in materials
    }

    active_profiles_by_product = {
        profile.product_id: profile
        for profile in profiles
        if profile.is_active
    }

    return {
        "warehouses": [
            {
                "id": warehouse.id,
                "name": warehouse.name,
                "location": warehouse.location
            }
            for warehouse in warehouses
        ],
        "products": [
            {
                "id": product.id,
                "name": product.name,
                "sku": product.sku,
                "base_unit": product.base_unit,
                "unit_weight_grams": (
                    product.unit_weight_grams
                ),
                "is_composite": product.is_composite,
                "active_packaging_profile_id": (
                    active_profiles_by_product[
                        product.id
                    ].id
                    if product.id
                    in active_profiles_by_product
                    else None
                ),
                "active_packaging_profile_version": (
                    active_profiles_by_product[
                        product.id
                    ].version
                    if product.id
                    in active_profiles_by_product
                    else None
                )
            }
            for product in products
        ],
        "materials": [
            {
                "id": material.id,
                "name": material.name,
                "sku": material.sku,
                "capacity_grams": (
                    material.capacity_grams
                ),
                "description": material.description,
                "material_type": material.material_type
            }
            for material in materials
        ],
        "inventories": [
            {
                "id": inventory.id,
                "warehouse_id": inventory.warehouse_id,
                "warehouse_name": warehouse_names.get(
                    inventory.warehouse_id
                ),
                "material_id": inventory.material_id,
                "material_name": (
                    material_names[
                        inventory.material_id
                    ].name
                    if inventory.material_id
                    in material_names
                    else None
                ),
                "material_sku": (
                    material_names[
                        inventory.material_id
                    ].sku
                    if inventory.material_id
                    in material_names
                    else None
                ),
                "material_type": (
                    material_names[
                        inventory.material_id
                    ].material_type
                    if inventory.material_id
                    in material_names
                    else None
                ),
                "quantity": inventory.quantity,
                "reserved_quantity": (
                    inventory.reserved_quantity
                ),
                "free_quantity": (
                    inventory.quantity
                    - inventory.reserved_quantity
                )
            }
            for inventory in inventories
        ],
        "profiles": [
            _serialize_packaging_profile(profile)
            for profile in profiles
        ]
    }


@router.get("/packaging-profiles")
def get_packaging_profiles(
    product_id: Optional[int] = None,
    active_only: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    query = db.query(models.PackagingProfile)

    if product_id is not None:
        query = query.filter(
            models.PackagingProfile.product_id == product_id
        )

    if active_only:
        query = query.filter(
            models.PackagingProfile.is_active == True
        )

    profiles = query.order_by(
        models.PackagingProfile.product_id.asc(),
        models.PackagingProfile.version.desc()
    ).all()

    return [
        _serialize_packaging_profile(profile)
        for profile in profiles
    ]


@router.post(
    "/packaging-profiles",
    status_code=status.HTTP_201_CREATED
)
def create_packaging_profile(
    request: PackagingProfileCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    profile_name = request.name.strip()

    if not profile_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Packaging profile name is required."
        )

    if not request.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one packaging item is required."
        )

    try:
        product = db.query(models.Product).filter(
            models.Product.id == request.product_id
        ).with_for_update().first()

        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product was not found."
            )

        product_weight = Decimal(
            str(product.unit_weight_grams or 0)
        )

        if (
            not product_weight.is_finite()
            or product_weight <= 0
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Product unit weight must be greater "
                    "than zero before defining packaging."
                )
            )

        material_ids = [
            item.material_id
            for item in request.items
        ]

        if len(material_ids) != len(set(material_ids)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Each packaging material may appear "
                    "only once in a profile."
                )
            )

        materials = db.query(
            models.PackagingMaterial
        ).filter(
            models.PackagingMaterial.id.in_(material_ids)
        ).all()

        materials_by_id = {
            material.id: material
            for material in materials
        }

        missing_material_ids = sorted(
            set(material_ids) - set(materials_by_id)
        )

        if missing_material_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "Packaging materials were not found: "
                    + ", ".join(
                        str(value)
                        for value in missing_material_ids
                    )
                )
            )

        primary_items = [
            item
            for item in request.items
            if item.is_primary
        ]

        if len(primary_items) != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Exactly one primary packaging item "
                    "must be selected."
                )
            )

        validated_items = []

        allowed_stages = {
            "production",
            "dispatch"
        }

        allowed_rounding_modes = {
            "exact",
            "ceil"
        }

        for item in request.items:
            stage = (
                item.consumption_stage
                or ""
            ).strip().lower()

            rounding_mode = (
                item.rounding_mode
                or ""
            ).strip().lower()

            if stage not in allowed_stages:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Invalid consumption stage for "
                        f"material {item.material_id}."
                    )
                )

            if rounding_mode not in allowed_rounding_modes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Invalid rounding mode for "
                        f"material {item.material_id}."
                    )
                )

            try:
                ratio = Decimal(
                    str(item.quantity_per_product)
                )
            except InvalidOperation:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Invalid packaging ratio for "
                        f"material {item.material_id}."
                    )
                )

            if not ratio.is_finite() or ratio <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Packaging ratio must be greater "
                        f"than zero for material {item.material_id}."
                    )
                )

            if (
                rounding_mode == "exact"
                and ratio != ratio.to_integral_value()
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Exact rounding requires a whole-number "
                        f"ratio for material {item.material_id}."
                    )
                )

            material = materials_by_id[item.material_id]

            validated_items.append({
                "request": item,
                "material": material,
                "ratio": ratio,
                "stage": stage,
                "rounding_mode": rounding_mode
            })

        primary_definition = next(
            row
            for row in validated_items
            if row["request"].is_primary
        )

        primary_material = primary_definition["material"]

        if primary_material.material_type != "container":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Primary packaging material must have "
                    "material_type=container."
                )
            )

        if primary_material.capacity_grams is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Primary packaging capacity must be defined."
                )
            )

        primary_capacity = Decimal(
            str(primary_material.capacity_grams)
        )

        if (
            not primary_capacity.is_finite()
            or primary_capacity < product_weight
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Primary packaging capacity is smaller "
                    "than the product unit weight."
                )
            )

        existing_profiles = db.query(
            models.PackagingProfile
        ).filter(
            models.PackagingProfile.product_id
            == request.product_id
        ).with_for_update().all()

        next_version = (
            max(
                (
                    profile.version
                    for profile in existing_profiles
                ),
                default=0
            )
            + 1
        )

        for existing_profile in existing_profiles:
            if existing_profile.is_active:
                existing_profile.is_active = False

        # Required so the partial unique index is released
        # before the new active profile is inserted.
        db.flush()

        new_profile = models.PackagingProfile(
            product_id=request.product_id,
            name=profile_name,
            version=next_version,
            is_active=True
        )

        db.add(new_profile)
        db.flush()

        for row in validated_items:
            material = row["material"]
            item_request = row["request"]

            db.add(models.PackagingProfileItem(
                profile_id=new_profile.id,
                material_id=material.id,
                quantity_per_product=row["ratio"],
                component_type=material.material_type,
                consumption_stage=row["stage"],
                rounding_mode=row["rounding_mode"],
                is_primary=item_request.is_primary
            ))

        db.add(models.AuditLog(
            action="PACKAGING_PROFILE_CREATE",
            product_id=request.product_id,
            user_id=current_user.id,
            details=(
                f"Packaging profile {new_profile.id}, "
                f"version {next_version}, was created "
                f"for product {request.product_id}."
            )
        ))

        db.commit()
        db.refresh(new_profile)

        return _serialize_packaging_profile(new_profile)

    except HTTPException:
        db.rollback()
        raise

    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Packaging profile conflicts with an "
                "existing version or active profile."
            )
        ) from exc

    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while creating packaging profile."
        ) from exc

