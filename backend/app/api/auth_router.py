# app/api/auth_router.py
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.domain import models
from app import security
from app.api.transfer_router import get_current_user


router = APIRouter(
    prefix="/auth",
    tags=["Authentication & Users"]
)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str
    warehouse_id: Optional[int] = None


def authenticate_user(username: str, password: str, db: Session):
    user = db.query(models.User).filter(
        models.User.username == username
    ).first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="نام کاربری یا رمز عبور نادرست است."
        )

    if not security.verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="نام کاربری یا رمز عبور نادرست است."
        )

    return user


def build_login_response(user: models.User):
    access_token = security.create_access_token(
        data={
            "sub": user.username,
            "role": user.role,
            "warehouse_id": user.warehouse_id
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "warehouse_id": user.warehouse_id,
        "username": user.username
    }


def require_admin(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="فقط مدیر ارشد مجاز به انجام این عملیات است."
        )
    return current_user


@router.post("/login")
def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    user = authenticate_user(request.username, request.password, db)
    return build_login_response(user)


@router.post("/token")
def swagger_token_login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = authenticate_user(form_data.username, form_data.password, db)
    return build_login_response(user)


@router.get("/me")
def get_me(
    current_user: models.User = Depends(get_current_user)
):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "warehouse_id": current_user.warehouse_id,
        "is_active": current_user.is_active
    }


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    request: UserCreateRequest,
    db: Session = Depends(get_db),
    _=Depends(require_admin)
):
    if request.role not in ["admin", "warehouse_manager"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="نقش کاربر فقط می‌تواند admin یا warehouse_manager باشد."
        )

    if len(request.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="رمز عبور باید حداقل ۸ کاراکتر باشد."
        )

    existing_user = db.query(models.User).filter(
        models.User.username == request.username
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="این نام کاربری از قبل وجود دارد."
        )

    if request.role == "warehouse_manager":
        if not request.warehouse_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="برای انباردار باید warehouse_id مشخص شود."
            )

        warehouse = db.query(models.Warehouse).filter(
            models.Warehouse.id == request.warehouse_id,
            models.Warehouse.is_active == True
        ).first()

        if not warehouse:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="انبار انتخاب‌شده یافت نشد یا غیرفعال است."
            )

    new_user = models.User(
        username=request.username,
        hashed_password=security.get_password_hash(request.password),
        role=request.role,
        warehouse_id=request.warehouse_id if request.role == "warehouse_manager" else None,
        is_active=True
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "کاربر با موفقیت ساخته شد.",
        "user_id": new_user.id,
        "username": new_user.username,
        "role": new_user.role,
        "warehouse_id": new_user.warehouse_id
    }


@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    _=Depends(require_admin)
):
    users = db.query(models.User).order_by(models.User.id.asc()).all()

    return [
        {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "warehouse_id": user.warehouse_id,
            "is_active": user.is_active,
            "created_at": user.created_at
        }
        for user in users
    ]




# USER_MANAGEMENT_API_20260731
class UserUpdateRequest(BaseModel):
    role: Optional[str] = None
    warehouse_id: Optional[int] = None
    is_active: Optional[bool] = None


class PasswordResetRequest(BaseModel):
    new_password: str


def _validate_user_assignment(
    db: Session,
    role: str,
    warehouse_id: Optional[int]
):
    if role not in ["admin", "warehouse_manager"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="نقش کاربر نامعتبر است."
        )

    if role == "warehouse_manager":
        if not warehouse_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="برای انباردار باید یک انبار انتخاب شود."
            )

        warehouse = db.query(models.Warehouse).filter(
            models.Warehouse.id == warehouse_id,
            models.Warehouse.is_active == True
        ).first()

        if not warehouse:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="انبار انتخاب‌شده یافت نشد یا غیرفعال است."
            )


@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    request: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin)
):
    user = db.get(models.User, user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="کاربر یافت نشد."
        )

    new_role = request.role if request.role is not None else user.role
    new_active = (
        request.is_active
        if request.is_active is not None
        else user.is_active
    )
    new_warehouse_id = (
        request.warehouse_id
        if request.warehouse_id is not None
        else user.warehouse_id
    )

    if user.id == current_admin.id and (
        new_role != "admin" or not new_active
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="مدیر واردشده نمی‌تواند حساب یا نقش خودش را غیرفعال کند."
        )

    if new_role == "admin":
        new_warehouse_id = None

    _validate_user_assignment(
        db,
        new_role,
        new_warehouse_id
    )

    user.role = new_role
    user.warehouse_id = new_warehouse_id
    user.is_active = new_active

    db.commit()
    db.refresh(user)

    return {
        "message": "اطلاعات کاربر با موفقیت به‌روزرسانی شد.",
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "warehouse_id": user.warehouse_id,
        "is_active": user.is_active
    }


@router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    request: PasswordResetRequest,
    db: Session = Depends(get_db),
    _=Depends(require_admin)
):
    if len(request.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="رمز عبور باید حداقل ۸ کاراکتر باشد."
        )

    user = db.get(models.User, user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="کاربر یافت نشد."
        )

    user.hashed_password = security.get_password_hash(
        request.new_password
    )

    db.commit()

    return {
        "message": "رمز عبور کاربر با موفقیت بازنشانی شد."
    }


@router.post("/setup-admin", include_in_schema=False)
def setup_initial_admin(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    if os.getenv("ALLOW_SETUP_ADMIN", "false").lower() != "true":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup admin endpoint is disabled."
        )

    admin_exists = db.query(models.User).filter(
        models.User.role == "admin"
    ).first()

    if admin_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="کاربر مدیر ارشد قبلاً در سیستم تعریف شده است."
        )

    if len(request.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="رمز عبور باید حداقل ۸ کاراکتر باشد."
        )

    new_admin = models.User(
        username=request.username,
        hashed_password=security.get_password_hash(request.password),
        role="admin",
        warehouse_id=None,
        is_active=True
    )

    db.add(new_admin)
    db.commit()

    return {
        "message": "حساب ادمین اولیه با موفقیت ساخته شد."
    }
