"""
CSV Parser — orchestrates row-by-row parsing and cross-row duplicate detection.
================================================================================

Usage::

    parser = CSVParser(group_id=1, group_members=[...])
    result = parser.parse(csv_string)
    # result = {
    #     'total_rows': 42,
    #     'results': [...],       # per-row parse results
    #     'summary': {...},       # aggregate counts
    # }

This module ONLY analyses — it never writes to the database.
Database writes are handled by ``importer.services.commit_row()``.
"""

import csv
import difflib
import io
from decimal import Decimal

from .anomaly_detector import AnomalyDetector, AnomalyResult
from .fx_client import FXClient


class CSVParser:
    """Parses CSV content and runs all anomaly checks."""

    def __init__(self, group_id: int, group_members: list):
        """
        Args:
            group_id:       primary key of the Group
            group_members:  list of dicts
                            ``{name, user_id, joined_at, left_at}``
        """
        self.group_id = group_id
        self.group_members = group_members
        self.fx_client = FXClient()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, csv_content: str) -> dict:
        """
        Parse CSV content string and return a ``ParseResult`` dict.

        Does **NOT** write to the database — only analyses.

        Returns::

            {
                'total_rows': int,
                'results': [
                    {
                        'row_number': int,   # 1-indexed from CSV (row 2 = first data row)
                        'original_row': dict,
                        'clean_row': dict,   # after auto-fixes
                        'anomalies': [AnomalyResult, ...],
                        'status': 'CLEAN' | 'AUTO_FIXED' | 'REQUIRES_APPROVAL' | 'SKIPPED',
                    },
                    ...
                ],
                'summary': { ... },
            }
        """
        reader = csv.DictReader(io.StringIO(csv_content))
        all_rows = list(reader)

        detector = AnomalyDetector(
            group_members=self.group_members,
            all_rows=all_rows,
            fx_client=self.fx_client,
        )

        # First pass: cross-row anomaly detection (exact & conflicting duplicates)
        duplicate_anomalies = self._find_duplicates(all_rows)

        results = []
        for idx, row in enumerate(all_rows):
            # row_number = idx + 2: +1 for 0→1 indexing, +1 for the header row
            row_number = idx + 2

            # Preserve original date string for ambiguous-date check
            # (check_date_format will overwrite row['date'] with ISO format)
            row['_original_date'] = row.get('date', '')

            # Run all per-row anomaly checks
            clean_row, anomalies = detector.detect_all(row, idx)

            # Append cross-row duplicate anomalies from first pass
            if row_number in duplicate_anomalies:
                anomalies.append(duplicate_anomalies[row_number])

            # Remove internal helper field before persisting
            clean_row.pop('_original_date', None)

            # Classify overall row status (most severe wins)
            if any(a.action == 'SKIPPED' for a in anomalies):
                status = 'SKIPPED'
            elif any(a.action == 'PENDING_USER' or a.requires_user_approval
                     for a in anomalies):
                status = 'REQUIRES_APPROVAL'
            elif anomalies:
                status = 'AUTO_FIXED'
            else:
                status = 'CLEAN'

            results.append({
                'row_number': row_number,
                'original_row': {
                    k: v for k, v in row.items()
                    if k != '_original_date'
                },
                'clean_row': clean_row,
                'anomalies': anomalies,
                'status': status,
            })

        return {
            'total_rows': len(all_rows),
            'results': results,
            'summary': self._build_summary(results),
        }

    # ------------------------------------------------------------------
    # Cross-row duplicate detection
    # ------------------------------------------------------------------

    def _normalize_date(self, raw_date: str) -> str:
        """Parse raw date into YYYY-MM-DD ISO format for uniform comparison."""
        from datetime import datetime
        raw_date = str(raw_date).strip()
        for fmt in ('%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y'):
            try:
                return datetime.strptime(raw_date, fmt).date().isoformat()
            except ValueError:
                continue
        try:
            from dateutil import parser as dateutil_parser
            parsed = dateutil_parser.parse(raw_date, dayfirst=True)
            if parsed.year < 2020:
                parsed = parsed.replace(year=2026)
            return parsed.date().isoformat()
        except Exception:
            return raw_date

    def _normalize_amount(self, raw_amount: str) -> str:
        """Strip commas/currency symbols and convert to standardized Decimal string."""
        cleaned = str(raw_amount).strip().replace(',', '').replace('₹', '').replace('$', '')
        try:
            return str(Decimal(cleaned))
        except Exception:
            return cleaned

    def _normalize_description(self, raw_desc: str) -> str:
        """
        Normalize descriptions by lowercasing, stripping punctuation,
        removing common English stop words, and sorting words alphabetically.
        """
        import re
        STOP_WORDS = {
            'at', 'for', 'the', 'in', 'and', 'a', 'of', 'to', 'on', 'with',
            'by', 'from', 'is', 'was', 'our', 'us', 'my',
        }
        desc = re.sub(r'[^a-zA-Z0-9\s]', ' ', str(raw_desc).lower())
        words = [w for w in desc.split() if w not in STOP_WORDS]
        return ' '.join(sorted(words))

    def _normalize_payer(self, raw_payer: str) -> str:
        """Resolve raw payer name to canonical lowercased member name if possible."""
        name_clean = str(raw_payer).strip().lower()
        if not name_clean:
            return ''
        for m in self.group_members:
            if m['name'].lower() == name_clean:
                return m['name'].lower()
        import difflib
        member_names = [m['name'].lower() for m in self.group_members]
        matches = difflib.get_close_matches(name_clean, member_names, n=1, cutoff=0.6)
        if matches:
            return matches[0]
        return name_clean

    def _find_duplicates(self, rows: list) -> dict:
        """
        Detect duplicates across all rows using normalized values.
        Returns ``{row_number: AnomalyResult}`` for flagged rows.

        Two types:

        **EXACT_DUPLICATE** (Rows 5 & 6 — Marina Bites):
          Same date + description + amount + paid_by.

        **CONFLICTING_DUPLICATE** (Rows 24 & 25 — Thalassa dinner):
          Same date + description + different amounts.
        """
        seen_exact: dict[tuple, int] = {}
        anomalies: dict[int, AnomalyResult] = {}

        # --- Pre-normalize all rows to make comparison robust ---
        normalized_rows = []
        for idx, row in enumerate(rows):
            row_number = idx + 2
            normalized_rows.append({
                'row_number': row_number,
                'raw': row,
                'date': self._normalize_date(row.get('date', '')),
                'desc': self._normalize_description(row.get('description', '')),
                'amount': self._normalize_amount(row.get('amount', '')),
                'paid_by': self._normalize_payer(row.get('paid_by', '')),
            })

        # --- Pass 1: Exact duplicates ---
        for nr in normalized_rows:
            key_exact = (
                nr['date'],
                nr['desc'],
                nr['amount'],
                nr['paid_by'],
            )

            # Ignore zero-amount rows as they are skipped anyway
            if nr['amount'] == '0':
                continue

            if key_exact in seen_exact:
                original_row_num = seen_exact[key_exact]
                anomalies[nr['row_number']] = AnomalyResult(
                    anomaly_type='EXACT_DUPLICATE',
                    description=(
                        f"Exact duplicate of row {original_row_num} "
                        f"(same date, description, amount, payer). "
                        f"Row {original_row_num} is kept. "
                        f"This row requires approval to skip."
                    ),
                    action='PENDING_USER',
                    requires_user_approval=True,
                    suggested_fix={
                        'keep_row': original_row_num,
                        'skip_row': nr['row_number'],
                    },
                )
            else:
                seen_exact[key_exact] = nr['row_number']

        # --- Pass 2: Conflicting duplicates (same date, same desc, different amounts) ---
        date_groups: dict[str, list] = {}
        for nr in normalized_rows:
            date_groups.setdefault(nr['date'], []).append(nr)

        for _date_key, group in date_groups.items():
            if len(group) < 2:
                continue
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    nr_a = group[i]
                    nr_b = group[j]

                    rn_a, rn_b = nr_a['row_number'], nr_b['row_number']

                    # Skip if either is already flagged as exact duplicate
                    if rn_a in anomalies or rn_b in anomalies:
                        continue

                    # If normalized description is identical, but amounts are different
                    if nr_a['desc'] and nr_a['desc'] == nr_b['desc'] and nr_a['amount'] != nr_b['amount']:
                        conflict = AnomalyResult(
                            anomaly_type='CONFLICTING_DUPLICATE',
                            description=(
                                f"Row {rn_a} "
                                f"('{nr_a['raw'].get('description')}', Rs.{nr_a['raw'].get('amount')}) "
                                f"and row {rn_b} "
                                f"('{nr_b['raw'].get('description')}', Rs.{nr_b['raw'].get('amount')}) "
                                f"appear to describe the same expense with "
                                f"different amounts. "
                                f"Cannot auto-resolve — please choose."
                            ),
                            action='PENDING_USER',
                            requires_user_approval=True,
                            suggested_fix={
                                'row_a': rn_a, 'amount_a': nr_a['raw'].get('amount'),
                                'row_b': rn_b, 'amount_b': nr_b['raw'].get('amount'),
                                'options': [
                                    f'keep_row_{rn_a}',
                                    f'keep_row_{rn_b}',
                                    'keep_both',
                                ],
                            },
                        )
                        # Flag both rows with the same anomaly
                        anomalies[rn_a] = conflict
                        anomalies[rn_b] = conflict

        return anomalies

    # ------------------------------------------------------------------
    # Summary builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_summary(results: list) -> dict:
        """Aggregate row statuses into a summary dict."""
        summary = {
            'total': len(results),
            'clean': 0,
            'auto_fixed': 0,
            'requires_approval': 0,
            'skipped': 0,
        }
        for r in results:
            key = r['status'].lower()
            if key in summary:
                summary[key] += 1
        return summary

