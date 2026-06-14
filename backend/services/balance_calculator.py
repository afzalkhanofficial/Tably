"""
Balance Calculation Engine
==========================

Core business logic for the flat expenses tracker.
Computes net balances, settlement plans, and per-user breakdowns.

All monetary values are in INR (Indian Rupee). Multi-currency expenses
are pre-converted to INR at import time and stored in ``amount_inr`` /
``ExpenseSplit.amount_owed``, so the calculator never touches exchange rates.
"""

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from apps.expenses.models import Expense, ExpenseSplit, Settlement
from apps.groups.models import GroupMember


class BalanceCalculator:
    """
    Computes net balances for all members of a group.

    All amounts are in INR (Indian Rupee). USD expenses are pre-converted
    to INR at the time of import and stored in amount_inr / expense_split.amount_owed.
    This means the calculator never needs to touch exchange rates.

    Balance sign convention:
        positive = other people owe this person money (they are owed)
        negative = this person owes money to others (they owe)
    """

    def __init__(self, group_id: int):
        self.group_id = group_id
        # Cache membership lookup so we don't hit the DB on every expense
        self._memberships = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_memberships(self):
        """
        Pre-load all memberships for this group into a dict keyed by user_id.
        Each user may have multiple membership windows (left and re-joined),
        so we store a list of GroupMember objects per user.
        """
        if self._memberships is not None:
            return
        self._memberships = defaultdict(list)
        for m in GroupMember.objects.filter(group_id=self.group_id):
            self._memberships[m.user_id].append(m)

    def _is_member_active_on(self, user_id: int, date) -> bool:
        """
        Check if a user was an active group member on the given date.

        A user can have multiple membership windows (e.g. left and re-joined).
        Returns True if ANY of their membership windows covers the date.
        """
        self._load_memberships()
        memberships = self._memberships.get(user_id, [])
        # If user has no memberships at all, they're a guest — still valid
        # for expenses they're explicitly added to (like Dev on the Goa trip).
        # But for balance purposes, we only count them if they have a membership.
        if not memberships:
            # No membership record at all — this is a guest user.
            # Guests don't get membership-date filtering; their splits
            # are included as-is since they were explicitly added.
            return True
        # Check each membership window for coverage on this date
        return any(m.is_active_on(date) for m in memberships)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_group_balances(self, as_of_date=None) -> dict:
        """
        Returns ``{user_id: Decimal(net_balance)}`` for all members.

        ``as_of_date``: if provided, only include expenses up to this date.
        Used to show "what did balances look like at end of March?" etc.

        Membership-date filtering:
            If a user's split falls on a date outside their membership window,
            that split is excluded. This enforces the time-scoped membership
            invariant (e.g. Sam joined 2026-04-08 → no balance from March expenses).
        """
        balances = defaultdict(Decimal)

        # Step 1: Get all non-deleted, non-settlement expenses for this group
        expenses_qs = Expense.objects.filter(
            group_id=self.group_id,
            is_deleted=False,
            is_settlement=False,
        ).prefetch_related('splits')

        if as_of_date:
            expenses_qs = expenses_qs.filter(expense_date__lte=as_of_date)

        for expense in expenses_qs:
            if expense.paid_by_id is None:
                # Cannot process expenses with unknown payer — skip
                continue

            # Collect only splits for members active on the expense date
            active_splits = [
                s for s in expense.splits.all()
                if self._is_member_active_on(s.user_id, expense.expense_date)
            ]

            # The payer is OWED the sum of ACTIVE splits (not the full amount)
            # because excluded splits (e.g. departed members) reduce the pool.
            # "I paid ₹3000 but only 3 of 4 people are active → I'm owed ₹2250"
            active_total = sum(s.amount_owed for s in active_splits)
            # Only credit the payer if they themselves are active on this date
            if self._is_member_active_on(expense.paid_by_id, expense.expense_date):
                balances[expense.paid_by_id] += active_total

            # Each active person in the split OWES their share
            # "I owe my portion of this expense back to whoever paid"
            for split in active_splits:
                balances[split.user_id] -= split.amount_owed

        # Step 2: Apply settlements (actual payments already made)
        settlements_qs = Settlement.objects.filter(group_id=self.group_id)
        if as_of_date:
            settlements_qs = settlements_qs.filter(settled_at__date__lte=as_of_date)

        for settlement in settlements_qs:
            # The person who paid a settlement has reduced their debt
            # "Rohan paid Aisha ₹5000, so Rohan owes ₹5000 less"
            balances[settlement.paid_by_id] += settlement.amount_inr
            # The person who received has reduced what they're owed
            # "Aisha received ₹5000, so others owe her ₹5000 less"
            balances[settlement.paid_to_id] -= settlement.amount_inr

        # Step 3: Round all balances to 2 decimal places
        return {
            uid: bal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            for uid, bal in balances.items()
            if bal != 0  # Skip users with exactly zero balance
        }

    def get_settlement_plan(self) -> list:
        """
        Computes the MINIMUM number of transactions to settle all debts.
        Uses a greedy algorithm — match the biggest debtor with the biggest creditor.

        This answers Aisha's requirement: "one number per person, who pays whom."

        Returns: ``[{"from_user_id": X, "to_user_id": Y, "amount": Z}, ...]``
        """
        balances = self.get_group_balances()

        # Separate into who owes (negative balance) and who is owed (positive balance)
        debtors = sorted(
            [(uid, -bal) for uid, bal in balances.items() if bal < 0],
            key=lambda x: x[1], reverse=True,  # Largest debt first
        )
        creditors = sorted(
            [(uid, bal) for uid, bal in balances.items() if bal > 0],
            key=lambda x: x[1], reverse=True,  # Largest credit first
        )

        transactions = []
        i, j = 0, 0  # Pointers into debtors and creditors lists

        # Convert to mutable lists of [user_id, remaining_amount]
        debtors = [[uid, amt] for uid, amt in debtors]
        creditors = [[uid, amt] for uid, amt in creditors]

        while i < len(debtors) and j < len(creditors):
            debtor_id, debt_remaining = debtors[i]
            creditor_id, credit_remaining = creditors[j]

            # The transaction amount is the smaller of what's owed and what's expected
            # Example: Rohan owes ₹2000 total, Aisha is owed ₹3000 total
            #   → Rohan pays Aisha ₹2000, Aisha still has ₹1000 credit left
            payment = min(debt_remaining, credit_remaining)
            payment = payment.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            if payment > 0:
                transactions.append({
                    'from_user_id': debtor_id,
                    'to_user_id': creditor_id,
                    'amount': payment,
                })

            # Reduce remaining amounts after this transaction
            debtors[i][1] -= payment
            creditors[j][1] -= payment

            if debtors[i][1] <= 0:
                i += 1  # This debtor is fully settled
            if creditors[j][1] <= 0:
                j += 1  # This creditor is fully settled

        return transactions

    def get_user_breakdown(self, user_id: int) -> dict:
        """
        Returns every expense that affects a user's balance.
        This is Rohan's requirement: "if the app says I owe ₹2300,
        I want to see exactly which expenses make that up."

        Returns a dict with ``user_id``, ``final_balance``, and ``entries``
        (a chronologically sorted list of expense entries with running balance).
        """
        splits = (
            ExpenseSplit.objects
            .filter(
                user_id=user_id,
                expense__group_id=self.group_id,
                expense__is_deleted=False,
                expense__is_settlement=False,
            )
            .select_related('expense', 'expense__paid_by')
            .order_by('expense__expense_date')
        )

        entries = []
        running_balance = Decimal('0')

        for split in splits:
            exp = split.expense

            # Check membership: skip if user wasn't active on the expense date
            if not self._is_member_active_on(user_id, exp.expense_date):
                continue

            if exp.paid_by_id == user_id:
                # User PAID this expense — they are owed the sum of ACTIVE splits
                # (consistent with get_group_balances which credits active_total,
                # not the raw amount_inr, to account for membership filtering).
                # We also subtract their OWN split here since get_group_balances
                # does: +active_total (payer credit) then -own_share (splits loop).
                # In the breakdown we handle both in a single entry.
                active_total = sum(
                    s.amount_owed
                    for s in exp.splits.all()
                    if self._is_member_active_on(s.user_id, exp.expense_date)
                )
                # Net for payer = credited amount - their own share of the expense
                contribution = active_total - split.amount_owed
                role = 'PAYER'
            else:
                # User is in the split but didn't pay — they OWE their share
                # (shown as negative contribution since it's money going out)
                contribution = -split.amount_owed
                role = 'PARTICIPANT'

            # Running tally: positive = owed by others, negative = owes others
            running_balance += contribution

            entries.append({
                'expense_id': exp.id,
                'date': str(exp.expense_date),
                'description': exp.description,
                'paid_by': exp.paid_by.name if exp.paid_by else 'Unknown',
                'total_amount_inr': float(exp.amount_inr),
                'original_currency': exp.currency,
                'original_amount': float(exp.total_amount),
                'your_share_inr': float(split.amount_owed),
                'role': role,
                'contribution_to_your_balance': float(contribution),
                'running_balance': float(
                    running_balance.quantize(Decimal('0.01'))
                ),
            })

        # Also include settlements this user PAID (reduces their debt)
        settlements_paid = Settlement.objects.filter(
            group_id=self.group_id, paid_by_id=user_id,
        ).select_related('paid_to')

        for s in settlements_paid:
            # Paying a settlement INCREASES your balance (you gave money away)
            running_balance += s.amount_inr
            entries.append({
                'type': 'SETTLEMENT',
                'date': str(s.settled_at.date()),
                'description': f'Payment to {s.paid_to.name}',
                'contribution_to_your_balance': float(s.amount_inr),
                'running_balance': float(
                    running_balance.quantize(Decimal('0.01'))
                ),
            })

        # Include settlements this user RECEIVED (reduces what others owe them)
        settlements_received = Settlement.objects.filter(
            group_id=self.group_id, paid_to_id=user_id,
        ).select_related('paid_by')

        for s in settlements_received:
            # Receiving a settlement DECREASES your balance (someone paid you back)
            running_balance -= s.amount_inr
            entries.append({
                'type': 'SETTLEMENT',
                'date': str(s.settled_at.date()),
                'description': f'Payment from {s.paid_by.name}',
                'contribution_to_your_balance': float(-s.amount_inr),
                'running_balance': float(
                    running_balance.quantize(Decimal('0.01'))
                ),
            })

        return {
            'user_id': user_id,
            'final_balance': float(
                running_balance.quantize(Decimal('0.01'))
            ),
            'entries': sorted(entries, key=lambda x: x['date']),
        }
