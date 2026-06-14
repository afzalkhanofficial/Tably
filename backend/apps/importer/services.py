"""
Import Services — database commit logic for parsed CSV rows.
=============================================================

Handles the conversion of clean parsed rows into Django model instances
(``Expense`` + ``ExpenseSplit`` records, or ``Settlement`` records).
"""

import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.expenses.models import Expense, ExpenseSplit, Settlement
from apps.groups.models import Group
from apps.users.models import User

logger = logging.getLogger(__name__)


class RowCommitter:
    """Commits a single parsed CSV row to the database."""

    def __init__(self, group: Group, import_session, member_map: dict):
        """
        Args:
            group:          the Group instance
            import_session: the ImportSession instance
            member_map:     ``{canonical_name_lower: User}`` lookup
        """
        self.group = group
        self.import_session = import_session
        self.member_map = member_map

    @transaction.atomic
    def commit_row(self, row: dict, row_number: int, anomalies: list) -> dict:
        """
        Write a parsed row to the database.

        Returns a dict with the created object info, or error details.
        """
        # Check if this row should be imported as a Settlement
        is_settlement = any(
            getattr(a, 'suggested_fix', None)
            and a.suggested_fix.get('import_as') == 'settlement'
            for a in anomalies
        )

        if is_settlement:
            return self._commit_settlement(row, row_number)
        else:
            return self._commit_expense(row, row_number)

    def _commit_expense(self, row: dict, row_number: int) -> dict:
        """Create an Expense + ExpenseSplit records from a parsed row."""
        try:
            # Resolve payer
            paid_by_name = str(row.get('paid_by', '')).strip()
            paid_by = self._resolve_user(paid_by_name)

            # Parse amounts
            amount = Decimal(str(row.get('amount', '0')).strip())
            currency = str(row.get('currency', 'INR')).strip().upper()
            amount_inr = Decimal(str(row.get('amount_inr', amount)).strip())

            # Parse exchange rate if present
            exchange_rate_used = None
            exchange_rate_date = None
            if row.get('exchange_rate_used'):
                exchange_rate_used = Decimal(str(row['exchange_rate_used']))
            if row.get('exchange_rate_date'):
                exchange_rate_date = row['exchange_rate_date']

            # Parse date
            expense_date = date.fromisoformat(
                str(row.get('date', '')).strip()
            )

            # Parse split type
            split_type = str(row.get('split_type', 'equal')).strip().lower()
            if not split_type:
                split_type = 'equal'

            # Is this a refund?
            is_refund = bool(row.get('is_refund', False))

            # Create Expense
            expense = Expense.objects.create(
                group=self.group,
                description=str(row.get('description', '')).strip(),
                total_amount=amount,
                currency=currency,
                amount_inr=amount_inr,
                exchange_rate_used=exchange_rate_used,
                exchange_rate_date=exchange_rate_date,
                paid_by=paid_by,
                expense_date=expense_date,
                split_type=split_type,
                is_refund=is_refund,
                is_settlement=False,
                notes=str(row.get('notes', '')).strip(),
                import_row_ref=row_number,
                import_session=self.import_session,
                created_by=paid_by,
            )

            # Create splits
            splits = self._calculate_splits(
                row, amount_inr, split_type, expense,
            )

            return {
                'type': 'expense',
                'expense_id': expense.id,
                'splits_count': len(splits),
            }

        except Exception as e:
            logger.exception(
                f"Failed to commit expense row {row_number}: {e}"
            )
            return {'type': 'error', 'error': str(e)}

    def _commit_settlement(self, row: dict, row_number: int) -> dict:
        """Create a Settlement record from a parsed row."""
        try:
            paid_by_name = str(row.get('paid_by', '')).strip()
            paid_by = self._resolve_user(paid_by_name)

            # For settlements, split_with contains the recipient
            split_with = str(row.get('split_with', '')).strip()
            recipient_names = [n.strip() for n in split_with.split(';') if n.strip()]
            if not recipient_names:
                return {
                    'type': 'error',
                    'error': 'Settlement has no recipient in split_with',
                }
            paid_to = self._resolve_user(recipient_names[0])

            amount = Decimal(str(row.get('amount', '0')).strip())
            amount_inr = Decimal(str(row.get('amount_inr', amount)).strip())

            settlement = Settlement.objects.create(
                group=self.group,
                paid_by=paid_by,
                paid_to=paid_to,
                amount=abs(amount),
                currency=str(row.get('currency', 'INR')).strip().upper(),
                amount_inr=abs(amount_inr),
                notes=str(row.get('notes', '')).strip(),
                import_row_ref=row_number,
                created_by=paid_by,
            )

            return {
                'type': 'settlement',
                'settlement_id': settlement.id,
            }

        except Exception as e:
            logger.exception(
                f"Failed to commit settlement row {row_number}: {e}"
            )
            return {'type': 'error', 'error': str(e)}

    def _calculate_splits(
        self, row: dict, amount_inr: Decimal, split_type: str, expense: Expense,
    ) -> list:
        """
        Calculate and create ExpenseSplit records based on split type.

        Returns the list of created ExpenseSplit instances.
        """
        split_with = str(row.get('split_with', '')).strip()
        split_details = str(row.get('split_details', '')).strip()
        names = [n.strip() for n in split_with.split(';') if n.strip()]

        # Resolve users (skip names we can't resolve)
        users = []
        for name in names:
            user = self._resolve_user(name)
            if user:
                users.append((name, user))

        if not users:
            return []

        splits = []

        if split_type == 'equal':
            # Equal split: amount_inr / number of people
            per_person = (amount_inr / len(users)).quantize(Decimal('0.01'))
            # Handle rounding: give remainder to last person
            remainder = amount_inr - (per_person * len(users))
            for i, (name, user) in enumerate(users):
                owed = per_person
                if i == len(users) - 1:
                    owed += remainder
                splits.append(
                    ExpenseSplit.objects.create(
                        expense=expense,
                        user=user,
                        amount_owed=owed,
                    )
                )

        elif split_type == 'unequal':
            # Unequal: parse "Name Amount; Name Amount" from split_details
            detail_map = self._parse_unequal_details(split_details)
            for name, user in users:
                owed = detail_map.get(name.lower(), Decimal('0'))
                splits.append(
                    ExpenseSplit.objects.create(
                        expense=expense,
                        user=user,
                        amount_owed=owed,
                    )
                )

        elif split_type == 'percentage':
            # Percentage: parse "Name XX%; Name YY%" from split_details
            pct_map = self._parse_percentage_details(split_details)
            for name, user in users:
                pct = pct_map.get(name.lower(), Decimal('0'))
                owed = (amount_inr * pct / Decimal('100')).quantize(
                    Decimal('0.01')
                )
                splits.append(
                    ExpenseSplit.objects.create(
                        expense=expense,
                        user=user,
                        amount_owed=owed,
                    )
                )

        elif split_type == 'share':
            # Share ratio: parse "Name N; Name M" from split_details
            share_map = self._parse_share_details(split_details)
            total_shares = sum(share_map.values()) or Decimal('1')
            for name, user in users:
                shares = share_map.get(name.lower(), Decimal('1'))
                owed = (amount_inr * shares / total_shares).quantize(
                    Decimal('0.01')
                )
                splits.append(
                    ExpenseSplit.objects.create(
                        expense=expense,
                        user=user,
                        amount_owed=owed,
                    )
                )

        else:
            # Fallback: equal split
            per_person = (amount_inr / len(users)).quantize(Decimal('0.01'))
            for name, user in users:
                splits.append(
                    ExpenseSplit.objects.create(
                        expense=expense,
                        user=user,
                        amount_owed=per_person,
                    )
                )

        return splits

    # ------------------------------------------------------------------
    # Detail parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_unequal_details(details: str) -> dict:
        """
        Parse ``"Rohan 700; Priya 400; Meera 400"`` into
        ``{'rohan': Decimal('700'), 'priya': Decimal('400'), ...}``
        """
        result = {}
        for part in details.split(';'):
            part = part.strip()
            if not part:
                continue
            # Match "Name Amount" — name may have spaces
            match = re.match(r'^(.+?)\s+([\d.]+)\s*$', part)
            if match:
                name = match.group(1).strip().lower()
                try:
                    result[name] = Decimal(match.group(2))
                except InvalidOperation:
                    pass
        return result

    @staticmethod
    def _parse_percentage_details(details: str) -> dict:
        """
        Parse ``"Aisha 30%; Rohan 30%"`` into
        ``{'aisha': Decimal('30'), 'rohan': Decimal('30'), ...}``
        """
        result = {}
        for part in details.split(';'):
            part = part.strip()
            if not part:
                continue
            match = re.match(r'^(.+?)\s+(\d+(?:\.\d+)?)\s*%\s*$', part)
            if match:
                name = match.group(1).strip().lower()
                try:
                    result[name] = Decimal(match.group(2))
                except InvalidOperation:
                    pass
        return result

    @staticmethod
    def _parse_share_details(details: str) -> dict:
        """
        Parse ``"Aisha 1; Rohan 2; Priya 1; Dev 2"`` into
        ``{'aisha': Decimal('1'), 'rohan': Decimal('2'), ...}``
        """
        result = {}
        for part in details.split(';'):
            part = part.strip()
            if not part:
                continue
            match = re.match(r'^(.+?)\s+(\d+(?:\.\d+)?)\s*$', part)
            if match:
                name = match.group(1).strip().lower()
                try:
                    result[name] = Decimal(match.group(2))
                except InvalidOperation:
                    pass
        return result

    # ------------------------------------------------------------------
    # User resolution
    # ------------------------------------------------------------------

    def _resolve_user(self, name: str):
        """
        Resolve a name string to a User instance.

        Tries exact lowercase match first, then falls back to case-insensitive
        DB lookup.

        Returns ``None`` if no match found (should have been caught by
        anomaly detector earlier).
        """
        if not name:
            return None

        name_lower = name.strip().lower()
        user = self.member_map.get(name_lower)
        if user:
            return user

        # Fallback: case-insensitive DB lookup
        try:
            return User.objects.get(name__iexact=name.strip())
        except User.DoesNotExist:
            logger.warning(f"Could not resolve user name: '{name}'")
            return None
        except User.MultipleObjectsReturned:
            logger.warning(f"Multiple users match name: '{name}'")
            return User.objects.filter(name__iexact=name.strip()).first()
