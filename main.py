import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from database import db
from database import get_documents
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
        from database import db as _db
        if _db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = _db.name if hasattr(_db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = _db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except ImportError:
        response["database"] = "❌ Database module not found"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    return response

# Utility to convert Mongo _id to id

def serialize_doc(doc: dict):
    if not doc:
        return doc
    if doc.get("_id"):
        doc["id"] = str(doc.pop("_id"))
    return doc

# Request models
class InvoiceCreate(BaseModel):
    invoice_no: str
    customer: str
    item_name: str
    surat_jalan_no: str
    quantity: int
    price: float
    tax_rate: float  # percentage, e.g., 11 for 11%

class InvoiceUpdate(BaseModel):
    # Allow editing primary key by providing a new invoice_no
    invoice_no: Optional[str] = None
    customer: Optional[str] = None
    item_name: Optional[str] = None
    surat_jalan_no: Optional[str] = None
    quantity: Optional[int] = None
    price: Optional[float] = None
    tax_rate: Optional[float] = None  # percentage


def compute_tax_and_total(quantity: int, price: float, tax_rate_percent: float):
    subtotal = quantity * price
    tax = round(subtotal * (tax_rate_percent / 100.0), 2)
    total = round(subtotal + tax, 2)
    return tax, total

@app.post("/api/invoices")
async def create_invoice(payload: InvoiceCreate):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    tax, total = compute_tax_and_total(payload.quantity, payload.price, payload.tax_rate)

    invoice = Invoice(
        invoice_no=payload.invoice_no,
        customer=payload.customer,
        item_name=payload.item_name,
        surat_jalan_no=payload.surat_jalan_no,
        quantity=payload.quantity,
        price=payload.price,
        tax_rate=payload.tax_rate,
        tax=tax,
        total=total,
    )
    data = invoice.model_dump()
    data["_id"] = payload.invoice_no  # primary key

    try:
        db["invoice"].insert_one(data)
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

@app.put("/api/invoices/{current_invoice_no}")
async def update_invoice(current_invoice_no: str, payload: InvoiceUpdate):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    existing = db["invoice"].find_one({"_id": current_invoice_no})
    if not existing:
        raise HTTPException(status_code=404, detail="Invoice not found")

    update_data = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}

    # Determine latest values for computation
    q = update_data.get("quantity", existing.get("quantity"))
    p = update_data.get("price", existing.get("price"))
    tr = update_data.get("tax_rate", existing.get("tax_rate", 11.0))
    tax, total = compute_tax_and_total(q, p, tr)
    update_data["tax"] = tax
    update_data["total"] = total
    update_data["updated_at"] = __import__('datetime').datetime.utcnow()

    new_invoice_no = update_data.pop("invoice_no", None)

    if new_invoice_no and new_invoice_no != current_invoice_no:
        # Changing primary key: ensure target not exists
        conflict = db["invoice"].find_one({"_id": new_invoice_no})
        if conflict:
            raise HTTPException(status_code=409, detail="Target invoice number already exists")
        # Create new document with new _id
        new_doc = {**existing, **update_data}
        new_doc["_id"] = new_invoice_no
        # Remove previous id remnants if any
        new_doc.pop("id", None)
        try:
            db["invoice"].insert_one(new_doc)
            db["invoice"].delete_one({"_id": current_invoice_no})
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        created = db["invoice"].find_one({"_id": new_invoice_no})
        return serialize_doc(created)
    else:
        # Regular update
        res = db["invoice"].update_one({"_id": current_invoice_no}, {"$set": update_data})
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail="Invoice not found")
        doc = db["invoice"].find_one({"_id": current_invoice_no})
        return serialize_doc(doc)

@app.delete("/api/invoices/{invoice_no}")
async def delete_invoice(invoice_no: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    result = db["invoice"].delete_one({"_id": invoice_no})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"deleted": True, "invoice_no": invoice_no}
