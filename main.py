import re
from datetime import date
from typing import Optional

from dateutil import parser as date_parser
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


app = FastAPI(title="IITM Invoice Extraction API")

# Lets a Cloudflare Worker (and other websites) call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class InvoiceRequest(BaseModel):
    invoice_text: str


class InvoiceResponse(BaseModel):
    invoice_no: Optional[str] = None
    date: Optional[str] = None
    vendor: Optional[str] = None
    amount: Optional[float] = None
    tax: Optional[float] = None
    currency: Optional[str] = None


def first_match(pattern: str, text: str) -> Optional[str]:
    """Return the first matching captured value, or None."""
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


def money_to_float(value: Optional[str]) -> Optional[float]:
    """Convert 'Rs. 2,199.00' or '2,199.00' into 2199.0."""
    if not value:
        return None

    cleaned = re.sub(r"[^\d.,-]", "", value)
    cleaned = cleaned.replace(",", "")

    try:
        return float(cleaned)
    except ValueError:
        return None


def to_iso_date(value: Optional[str]) -> Optional[str]:
    """Convert '15 March 2026' into '2026-03-15'."""
    if not value:
        return None

    try:
        return date_parser.parse(value, dayfirst=True, fuzzy=True).date().isoformat()
    except (ValueError, OverflowError):
        return None


def detect_currency(text: str) -> Optional[str]:
    text_upper = text.upper()

    if "INR" in text_upper or "RS." in text_upper or "RS " in text_upper or "₹" in text:
        return "INR"
    if "USD" in text_upper or "$" in text:
        return "USD"
    if "EUR" in text_upper or "€" in text:
        return "EUR"

    return None


@app.get("/")
def home():
    return {"message": "Invoice extraction API is running"}


@app.post("/extract", response_model=InvoiceResponse)
def extract_invoice(data: InvoiceRequest):
    text = data.invoice_text

    # Find invoice number.
    invoice_no = first_match(
        r"(?:invoice\s*(?:no|number|#)?|bill\s*(?:no|number|#)?)\s*[:#-]?\s*([A-Za-z0-9/_-]+)",
        text,
    )

    # Find a date written after Date:, Invoice Date:, etc.
    raw_date = first_match(
        r"(?:invoice\s*date|date)\s*[:\-]?\s*([A-Za-z0-9,\-/ ]{6,30})",
        text,
    )
    invoice_date = to_iso_date(raw_date)

    # Stop vendor value when another known label begins.
    vendor = first_match(
        r"(?:vendor|supplier|seller|company)\s*[:\-]\s*(.+?)(?=\s+(?:subtotal|tax|gst|total|amount|invoice\s*date|date)\s*[:\-]|\n|$)",
        text,
    )

    # Important: amount must be SUBTOTAL, before tax.
    raw_amount = first_match(
        r"(?:subtotal|sub[- ]?total|amount\s*before\s*tax|net\s*amount)\s*[:\-]?\s*(?:rs\.?|inr|₹|\$)?\s*([\d,]+(?:\.\d{1,2})?)",
        text,
    )
    amount = money_to_float(raw_amount)

    # Find tax only, such as GST, CGST, SGST, VAT, or Tax.
    raw_tax = first_match(
        r"\b(?:gst|cgst|sgst|igst|vat|tax)"
        r"(?:\s+(?:amount|total|payable))?"
        r"(?:\s*(?:\([^)]*\)|(?:@|at)\s*\d+(?:\.\d+)?\s*%|\d+(?:\.\d+)?\s*%))?"
        r"\s*[:=\-]?\s*(?:rs\.?|inr|₹|\$)?\s*"
        r"([\d,]+(?:\.\d{1,2})?)",
        text,
    )
    tax = money_to_float(raw_tax)

    return InvoiceResponse(
        invoice_no=invoice_no,
        date=invoice_date,
        vendor=vendor,
        amount=amount,
        tax=tax,
        currency=detect_currency(text),
    )