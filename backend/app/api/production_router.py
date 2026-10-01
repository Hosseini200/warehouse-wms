# app/api/production_router.py
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.domain import models
from app.api.transfer_router import get_current_user


router = APIRouter(
    prefix="/production",
    tags=["Production & Recipes"]
)


class RecipeIngredientInput(BaseModel):
    ingredient_id: int
    percentage: float


class RecipeCreateRequest(BaseModel):
    final_product_id: int
    ingredients: List[RecipeIngredientInput]


class ProductionRequest(BaseModel):
    warehouse_id: int
    final_product_id: int
    produce_quantity: float
    new_batch_number: str
    expiry_days: Optional[int] = 730


def require_admin(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="فقط مدیر ارشد مجاز به انجام این عملیات است."
        )
    return current_user

def calculate_packaging_needed(produce_quantity: float) -> int:
    """
    برای محصول نهایی بسته‌بندی‌شده، هر واحد محصول نهایی به یک ظرف/ابزار بسته‌بندی نیاز دارد.
    چون بسته‌بندی عددی است، مقدار تولید باید عدد صحیح باشد.
    """
    if produce_quantity <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="مقدار تولید باید بزرگتر از صفر باشد."
        )

    if abs(produce_quantity - int(produce_quantity)) > 0.000001:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="برای محصول دارای بسته‌بندی، مقدار تولید باید عدد صحیح باشد."
        )

    return int(produce_quantity)


def _to_decimal(value, field_name: str) -> Decimal:
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


def convert_grams_to_inventory_unit(
    weight_grams,
    base_unit: str
) -> Decimal:
    grams = _to_decimal(weight_grams, "weight_grams")

    if grams < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Weight cannot be negative."
        )

    normalized_unit = (base_unit or "").strip().lower()

    grams_per_unit = {
        "kg": Decimal("1000"),
        "kilogram": Decimal("1000"),
        "kilograms": Decimal("1000"),
        "g": Decimal("1"),
        "gram": Decimal("1"),
        "grams": Decimal("1"),
        "mg": Decimal("0.001"),
        "milligram": Decimal("0.001"),
        "milligrams": Decimal("0.001"),
    }

    factor = grams_per_unit.get(normalized_unit)

    if factor is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Ingredient inventory unit must be a supported "
                f"mass unit. Unsupported unit: {base_unit}"
            )
        )

    return grams / factor


def calculate_profile_packaging_quantity(
    produce_quantity,
    quantity_per_product,
    rounding_mode: str
) -> int:
    product_quantity = _to_decimal(
        produce_quantity,
        "produce_quantity"
    )
    ratio = _to_decimal(
        quantity_per_product,
        "quantity_per_product"
    )

    if product_quantity <= 0 or ratio <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Production quantity and packaging ratio "
                "must be greater than zero."
            )
        )

    calculated = product_quantity * ratio
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


@router.post("/recipes/create", status_code=status.HTTP_201_CREATED)
def create_recipe(
    payload: RecipeCreateRequest,
    db: Session = Depends(get_db),
    _=Depends(require_admin)
):
    """
    ثبت فرمولاسیون درصدی برای محصول ترکیبی.
    مدل فعلی Recipe فقط فیلد percentage دارد، نه quantity_required.
    """

    final_product = db.query(models.Product).filter(
        models.Product.id == payload.final_product_id
    ).first()

    if not final_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="محصول نهایی با این شناسه یافت نشد."
        )

    if not payload.ingredients:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="حداقل یک ماده اولیه باید برای فرمولاسیون ثبت شود."
        )

    total_percentage = sum(item.percentage for item in payload.ingredients)

    if abs(total_percentage - 100.0) > 0.01:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"مجموع درصدهای فرمولاسیون باید دقیقاً ۱۰۰ باشد. مقدار فعلی: {total_percentage}"
        )

    for item in payload.ingredients:
        if item.percentage <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="درصد هر ماده اولیه باید بزرگتر از صفر باشد."
            )

        ingredient = db.query(models.Product).filter(
            models.Product.id == item.ingredient_id
        ).first()

        if not ingredient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ماده اولیه با شناسه {item.ingredient_id} یافت نشد."
            )

    try:
        db.query(models.Recipe).filter(
            models.Recipe.final_product_id == payload.final_product_id
        ).delete()

        for item in payload.ingredients:
            recipe = models.Recipe(
                final_product_id=payload.final_product_id,
                ingredient_id=item.ingredient_id,
                percentage=item.percentage
            )
            db.add(recipe)

        final_product.is_composite = True
        db.commit()

        return {
            "status": "success",
            "message": f"فرمولاسیون محصول '{final_product.name}' با موفقیت ثبت شد."
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="???? ????? ????."
        )


@router.get("/options")
def get_production_options(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role not in {
        "admin",
        "warehouse_manager",
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User role is not allowed to register production."
        )

    warehouse_query = db.query(
        models.Warehouse
    ).filter(
        models.Warehouse.is_active == True
    )

    if current_user.role == "warehouse_manager":
        if not current_user.warehouse_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Warehouse manager is not assigned "
                    "to a warehouse."
                )
            )

        warehouse_query = warehouse_query.filter(
            models.Warehouse.id
            == current_user.warehouse_id
        )

    warehouses = warehouse_query.order_by(
        models.Warehouse.id.asc()
    ).all()

    products = db.query(
        models.Product
    ).filter(
        models.Product.product_type == "finished_good"
    ).order_by(
        models.Product.id.asc()
    ).all()

    product_results = []

    for product in products:
        recipes = db.query(
            models.Recipe
        ).filter(
            models.Recipe.final_product_id == product.id
        ).order_by(
            models.Recipe.id.asc()
        ).all()

        recipe_total = sum(
            (
                _to_decimal(
                    recipe.percentage,
                    "recipe_percentage"
                )
                for recipe in recipes
            ),
            Decimal("0")
        )

        active_profile = db.query(
            models.PackagingProfile
        ).filter(
            models.PackagingProfile.product_id
            == product.id,
            models.PackagingProfile.is_active == True
        ).first()

        configuration_errors = []

        unit_weight = _to_decimal(
            product.unit_weight_grams or 0,
            "unit_weight_grams"
        )

        if unit_weight <= 0:
            configuration_errors.append(
                "Unit weight is not defined."
            )

        if not recipes:
            configuration_errors.append(
                "Recipe is not defined."
            )
        elif (
            abs(recipe_total - Decimal("100"))
            > Decimal("0.01")
        ):
            configuration_errors.append(
                "Recipe percentages do not total 100."
            )

        profile_items = []

        if not active_profile:
            configuration_errors.append(
                "Active packaging profile is not defined."
            )
        else:
            ordered_items = sorted(
                active_profile.items or [],
                key=lambda item: item.id or 0
            )

            primary_items = [
                item
                for item in ordered_items
                if item.is_primary
            ]

            if not ordered_items:
                configuration_errors.append(
                    "Active packaging profile has no items."
                )

            if len(primary_items) != 1:
                configuration_errors.append(
                    "Packaging profile must have one primary item."
                )
            else:
                primary_material = primary_items[0].material

                if (
                    primary_material is None
                    or primary_material.material_type
                    != "container"
                ):
                    configuration_errors.append(
                        "Primary packaging is not a container."
                    )
                elif (
                    primary_material.capacity_grams is None
                ):
                    configuration_errors.append(
                        "Primary container capacity is not defined."
                    )
                elif (
                    _to_decimal(
                        primary_material.capacity_grams,
                        "primary_container_capacity"
                    )
                    < unit_weight
                ):
                    configuration_errors.append(
                        "Primary container capacity is too small."
                    )

            for item in ordered_items:
                material = item.material

                profile_items.append({
                    "profile_item_id": item.id,
                    "material_id": item.material_id,
                    "material_name": (
                        material.name
                        if material
                        else None
                    ),
                    "material_sku": (
                        material.sku
                        if material
                        else None
                    ),
                    "material_type": (
                        material.material_type
                        if material
                        else None
                    ),
                    "quantity_per_product": float(
                        item.quantity_per_product
                    ),
                    "consumption_stage": (
                        item.consumption_stage
                    ),
                    "rounding_mode": (
                        item.rounding_mode
                    ),
                    "is_primary": item.is_primary
                })

        product_results.append({
            "product_id": product.id,
            "product_name": product.name,
            "product_sku": product.sku,
            "base_unit": product.base_unit,
            "unit_weight_grams": (
                product.unit_weight_grams
            ),
            "is_composite": product.is_composite,
            "recipe_total_percentage": float(
                recipe_total
            ),
            "recipe_components": [
                {
                    "ingredient_id": (
                        recipe.ingredient_id
                    ),
                    "ingredient_name": (
                        recipe.ingredient.name
                        if recipe.ingredient
                        else None
                    ),
                    "ingredient_sku": (
                        recipe.ingredient.sku
                        if recipe.ingredient
                        else None
                    ),
                    "base_unit": (
                        recipe.ingredient.base_unit
                        if recipe.ingredient
                        else None
                    ),
                    "percentage": (
                        recipe.percentage
                    )
                }
                for recipe in recipes
            ],
            "packaging_profile": (
                {
                    "profile_id": active_profile.id,
                    "profile_name": active_profile.name,
                    "profile_version": (
                        active_profile.version
                    ),
                    "items": profile_items
                }
                if active_profile
                else None
            ),
            "configuration_ready": (
                len(configuration_errors) == 0
            ),
            "configuration_errors": (
                configuration_errors
            )
        })

    return {
        "warehouses": [
            {
                "id": warehouse.id,
                "name": warehouse.name,
                "location": warehouse.location
            }
            for warehouse in warehouses
        ],
        "products": product_results
    }


@router.post("/manufacture", status_code=status.HTTP_201_CREATED)
def manufacture_product(
    payload: ProductionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if (
        current_user.role != "admin"
        and current_user.warehouse_id != payload.warehouse_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to register production for this warehouse."
        )

    produce_quantity = _to_decimal(
        payload.produce_quantity,
        "produce_quantity"
    )

    if produce_quantity <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Production quantity must be greater than zero."
        )

    if produce_quantity != produce_quantity.to_integral_value():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Finished-product production quantity must be a whole number."
        )

    warehouse = db.query(models.Warehouse).filter(
        models.Warehouse.id == payload.warehouse_id,
        models.Warehouse.is_active == True
    ).first()

    if not warehouse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active warehouse was not found."
        )

    final_product = db.query(models.Product).filter(
        models.Product.id == payload.final_product_id
    ).with_for_update().first()

    if not final_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Final product was not found."
        )

    if final_product.product_type != "finished_good":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Production output must be a finished_good product."
        )

    unit_weight_grams = _to_decimal(
        final_product.unit_weight_grams or 0,
        "unit_weight_grams"
    )

    if unit_weight_grams <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Final-product unit weight must be greater than zero."
        )

    batch_number = (payload.new_batch_number or "").strip()

    if not batch_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch number is required."
        )

    existing_batch = db.query(models.Batch).filter(
        models.Batch.batch_number == batch_number
    ).first()

    if existing_batch:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Batch number already exists."
        )

    recipes = db.query(models.Recipe).filter(
        models.Recipe.final_product_id == payload.final_product_id
    ).order_by(
        models.Recipe.id.asc()
    ).all()

    if not recipes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No recipe is defined for this product."
        )

    recipe_total = sum(
        (
            _to_decimal(recipe.percentage, "recipe_percentage")
            for recipe in recipes
        ),
        Decimal("0")
    )

    if abs(recipe_total - Decimal("100")) > Decimal("0.01"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Recipe percentages must total 100. Current total: {recipe_total}"
        )

    active_profile = db.query(
        models.PackagingProfile
    ).filter(
        models.PackagingProfile.product_id == payload.final_product_id,
        models.PackagingProfile.is_active == True
    ).with_for_update().first()

    if not active_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An active packaging profile is required before production."
        )

    profile_items = sorted(
        active_profile.items,
        key=lambda item: item.id or 0
    )

    if not profile_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The active packaging profile has no items."
        )

    primary_items = [
        item for item in profile_items
        if item.is_primary
    ]

    if len(primary_items) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The active packaging profile must have exactly one primary item."
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

    primary_capacity = _to_decimal(
        primary_material.capacity_grams,
        "primary_container_capacity"
    )

    if primary_capacity < unit_weight_grams:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Primary container capacity is smaller than product unit weight."
        )

    total_final_weight_grams = (
        produce_quantity * unit_weight_grams
    )

    ingredient_plans = []

    for recipe in recipes:
        ingredient = recipe.ingredient

        if ingredient is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Recipe ingredient {recipe.ingredient_id} was not found."
            )

        percentage = _to_decimal(
            recipe.percentage,
            "recipe_percentage"
        )

        required_weight_grams = (
            total_final_weight_grams
            * percentage
            / Decimal("100")
        )

        required_quantity = convert_grams_to_inventory_unit(
            required_weight_grams,
            ingredient.base_unit
        )

        inventories = db.query(models.Inventory).filter(
            models.Inventory.warehouse_id == payload.warehouse_id,
            models.Inventory.product_id == recipe.ingredient_id,
            models.Inventory.quantity > 0
        ).order_by(
            models.Inventory.id.asc()
        ).with_for_update().all()

        available_quantity = sum(
            (
                _to_decimal(inv.quantity, "inventory_quantity")
                - _to_decimal(
                    inv.reserved_quantity or 0,
                    "reserved_quantity"
                )
                for inv in inventories
            ),
            Decimal("0")
        )

        if available_quantity < required_quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Insufficient inventory for ingredient "
                    f"{ingredient.sku}. Required: {required_quantity} "
                    f"{ingredient.base_unit}; available: "
                    f"{available_quantity} {ingredient.base_unit}."
                )
            )

        ingredient_plans.append({
            "recipe": recipe,
            "ingredient": ingredient,
            "percentage": percentage,
            "required_quantity": required_quantity,
            "inventories": inventories
        })

    production_packaging_plans = []
    dispatch_packaging_plans = []

    for profile_item in profile_items:
        required_quantity = calculate_profile_packaging_quantity(
            produce_quantity,
            profile_item.quantity_per_product,
            profile_item.rounding_mode
        )

        plan = {
            "profile_item": profile_item,
            "material": profile_item.material,
            "required_quantity": required_quantity
        }

        if profile_item.consumption_stage == "production":
            packaging_inventory = db.query(
                models.PackagingInventory
            ).filter(
                models.PackagingInventory.warehouse_id
                == payload.warehouse_id,
                models.PackagingInventory.material_id
                == profile_item.material_id
            ).with_for_update().first()

            if not packaging_inventory:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Packaging inventory was not found for "
                        f"material {profile_item.material.sku}."
                    )
                )

            free_quantity = (
                packaging_inventory.quantity
                - packaging_inventory.reserved_quantity
            )

            if free_quantity < required_quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Insufficient production packaging "
                        f"{profile_item.material.sku}. "
                        f"Required: {required_quantity}; "
                        f"available: {free_quantity}."
                    )
                )

            plan["inventory"] = packaging_inventory
            production_packaging_plans.append(plan)

        elif profile_item.consumption_stage == "dispatch":
            dispatch_packaging_plans.append(plan)

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Unsupported packaging consumption stage: "
                    f"{profile_item.consumption_stage}"
                )
            )

    try:
        new_batch = models.Batch(
            product_id=payload.final_product_id,
            batch_number=batch_number,
            production_date=datetime.utcnow(),
            expiry_date=(
                datetime.utcnow()
                + timedelta(days=payload.expiry_days or 730)
            )
        )

        db.add(new_batch)
        db.flush()

        production_run = models.ProductionRun(
            warehouse_id=payload.warehouse_id,
            final_product_id=payload.final_product_id,
            batch_id=new_batch.id,
            packaging_profile_id=active_profile.id,
            produce_quantity=float(produce_quantity),
            status="completed",
            created_by=current_user.id
        )

        db.add(production_run)
        db.flush()

        for plan in ingredient_plans:
            remaining = plan["required_quantity"]

            for inventory in plan["inventories"]:
                if remaining <= 0:
                    break

                free_quantity = (
                    _to_decimal(
                        inventory.quantity,
                        "inventory_quantity"
                    )
                    - _to_decimal(
                        inventory.reserved_quantity or 0,
                        "reserved_quantity"
                    )
                )

                deducted = min(free_quantity, remaining)

                inventory.quantity = float(
                    _to_decimal(
                        inventory.quantity,
                        "inventory_quantity"
                    ) - deducted
                )

                remaining -= deducted

            if remaining > Decimal("0.000001"):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Ingredient inventory changed during "
                        "production processing."
                    )
                )

            db.add(models.ProductionRunIngredient(
                production_run_id=production_run.id,
                ingredient_id=plan["ingredient"].id,
                percentage=float(plan["percentage"]),
                required_quantity=float(
                    plan["required_quantity"]
                ),
                consumed_quantity=float(
                    plan["required_quantity"]
                )
            ))

        production_packaging_result = []

        for plan in production_packaging_plans:
            profile_item = plan["profile_item"]
            material = plan["material"]
            packaging_inventory = plan["inventory"]
            required_quantity = plan["required_quantity"]

            packaging_inventory.quantity -= required_quantity

            db.add(models.ProductionRunPackagingItem(
                production_run_id=production_run.id,
                material_id=material.id,
                quantity_per_product=(
                    profile_item.quantity_per_product
                ),
                required_quantity=required_quantity,
                consumed_quantity=required_quantity
            ))

            db.add(models.PackagingAdjustment(
                warehouse_id=payload.warehouse_id,
                material_id=material.id,
                quantity=required_quantity,
                action_type="production_usage",
                reference_type="production_run",
                reference_id=production_run.id,
                reason=(
                    f"Packaging consumed for production run "
                    f"{production_run.id}."
                ),
                user_id=current_user.id
            ))

            production_packaging_result.append({
                "material_id": material.id,
                "material_sku": material.sku,
                "required_quantity": required_quantity,
                "consumed_quantity": required_quantity
            })

        final_inventory = models.Inventory(
            warehouse_id=payload.warehouse_id,
            product_id=payload.final_product_id,
            batch_id=new_batch.id,
            quantity=float(produce_quantity),
            reserved_quantity=0.0
        )

        db.add(final_inventory)

        db.add(models.AuditLog(
            action="PRODUCTION_MANUFACTURE",
            product_id=payload.final_product_id,
            user_id=current_user.id,
            details=(
                f"Production run {production_run.id}: "
                f"{produce_quantity} units of product "
                f"{payload.final_product_id} in warehouse "
                f"{payload.warehouse_id}; packaging profile "
                f"{active_profile.id} version "
                f"{active_profile.version}."
            )
        ))

        db.commit()
        db.refresh(production_run)

        return {
            "status": "success",
            "message": "Production was registered successfully.",
            "production_run_id": production_run.id,
            "batch_id": new_batch.id,
            "packaging_profile_id": active_profile.id,
            "packaging_profile_version": active_profile.version,
            "produced_quantity": float(produce_quantity),
            "ingredient_consumption": [
                {
                    "ingredient_id": plan["ingredient"].id,
                    "ingredient_sku": plan["ingredient"].sku,
                    "base_unit": plan["ingredient"].base_unit,
                    "percentage": float(plan["percentage"]),
                    "required_quantity": float(
                        plan["required_quantity"]
                    )
                }
                for plan in ingredient_plans
            ],
            "production_packaging": production_packaging_result,
            "dispatch_packaging_plan": [
                {
                    "material_id": plan["material"].id,
                    "material_sku": plan["material"].sku,
                    "required_quantity": plan["required_quantity"]
                }
                for plan in dispatch_packaging_plans
            ]
        }

    except HTTPException:
        db.rollback()
        raise

    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while registering production."
        ) from exc


@router.get("/recipes/{final_product_id}")
def get_recipe(
    final_product_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    product = db.query(models.Product).filter(
        models.Product.id == final_product_id
    ).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="محصول یافت نشد."
        )

    recipes = db.query(models.Recipe).filter(
        models.Recipe.final_product_id == final_product_id
    ).all()

    return {
        "final_product_id": final_product_id,
        "product_name": product.name,
        "components": [
            {
                "ingredient_id": r.ingredient_id,
                "percentage": r.percentage
            }
            for r in recipes
        ]
    }