"""
parse_xml.py — parse MoMo SMS XML into a list of transaction dictionaries.

The XML we're given is a phone SMS backup. Each <sms> element carries a
`body` attribute containing the actual mobile-money message text. The
interesting fields (amount, sender, receiver, transaction id, new balance,
date) live inside that body text, so we need regex-based extraction.

This module exposes:
    parse_xml(path)   -> list[dict]      transactions parsed from the XML
    save_json(txs, out_path)             writes the list to a JSON file

Running the file directly parses `data/raw/modified_sms_v2.xml` and writes
`data/processed/transactions.json` for the API to load at startup.
"""

from __future__ import annotations

import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Category detection — pattern-match on the SMS body to figure out which
# type of MoMo transaction this SMS represents.
# ---------------------------------------------------------------------------
CATEGORY_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("Incoming Money",         re.compile(r"You have received", re.I)),
    ("Bank Deposit",           re.compile(r"bank deposit", re.I)),
    ("Airtime Purchase",       re.compile(r"to Airtime", re.I)),
    ("Internet Bundle",        re.compile(r"internet bundle|bundle", re.I)),
    ("Withdrawal",             re.compile(r"withdrawn|withdraw", re.I)),
    ("Direct Payment",         re.compile(r"DIRECT PAYMENT|debit receiver", re.I)),
    ("Transfer to Mobile",     re.compile(r"transferred to", re.I)),
    ("Payment to Code Holder", re.compile(r"payment of .*? to", re.I)),
    ("OTP / System Notice",    re.compile(r"one-time password|OTP", re.I)),
]


def detect_category(body: str) -> str:
    for name, pattern in CATEGORY_RULES:
        if pattern.search(body):
            return name
    return "Unknown"


# ---------------------------------------------------------------------------
# Field extraction — pull structured values out of the SMS body.
# ---------------------------------------------------------------------------
AMOUNT_RE      = re.compile(r"([\d,]+)\s*RWF")
FEE_RE         = re.compile(r"Fee(?: was)?[:\s]*([\d,]+)\s*RWF", re.I)
BALANCE_RE     = re.compile(r"(?:new balance|NEW BALANCE)\s*:?\s*([\d,]+)\s*RWF", re.I)
TXID_RE        = re.compile(r"(?:Financial Transaction Id|TxId)[:\s]*([\d]+)", re.I)
EXT_TXID_RE    = re.compile(r"External Transaction Id[:\s]*([\d]+)", re.I)
BODY_DATE_RE   = re.compile(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})")
SENDER_RE      = re.compile(r"from\s+([A-Z][A-Za-z .'-]+?)\s*\(", re.I)
RECEIVER_RE    = re.compile(r"to\s+([A-Z][A-Za-z .'-]+?)(?:\s+\d+|\s*\(|\s+has been|,)", re.I)
PHONE_RE       = re.compile(r"\((\*+\d{3,4}|\d{9,12})\)")


def clean_number(text: str | None) -> float | None:
    if not text:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def first_match(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    return m.group(1).strip() if m else None


def parse_body(body: str) -> dict[str, Any]:
    """Extract structured fields from a single SMS body string."""
    amounts = AMOUNT_RE.findall(body)
    # The first RWF number is usually the transaction amount.
    amount = clean_number(amounts[0]) if amounts else None

    return {
        "amount":         amount,
        "fee":            clean_number(first_match(FEE_RE, body)) or 0.0,
        "new_balance":    clean_number(first_match(BALANCE_RE, body)),
        "tx_id":          first_match(TXID_RE, body),
        "external_tx_id": first_match(EXT_TXID_RE, body),
        "sender":         first_match(SENDER_RE, body),
        "receiver":       first_match(RECEIVER_RE, body),
        "counterparty_phone": first_match(PHONE_RE, body),
        "tx_datetime":    first_match(BODY_DATE_RE, body),
    }


# ---------------------------------------------------------------------------
# Top-level parsing.
# ---------------------------------------------------------------------------
def _ms_to_iso(ms_string: str | None) -> str | None:
    if not ms_string:
        return None
    try:
        dt = datetime.fromtimestamp(int(ms_string) / 1000, tz=timezone.utc)
        return dt.isoformat()
    except (ValueError, OSError):
        return None


def parse_xml(path: str) -> list[dict[str, Any]]:
    """Parse the MoMo SMS backup file into a list of transaction dicts."""
    tree = ET.parse(path)
    root = tree.getroot()

    transactions: list[dict[str, Any]] = []
    for idx, sms in enumerate(root.findall("sms"), start=1):
        body = sms.get("body", "") or ""
        category = detect_category(body)

        # Skip non-transaction messages (OTPs etc). We still count them.
        if category == "OTP / System Notice":
            continue

        fields = parse_body(body)

        transactions.append({
            "id":              idx,
            "category":        category,
            "amount":          fields["amount"],
            "fee":             fields["fee"],
            "new_balance":     fields["new_balance"],
            "sender":          fields["sender"],
            "receiver":        fields["receiver"],
            "counterparty_phone": fields["counterparty_phone"],
            "tx_id":           fields["tx_id"],
            "external_tx_id":  fields["external_tx_id"],
            "tx_datetime":     fields["tx_datetime"],
            "sms_received_at": _ms_to_iso(sms.get("date")),
            "readable_date":   sms.get("readable_date"),
            "raw_body":        body,
        })

    return transactions


def save_json(transactions: list[dict[str, Any]], out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(transactions, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# CLI entrypoint — `python dsa/parse_xml.py`
# ---------------------------------------------------------------------------
def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)
    xml_path = os.path.join(repo_root, "data", "raw", "modified_sms_v2.xml")
    out_path = os.path.join(repo_root, "data", "processed", "transactions.json")

    if not os.path.exists(xml_path):
        print(f"XML not found at {xml_path}", file=sys.stderr)
        return 1

    print(f"Parsing {xml_path} ...")
    txs = parse_xml(xml_path)
    save_json(txs, out_path)

    # Small summary so we can eyeball the run.
    categories: dict[str, int] = {}
    for t in txs:
        categories[t["category"]] = categories.get(t["category"], 0) + 1

    print(f"Parsed {len(txs)} transactions -> {out_path}")
    print("Category breakdown:")
    for c, n in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {n:>5}  {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
