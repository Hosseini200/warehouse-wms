# app/domain/models.py
from sqlalchemy import Column, Integer, String, Boolean, Float, Numeric, ForeignKey, DateTime, Text, UniqueConstraint, CheckConstraint, Index, text
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import enum

# کلاس پایه واحد برای ثبت و نگاشت جداول سیستم به SQLAlchemy
Base = declarative_base()

class TransferStatus(str, enum.Enum):
    DRAFT = "draft"                                 # ثبت اولیه توسط انبار مبدأ
    PENDING_SOURCE_APPROVAL = "pending_source_approval" # در انتظار تایید ۲۴ ساعته انبار مبدأ
    PENDING_DESTINATION = "pending_destination"         # تایید شده توسط مبدأ، در راه مقصد
    DISPUTED = "disputed"                               # دارای مغایرت و در حال مذاکره/تیکت
    CONFIRMED = "confirmed"                             # تایید نهایی و قطعی شده (موجوبی جابجا شد)
    REJECTED = "rejected"                               # لغو یا رد شده
    EXPIRED = "expired"                                 # منقضی شده به دلیل عدم اقدام در ۲۴ ساعت

class TicketStatus(str, enum.Enum):
    OPEN = "open"                                       # تیکت باز بین انبار ۱ و ۲
    ESCALATED_TO_ADMIN = "escalated_to_admin"           # ارجاع خودکار یا دستی به مدیریت
    RESOLVED = "resolved"                               # حل شده و بسته

class Warehouse(Base):
    """مدل انبارها"""
    __tablename__ = "warehouses"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    location = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    manager_name = Column(String, nullable=True)
    
    # روابط (Relationships)
    inventories = relationship("Inventory", back_populates="warehouse")
    transfers_out = relationship("Transfer", foreign_keys="[Transfer.source_warehouse_id]", back_populates="source_warehouse")
    transfers_in = relationship("Transfer", foreign_keys="[Transfer.destination_warehouse_id]", back_populates="destination_warehouse")
    packaging_inventories = relationship("PackagingInventory", back_populates="warehouse")


class PackagingMaterial(Base):
    """
    مورد تاکید کارفرما: مدل ملزومات و ظروف بسته‌بندی (مانند شیشه ۵۰۰ گرمی، قوطی ۲۰۰ گرمی و...)
    جهت کنترل ضایعات و ملوگیری از خرابی و مفقودی ظروف
    """
    __tablename__ = "packaging_materials"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    sku = Column(String(50), unique=True, index=True, nullable=False)
    capacity_grams = Column(Float, nullable=True)  # گنجایش ظرف به گرم (مثلاً ۵۰۰ یا ۲۰۰)
    description = Column(Text, nullable=True)
    material_type = Column(String(30), default="container", nullable=False)
    
    # روابط (Relationships)
    products = relationship("Product", back_populates="packaging_material")
    inventories = relationship("PackagingInventory", back_populates="material")

    __table_args__ = (
        CheckConstraint(
            "material_type IN ('container', 'lid', 'label', 'inner_box', 'carton', 'pallet', 'other')",
            name="ck_packaging_material_type"
        ),
    )


class PackagingInventory(Base):
    """جدول کنترل موجودی ملزومات بسته‌بندی به تفکیک هر انبار"""
    __tablename__ = "packaging_inventory"
    
    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    material_id = Column(Integer, ForeignKey("packaging_materials.id"), nullable=False)
    quantity = Column(Integer, default=0, nullable=False)          # تعداد ظروف موجود و سالم در انبار
    reserved_quantity = Column(Integer, default=0, nullable=False) # تعداد ظروف رزرو شده در حواله‌های معلق
    
    # روابط (Relationships)
    warehouse = relationship("Warehouse", back_populates="packaging_inventories")
    material = relationship("PackagingMaterial", back_populates="inventories")
    
    # تضمین عدم هم‌پوشانی رکوردها
    __table_args__ = (UniqueConstraint('warehouse_id', 'material_id', name='_warehouse_packaging_uc'),)

class PackagingAdjustment(Base):
    """
    ثبت مصرف، کسری، خرابی یا مفقودی ملزومات بسته‌بندی.
    این جدول برای گزارش خسارت ابزار بسته‌بندی و ردیابی مصرف در تولید استفاده می‌شود.
    """
    __tablename__ = "packaging_adjustments"

    id = Column(Integer, primary_key=True, index=True)

    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    material_id = Column(Integer, ForeignKey("packaging_materials.id"), nullable=False)

    quantity = Column(Integer, nullable=False)

    # production_usage, damaged, lost, manual_increase, manual_decrease
    action_type = Column(String(50), nullable=False)

    # production, admin_adjustment, audit, other
    reference_type = Column(String(50), nullable=True)
    reference_id = Column(Integer, nullable=True)

    reason = Column(Text, nullable=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    warehouse = relationship("Warehouse")
    material = relationship("PackagingMaterial")
    user = relationship("User")
    
class Product(Base):
    """مدل اطلاعات پایه کالاها - اصلاح شده جهت پشتیبانی از ملزومات بسته‌بندی"""
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    sku = Column(String(50), unique=True, index=True, nullable=False)
    base_unit = Column(String(20), nullable=False)  # عدد، گرم، کیلوگرم
    is_composite = Column(Boolean, default=False)   # آیا محصول ترکیبی و فرمول‌دار است؟ (مثل حنای عسلی)
    product_type = Column(String(50), nullable=True) # raw_material, finished_good
    
    # ارتباط محصول با ظرف بسته‌بندی پیش‌فرض خود
    packaging_material_id = Column(Integer, ForeignKey("packaging_materials.id"), nullable=True)
    unit_weight_grams = Column(Float, default=0.0, nullable=True) # وزن خالص هر واحد محصول به گرم برای محاسبات فرمولاسیون پودری
    
    # روابط (Relationships)
    batches = relationship("Batch", back_populates="product")
    inventories = relationship("Inventory", back_populates="product")
    packaging_material = relationship("PackagingMaterial", back_populates="products")
    packaging_profiles = relationship(
        "PackagingProfile",
        back_populates="product",
        cascade="all, delete-orphan"
    )
    
    # روابط مربوط به فرمولاسیون (BOM)
    recipes_as_final = relationship("Recipe", foreign_keys="[Recipe.final_product_id]", back_populates="final_product")
    recipes_as_ingredient = relationship("Recipe", foreign_keys="[Recipe.ingredient_id]", back_populates="ingredient")


class Batch(Base):
    """مدل سری ساخت دارویی/غذایی"""
    __tablename__ = "batches"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    batch_number = Column(String(50), unique=True, index=True, nullable=False)
    production_date = Column(DateTime, nullable=True)
    expiry_date = Column(DateTime, nullable=False)
    
    # روابط (Relationships)
    product = relationship("Product", back_populates="batches")
    transfers = relationship("Transfer", back_populates="batch")
    inventories = relationship("Inventory", back_populates="batch")


class Inventory(Base):
    """جدول موجودی انبارها - همراه با منطق رزرویشن بار برای چرخه‌های زمان‌دار"""
    __tablename__ = "inventories"
    
    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    quantity = Column(Float, default=0.0, nullable=False)          # موجودی فیزیکی واقعی انبار
    reserved_quantity = Column(Float, default=0.0, nullable=False) # موجودی رزرو شده در حواله‌های معلق
    
    # روابط (Relationships)
    warehouse = relationship("Warehouse", back_populates="inventories")
    product = relationship("Product", back_populates="inventories")
    batch = relationship("Batch", back_populates="inventories")
    
    # تضمین اینکه برای یک کالا با یک بچ خاص در یک انبار فقط یک سطر موجودی داشته باشیم
    __table_args__ = (UniqueConstraint('warehouse_id', 'product_id', 'batch_id', name='_warehouse_product_batch_uc'),)


class Transfer(Base):
    """مدل حواله جابجایی بین انبارها"""
    __tablename__ = "transfers"
    
    id = Column(Integer, primary_key=True, index=True)
    source_warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    destination_warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    
    status = Column(String(50), default="pending_source_approval", nullable=False)
    description = Column(Text, nullable=True)
    
    # فیلدهای زمانی حساس کنترل مهلت‌ها و پیگیری‌ها
    source_approved_at = Column(DateTime, nullable=True)     # زمان تایید نهایی توسط انبار مبدأ
    tracking_deadline = Column(DateTime, nullable=True)      # ضرب‌الاجل ۲۴ ساعته برای تایید یا پیگیری خودکار
    dispute_deadline = Column(DateTime, nullable=True)       # ضرب‌الاجل ۲۴ ساعته تیکت پیش از ارجاع خودکار به مدیریت
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # روابط (Relationships)
    source_warehouse = relationship("Warehouse", foreign_keys=[source_warehouse_id], back_populates="transfers_out")
    destination_warehouse = relationship("Warehouse", foreign_keys=[destination_warehouse_id], back_populates="transfers_in")
    product = relationship("Product")
    batch = relationship("Batch", back_populates="transfers")
    dispute = relationship("Dispute", back_populates="transfer", uselist=False)
    tickets = relationship("TransferTicket", back_populates="transfer")
    packaging_items = relationship(
        "TransferPackagingItem",
        back_populates="transfer",
        cascade="all, delete-orphan"
    )


class Dispute(Base):
    """مدل ثبت مغایرت در دریافت کالا"""
    __tablename__ = "disputes"
    
    id = Column(Integer, primary_key=True, index=True)
    transfer_id = Column(Integer, ForeignKey("transfers.id"), unique=True, nullable=False)
    reported_quantity = Column(Float, nullable=False)  # مقداری که واقعاً در مقصد دریافت شده
    missing_amount = Column(Float, nullable=False)     # مقدار کسری کالا
    reason = Column(Text, nullable=True)
    status = Column(String(20), default="OPEN", nullable=False)  # OPEN, RESOLVED
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # روابط (Relationships)
    transfer = relationship("Transfer", back_populates="dispute")


class TransferTicket(Base):
    """سیستم تیکتینگ و گفتگوی بین انبارها برای حل مغایرت یا ارجاع به مدیریت"""
    __tablename__ = "transfer_tickets"
    
    id = Column(Integer, primary_key=True, index=True)
    transfer_id = Column(Integer, ForeignKey("transfers.id"), nullable=False)
    status = Column(String(50), default="open", nullable=False)
    title = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # روابط (Relationships)
    transfer = relationship("Transfer", back_populates="tickets")
    messages = relationship("TicketMessage", back_populates="ticket", cascade="all, delete-orphan")


class TicketMessage(Base):
    """پیام‌های ثبت شده در تیکت توسط انبار مبدأ، انبار مقصد یا مدیریت کل"""
    __tablename__ = "ticket_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("transfer_tickets.id"), nullable=False)
    sender_role = Column(String(50), nullable=False)   # مقادیر: source_warehouse, destination_warehouse, admin
    sender_name = Column(String(100), nullable=True)
    message_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # روابط (Relationships)
    ticket = relationship("TransferTicket", back_populates="messages")


class Recipe(Base):
    """
    مدل فرمولاسیون و ساختار محصول (BOM)
    اصلاح شده بر اساس درصد ترکیب یا مقدار ثابت فیزیکی (مانند ۳۰ درصد عسل و ۷۰ درصد حنا)
    """
    __tablename__ = "recipes"
    
    id = Column(Integer, primary_key=True, index=True)
    final_product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    ingredient_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    percentage = Column(Float, nullable=False)  # درصد سهم ماده اولیه از کل محصول (مثلاً ۳۰.۰ برای عسل)
    
    # روابط (Relationships)
    final_product = relationship("Product", foreign_keys=[final_product_id], back_populates="recipes_as_final")
    ingredient = relationship("Product", foreign_keys=[ingredient_id], back_populates="recipes_as_ingredient")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    action = Column(String(100), nullable=False)
    transfer_id = Column(Integer, ForeignKey("transfers.id"), nullable=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    details = Column(Text, nullable=True)
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    
    # نقش کاربر: می تواند 'admin' (کارفرما)، یا 'warehouse_manager' (انباردار) باشد
    role = Column(String, default="warehouse_manager", nullable=False)
    
    # اتصال کاربر به یک انبار خاص (اگر ادمین باشد این فیلد می تواند Null یا خالی باشد)
    # توجه: نام جدول انبار را متمایز با کد خودت چک کن (احتمالاً warehouses است)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True) 
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
class PackagingProfile(Base):
    __tablename__ = "packaging_profiles"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False
    )
    name = Column(String(150), nullable=False)
    version = Column(Integer, default=1, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    effective_from = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    product = relationship(
        "Product",
        back_populates="packaging_profiles"
    )
    items = relationship(
        "PackagingProfileItem",
        back_populates="profile",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "version > 0",
            name="ck_packaging_profile_version"
        ),
        UniqueConstraint(
            "product_id",
            "version",
            name="uq_packaging_profile_product_version"
        ),
        Index(
            "uq_packaging_profile_active_product",
            "product_id",
            unique=True,
            postgresql_where=text("is_active = TRUE")
        ),
    )


class PackagingProfileItem(Base):
    __tablename__ = "packaging_profile_items"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(
        Integer,
        ForeignKey("packaging_profiles.id", ondelete="CASCADE"),
        nullable=False
    )
    material_id = Column(
        Integer,
        ForeignKey("packaging_materials.id", ondelete="RESTRICT"),
        nullable=False
    )
    quantity_per_product = Column(Numeric(14, 6), nullable=False)
    component_type = Column(
        String(30),
        default="container",
        nullable=False
    )
    consumption_stage = Column(
        String(30),
        default="production",
        nullable=False
    )
    rounding_mode = Column(
        String(20),
        default="exact",
        nullable=False
    )
    is_primary = Column(Boolean, default=False, nullable=False)
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    profile = relationship(
        "PackagingProfile",
        back_populates="items"
    )
    material = relationship("PackagingMaterial")

    __table_args__ = (
        CheckConstraint(
            "quantity_per_product > 0",
            name="ck_packaging_profile_item_quantity"
        ),
        CheckConstraint(
            "component_type IN ('container', 'lid', 'label', 'inner_box', 'carton', 'pallet', 'other')",
            name="ck_packaging_component_type"
        ),
        CheckConstraint(
            "consumption_stage IN ('production', 'dispatch')",
            name="ck_packaging_consumption_stage"
        ),
        CheckConstraint(
            "rounding_mode IN ('exact', 'ceil')",
            name="ck_packaging_rounding_mode"
        ),
        UniqueConstraint(
            "profile_id",
            "material_id",
            name="uq_packaging_profile_material"
        ),
        Index(
            "ix_packaging_profile_items_profile_id",
            "profile_id"
        ),
        Index(
            "ix_packaging_profile_items_material_id",
            "material_id"
        ),
    )


class ProductionRun(Base):
    __tablename__ = "production_runs"

    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(
        Integer,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False
    )
    final_product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False
    )
    batch_id = Column(
        Integer,
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=True
    )
    packaging_profile_id = Column(
        Integer,
        ForeignKey("packaging_profiles.id", ondelete="SET NULL"),
        nullable=True
    )
    produce_quantity = Column(Float, nullable=False)
    status = Column(
        String(30),
        default="completed",
        nullable=False
    )
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    warehouse = relationship("Warehouse")
    final_product = relationship("Product")
    batch = relationship("Batch")
    packaging_profile = relationship("PackagingProfile")
    created_by_user = relationship("User")

    ingredients = relationship(
        "ProductionRunIngredient",
        back_populates="production_run",
        cascade="all, delete-orphan"
    )
    packaging_items = relationship(
        "ProductionRunPackagingItem",
        back_populates="production_run",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "produce_quantity > 0",
            name="ck_production_run_quantity"
        ),
        CheckConstraint(
            "status IN ('draft', 'completed', 'cancelled')",
            name="ck_production_run_status"
        ),
    )


class ProductionRunIngredient(Base):
    __tablename__ = "production_run_ingredients"

    id = Column(Integer, primary_key=True, index=True)
    production_run_id = Column(
        Integer,
        ForeignKey("production_runs.id", ondelete="CASCADE"),
        nullable=False
    )
    ingredient_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False
    )
    percentage = Column(Float, nullable=False)
    required_quantity = Column(Float, nullable=False)
    consumed_quantity = Column(Float, nullable=False)

    production_run = relationship(
        "ProductionRun",
        back_populates="ingredients"
    )
    ingredient = relationship("Product")

    __table_args__ = (
        CheckConstraint(
            "percentage > 0 AND percentage <= 100",
            name="ck_production_ingredient_percentage"
        ),
        CheckConstraint(
            "required_quantity >= 0",
            name="ck_production_ingredient_required"
        ),
        CheckConstraint(
            "consumed_quantity >= 0",
            name="ck_production_ingredient_consumed"
        ),
    )


class ProductionRunPackagingItem(Base):
    __tablename__ = "production_run_packaging_items"

    id = Column(Integer, primary_key=True, index=True)
    production_run_id = Column(
        Integer,
        ForeignKey("production_runs.id", ondelete="CASCADE"),
        nullable=False
    )
    material_id = Column(
        Integer,
        ForeignKey("packaging_materials.id", ondelete="RESTRICT"),
        nullable=False
    )
    quantity_per_product = Column(Numeric(14, 6), nullable=False)
    required_quantity = Column(Integer, nullable=False)
    consumed_quantity = Column(Integer, nullable=False)

    production_run = relationship(
        "ProductionRun",
        back_populates="packaging_items"
    )
    material = relationship("PackagingMaterial")

    __table_args__ = (
        CheckConstraint(
            "quantity_per_product > 0",
            name="ck_production_packaging_ratio"
        ),
        CheckConstraint(
            "required_quantity >= 0",
            name="ck_production_packaging_required"
        ),
        CheckConstraint(
            "consumed_quantity >= 0",
            name="ck_production_packaging_consumed"
        ),
        UniqueConstraint(
            "production_run_id",
            "material_id",
            name="uq_production_run_packaging_material"
        ),
    )


class TransferPackagingItem(Base):
    __tablename__ = "transfer_packaging_items"

    id = Column(Integer, primary_key=True, index=True)
    transfer_id = Column(
        Integer,
        ForeignKey("transfers.id", ondelete="CASCADE"),
        nullable=False
    )
    packaging_profile_id = Column(
        Integer,
        ForeignKey("packaging_profiles.id", ondelete="SET NULL"),
        nullable=True
    )
    material_id = Column(
        Integer,
        ForeignKey("packaging_materials.id", ondelete="RESTRICT"),
        nullable=False
    )

    material_name_snapshot = Column(String(150), nullable=False)
    material_sku_snapshot = Column(String(50), nullable=False)
    profile_version_snapshot = Column(Integer, nullable=True)

    quantity_per_product = Column(Numeric(14, 6), nullable=False)
    consumption_stage_snapshot = Column(String(30), nullable=False)
    rounding_mode_snapshot = Column(String(20), nullable=False)

    required_quantity = Column(Integer, nullable=False)
    reserved_quantity = Column(Integer, default=0, nullable=False)
    issued_quantity = Column(Integer, default=0, nullable=False)
    received_quantity = Column(Integer, default=0, nullable=False)
    damaged_quantity = Column(Integer, default=0, nullable=False)
    missing_quantity = Column(Integer, default=0, nullable=False)

    status = Column(
        String(30),
        default="planned",
        nullable=False
    )
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    transfer = relationship(
        "Transfer",
        back_populates="packaging_items"
    )
    packaging_profile = relationship("PackagingProfile")
    material = relationship("PackagingMaterial")

    __table_args__ = (
        CheckConstraint(
            "quantity_per_product > 0",
            name="ck_transfer_packaging_ratio"
        ),
        CheckConstraint(
            "consumption_stage_snapshot IN ('production', 'dispatch')",
            name="ck_transfer_packaging_stage"
        ),
        CheckConstraint(
            "rounding_mode_snapshot IN ('exact', 'ceil')",
            name="ck_transfer_packaging_rounding"
        ),
        CheckConstraint(
            "required_quantity >= 0 AND reserved_quantity >= 0 "
            "AND issued_quantity >= 0 AND received_quantity >= 0 "
            "AND damaged_quantity >= 0 AND missing_quantity >= 0",
            name="ck_transfer_packaging_quantities"
        ),
        CheckConstraint(
            "status IN ('planned', 'reserved', 'issued', 'received', 'disputed', 'released')",
            name="ck_transfer_packaging_status"
        ),
        UniqueConstraint(
            "transfer_id",
            "material_id",
            name="uq_transfer_packaging_material"
        ),
        Index(
            "ix_transfer_packaging_items_transfer_id",
            "transfer_id"
        ),
        Index(
            "ix_transfer_packaging_items_material_id",
            "material_id"
        ),
    )
