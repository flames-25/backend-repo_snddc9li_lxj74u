"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional

# Example schemas (you can keep or remove if not needed by your app)

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product" (lowercase of class name)
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in currency units")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")

# Application-specific schema: Invoice

class Invoice(BaseModel):
    """
    Invoice collection schema
    Collection name: "invoice"
    """
    invoice_no: str = Field(..., description="Nomor Invoice (primary key)")
    customer: str = Field(..., description="Nama Customer")
    item_name: str = Field(..., description="Nama Barang")
    surat_jalan_no: str = Field(..., description="Nomor Surat Jalan")
    quantity: int = Field(..., ge=0, description="Quantity")
    price: float = Field(..., ge=0, description="Harga per unit")
    tax_rate: float = Field(11, ge=0, description="PPN dalam persen, contoh 11 untuk 11%")
    tax: float = Field(..., ge=0, description="Nilai PPN (rupiah) yang dihitung otomatis")
    total: float = Field(..., ge=0, description="Total harga (qty * price + tax)")
