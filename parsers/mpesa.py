# parsers/mpesa.py
"""M-Pesa PDF statement parsing.

Pipeline
--------
1. ``extract_text_from_pdf``  PDF bytes -> text (pdfplumber)
2. ``_scan_lines``            text -> raw rows (one per statement line), skipping
                              page headers/footers so they never glue onto a row
3. ``reconcile``              checks the running balance column against the amounts
                              (the correctness check for the whole parse)
4. classify + payee           per raw row
5. ``_group_by_receipt``      folds charge rows into their parent receipt

Use ``parse_statement(text)`` (returns a ParseResult with a reconciliation
report). ``parse_mpesa_text(text)`` is kept for backwards compatibility.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pandas as pd

# ------------------------------------------------------------------
# Regexes
# ------------------------------------------------------------------
# receipt | date | time | details | status | 1-3 numbers
# The numbers are: [amount] [balance]            (2-column layout)
#             or: [paid in] [withdrawn] [balance] (3-column layout)
TX_START = re.compile(
    r"^([A-Z0-9]{10})\s+"
    r"(\d{4}-\d{2}-\d{2})\s+"
    r"(\d{2}:\d{2}:\d{2})\s+"
    r"(.+?)\s+"
    r"(Completed|Failed|Pending)\s+"
    r"((?:-?[\d,]+\.\d{2}\s*){1,3})"
)
NUMBER = re.compile(r"-?[\d,]+\.\d{2}")

# Lines that are page furniture, not transaction text. Extend as you meet new ones.
JUNK = re.compile(
    r"^(?:"
    r"receipt\s*no|completion\s*time|details\s+transaction|transaction\s*status"
    r"|page\s+\d+(?:\s+of\s+\d+)?\b|detailed\s+statement|m-?pesa\s+(?:full\s+)?statement"
    r"|customer\s+name|mobile\s+number|email\s+address|statement\s+period|request\s+date"
    r"|disclaimer|statement\s+verification|this\s+statement|for\s+self|kindly"
    r"|terms\s+and|twitter|facebook|www\.|head\s+office|safaricom\s+(?:plc|house|limited\s+is)"
    r"|summary\b|transaction\s+type"
    r")",
    re.IGNORECASE,
)
# A line made only of column-header words, e.g. "Paid In Withdrawn Balance"
HEADER_ONLY = re.compile(
    r"^(?:(?:receipt|no\.?|completion|time|details|transaction|status|paid|in|out|withdrawn?|balance)\s*)+$",
    re.IGNORECASE,
)
MAX_CONTINUATION_LINES = 2  # wrapped "details" never need more than this

KNOWN_TYPES = [
    "Paybill", "Merchant", "Transfer", "Received", "Deposit", "Withdrawal",
    "Data/Airtime", "M-Shwari", "Fuliza Repayment", "Fuliza Fee",
    "Paybill Charge", "Transfer Charge", "Withdrawal Charge", "Reversal", "Other",
]

PAYEE_PATTERNS = [
    (re.compile(r"to\s+\d+\s*-\s*(.+?)(?:\s+Acc\.|\s+Account|$)", re.IGNORECASE), 1),
    (re.compile(r"^(Pay Bill Charge|Customer Transfer of Funds Charge|Withdrawal Charge)$", re.IGNORECASE), None),
    (re.compile(r"Merchant Payment to \d+\s*-\s*(.+?)$", re.IGNORECASE), 1),
    (re.compile(r"Buy Goods from \d+\s*-\s*(.+?)$", re.IGNORECASE), 1),
    (re.compile(r"Customer Payment to Small Business to\s*-?\s*\d+\*+\d+\s+(.+?)(?:\s+\||$)", re.IGNORECASE), 1),
    (re.compile(r"Customer Transfer(?: Fuliza MPesa)? to\s*-\s*\d+\*+\d+\s+(.+?)(?:\s+\||$)", re.IGNORECASE), 1),
    (re.compile(r"Funds received from\s*-\s*\d+\*+\d+\s+(.+?)(?:\s+\||$)", re.IGNORECASE), 1),
    (re.compile(r"(?:Bundle Purchase|Data Bundles)\s+(?:with Fuliza )?(?:to|by)\s+\S+\s*-?\s*(.+?)(?:\s+\||$)", re.IGNORECASE), 1),
    (re.compile(r"Agent (?:Deposit|Withdrawal)", re.IGNORECASE), None),
    (re.compile(r"OD Loan Repayment", re.IGNORECASE), None),
    (re.compile(r"(M-?Shwari)", re.IGNORECASE), 1),
]


@dataclass
class ParseResult:
    df: pd.DataFrame
    reconciliation: dict = field(default_factory=dict)
    n_raw_rows: int = 0


# ------------------------------------------------------------------
# PDF -> text
# ------------------------------------------------------------------
def extract_text_from_pdf(file_bytes: bytes, password: str | None = None) -> str:
    """Extract all text from a PDF, optionally password-protected."""
    import pdfplumber  # imported lazily so the parser can be unit-tested without it

    parts = []
    with pdfplumber.open(io.BytesIO(file_bytes), password=password) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


# ------------------------------------------------------------------
# Classification / payee
# ------------------------------------------------------------------
def classify_type(details: str) -> str:
    d = details.lower()
    if "overdraft of credit party" in d:
        return "Fuliza OverDraft"
    if "od loan repayment" in d:
        return "Fuliza Repayment"
    if "overdraft charge" in d or "fuliza charge" in d or "access fee" in d:
        return "Fuliza Fee"
    if "pay bill charge" in d:
        return "Paybill Charge"
    if "customer transfer of funds charge" in d or "transfer charge" in d:
        return "Transfer Charge"
    if "withdrawal charge" in d or "withdraw charge" in d:
        return "Withdrawal Charge"
    if "reversal" in d:
        return "Reversal"
    # M-Shwari must come before the generic deposit/withdraw/transfer rules,
    # otherwise it is unreachable.
    if "m-shwari" in d or "mshwari" in d:
        return "M-Shwari"
    if "bundle purchase" in d or "airtime purchase" in d or "data bundle" in d:
        return "Data/Airtime"
    if "pay bill" in d or "paybill" in d:
        return "Paybill"
    if "buy goods" in d or "merchant payment" in d or "small business" in d:
        return "Merchant"
    if "customer transfer" in d or "transfer to" in d or "transfer from" in d:
        return "Transfer"
    if "funds received" in d or "received from" in d:
        return "Received"
    if "agent deposit" in d or "deposit" in d:
        return "Deposit"
    if "agent withdrawal" in d or "withdrawal" in d or "withdraw" in d:
        return "Withdrawal"
    if "airtime" in d:  # last, so a paybill whose account says "airtime" stays a Paybill
        return "Data/Airtime"
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


# ------------------------------------------------------------------
# Line scanning
# ------------------------------------------------------------------
def _interpret_numbers(raw: str) -> tuple[float, float | None]:
    vals = [float(n.replace(",", "")) for n in NUMBER.findall(raw)]
    if len(vals) >= 3:  # paid in | withdrawn | balance
        paid_in, withdrawn, balance = vals[0], vals[1], vals[2]
        amount = paid_in if paid_in != 0 else -abs(withdrawn)
        return amount, balance
    if len(vals) == 2:  # amount | balance
        return vals[0], vals[1]
    return vals[0], None


def _scan_lines(text: str) -> list[dict]:
    rows: list[dict] = []
    current: dict | None = None
    continuation = 0

    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue

        m = TX_START.match(s)
        if m:
            receipt, date_str, time_str, details, status, nums = m.groups()
            amount, balance = _interpret_numbers(nums)
            current = {
                "seq": len(rows),
                "receipt": receipt,
                "date": date_str,
                "time": time_str,
                "details": details.strip(),
                "status": status,
                "amount": amount,
                "balance": balance,
            }
            rows.append(current)
            continuation = 0
            continue

        if JUNK.match(s) or HEADER_ONLY.match(s):
            current = None  # page furniture ends the previous row: nothing may glue on
            continue

        if current is not None and continuation < MAX_CONTINUATION_LINES:
            current["details"] += " " + s
            continuation += 1

    return rows


# ------------------------------------------------------------------
# Reconciliation (the parser's self-test)
# ------------------------------------------------------------------
def reconcile(rows: list[dict], tol: float = 0.02) -> dict:
    """Check the running balance against the amounts, on the raw rows.

    Statements may be oldest-first or newest-first, so both directions are
    tried and the better one wins.
    """
    seq = [
        r for r in rows
        if r["status"] == "Completed" and r["balance"] is not None and r["amount"] is not None
    ]
    if len(seq) < 2:
        return {"checked": 0, "mismatches": 0, "direction": 0, "ok": None, "examples": []}

    asc = [abs(seq[i]["balance"] - (seq[i - 1]["balance"] + seq[i]["amount"])) <= tol
           for i in range(1, len(seq))]
    desc = [abs(seq[i - 1]["balance"] - (seq[i]["balance"] + seq[i - 1]["amount"])) <= tol
            for i in range(1, len(seq))]
    direction = 1 if sum(asc) >= sum(desc) else -1
    flags = asc if direction == 1 else desc

    bad = [i for i, ok in enumerate(flags, start=1) if not ok]
    examples = [
        {
            "receipt": seq[i]["receipt"],
            "date": seq[i]["date"],
            "details": seq[i]["details"][:60],
            "amount": seq[i]["amount"],
            "balance": seq[i]["balance"],
        }
        for i in bad[:5]
    ]
    return {
        "checked": len(flags),
        "mismatches": len(bad),
        "direction": direction,
        "ok": len(bad) == 0,
        "examples": examples,
    }


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------
def parse_statement(text: str) -> ParseResult:
    """Parse a full M-Pesa statement text into a tidy DataFrame + reconciliation."""
    rows = _scan_lines(text)
    if not rows:
        return ParseResult(pd.DataFrame(), reconcile([]), 0)

    recon = reconcile(rows)

    df = pd.DataFrame(rows)
    df["details"] = df["details"].str.replace(r"\s+", " ", regex=True).str.strip()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "amount"])
    df = df[df["status"] == "Completed"].copy()
    if df.empty:
        return ParseResult(pd.DataFrame(), recon, len(rows))

    df["type"] = df["details"].apply(classify_type)
    df["payee"] = df["details"].apply(extract_payee)
    # Fuliza "OverDraft of Credit Party" credits are the other half of a Fuliza
    # purchase; keeping them would double count. The repayment is treated as an
    # internal movement downstream (see analytics/common.py).
    df = df[df["type"] != "Fuliza OverDraft"].copy()
    if df.empty:
        return ParseResult(pd.DataFrame(), recon, len(rows))

    out = _group_by_receipt(df, recon["direction"])
    out = out.sort_values(["date", "time"], kind="stable").reset_index(drop=True)
    return ParseResult(out, recon, len(rows))


def parse_mpesa_text(text: str) -> pd.DataFrame:
    """Backwards-compatible wrapper: DataFrame only."""
    return parse_statement(text).df


def _group_by_receipt(df: pd.DataFrame, direction: int = 1) -> pd.DataFrame:
    out = []
    for receipt, group in df.groupby("receipt", sort=False):
        group = group.sort_values("seq")
        details = " | ".join(dict.fromkeys(group["details"].tolist()))
        amounts = group["amount"].tolist()

        main_idx = max(range(len(amounts)), key=lambda i: abs(amounts[i]))
        main_amount = amounts[main_idx]
        charge_total = sum(a for i, a in enumerate(amounts) if i != main_idx)

        balances = group["balance"].dropna()
        if balances.empty:
            balance = None
        else:  # the balance *after* the receipt's last row, in chronological terms
            balance = float(balances.iloc[0] if direction == -1 else balances.iloc[-1])

        out.append({
            "receipt": receipt,
            "date": group["date"].iloc[0],
            "time": group["time"].iloc[0],
            "details": details,
            "amount": main_amount,
            "charge": charge_total,
            "net_amount": main_amount + charge_total,
            "balance": balance,
            "type": group["type"].iloc[main_idx],
            "payee": group["payee"].iloc[main_idx],
            "status": group["status"].iloc[0],
        })

    result = pd.DataFrame(out)

    def _direction(x: float) -> str:
        if x > 0:
            return "Income"
        if x < 0:
            return "Expense"
        return "Neutral"

    result["direction"] = result["net_amount"].apply(_direction)
    return result