import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from bson import ObjectId

from database import db
from database import create_document, get_documents
from schemas import Invoice

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    
    try:
        # Try to import database module
        from database import db
        
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            
            # Try to list collections to verify connectivity
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]  # Show first 10 collections
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
            
    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    
    # Check environment variables
    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    
    return response

# Utility to convert Mongo ObjectId to str recursively

def serialize_doc(doc: dict):
    if not doc:
        return doc
    if doc.get("_id"):
        doc["id"] = str(doc.pop("_id"))
    return doc

# Request model for creating/updating invoice (without timestamps)
class InvoiceCreate(BaseModel):
    invoice_no: str
    customer: str
    item_name: str
    surat_jalan_no: str
    quantity: int
    price: float

class InvoiceUpdate(BaseModel):
    # Primary key (invoice_no) is not updatable
    customer: Optional[str] = None
    item_name: Optional[str] = None
    surat_jalan_no: Optional[str] = None
    quantity: Optional[int] = None
    price: Optional[float] = None

TAX_RATE = 0.11

def compute_tax_and_total(quantity: int, price: float):
    subtotal = quantity * price
    tax = round(subtotal * TAX_RATE, 2)
    total = round(subtotal + tax, 2)
    return tax, total

@app.post("/api/invoices")
async def create_invoice(payload: InvoiceCreate):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    
    # Compute totals
    tax, total = compute_tax_and_total(payload.quantity, payload.price)

    # Prepare document with custom primary key (_id = invoice_no)
    invoice = Invoice(
        invoice_no=payload.invoice_no,
        customer=payload.customer,
        item_name=payload.item_name,
        surat_jalan_no=payload.surat_jalan_no,
        quantity=payload.quantity,
        price=payload.price,
        tax=tax,
        total=total,
    )
    data = invoice.model_dump()
    data["_id"] = payload.invoice_no  # make invoice_no the primary key

    # Insert and handle duplicate key as 409 Conflict
    try:
        result = db["invoice"].insert_one(data)
    except Exception as e:
        if "E11000" in str(e):
            raise HTTPException(status_code=409, detail="Invoice number already exists")
        raise

    doc = db["invoice"].find_one({"_id": payload.invoice_no})
    return serialize_doc(doc)

@app.get("/api/invoices")
async def list_invoices():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    docs = get_documents("invoice")
    return [serialize_doc(d) for d in docs]

@app.get("/api/invoices/{invoice_no}")
async def get_invoice(invoice_no: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    doc = db["invoice"].find_one({"_id": invoice_no})
    if not doc:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return serialize_doc(doc)

@app.put("/api/invoices/{invoice_no}")
async def update_invoice(invoice_no: str, payload: InvoiceUpdate):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    existing = db["invoice"].find_one({"_id": invoice_no})
    if not existing:
        raise HTTPException(status_code=404, detail="Invoice not found")

    update_data = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    # If quantity or price updated, recompute tax and total based on newest values
    q = update_data.get("quantity", existing.get("quantity"))
    p = update_data.get("price", existing.get("price"))
    tax, total = compute_tax_and_total(q, p)
    update_data["tax"] = tax
    update_data["total"] = total

    update_data["updated_at"] = __import__('datetime').datetime.utcnow()

    result = db["invoice"].update_one({"_id": invoice_no}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")

    doc = db["invoice"].find_one({"_id": invoice_no})
    return serialize_doc(doc)

@app.delete("/api/invoices/{invoice_no}")
async def delete_invoice(invoice_no: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    result = db["invoice"].delete_one({"_id": invoice_no})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"deleted": True, "invoice_no": invoice_no}
