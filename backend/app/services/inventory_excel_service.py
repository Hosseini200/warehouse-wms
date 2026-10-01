from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.domain import models


MAX_ROWS_PER_SHEET = 5000

INVENTORY_COLUMNS = {
    "نام انبار": "warehouse_name",
    "warehousename": "warehouse_name",
    "نام کالا": "product_name",
    "productname": "product_name",
    "کد کالا": "sku",
    "sku": "sku",
    "واحد پایه": "base_unit",
    "baseunit": "base_unit",
    "نوع کالا": "product_type",
    "producttype": "product_type",
    "شماره بچ": "batch_number",
    "batchnumber": "batch_number",
    "تاریخ تولید": "production_date",
    "productiondate": "production_date",
    "تاریخ انقضا": "expiry_date",
    "expirydate": "expiry_date",
    "موجودی کل": "quantity",
    "quantity": "quantity",
    "موجودی رزرو": "reserved_quantity",
    "reservedquantity": "reserved_quantity",
    "ترکیبی": "is_composite",
    "iscomposite": "is_composite",
    "وزن واحد گرم": "unit_weight_grams",
    "unitweightgrams": "unit_weight_grams",
    "کد بسته‌بندی اصلی": "primary_packaging_sku",
    "primarypackagingsku": "primary_packaging_sku",
}

PACKAGING_COLUMNS = {
    "نام انبار": "warehouse_name",
    "warehousename": "warehouse_name",
    "نام قلم بسته‌بندی": "material_name",
    "materialname": "material_name",
    "کد بسته‌بندی": "sku",
    "sku": "sku",
    "نوع بسته‌بندی": "material_type",
    "materialtype": "material_type",
    "گنجایش گرم": "capacity_grams",
    "capacitygrams": "capacity_grams",
    "توضیحات": "description",
    "description": "description",
    "تعداد کل": "quantity",
    "quantity": "quantity",
    "تعداد رزرو": "reserved_quantity",
    "reservedquantity": "reserved_quantity",
}

INVENTORY_REQUIRED = {
    "warehouse_name",
    "product_name",
    "sku",
    "base_unit",
    "product_type",
    "batch_number",
    "expiry_date",
    "quantity",
    "primary_packaging_sku",
}

PACKAGING_REQUIRED = {
    "warehouse_name",
    "material_name",
    "sku",
    "material_type",
    "quantity",
}

PRODUCT_TYPES = {"raw_material", "finished_good"}

PACKAGING_TYPES = {
    "container",
    "lid",
    "label",
    "inner_box",
    "carton",
    "pallet",
    "other",
}


def _column_key(value: Any) -> str:
    return str(value).strip().replace(" ", "").replace("_", "").casefold()


def _build_aliases(columns: dict[str, str]) -> dict[str, str]:
    return {
        _column_key(source): destination
        for source, destination in columns.items()
    }


INVENTORY_ALIASES = _build_aliases(INVENTORY_COLUMNS)
PACKAGING_ALIASES = _build_aliases(PACKAGING_COLUMNS)


def _clean_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    text = str(value).strip()
    return text or None


def _parse_number(value: Any, field_name: str) -> float:
    text = _clean_text(value)

    if text is None:
        raise ValueError(f"{field_name} الزامی است.")

    try:
        number = Decimal(text.replace(",", ""))
    except (InvalidOperation, AttributeError):
        raise ValueError(f"{field_name} باید عدد باشد.")

    if not number.is_finite():
        raise ValueError(f"{field_name} معتبر نیست.")

    return float(number)


def _parse_integer(value: Any, field_name: str) -> int:
    number = _parse_number(value, field_name)

    if not number.is_integer():
        raise ValueError(f"{field_name} باید عدد صحیح باشد.")

    return int(number)


def _parse_optional_number(value: Any, field_name: str) -> float | None:
    if _clean_text(value) is None:
        return None

    return _parse_number(value, field_name)


def _parse_optional_integer(value: Any, field_name: str) -> int | None:
    if _clean_text(value) is None:
        return None

    return _parse_integer(value, field_name)


def _parse_bool(value: Any) -> bool:
    text = _clean_text(value)

    if text is None:
        return False

    normalized = text.casefold()

    if normalized in {"1", "true", "yes", "بله", "بلی"}:
        return True

    if normalized in {"0", "false", "no", "خیر", "نه"}:
        return False

    raise ValueError("مقدار ستون ترکیبی باید بله/خیر یا true/false باشد.")


def _parse_date(
    value: Any,
    field_name: str,
    required: bool,
) -> datetime | None:
    if _clean_text(value) is None:
        if required:
            raise ValueError(f"{field_name} الزامی است.")
        return None

    try:
        parsed = pd.to_datetime(value, errors="raise")
    except Exception:
        raise ValueError(
            f"{field_name} معتبر نیست. قالب پیشنهادی YYYY-MM-DD است."
        )

    result = parsed.to_pydatetime()

    if result.tzinfo is not None:
        result = result.astimezone(timezone.utc).replace(tzinfo=None)

    return result


def _prepare_sheet(
    dataframe: pd.DataFrame,
    aliases: dict[str, str],
    required_columns: set[str],
    sheet_name: str,
    allow_empty: bool = False,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []

    dataframe = dataframe.dropna(how="all").copy()

    if dataframe.empty:
        if not allow_empty:
            errors.append({
                "sheet": sheet_name,
                "row": None,
                "field": None,
                "message": "این برگه خالی است.",
            })
        return dataframe, errors

    if len(dataframe.index) > MAX_ROWS_PER_SHEET:
        errors.append({
            "sheet": sheet_name,
            "row": None,
            "field": None,
            "message": (
                f"حداکثر تعداد مجاز ردیف در هر برگه "
                f"{MAX_ROWS_PER_SHEET} است."
            ),
        })

    mapped_columns: list[str] = []

    for column in dataframe.columns:
        mapped_columns.append(
            aliases.get(_column_key(column), str(column).strip())
        )

    if len(mapped_columns) != len(set(mapped_columns)):
        errors.append({
            "sheet": sheet_name,
            "row": None,
            "field": None,
            "message": "دو ستون با مفهوم یکسان در فایل وجود دارد.",
        })

    dataframe.columns = mapped_columns

    missing = sorted(required_columns - set(dataframe.columns))

    if missing:
        errors.append({
            "sheet": sheet_name,
            "row": None,
            "field": None,
            "message": "ستون‌های الزامی موجود نیستند: " + ", ".join(missing),
        })

    return dataframe, errors


def _read_workbook(file_bytes: bytes) -> dict[str, pd.DataFrame]:
    try:
        workbook = pd.read_excel(
            BytesIO(file_bytes),
            sheet_name=None,
            dtype=object,
            engine="openpyxl",
        )
    except Exception as exc:
        raise ValueError(f"فایل Excel قابل خواندن نیست: {exc}")

    if "Inventory" not in workbook:
        raise ValueError("برگه Inventory در فایل وجود ندارد.")

    return workbook


def validate_workbook(
    db: Session,
    file_bytes: bytes,
) -> dict[str, Any]:
    workbook = _read_workbook(file_bytes)

    errors: list[dict[str, Any]] = []
    inventory_records: list[dict[str, Any]] = []
    packaging_records: list[dict[str, Any]] = []
    preview_rows: list[dict[str, Any]] = []

    warehouses = {
        warehouse.name.strip().casefold(): warehouse
        for warehouse in db.query(models.Warehouse).filter(
            models.Warehouse.is_active == True
        ).all()
    }

    products = {
        product.sku.strip().casefold(): product
        for product in db.query(models.Product).all()
    }

    batches = {
        batch.batch_number.strip().casefold(): batch
        for batch in db.query(models.Batch).all()
    }

    inventories = {
        (
            inventory.warehouse_id,
            inventory.product_id,
            inventory.batch_id,
        ): inventory
        for inventory in db.query(models.Inventory).all()
    }

    materials = {
        material.sku.strip().casefold(): material
        for material in db.query(models.PackagingMaterial).all()
    }

    packaging_inventories = {
        (
            inventory.warehouse_id,
            inventory.material_id,
        ): inventory
        for inventory in db.query(models.PackagingInventory).all()
    }

    inventory_df, sheet_errors = _prepare_sheet(
        workbook["Inventory"],
        INVENTORY_ALIASES,
        INVENTORY_REQUIRED,
        "Inventory",
    )
    errors.extend(sheet_errors)

    file_product_definitions: dict[str, tuple[Any, ...]] = {}
    file_batch_definitions: dict[str, str] = {}
    seen_inventory_rows: set[tuple[str, str, str]] = set()

    if not sheet_errors:
        for index, row in inventory_df.iterrows():
            excel_row = int(index) + 2
            row_errors: list[dict[str, Any]] = []

            try:
                warehouse_name = _clean_text(row.get("warehouse_name"))
                product_name = _clean_text(row.get("product_name"))
                sku = _clean_text(row.get("sku"))
                base_unit = _clean_text(row.get("base_unit"))
                product_type = _clean_text(row.get("product_type"))
                batch_number = _clean_text(row.get("batch_number"))
                primary_packaging_sku = _clean_text(
                    row.get("primary_packaging_sku")
                )

                required_texts = {
                    "نام انبار": warehouse_name,
                    "نام کالا": product_name,
                    "کد کالا": sku,
                    "واحد پایه": base_unit,
                    "نوع کالا": product_type,
                    "شماره بچ": batch_number,
                    "کد بسته‌بندی اصلی": primary_packaging_sku,
                }

                for field, value in required_texts.items():
                    if not value:
                        raise ValueError(f"{field} الزامی است.")

                product_type = product_type.casefold()

                if product_type not in PRODUCT_TYPES:
                    raise ValueError(
                        "نوع کالا باید raw_material یا finished_good باشد."
                    )

                quantity = _parse_number(
                    row.get("quantity"),
                    "موجودی کل",
                )
                reserved_quantity = _parse_optional_number(
                    row.get("reserved_quantity"),
                    "موجودی رزرو",
                )
                reserved_quantity = reserved_quantity or 0.0

                if quantity < 0:
                    raise ValueError("موجودی کل نمی‌تواند منفی باشد.")

                if reserved_quantity < 0:
                    raise ValueError("موجودی رزرو نمی‌تواند منفی باشد.")

                if reserved_quantity > quantity:
                    raise ValueError(
                        "موجودی رزرو نمی‌تواند بیشتر از موجودی کل باشد."
                    )

                production_date = _parse_date(
                    row.get("production_date"),
                    "تاریخ تولید",
                    required=False,
                )

                expiry_date = _parse_date(
                    row.get("expiry_date"),
                    "تاریخ انقضا",
                    required=True,
                )

                if expiry_date <= datetime.utcnow():
                    raise ValueError("تاریخ انقضا باید در آینده باشد.")

                if production_date and production_date > expiry_date:
                    raise ValueError(
                        "تاریخ تولید نمی‌تواند بعد از تاریخ انقضا باشد."
                    )

                is_composite = _parse_bool(row.get("is_composite"))

                unit_weight_grams = _parse_optional_number(
                    row.get("unit_weight_grams"),
                    "وزن واحد گرم",
                )
                unit_weight_grams = unit_weight_grams or 0.0

                if unit_weight_grams <= 0:
                    raise ValueError(
                        "وزن واحد باید بیشتر از صفر باشد."
                    )

                warehouse_key = warehouse_name.casefold()
                sku_key = sku.casefold()
                batch_key = batch_number.casefold()

                warehouse = warehouses.get(warehouse_key)

                if not warehouse:
                    raise ValueError(
                        f"انبار فعال با نام '{warehouse_name}' یافت نشد."
                    )

                product_definition = (
                    product_name.casefold(),
                    base_unit.casefold(),
                    product_type,
                    is_composite,
                    unit_weight_grams,
                    primary_packaging_sku.casefold(),
                )

                previous_product_definition = file_product_definitions.get(
                    sku_key
                )

                if (
                    previous_product_definition is not None
                    and previous_product_definition != product_definition
                ):
                    raise ValueError(
                        "اطلاعات این کد کالا در ردیف‌های فایل یکسان نیست."
                    )

                file_product_definitions[sku_key] = product_definition

                existing_product = products.get(sku_key)

                if existing_product:
                    if existing_product.name.strip().casefold() != product_name.casefold():
                        raise ValueError(
                            "نام کالا با اطلاعات موجود این کد کالا یکسان نیست."
                        )

                    if existing_product.base_unit.strip().casefold() != base_unit.casefold():
                        raise ValueError(
                            "واحد پایه با اطلاعات موجود این کد کالا یکسان نیست."
                        )

                    if (
                        existing_product.product_type
                        and existing_product.product_type.casefold()
                        != product_type
                    ):
                        raise ValueError(
                            "نوع کالا با اطلاعات موجود این کد کالا یکسان نیست."
                        )

                previous_batch_sku = file_batch_definitions.get(batch_key)

                if previous_batch_sku and previous_batch_sku != sku_key:
                    raise ValueError(
                        "یک شماره بچ برای دو کالای متفاوت استفاده شده است."
                    )

                file_batch_definitions[batch_key] = sku_key

                existing_batch = batches.get(batch_key)

                if existing_batch:
                    if not existing_product:
                        raise ValueError(
                            "شماره بچ موجود است ولی کد کالا در فایل جدید است."
                        )

                    if existing_batch.product_id != existing_product.id:
                        raise ValueError(
                            "شماره بچ به کالای دیگری تعلق دارد."
                        )

                inventory_identity = (
                    warehouse_key,
                    sku_key,
                    batch_key,
                )

                if inventory_identity in seen_inventory_rows:
                    raise ValueError(
                        "این ترکیب انبار، کالا و بچ در فایل تکرار شده است."
                    )

                seen_inventory_rows.add(inventory_identity)

                existing_inventory = None

                if existing_product and existing_batch:
                    existing_inventory = inventories.get((
                        warehouse.id,
                        existing_product.id,
                        existing_batch.id,
                    ))

                action = (
                    "update_inventory"
                    if existing_inventory
                    else "create_inventory"
                )

                inventory_records.append({
                    "excel_row": excel_row,
                    "warehouse_name": warehouse_name,
                    "product_name": product_name,
                    "sku": sku,
                    "base_unit": base_unit,
                    "product_type": product_type,
                    "batch_number": batch_number,
                    "production_date": production_date,
                    "expiry_date": expiry_date,
                    "quantity": quantity,
                    "reserved_quantity": reserved_quantity,
                    "is_composite": is_composite,
                    "unit_weight_grams": unit_weight_grams,
                    "primary_packaging_sku": primary_packaging_sku,
                    "action": action,
                })

                preview_rows.append({
                    "sheet": "Inventory",
                    "row": excel_row,
                    "sku": sku,
                    "batch_number": batch_number,
                    "warehouse": warehouse_name,
                    "action": action,
                })

            except ValueError as exc:
                row_errors.append({
                    "sheet": "Inventory",
                    "row": excel_row,
                    "field": None,
                    "message": str(exc),
                })

            errors.extend(row_errors)

    if "PackagingInventory" in workbook:
        packaging_df, packaging_sheet_errors = _prepare_sheet(
            workbook["PackagingInventory"],
            PACKAGING_ALIASES,
            PACKAGING_REQUIRED,
            "PackagingInventory",
            allow_empty=True,
        )
        errors.extend(packaging_sheet_errors)

        seen_material_rows: set[tuple[str, str]] = set()
        file_material_definitions: dict[str, tuple[Any, ...]] = {}

        if not packaging_sheet_errors:
            for index, row in packaging_df.iterrows():
                excel_row = int(index) + 2

                try:
                    warehouse_name = _clean_text(
                        row.get("warehouse_name")
                    )
                    material_name = _clean_text(
                        row.get("material_name")
                    )
                    sku = _clean_text(row.get("sku"))
                    material_type = _clean_text(
                        row.get("material_type")
                    )

                    required_texts = {
                        "نام انبار": warehouse_name,
                        "نام قلم بسته‌بندی": material_name,
                        "کد بسته‌بندی": sku,
                        "نوع بسته‌بندی": material_type,
                    }

                    for field, value in required_texts.items():
                        if not value:
                            raise ValueError(f"{field} الزامی است.")

                    material_type = material_type.casefold()

                    if material_type not in PACKAGING_TYPES:
                        raise ValueError(
                            "نوع بسته‌بندی معتبر نیست."
                        )

                    quantity = _parse_integer(
                        row.get("quantity"),
                        "تعداد کل",
                    )
                    reserved_quantity = _parse_optional_integer(
                        row.get("reserved_quantity"),
                        "تعداد رزرو",
                    )
                    reserved_quantity = reserved_quantity or 0

                    if quantity < 0:
                        raise ValueError("تعداد کل نمی‌تواند منفی باشد.")

                    if reserved_quantity < 0:
                        raise ValueError(
                            "تعداد رزرو نمی‌تواند منفی باشد."
                        )

                    if reserved_quantity > quantity:
                        raise ValueError(
                            "تعداد رزرو نمی‌تواند بیشتر از تعداد کل باشد."
                        )

                    capacity_grams = _parse_optional_number(
                        row.get("capacity_grams"),
                        "گنجایش گرم",
                    )

                    if (
                        capacity_grams is not None
                        and capacity_grams <= 0
                    ):
                        raise ValueError(
                            "گنجایش باید بیشتر از صفر باشد."
                        )

                    description = _clean_text(row.get("description"))

                    warehouse_key = warehouse_name.casefold()
                    sku_key = sku.casefold()

                    warehouse = warehouses.get(warehouse_key)

                    if not warehouse:
                        raise ValueError(
                            f"انبار فعال با نام '{warehouse_name}' یافت نشد."
                        )

                    definition = (
                        material_name.casefold(),
                        material_type,
                        capacity_grams,
                    )

                    previous_definition = file_material_definitions.get(
                        sku_key
                    )

                    if (
                        previous_definition is not None
                        and previous_definition != definition
                    ):
                        raise ValueError(
                            "اطلاعات این کد بسته‌بندی در فایل یکسان نیست."
                        )

                    file_material_definitions[sku_key] = definition

                    existing_material = materials.get(sku_key)

                    if existing_material:
                        if (
                            existing_material.name.strip().casefold()
                            != material_name.casefold()
                        ):
                            raise ValueError(
                                "نام بسته‌بندی با اطلاعات موجود یکسان نیست."
                            )

                        if (
                            existing_material.material_type.casefold()
                            != material_type
                        ):
                            raise ValueError(
                                "نوع بسته‌بندی با اطلاعات موجود یکسان نیست."
                            )

                    identity = (warehouse_key, sku_key)

                    if identity in seen_material_rows:
                        raise ValueError(
                            "این ترکیب انبار و بسته‌بندی در فایل تکرار شده است."
                        )

                    seen_material_rows.add(identity)

                    existing_inventory = None

                    if existing_material:
                        existing_inventory = packaging_inventories.get((
                            warehouse.id,
                            existing_material.id,
                        ))

                    action = (
                        "update_packaging_inventory"
                        if existing_inventory
                        else "create_packaging_inventory"
                    )

                    packaging_records.append({
                        "excel_row": excel_row,
                        "warehouse_name": warehouse_name,
                        "material_name": material_name,
                        "sku": sku,
                        "material_type": material_type,
                        "capacity_grams": capacity_grams,
                        "description": description,
                        "quantity": quantity,
                        "reserved_quantity": reserved_quantity,
                        "action": action,
                    })

                    preview_rows.append({
                        "sheet": "PackagingInventory",
                        "row": excel_row,
                        "sku": sku,
                        "warehouse": warehouse_name,
                        "action": action,
                    })

                except ValueError as exc:
                    errors.append({
                        "sheet": "PackagingInventory",
                        "row": excel_row,
                        "field": None,
                        "message": str(exc),
                    })


    file_material_records = {
        record["sku"].casefold(): record
        for record in packaging_records
    }

    active_profiles = {
        profile.product_id: profile
        for profile in db.query(models.PackagingProfile).filter(
            models.PackagingProfile.is_active == True
        ).all()
    }

    profile_validation_errors: set[tuple[int, str]] = set()

    for record in inventory_records:
        try:
            material_sku_key = (
                record["primary_packaging_sku"].casefold()
            )
            existing_material = materials.get(material_sku_key)
            file_material = file_material_records.get(material_sku_key)

            if existing_material:
                material_type = (
                    existing_material.material_type or ""
                ).casefold()
                capacity_grams = existing_material.capacity_grams
            elif file_material:
                material_type = file_material["material_type"]
                capacity_grams = file_material["capacity_grams"]
            else:
                raise ValueError(
                    "کد بسته‌بندی اصلی در سامانه یا برگه "
                    "PackagingInventory یافت نشد."
                )

            if material_type != "container":
                raise ValueError(
                    "بسته‌بندی اصلی باید از نوع container باشد."
                )

            if capacity_grams is None:
                raise ValueError(
                    "گنجایش بسته‌بندی اصلی باید مشخص باشد."
                )

            if float(capacity_grams) < float(
                record["unit_weight_grams"]
            ):
                raise ValueError(
                    "گنجایش بسته‌بندی اصلی از وزن واحد کالا کمتر است."
                )

            existing_product = products.get(
                record["sku"].casefold()
            )

            if existing_product:
                active_profile = active_profiles.get(
                    existing_product.id
                )

                if active_profile:
                    primary_items = [
                        item
                        for item in active_profile.items
                        if item.is_primary
                    ]

                    if len(primary_items) != 1:
                        raise ValueError(
                            "پروفایل فعال کالا باید دقیقاً یک "
                            "بسته‌بندی اصلی داشته باشد."
                        )

                    primary_item = primary_items[0]
                    primary_material = primary_item.material

                    if (
                        primary_material is None
                        or primary_material.sku.strip().casefold()
                        != material_sku_key
                    ):
                        raise ValueError(
                            "کد بسته‌بندی اصلی فایل با پروفایل "
                            "فعال کالا یکسان نیست."
                        )

                    if (
                        float(primary_item.quantity_per_product) != 1.0
                        or primary_item.consumption_stage != "dispatch"
                        or primary_item.rounding_mode != "exact"
                    ):
                        raise ValueError(
                            "بسته‌بندی اصلی پروفایل فعال باید با "
                            "نسبت ۱، مرحله dispatch و روش exact باشد."
                        )

        except ValueError as exc:
            error_key = (record["excel_row"], str(exc))

            if error_key not in profile_validation_errors:
                profile_validation_errors.add(error_key)
                errors.append({
                    "sheet": "Inventory",
                    "row": record["excel_row"],
                    "field": "primary_packaging_sku",
                    "message": str(exc),
                })

    new_product_skus = {
        record["sku"].casefold()
        for record in inventory_records
        if record["sku"].casefold() not in products
    }

    new_batch_numbers = {
        record["batch_number"].casefold()
        for record in inventory_records
        if record["batch_number"].casefold() not in batches
    }

    new_material_skus = {
        record["sku"].casefold()
        for record in packaging_records
        if record["sku"].casefold() not in materials
    }

    summary = {
        "inventory_rows": len(inventory_records),
        "packaging_rows": len(packaging_records),
        "new_products": len(new_product_skus),
        "new_batches": len(new_batch_numbers),
        "new_packaging_materials": len(new_material_skus),
        "inventory_creates": sum(
            record["action"] == "create_inventory"
            for record in inventory_records
        ),
        "inventory_updates": sum(
            record["action"] == "update_inventory"
            for record in inventory_records
        ),
        "packaging_creates": sum(
            record["action"] == "create_packaging_inventory"
            for record in packaging_records
        ),
        "packaging_updates": sum(
            record["action"] == "update_packaging_inventory"
            for record in packaging_records
        ),
        "error_count": len(errors),
    }

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "summary": summary,
        "preview_rows": preview_rows[:200],
        "inventory_records": inventory_records,
        "packaging_records": packaging_records,
    }


def commit_workbook(
    db: Session,
    current_user: models.User,
    file_bytes: bytes,
) -> dict[str, Any]:
    validation = validate_workbook(db, file_bytes)

    if not validation["valid"]:
        return validation

    products = {
        product.sku.strip().casefold(): product
        for product in db.query(models.Product).all()
    }

    batches = {
        batch.batch_number.strip().casefold(): batch
        for batch in db.query(models.Batch).all()
    }

    warehouses = {
        warehouse.name.strip().casefold(): warehouse
        for warehouse in db.query(models.Warehouse).filter(
            models.Warehouse.is_active == True
        ).all()
    }

    materials = {
        material.sku.strip().casefold(): material
        for material in db.query(models.PackagingMaterial).all()
    }

    try:
        for record in validation["inventory_records"]:
            sku_key = record["sku"].casefold()
            batch_key = record["batch_number"].casefold()
            warehouse_key = record["warehouse_name"].casefold()

            product = products.get(sku_key)

            if not product:
                product = models.Product(
                    name=record["product_name"],
                    sku=record["sku"],
                    base_unit=record["base_unit"],
                    is_composite=record["is_composite"],
                    product_type=record["product_type"],
                    unit_weight_grams=record["unit_weight_grams"],
                )
                db.add(product)
                db.flush()
                products[sku_key] = product

            batch = batches.get(batch_key)

            if not batch:
                batch = models.Batch(
                    product_id=product.id,
                    batch_number=record["batch_number"],
                    production_date=(
                        record["production_date"] or datetime.utcnow()
                    ),
                    expiry_date=record["expiry_date"],
                )
                db.add(batch)
                db.flush()
                batches[batch_key] = batch

            warehouse = warehouses[warehouse_key]

            inventory = db.query(models.Inventory).filter(
                models.Inventory.warehouse_id == warehouse.id,
                models.Inventory.product_id == product.id,
                models.Inventory.batch_id == batch.id,
            ).with_for_update().first()

            if inventory:
                inventory.quantity = record["quantity"]
                inventory.reserved_quantity = record[
                    "reserved_quantity"
                ]
            else:
                db.add(models.Inventory(
                    warehouse_id=warehouse.id,
                    product_id=product.id,
                    batch_id=batch.id,
                    quantity=record["quantity"],
                    reserved_quantity=record["reserved_quantity"],
                ))

        for record in validation["packaging_records"]:
            sku_key = record["sku"].casefold()
            warehouse_key = record["warehouse_name"].casefold()

            material = materials.get(sku_key)

            if not material:
                material = models.PackagingMaterial(
                    name=record["material_name"],
                    sku=record["sku"],
                    material_type=record["material_type"],
                    capacity_grams=record["capacity_grams"],
                    description=record["description"],
                )
                db.add(material)
                db.flush()
                materials[sku_key] = material

            warehouse = warehouses[warehouse_key]

            inventory = db.query(
                models.PackagingInventory
            ).filter(
                models.PackagingInventory.warehouse_id == warehouse.id,
                models.PackagingInventory.material_id == material.id,
            ).with_for_update().first()

            if inventory:
                inventory.quantity = record["quantity"]
                inventory.reserved_quantity = record[
                    "reserved_quantity"
                ]
            else:
                db.add(models.PackagingInventory(
                    warehouse_id=warehouse.id,
                    material_id=material.id,
                    quantity=record["quantity"],
                    reserved_quantity=record["reserved_quantity"],
                ))


        profile_definitions = {}

        for record in validation["inventory_records"]:
            profile_definitions[
                record["sku"].casefold()
            ] = record["primary_packaging_sku"].casefold()

        for product_sku_key, material_sku_key in (
            profile_definitions.items()
        ):
            product = products[product_sku_key]
            material = materials[material_sku_key]

            profiles = db.query(
                models.PackagingProfile
            ).filter(
                models.PackagingProfile.product_id == product.id
            ).with_for_update().all()

            active_profile = next(
                (
                    profile
                    for profile in profiles
                    if profile.is_active
                ),
                None,
            )

            if active_profile is None:
                next_version = (
                    max(
                        (
                            profile.version
                            for profile in profiles
                        ),
                        default=0,
                    )
                    + 1
                )

                active_profile = models.PackagingProfile(
                    product_id=product.id,
                    name=(
                        "پروفایل خودکار ورود Excel - "
                        f"{product.sku}"
                    ),
                    version=next_version,
                    is_active=True,
                )
                db.add(active_profile)
                db.flush()

                db.add(models.PackagingProfileItem(
                    profile_id=active_profile.id,
                    material_id=material.id,
                    quantity_per_product=1,
                    component_type=material.material_type,
                    consumption_stage="dispatch",
                    rounding_mode="exact",
                    is_primary=True,
                ))

            product.packaging_material_id = material.id

        db.add(models.AuditLog(
            action="INVENTORY_EXCEL_IMPORT",
            user_id=current_user.id,
            details=(
                f"ورود Excel موجودی: "
                f"{validation['summary']['inventory_rows']} ردیف کالا و "
                f"{validation['summary']['packaging_rows']} ردیف بسته‌بندی."
            ),
        ))

        db.commit()

        return {
            "valid": True,
            "message": "اطلاعات Excel با موفقیت ثبت شد.",
            "summary": validation["summary"],
        }

    except Exception:
        db.rollback()
        raise