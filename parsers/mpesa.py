# parsers/mpesa.py
"""M-Pesa PDF statement parsing."""
import io
import re
from datetime import datetime

import pandas as pd
import pdfplumber


TX_START = re.compile(
    r"^([A-Z0-9]{10})\s+"                 # receipt
    r"(\d{4}-\d{2}-\d{2})\s+"              # date
    r"(\d{2}:\d{2}:\d{2})\s+"              # time
    r"(.+?)\s+"                            # details
    r"(Completed|Failed|Pending)\s+"       # status
    r"(-?[\d,]+\.\d{2})"                   # amount
    r"(?:\s+(-?[\d,]+\.\d{2}))?"           # optional balance
)


PAYEE_PATTERNS = [
    (re.compile(r"to\s+\d+\s*-\s*(.+?)(?:\s+Acc\.|\s+Account|$)", re.IGNORECASE), 1),
    (re.compile(r"^(Pay Bill Charge|Customer Transfer of Funds Charge|Withdrawal Charge)$", re.IGNORECASE), None),
    (re.compile(r"Merchant Payment to \d+\s*-\s*(.+?)$", re.IGNORECASE), 1),
    (re.compile(r"Buy Goods from \d+\s*-\s*(.+?)$", re.IGNORECASE), 1),
    (re.compile(r"Customer Transfer(?: Fuliza MPesa)? to\s*-\s*\d+\*+\d+\s+(.+?)(?:\s+\||$)", re.IGNORECASE), 1),
    (re.compile(r"Funds received from\s*-\s*\d+\*+\d+\s+(.+?)(?:\s+\||$)", re.IGNORECASE), 1),
    (re.compile(r"(?:Bundle Purchase|Data Bundles)\s+(?:with Fuliza )?(?:to|by)\s+\S+\s*-?\s*(.+?)(?:\s+\||$)", re.IGNORECASE), 1),
    (re.compile(r"Agent (Deposit|Withdrawal)", re.IGNORECASE), 1),
    (re.compile(r"OD Loan Repayment", re.IGNORECASE), None),
    (re.compile(r"(M-?Shwari)", re.IGNORECASE), 1),
]


def extract_text_from_pdf(file_bytes: bytes, password: str | None = None) -> str:
    """Extract all text from a PDF, optionally password-protected."""
    parts = []
    with pdfplumber.open(io.BytesIO(file_bytes), password=password) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def classify_type(details: str) -> str:
    d = details.lower()
    if "overdraft of credit party" in d:
        return "Fuliza OverDraft"
    if "od loan repayment" in d:
        return "Fuliza Repayment"
    if "pay bill charge" in d:
        return "Paybill Charge"
    if "customer transfer of funds charge" in d:
        return "Transfer Charge"
    if "withdrawal charge" in d or "withdraw charge" in d:
        return "Withdrawal Charge"
    if "bundle purchase" in d or "airtime" in d:
        return "Data/Airtime"
    if "pay bill" in d or "paybill" in d:
        return "Paybill"
    if "buy goods" in d or "merchant payment" in d:
        return "Merchant"
    if "customer transfer" in d or "transfer to" in d or "transfer from" in d:
        return "Transfer"
    if "funds received" in d or "received from" in d:
        return "Received"
    if "agent deposit" in d or "deposit" in d:
        return "Deposit"
    if "agent withdrawal" in d or "withdrawal" in d or "withdraw" in d:
        return "Withdrawal"
    if "m-shwari" in d or "mshwari" in d:
        return "M-Shwari"
    return "Other"


def extract_payee(details: str) -> str:
    """Best-effort extraction of a payee/merchant name from details."""
    for pattern, group in PAYEE_PATTERNS:
        m = pattern.search(details)
        if m:
            if group is None:
                return ""
            value = m.group(group).strip()
            value = re.sub(r"\s+", " ", value).strip(" -|.")
            return value[:60]
    return ""


def parse_mpesa_text(text: str) -> pd.DataFrame:
    """Parse a full M-Pesa statement text into a tidy DataFrame."""
    lines = text.splitlines()
    raw_rows = []
    current = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        m = TX_START.match(stripped)
        if m:
            if current:
                raw_rows.append(current)
            receipt, date_str, time_str, details, status, amount_str, balance_str = m.groups()
            try:
                amount = float(amount_str.replace(",", ""))
            except ValueError:
                amount = None
            current = {
                "receipt": receipt,
                "date": date_str,
                "time": time_str,
                "details": details.strip(),
                "status": status,
                "amount": amount,
                "balance": float(balance_str.replace(",", "")) if balance_str else None,
            }
        else:
            if current:
                current["details"] += " " + stripped

    if current:
        raw_rows.append(current)
    if not raw_rows:
        return pd.DataFrame()

    df = pd.DataFrame(raw_rows)
    df["details"] = df["details"].str.replace(r"\s+", " ", regex=True).str.strip()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "amount"])
    df = df[df["status"] == "Completed"].copy()
    df["type"] = df["details"].apply(classify_type)
    df["payee"] = df["details"].apply(extract_payee)
    df = df[df["type"] != "Fuliza OverDraft"].copy()

    return _group_by_receipt(df).sort_values("date").reset_index(drop=True)


def _group_by_receipt(df: pd.DataFrame) -> pd.DataFrame:
    out = []
    for receipt, group in df.groupby("receipt", sort=False):
        details = " | ".join(sorted(set(group["details"].tolist())))
        status = group["status"].iloc[0]
        date = group["date"].iloc[0]
        time = group["time"].iloc[0]
        amounts = group["amount"].tolist()

        main_idx = max(range(len(amounts)), key=lambda i: abs(amounts[i]))
        main_amount = amounts[main_idx]
        main_type = group["type"].iloc[main_idx]
        main_payee = group["payee"].iloc[main_idx] if "payee" in group.columns else ""
        charge_total = sum(a for i, a in enumerate(amounts) if i != main_idx)

        out.append({
            "receipt": receipt,
            "date": date,
            "time": time,
            "details": details,
            "amount": main_amount,
            "charge": charge_total,
            "net_amount": main_amount + charge_total,
            "type": main_type,
            "payee": main_payee,
            "status": status,
        })

    result = pd.DataFrame(out)
    result["direction"] = result["net_amount"].apply(
        lambda x: "Income" if x > 0 else "Expense"
    )
    return result