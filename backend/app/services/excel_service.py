import pandas as pd
from sqlalchemy.orm import Session
from app.repositories.product_repository import ProductRepository
from app.schemas.schemas import ProductCreate

class ExcelImportService:
    def __init__(self, db: Session):
        self.db = db
        self.product_repo = ProductRepository(db)

    def import_products_from_excel(self, file_path: str):
        try:
            # خواندن فایل اکسل
            df = pd.read_excel(file_path)
            
            # مپ کردن (تطبیق) نام ستون‌های اکسل به فیلدهای Pydantic
            column_mapping = {
                "Name": "name",
                "SKU": "sku",  # <<< تغییر از ItemCode به SKU
                "BaseUnit": "base_unit",
                "IsComposite": "is_composite",
                "ProductType": "product_type" # <<< اضافه شد: نوع محصول را هم وارد می‌کنیم
            }
            df.rename(columns=column_mapping, inplace=True)
            
            # تبدیل مقادیر NaN به None برای جلوگیری از خطا
            df = df.where(pd.notnull(df), None)
            
            # در صورتی که ستون is_composite خالی بود، False در نظر بگیر
            if "is_composite" in df.columns:
                df["is_composite"] = df["is_composite"].fillna(False)

            # اطمینان از اینکه product_type خالی نماند
            if "product_type" not in df.columns or df["product_type"].isnull().any():
                 return {
                    "status": "error", 
                    "message": "ستون 'ProductType' در فایل اکسل وجود ندارد یا دارای مقادیر خالی است. مقادیر مجاز: 'raw_material' یا 'finished_good'."
                }
            
            records = df.to_dict(orient="records")
            imported_count = 0
            
            for row in records:
                # اگر محصول از قبل با این sku وجود نداشت، آن را بساز
                # <<< تغییر از get_by_item_code به get_by_sku و استفاده از row["sku"]
                existing = self.product_repo.get_by_sku(row["sku"])
                if not existing:
                    product_data = ProductCreate(**row)
                    self.product_repo.create(product_data)
                    imported_count += 1
                    
            return {
                "status": "success", 
                "message": f"{imported_count} محصول با موفقیت وارد دیتابیس شد."
            }
            
        except FileNotFoundError:
            return {"status": "error", "message": f"فایل {file_path} پیدا نشد."}
        except Exception as e:
            # برگرداندن خطای دقیق‌تر برای دیباگ
            return {"status": "error", "message": f"خطا در پردازش اکسل: {str(e)}"}
