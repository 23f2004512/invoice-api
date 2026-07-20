from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dateutil.parser import parse
import re

app = FastAPI(title="Invoice Extraction API")

# ---------------- CORS ---------------- #

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- Request ---------------- #

class InvoiceRequest(BaseModel):
    invoice_text: str


# ---------------- Helpers ---------------- #

def extract_money(text):
    if not text:
        return None

    text = text.replace(",", "")

    m = re.search(r"(\d+(?:\.\d+)?)", text)

    if m:
        return float(m.group(1))

    return None


def extract_currency(text):
    upper = text.upper()

    if "INR" in upper or "RS." in upper or "RS " in upper or "₹" in text:
        return "INR"

    if "USD" in upper or "$" in text:
        return "USD"

    if "EUR" in upper or "€" in text:
        return "EUR"

    if "GBP" in upper or "£" in text:
        return "GBP"

    return None


def extract_field(patterns, text):
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).strip()

    return None


def normalize_date(value):
    if value is None:
        return None

    try:
        return parse(value, dayfirst=True).date().isoformat()
    except:
        return None


# ---------------- Endpoint ---------------- #

@app.get("/")
def root():
    return {"status": "running"}


@app.post("/extract")
def extract(req: InvoiceRequest):

    text = req.invoice_text

    invoice_no = extract_field([
        r"Invoice\s*(?:No|Number)?\s*[:#]\s*([^\n]+)",
        r"Invoice\s*#\s*([^\n]+)",
        r"Inv\s*(?:No)?\s*[:#]?\s*([^\n]+)",
    ], text)

    date = extract_field([
        r"Date\s*:\s*([^\n]+)",
        r"Invoice\s*Date\s*:\s*([^\n]+)",
    ], text)

    vendor = extract_field([
        r"Vendor\s*:\s*([^\n]+)",
        r"Seller\s*:\s*([^\n]+)",
        r"Supplier\s*:\s*([^\n]+)",
    ], text)

    subtotal = extract_field([
        r"Subtotal.*?([A-Z]{3}|Rs\.?|₹|\$|€|£)?\s*([\d,]+\.\d{2})",
        r"Sub\s*Total.*?([A-Z]{3}|Rs\.?|₹|\$|€|£)?\s*([\d,]+\.\d{2})",
        r"Amount\s*Before\s*Tax\s*[:\-]?\s*(.*)",
        r"Before\s*Tax\s*[:\-]?\s*(.*)",
        r"Net\s*Amount\s*[:\-]?\s*(.*)",
        r"Taxable\s*Value\s*[:\-]?\s*(.*)",
        r"Amount\s*[:\-]?\s*(.*)",
    ], text)

    tax = extract_field([
        r"GST.*?([A-Z]{3}|Rs\.?|₹|\$|€|£)?\s*([\d,]+\.\d{2})",
        r"VAT.*?([A-Z]{3}|Rs\.?|₹|\$|€|£)?\s*([\d,]+\.\d{2})",
        r"Tax.*?([A-Z]{3}|Rs\.?|₹|\$|€|£)?\s*([\d,]+\.\d{2})",
    ], text)

    # Because regex above has two capture groups
    if subtotal:
        amount = extract_money(subtotal)
    else:
        amount = None

    if tax:
        tax_amount = extract_money(tax)
    else:
        tax_amount = None

    currency = extract_currency(text)

    return {
        "invoice_no": invoice_no,
        "date": normalize_date(date),
        "vendor": vendor,
        "amount": amount,
        "tax": tax_amount,
        "currency": currency
    }