"""
Anomaly Detector — checks every CSV row for data quality issues.
=================================================================

Each check method returns an ``AnomalyResult`` or ``None``.
If ``None``: no anomaly found.
If ``AnomalyResult``: includes type, description, action, whether user
approval is needed.

The 17 anomalies detected, mapped to CSV rows
----------------------------------------------

==  ==========================  ===========  =========================================
#   Anomaly Type                CSV Row(s)   Example
==  ==========================  ===========  =========================================
 1  EXACT_DUPLICATE             5 & 6        Marina Bites dinner (identical)
 2  AMOUNT_FORMAT               7            "1,200" with comma
 3  NAME_FUZZY_MATCH            9, 11, 27    priya / Priya S / rohan (trailing space)
 4  MISSING_PAID_BY             13           House cleaning supplies (no payer)
 5  SETTLEMENT_PATTERN          14, 38       "Rohan paid Aisha back" / "Sam deposit"
 6  PERCENTAGE_SUM_ERROR        15           Pizza Friday sums to 110%
 7  FOREIGN_CURRENCY            20,21,23,26  USD amounts
 8  UNKNOWN_MEMBER              23           Dev's friend Kabir
 9  CONFLICTING_DUPLICATE       24 & 25      Thalassa dinner, different amounts
10  NEGATIVE_AMOUNT             26           Parasailing refund −30 USD
11  NONSTANDARD_DATE            27           Mar-14
12  MISSING_CURRENCY            28           Groceries DMart, no currency
13  ZERO_AMOUNT                 31           Swiggy Rs.0
14  AMBIGUOUS_DATE              34           04-05-2026 (Apr 5 or May 4?)
15  MEMBER_POST_DEPARTURE       36           Meera in April after she left 28 Mar
16  SPLIT_TYPE_CONFLICT         42           equal + share details both present
17  DECIMAL_PRECISION           10           Rs.899.995 — 3 decimal places
==  ==========================  ===========  =========================================
"""

import difflib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from dateutil import parser as dateutil_parser


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SETTLEMENT_KEYWORDS = [
    'paid back', 'paid aisha', 'paid rohan', 'paid priya',
    'paid meera', 'paid sam', 'paid dev',
    'settlement', 'deposit share', 'repaid', 'transferred',
    'sent money', 'returned',
]

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AnomalyResult:
    """Result of a single anomaly check on one CSV row."""
    anomaly_type: str
    description: str
    action: str                          # AUTO_FIXED | SKIPPED | PENDING_USER | AUTO_IMPORTED
    requires_user_approval: bool
    suggested_fix: Optional[dict] = None
    modified_row: Optional[dict] = None  # Row after auto-fix, if any


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class AnomalyDetector:
    """Runs all 17 anomaly checks against a single CSV row."""

    def __init__(self, group_members: list, all_rows: list, fx_client):
        """
        Args:
            group_members: list of dicts ``{name, user_id, joined_at, left_at}``
            all_rows:      all CSV rows (needed for duplicate detection)
            fx_client:     ``FXClient`` instance
        """
        self.group_members = group_members
        # Build a lookup: lowercased canonical name → member dict
        self.member_names_lower = {
            m['name'].lower(): m for m in group_members
        }
        self.all_rows = all_rows
        self.fx_client = fx_client

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def detect_all(self, row: dict, row_index: int) -> tuple:
        """
        Run all checks on a row.

        Returns:
            ``(clean_row, [AnomalyResult])``
            - ``clean_row``: the row after auto-fixes applied
            - ``anomalies``: list of AnomalyResult (may be empty)
        """
        anomalies: List[AnomalyResult] = []
        working_row = dict(row)  # Work on a copy, never mutate original

        # Check 1: Amount format (must do first — other checks need a clean amount)
        result, working_row = self.check_amount_format(working_row)
        if result:
            anomalies.append(result)

        # Check 2: Decimal precision (e.g. 899.995 → round to 2dp)
        result = self.check_decimal_precision(working_row)
        if result:
            anomalies.append(result)

        # Check 3: Zero amount → stop processing (nothing to import)
        result = self.check_zero_amount(working_row)
        if result:
            return working_row, [result]

        # Check 4: Negative amount → flag as refund
        result, working_row = self.check_negative_amount(working_row)
        if result:
            anomalies.append(result)

        # Check 5: Date format (parse non-standard dates)
        result, working_row = self.check_date_format(working_row)
        if result:
            anomalies.append(result)

        # Check 6: Ambiguous date (DD-MM vs MM-DD when both are valid)
        result = self.check_ambiguous_date(working_row)
        if result:
            anomalies.append(result)

        # Check 7: Missing currency → default to INR
        result, working_row = self.check_missing_currency(working_row)
        if result:
            anomalies.append(result)

        # Check 8: Foreign currency → convert to INR via FX API
        result, working_row = self.check_foreign_currency(working_row, row_index)
        if result:
            anomalies.append(result)

        # Check 9: Missing paid_by
        result = self.check_missing_paid_by(working_row)
        if result:
            anomalies.append(result)

        # Check 10: Settlement pattern detection
        result = self.check_settlement_pattern(working_row)
        if result:
            anomalies.append(result)

        # Check 11: Fuzzy name matching (typos, trailing spaces, suffixes)
        result, working_row = self.check_name_fuzzy_match(working_row)
        if result:
            anomalies.append(result)

        # Check 12: Unknown member in split_with
        result = self.check_unknown_member(working_row)
        if result:
            anomalies.append(result)

        # Check 13: Member included after departure date
        result, working_row = self.check_member_post_departure(working_row)
        if result:
            anomalies.append(result)

        # Check 14: Percentage sum ≠ 100%
        result = self.check_percentage_sum(working_row)
        if result:
            anomalies.append(result)

        # Check 15: Split type conflicts (equal + details present)
        result = self.check_split_type_conflict(working_row)
        if result:
            anomalies.append(result)

        # Checks 16 & 17: EXACT_DUPLICATE / CONFLICTING_DUPLICATE
        # → handled at session level in parser._find_duplicates()

        return working_row, anomalies

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def check_amount_format(self, row: dict):
        """
        **Row 7**: ``"1,200"`` with comma.

        Strip commas and other non-numeric formatting. If the result is a
        valid number, auto-fix; otherwise flag for manual correction.
        """
        raw = str(row.get('amount', '')).strip()
        # Remove commas (Indian/US formatting) and currency symbols
        cleaned = raw.replace(',', '').replace('₹', '').replace('$', '').strip()
        try:
            Decimal(cleaned)
            if raw != cleaned:
                row['amount'] = cleaned
                return AnomalyResult(
                    anomaly_type='AMOUNT_FORMAT',
                    description=(
                        f"Amount '{raw}' contained formatting characters. "
                        f"Auto-corrected to '{cleaned}'."
                    ),
                    action='AUTO_FIXED',
                    requires_user_approval=False,
                    modified_row=dict(row),
                ), row
        except InvalidOperation:
            return AnomalyResult(
                anomaly_type='AMOUNT_FORMAT',
                description=f"Amount '{raw}' is not a valid number.",
                action='PENDING_USER',
                requires_user_approval=True,
            ), row
        return None, row

    def check_decimal_precision(self, row: dict):
        """
        **Row 10**: ``899.995`` — more than 2 decimal places.

        Auto-round to 2 decimal places with banker's rounding.
        """
        raw = str(row.get('amount', '')).strip()
        try:
            d = Decimal(raw)
            # Count digits after decimal point
            decimal_places = abs(d.as_tuple().exponent)
            if decimal_places > 2:
                rounded = d.quantize(Decimal('0.01'))
                row['amount'] = str(rounded)
                return AnomalyResult(
                    anomaly_type='DECIMAL_PRECISION',
                    description=(
                        f"Amount {raw} has {decimal_places} decimal places. "
                        f"Rounded to {rounded}."
                    ),
                    action='AUTO_FIXED',
                    requires_user_approval=False,
                    modified_row=dict(row),
                )
        except (InvalidOperation, ArithmeticError):
            pass
        return None

    def check_zero_amount(self, row: dict):
        """
        **Row 31**: Swiggy Rs.0.

        Zero-amount expenses carry no financial information. Skip entirely.
        """
        try:
            if Decimal(str(row.get('amount', '0')).strip()) == 0:
                return AnomalyResult(
                    anomaly_type='ZERO_AMOUNT',
                    description=(
                        f"'{row.get('description', '')}' has Rs.0 amount. "
                        f"Notes say: '{row.get('notes', '')}'. Skipped."
                    ),
                    action='SKIPPED',
                    requires_user_approval=False,
                )
        except (InvalidOperation, ArithmeticError):
            pass
        return None

    def check_negative_amount(self, row: dict):
        """
        **Row 26**: Parasailing refund ``-30 USD``.

        Negative amounts are treated as refunds/credits. Flag ``is_refund``
        so the balance calculator applies them as debt reduction.
        """
        try:
            amount = Decimal(str(row.get('amount', '0')).strip())
            if amount < 0:
                row['is_refund'] = True
                return AnomalyResult(
                    anomaly_type='NEGATIVE_AMOUNT',
                    description=(
                        f"Negative amount {amount} detected. "
                        f"Treated as refund/credit split among participants."
                    ),
                    action='AUTO_FIXED',
                    requires_user_approval=False,
                    modified_row=dict(row),
                ), row
        except (InvalidOperation, ArithmeticError):
            pass
        return None, row

    def check_date_format(self, row: dict):
        """
        **Row 27**: ``Mar-14`` — non-standard date format.

        Try standard formats first (DD-MM-YYYY, YYYY-MM-DD, DD/MM/YYYY).
        Fall back to ``dateutil.parser`` for non-standard formats.
        """
        raw_date = str(row.get('date', '')).strip()

        # Try standard formats first (fast path, no ambiguity)
        for fmt in ('%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y'):
            try:
                parsed = datetime.strptime(raw_date, fmt).date()
                row['date'] = parsed.isoformat()
                return None, row  # Clean — no anomaly
            except ValueError:
                continue

        # Fall back to dateutil for non-standard formats like "Mar-14"
        try:
            parsed = dateutil_parser.parse(raw_date, dayfirst=True)
            # dateutil may default to year 1900 for partial dates
            if parsed.year < 2020:
                parsed = parsed.replace(year=2026)
            row['date'] = parsed.date().isoformat()
            return AnomalyResult(
                anomaly_type='NONSTANDARD_DATE',
                description=(
                    f"Date '{raw_date}' is non-standard. "
                    f"Auto-parsed as {row['date']}."
                ),
                action='AUTO_FIXED',
                requires_user_approval=False,
                modified_row=dict(row),
            ), row
        except Exception:
            return AnomalyResult(
                anomaly_type='NONSTANDARD_DATE',
                description=(
                    f"Date '{raw_date}' could not be parsed. "
                    f"Manual correction needed."
                ),
                action='PENDING_USER',
                requires_user_approval=True,
            ), row

    def check_ambiguous_date(self, row: dict):
        """
        **Row 34**: ``04-05-2026`` — could be April 5 or May 4.

        Ambiguous when the *original* raw date has DD-MM-YYYY format and
        both DD and MM are ≤ 12 (so swapping them produces a valid date).
        We check the original CSV value, not the already-parsed ISO date.
        """
        raw_date = str(row.get('_original_date', row.get('date', ''))).strip()
        match = re.match(r'^(\d{2})-(\d{2})-(\d{4})$', raw_date)
        if match:
            d1, d2, year = (
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
            )
            # Both parts ≤ 12 and different → genuinely ambiguous
            if d1 <= 12 and d2 <= 12 and d1 != d2:
                interp_dm = f"{year}-{d2:02d}-{d1:02d}"   # DD-MM-YYYY interpretation
                interp_md = f"{year}-{d1:02d}-{d2:02d}"   # MM-DD-YYYY interpretation
                return AnomalyResult(
                    anomaly_type='AMBIGUOUS_DATE',
                    description=(
                        f"Date '{raw_date}' is ambiguous. "
                        f"Could be {interp_dm} (DD-MM) or {interp_md} (MM-DD). "
                        f"Note on row: '{row.get('notes', '')}'"
                    ),
                    action='PENDING_USER',
                    requires_user_approval=True,
                    suggested_fix={
                        'option_a': interp_dm,
                        'option_b': interp_md,
                    },
                )
        return None

    def check_missing_currency(self, row: dict):
        """
        **Row 28**: No currency set.

        Default to INR but flag for user confirmation since the original
        data might have been in a foreign currency.
        """
        currency = str(row.get('currency', '')).strip()
        if not currency:
            row['currency'] = 'INR'
            return AnomalyResult(
                anomaly_type='MISSING_CURRENCY',
                description=(
                    f"'{row.get('description', '')}' has no currency. "
                    f"Defaulted to INR. Please confirm."
                ),
                action='AUTO_FIXED',
                requires_user_approval=True,
                modified_row=dict(row),
            ), row
        return None, row

    def check_foreign_currency(self, row: dict, row_index: int):
        """
        **Rows 20, 21, 23, 26**: USD amounts.

        Convert to INR using historical FX rate for the expense date.
        Store the conversion rate and date for audit trail.
        """
        currency = str(row.get('currency', 'INR')).strip().upper()

        if currency == 'INR':
            # No conversion needed — INR amount IS the canonical amount
            row['amount_inr'] = row.get('amount')
            return None, row

        try:
            expense_date = row.get('date', '')
            rate = self.fx_client.get_rate(currency, 'INR', expense_date)
            original_amount = Decimal(str(row.get('amount', '0')))
            converted = (original_amount * rate).quantize(Decimal('0.01'))
            row['amount_inr'] = str(converted)
            row['exchange_rate_used'] = str(rate)
            row['exchange_rate_date'] = expense_date
            return AnomalyResult(
                anomaly_type='FOREIGN_CURRENCY',
                description=(
                    f"{currency} {original_amount} converted to "
                    f"INR {converted} using rate "
                    f"{currency}/INR = {rate} on {expense_date}."
                ),
                action='AUTO_FIXED',
                requires_user_approval=False,
                modified_row=dict(row),
            ), row
        except Exception as e:
            return AnomalyResult(
                anomaly_type='FOREIGN_CURRENCY',
                description=(
                    f"Could not convert {currency} to INR: {e}. "
                    f"Manual amount needed."
                ),
                action='PENDING_USER',
                requires_user_approval=True,
            ), row

    def check_missing_paid_by(self, row: dict):
        """
        **Row 13**: House cleaning supplies — no payer recorded.

        Cannot calculate balances without knowing who fronted the money.
        """
        paid_by = str(row.get('paid_by', '')).strip()
        if not paid_by:
            return AnomalyResult(
                anomaly_type='MISSING_PAID_BY',
                description=(
                    f"'{row.get('description', '')}' has no payer. "
                    f"Notes: '{row.get('notes', '')}'. "
                    f"Cannot calculate balances without a payer."
                ),
                action='PENDING_USER',
                requires_user_approval=True,
                suggested_fix={
                    'options': [m['name'] for m in self.group_members],
                },
            )
        return None

    def check_settlement_pattern(self, row: dict):
        """
        **Rows 14, 38**: Detect settlements disguised as expenses.

        Keywords in description/notes signal this is a direct payment
        between members, not a shared expense.
        """
        desc = str(row.get('description', '')).lower()
        notes = str(row.get('notes', '')).lower()
        combined = f"{desc} {notes}"

        if any(kw in combined for kw in SETTLEMENT_KEYWORDS):
            return AnomalyResult(
                anomaly_type='SETTLEMENT_PATTERN',
                description=(
                    f"'{row.get('description', '')}' appears to be a "
                    f"settlement/payment, not a shared expense. "
                    f"Will import as Settlement record, not Expense."
                ),
                action='AUTO_FIXED',
                requires_user_approval=False,
                suggested_fix={'import_as': 'settlement'},
            )
        return None

    def check_name_fuzzy_match(self, row: dict):
        """
        **Rows 9, 11, 27**: Name variants and typos.

        - ``priya`` → ``Priya`` (case mismatch)
        - ``Priya S`` → ``Priya`` (≥ 80% similarity via difflib)
        - ``rohan `` → ``Rohan`` (trailing whitespace)

        Uses ``difflib.get_close_matches`` with cutoff=0.6 for fuzzy matching.
        """
        anomaly = None

        # --- Check paid_by field ---
        paid_by_raw = str(row.get('paid_by', '')).strip()
        if paid_by_raw:
            canonical = self._fuzzy_resolve(paid_by_raw)
            if canonical and canonical != paid_by_raw:
                row['paid_by_original'] = paid_by_raw
                row['paid_by'] = canonical
                anomaly = AnomalyResult(
                    anomaly_type='NAME_FUZZY_MATCH',
                    description=(
                        f"Payer name '{paid_by_raw}' did not exactly match "
                        f"any member. Auto-matched to '{canonical}' "
                        f"(fuzzy match >= 60%). Original preserved."
                    ),
                    action='AUTO_FIXED',
                    requires_user_approval=False,
                    modified_row=dict(row),
                )
            elif canonical:
                row['paid_by'] = canonical

        # --- Check split_with names ---
        split_with_raw = str(row.get('split_with', '')).strip()
        if split_with_raw:
            names = [n.strip() for n in split_with_raw.split(';')]
            resolved = []
            any_fuzzy = False
            for name in names:
                canonical = self._fuzzy_resolve(name)
                if canonical:
                    if canonical != name:
                        any_fuzzy = True
                    resolved.append(canonical)
                else:
                    resolved.append(name)  # Unknown — keep original
            row['split_with'] = ';'.join(resolved)

            # If split_with names were fuzzy-matched but paid_by was clean,
            # create an anomaly for the split_with changes
            if any_fuzzy and anomaly is None:
                anomaly = AnomalyResult(
                    anomaly_type='NAME_FUZZY_MATCH',
                    description=(
                        f"Some names in split_with were fuzzy-matched. "
                        f"Original: '{split_with_raw}' → Resolved: '{row['split_with']}'."
                    ),
                    action='AUTO_FIXED',
                    requires_user_approval=False,
                    modified_row=dict(row),
                )

        return anomaly, row

    def _fuzzy_resolve(self, name: str) -> Optional[str]:
        """
        Return canonical member name if fuzzy match found, else ``None``.

        Matching strategy (in order):
          1. Exact case-insensitive match
          2. ``difflib.get_close_matches`` with cutoff=0.6
        """
        name_clean = name.strip().lower()
        # 1. Exact match
        if name_clean in self.member_names_lower:
            return self.member_names_lower[name_clean]['name']
        # 2. Fuzzy match
        matches = difflib.get_close_matches(
            name_clean,
            list(self.member_names_lower.keys()),
            n=1,
            cutoff=0.6,
        )
        if matches:
            return self.member_names_lower[matches[0]]['name']
        return None

    def check_unknown_member(self, row: dict):
        """
        **Row 23**: ``Dev's friend Kabir`` — not a registered group member.

        After fuzzy matching, any remaining unresolved names are flagged.
        User must decide: add as guest or absorb their share.
        """
        split_with = str(row.get('split_with', '')).strip()
        if not split_with:
            return None

        names = [n.strip() for n in split_with.split(';')]
        unknown = [
            name for name in names
            if not self._fuzzy_resolve(name)
        ]

        if unknown:
            return AnomalyResult(
                anomaly_type='UNKNOWN_MEMBER',
                description=(
                    f"Unknown member(s) in split: {', '.join(unknown)}. "
                    f"These people are not registered group members. "
                    f"Options: (a) Add as guest, (b) Absorb their share "
                    f"among existing group members."
                ),
                action='PENDING_USER',
                requires_user_approval=True,
                suggested_fix={
                    'unknown_names': unknown,
                    'options': ['add_as_guest', 'absorb_share'],
                },
            )
        return None

    def check_member_post_departure(self, row: dict):
        """
        **Row 36**: Meera in April groceries after she left end of March.

        If an expense date is after a member's ``left_at``, auto-remove
        them from the split and flag for user approval.
        """
        expense_date_str = str(row.get('date', '')).strip()
        try:
            expense_date = date.fromisoformat(expense_date_str)
        except (ValueError, TypeError):
            return None, row

        split_with = str(row.get('split_with', '')).strip()
        if not split_with:
            return None, row

        names = [n.strip() for n in split_with.split(';')]
        removed = []
        kept = []

        for name in names:
            member = self._get_member_by_name(name)
            if member and member.get('left_at') and expense_date > member['left_at']:
                # This member had already left the group on the expense date
                removed.append(name)
            else:
                kept.append(name)

        if removed:
            row['split_with'] = ';'.join(kept)
            return AnomalyResult(
                anomaly_type='MEMBER_POST_DEPARTURE',
                description=(
                    f"Expense dated {expense_date} includes "
                    f"{', '.join(removed)} who had already left the group. "
                    f"Auto-removed from split. "
                    f"Shares recalculated among remaining: {', '.join(kept)}."
                ),
                action='AUTO_FIXED',
                requires_user_approval=True,
                modified_row=dict(row),
            ), row

        return None, row

    def check_percentage_sum(self, row: dict):
        """
        **Row 15**: Pizza Friday — Aisha 30% + Rohan 30% + Priya 30% + Meera 20% = 110%.

        Percentages must sum to exactly 100%. Any deviation requires manual
        review because auto-scaling vs. reassigning produces different results.
        """
        if str(row.get('split_type', '')).strip().lower() != 'percentage':
            return None

        details = str(row.get('split_details', '')).strip()
        if not details:
            return None

        total = Decimal('0')
        parts = [p.strip() for p in details.split(';')]
        for part in parts:
            pct_match = re.search(r'(\d+(?:\.\d+)?)\s*%', part)
            if pct_match:
                total += Decimal(pct_match.group(1))

        if abs(total - 100) > Decimal('0.01'):
            return AnomalyResult(
                anomaly_type='PERCENTAGE_SUM_ERROR',
                description=(
                    f"Percentages sum to {total}%, not 100%. "
                    f"Details: '{details}'. Cannot auto-correct — "
                    f"different fixes (scale vs reassign) would produce "
                    f"different results. Manual review required."
                ),
                action='PENDING_USER',
                requires_user_approval=True,
                suggested_fix={
                    'current_sum': float(total),
                    'raw_details': details,
                    'options': ['scale_to_100', 'manual_edit'],
                },
            )
        return None

    def check_split_type_conflict(self, row: dict):
        """
        **Row 42**: ``split_type=equal`` but ``split_details`` also provided.

        Equal split needs no details — the presence of both signals
        conflicting intent. Auto-resolve by ignoring details.
        """
        split_type = str(row.get('split_type', '')).strip().lower()
        split_details = str(row.get('split_details', '')).strip()

        if split_type == 'equal' and split_details:
            return AnomalyResult(
                anomaly_type='SPLIT_TYPE_CONFLICT',
                description=(
                    f"split_type is 'equal' but split_details "
                    f"'{split_details}' are also provided. "
                    f"Equal split takes precedence. Details ignored."
                ),
                action='AUTO_FIXED',
                requires_user_approval=False,
            )
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_member_by_name(self, name: str) -> Optional[dict]:
        """Look up a group member by name (with fuzzy matching)."""
        canonical = self._fuzzy_resolve(name)
        if canonical:
            return self.member_names_lower.get(canonical.lower())
        return None
