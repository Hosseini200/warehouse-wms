#app.schemas.product.py
from pydantic import BaseModel, Field
from datetime import date

class ProductBase(BaseModel):
    item_code: str = Field(..., example="DRC-1001")
    name: str = Field(..., example="قرص جوشان ویتامین ث 1000")
    category: str = Field(..., example="Vitamins")
    base_unit: str = Field(..., example="Box")
    unit_price: float = Field(..., gt=0)
    expiration_date: date

class ProductCreate(ProductBase):
    pass

class ProductResponse(ProductBase):
    id: int

    class Config:
        from_attributes = True # جایگزین orm_mode در Pydantic V2
