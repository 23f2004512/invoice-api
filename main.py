from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dateutil.parser import parse
import re

app = FastAPI(title="Invoice Extraction API")

# Enable CORS (required for Cloudflare Worker)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class InvoiceRequest(BaseModel):
    invoice_text: str


def clean_amount(text):
    """Extract the first number from a string and return it as float."""
    if text is None:
        return None

    text = text.replace(",", "")

    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if match:
        return float(match.group(1))

    return None


def parse_date(date_string):
    """Convert dates like '15 March 2026' to '2026-03-15'."""
    if not date_string:
        return None

    try:
        return parse(date_string, dayfirst=True).date().isoformat()
    except Exception:
        return None


@app.get("/")
def home():
    return {"message": "Invoice Extraction API is running."}


@app.post("/extract")
def extract(data: InvoiceRequest):
    text = data.invoice_text

    invoice_no = None
    date = None
    vendor = None
    amount = None
    tax = None
    currency = "INR"

    # -------- Invoice Number --------
    patterns = [
        r"Invoice\s*(?:No|Number)?\s*[:#-]?\s*([A-Za-z0-9\-\/]+)",
        r"Inv\s*(?:No)?\s*[:#-]?\s*([A-Za-z0-9\-\/]+)",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            invoice_no = m.group(1).strip()
            break

    # -------- Date --------
    m = re.search(r"Date\s*[:\-]?\s*(.+)", text, re.IGNORECASE)
    if m:
        line = m.group(1).split("\n")[0].strip()
        date = parse_date(line)

    # -------- Vendor --------
    vendor_patterns = [
        r"Vendor\s*[:\-]?\s*(.+)",
        r"Supplier\s*[:\-]?\s*(.+)",
        r"From\s*[:\-]?\s*(.+)",
    ]

    for pattern in vendor_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            vendor = m.group(1).split("\n")[0].strip()
            break

    # -------- Amount (Subtotal only) --------
    subtotal_patterns = [
        r"Subtotal\s*[:\-]?\s*(.+)",
        r"Sub\s*Total\s*[:\-]?\s*(.+)",
        r"Amount\s*Before\s*Tax\s*[:\-]?\s*(.+)",
    ]

    for pattern in subtotal_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            amount = clean_amount(m.group(1))
            break

    # -------- Tax --------
    tax_patterns = [
        r"GST.*?[:\-]?\s*(.+)",
        r"CGST.*?[:\-]?\s*(.+)",
        r"SGST.*?[:\-]?\s*(.+)",
        r"IGST.*?[:\-]?\s*(.+)",
        r"Tax.*?[:\-]?\s*(.+)",
    ]

    for pattern in tax_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            tax = clean_amount(m.group(1))
            break

    # -------- Currency --------
    upper = text.upper()

    if "USD" in upper or "$" in text:
        currency = "USD"
    elif "EUR" in upper or "€" in text:
        currency = "EUR"
    elif "GBP" in upper or "£" in text:
        currency = "GBP"
    elif (
        "INR" in upper
        or "RS." in upper
        or "RS " in upper
        or "₹" in text
    ):
        currency = "INR"
    else:
        currency = None

    return {
        "invoice_no": invoice_no,
        "date": date,
        "vendor": vendor,
        "amount": amount,
        "tax": tax,
        "currency": currency,
    }