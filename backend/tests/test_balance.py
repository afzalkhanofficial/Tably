"""
Unit tests for the Balance Calculation Engine.

Covers: equal splits, percentage splits, share-ratio splits,
settlements, membership-date filtering, minimum transaction
optimisation, and negative-amount refunds.

Run with:
    cd backend
    ..\\venv\\Scripts\\pytest.exe tests/test_balance.py -v
"""
from datetime import date
from decimal import Decimal

import pytest

from services.balance_calculator import BalanceCalculator


# ===================================================================
# 1. Equal split among three people
# ===================================================================

@pytest.mark.django_db
class TestEqualSplitThreePeople:
    """
    Expense: Aisha pays Rs.3000, split equal among Aisha/Rohan/Priya.
    Each person's share = 3000 / 3 = Rs.1000.

    Expected balances:
        Aisha: +3000 (paid) - 1000 (own share) = +2000  (owed by others)
        Rohan: -1000                                     (owes Aisha)
        Priya: -1000                                     (owes Aisha)

    Settlement plan: Rohan->Aisha Rs.1000, Priya->Aisha Rs.1000
    """

    def test_balances(self, flat_group, aisha, rohan, priya, memberships, make_expense):
        # Aisha pays Rs.3000, split equally among 3 people
        make_expense(
            paid_by=aisha,
            amount=Decimal('3000'),
            expense_date=date(2026, 3, 1),
            splits={
                aisha: Decimal('1000'),  # Each person owes Rs.1000
                rohan: Decimal('1000'),
                priya: Decimal('1000'),
            },
            description='March groceries',
        )

        calc = BalanceCalculator(flat_group.id)
        balances = calc.get_group_balances()

        # Aisha paid Rs.3000, her own share is Rs.1000 → net = +Rs.2000
        assert balances[aisha.id] == Decimal('2000.00')
        # Rohan owes his share → net = -Rs.1000
        assert balances[rohan.id] == Decimal('-1000.00')
        # Priya owes her share → net = -Rs.1000
        assert balances[priya.id] == Decimal('-1000.00')

    def test_zero_sum(self, flat_group, aisha, rohan, priya, memberships, make_expense):
        """All balances must sum to exactly zero — money doesn't appear from nowhere."""
        make_expense(
            paid_by=aisha,
            amount=Decimal('3000'),
            expense_date=date(2026, 3, 1),
            splits={aisha: Decimal('1000'), rohan: Decimal('1000'), priya: Decimal('1000')},
        )

        calc = BalanceCalculator(flat_group.id)
        balances = calc.get_group_balances()

        # Zero-sum invariant: total of all balances must be zero
        total = sum(balances.values())
        assert total == Decimal('0.00'), f'Balances are not zero-sum: {total}'

    def test_settlement_plan(self, flat_group, aisha, rohan, priya, memberships, make_expense):
        """Settlement plan should have Rohan & Priya each paying Aisha Rs.1000."""
        make_expense(
            paid_by=aisha,
            amount=Decimal('3000'),
            expense_date=date(2026, 3, 1),
            splits={aisha: Decimal('1000'), rohan: Decimal('1000'), priya: Decimal('1000')},
        )

        calc = BalanceCalculator(flat_group.id)
        plan = calc.get_settlement_plan()

        # Exactly 2 transactions needed
        assert len(plan) == 2

        # Both transactions should go to Aisha
        for txn in plan:
            assert txn['to_user_id'] == aisha.id
            assert txn['amount'] == Decimal('1000.00')

        # Debtors are Rohan and Priya
        debtor_ids = {txn['from_user_id'] for txn in plan}
        assert debtor_ids == {rohan.id, priya.id}


# ===================================================================
# 2. Percentage split
# ===================================================================

@pytest.mark.django_db
class TestPercentageSplit:
    """
    Expense: Rs.1440, split as Aisha 30%, Rohan 30%, Priya 30%, Meera 10%.
    Amounts: 432 + 432 + 432 + 144 = 1440.
    """

    def test_splits_sum_to_total(
        self, flat_group, aisha, rohan, priya, meera, memberships, make_expense,
    ):
        # Calculate each person's share using percentages
        total = Decimal('1440')
        aisha_share = (total * Decimal('30') / Decimal('100'))   # Rs.432
        rohan_share = (total * Decimal('30') / Decimal('100'))   # Rs.432
        priya_share = (total * Decimal('30') / Decimal('100'))   # Rs.432
        meera_share = (total * Decimal('10') / Decimal('100'))   # Rs.144

        make_expense(
            paid_by=aisha,
            amount=total,
            expense_date=date(2026, 3, 1),
            splits={
                aisha: aisha_share,
                rohan: rohan_share,
                priya: priya_share,
                meera: meera_share,
            },
            split_type='percentage',
            description='Percentage split expense',
        )

        calc = BalanceCalculator(flat_group.id)
        balances = calc.get_group_balances()

        # The sum of all absolute split amounts must equal the expense total
        assert aisha_share + rohan_share + priya_share + meera_share == total

        # Verify individual balances:
        # Aisha paid Rs.1440, owes Rs.432 → net = +1008
        assert balances[aisha.id] == Decimal('1008.00')
        # Rohan owes Rs.432
        assert balances[rohan.id] == Decimal('-432.00')
        # Priya owes Rs.432
        assert balances[priya.id] == Decimal('-432.00')
        # Meera owes Rs.144 (she left later, but expense is in March while she's still active)
        assert balances[meera.id] == Decimal('-144.00')

        # Zero-sum check
        total_balance = sum(balances.values())
        assert total_balance == Decimal('0.00')


# ===================================================================
# 3. Share-ratio split
# ===================================================================

@pytest.mark.django_db
class TestShareSplit:
    """
    Expense: Rs.3600, Aisha 1 share, Rohan 2 shares, Priya 1 share, Dev 2 shares.
    Total shares = 1 + 2 + 1 + 2 = 6.
    Each share = 3600 / 6 = Rs.600.

    Aisha = Rs.600, Rohan = Rs.1200, Priya = Rs.600, Dev = Rs.1200.
    """

    def test_share_amounts(
        self, flat_group, aisha, rohan, priya, dev, memberships, make_expense,
    ):
        total = Decimal('3600')
        # share_value = total / total_shares = 3600 / 6 = 600
        share_value = total / Decimal('6')

        make_expense(
            paid_by=aisha,
            amount=total,
            expense_date=date(2026, 3, 15),
            splits={
                aisha: share_value * 1,  # 1 share = Rs.600
                rohan: share_value * 2,  # 2 shares = Rs.1200
                priya: share_value * 1,  # 1 share = Rs.600
                dev:   share_value * 2,  # 2 shares = Rs.1200
            },
            split_type='share',
            description='Goa trip (share-based)',
        )

        calc = BalanceCalculator(flat_group.id)
        balances = calc.get_group_balances()

        # Aisha paid Rs.3600, owes Rs.600 → net = +3000
        assert balances[aisha.id] == Decimal('3000.00')
        # Rohan owes 2 shares = Rs.1200
        assert balances[rohan.id] == Decimal('-1200.00')
        # Priya owes 1 share = Rs.600
        assert balances[priya.id] == Decimal('-600.00')
        # Dev owes 2 shares = Rs.1200 (guest, no membership, still included)
        assert balances[dev.id] == Decimal('-1200.00')

        # Zero-sum check
        assert sum(balances.values()) == Decimal('0.00')


# ===================================================================
# 4. Settlement reduces balance to zero
# ===================================================================

@pytest.mark.django_db
class TestSettlementReducesBalance:
    """
    Setup: Expense gives Rohan a balance of -Rs.2000 (he owes Aisha).
    Action: Settlement — Rohan pays Aisha Rs.2000.
    Expected: All balances become zero.
    """

    def test_full_settlement(
        self, flat_group, aisha, rohan, memberships, make_expense, make_settlement,
    ):
        # Expense: Aisha pays Rs.2000, Rohan owes all of it
        make_expense(
            paid_by=aisha,
            amount=Decimal('2000'),
            expense_date=date(2026, 3, 5),
            splits={
                rohan: Decimal('2000'),  # Rohan owes the full Rs.2000
            },
            description='Rohan-only expense',
        )

        # Before settlement: Aisha = +2000, Rohan = -2000
        calc = BalanceCalculator(flat_group.id)
        pre_balances = calc.get_group_balances()
        assert pre_balances[aisha.id] == Decimal('2000.00')
        assert pre_balances[rohan.id] == Decimal('-2000.00')

        # Rohan pays Aisha Rs.2000 to settle up
        make_settlement(paid_by=rohan, paid_to=aisha, amount=Decimal('2000'))

        # After settlement: all balances must be zero (empty dict since zeros are excluded)
        calc_after = BalanceCalculator(flat_group.id)
        post_balances = calc_after.get_group_balances()
        assert len(post_balances) == 0, (
            f'Expected all-zero balances but got: {post_balances}'
        )

    def test_partial_settlement(
        self, flat_group, aisha, rohan, memberships, make_expense, make_settlement,
    ):
        """Settling half the debt should leave half remaining."""
        make_expense(
            paid_by=aisha,
            amount=Decimal('2000'),
            expense_date=date(2026, 3, 5),
            splits={rohan: Decimal('2000')},
        )

        # Rohan pays only Rs.1000 (half)
        make_settlement(paid_by=rohan, paid_to=aisha, amount=Decimal('1000'))

        calc = BalanceCalculator(flat_group.id)
        balances = calc.get_group_balances()

        # Rohan still owes Rs.1000
        assert balances[rohan.id] == Decimal('-1000.00')
        # Aisha is still owed Rs.1000
        assert balances[aisha.id] == Decimal('1000.00')


# ===================================================================
# 5. Member outside date range is excluded
# ===================================================================

@pytest.mark.django_db
class TestMemberOutsideDateRangeExcluded:
    """
    Sam joins 2026-04-08. An expense dated 2026-03-15 includes Sam in the split.
    Sam's balance contribution from that expense must be 0 because he was
    not yet a member on that date.

    The calculator enforces time-scoped membership — splits for inactive
    members are excluded, and the payer is only credited the active split total.
    """

    def test_sam_excluded_from_pre_join_expense(
        self, flat_group, aisha, rohan, sam, memberships, make_expense,
    ):
        # Expense on 2026-03-15: Sam hasn't joined yet (joins 2026-04-08)
        make_expense(
            paid_by=aisha,
            amount=Decimal('3000'),
            expense_date=date(2026, 3, 15),
            splits={
                aisha: Decimal('1000'),
                rohan: Decimal('1000'),
                sam:   Decimal('1000'),  # Sam shouldn't count — he wasn't a member yet
            },
            description='Pre-Sam expense',
        )

        calc = BalanceCalculator(flat_group.id)
        balances = calc.get_group_balances()

        # Sam's split should be excluded — he has no balance from this expense
        assert sam.id not in balances, (
            f'Sam should have no balance but got: {balances.get(sam.id)}'
        )

        # Only Aisha and Rohan should have balances
        # Payer (Aisha) is credited only the active splits total (2000, not 3000)
        # Aisha: +2000 (active total) - 1000 (own share) = +1000
        assert balances[aisha.id] == Decimal('1000.00')
        # Rohan: -1000
        assert balances[rohan.id] == Decimal('-1000.00')

        # Zero-sum with only active members
        assert sum(balances.values()) == Decimal('0.00')

    def test_meera_excluded_after_departure(
        self, flat_group, aisha, rohan, meera, memberships, make_expense,
    ):
        """Meera left 2026-03-28. An April expense including her should exclude her."""
        make_expense(
            paid_by=aisha,
            amount=Decimal('2000'),
            expense_date=date(2026, 4, 5),
            splits={
                aisha: Decimal('500'),
                rohan: Decimal('500'),
                meera: Decimal('1000'),  # Meera left before this date
            },
            description='Post-Meera departure expense',
        )

        calc = BalanceCalculator(flat_group.id)
        balances = calc.get_group_balances()

        # Meera's split is excluded — she has no balance
        assert meera.id not in balances
        # Payer credited only active splits: 500 + 500 = 1000
        # Aisha: +1000 - 500 = +500
        assert balances[aisha.id] == Decimal('500.00')
        assert balances[rohan.id] == Decimal('-500.00')

    def test_sam_included_after_join_date(
        self, flat_group, aisha, sam, memberships, make_expense,
    ):
        """Sam joined 2026-04-08 — expenses on or after that date SHOULD include him."""
        make_expense(
            paid_by=aisha,
            amount=Decimal('2000'),
            expense_date=date(2026, 4, 10),
            splits={
                aisha: Decimal('1000'),
                sam:   Decimal('1000'),
            },
            description='Post-Sam join expense',
        )

        calc = BalanceCalculator(flat_group.id)
        balances = calc.get_group_balances()

        # Sam IS active on 2026-04-10 — his split should be included
        assert sam.id in balances
        assert balances[sam.id] == Decimal('-1000.00')
        assert balances[aisha.id] == Decimal('1000.00')


# ===================================================================
# 6. Minimum transactions (settlement plan optimality)
# ===================================================================

@pytest.mark.django_db
class TestMinimumTransactions:
    """
    Scenario: 5 people, multiple expenses creating 3 debtors and 2 creditors.
    The greedy algorithm should produce fewer transactions than the
    number of unique debtor-creditor pairs (3 * 2 = 6 maximum).
    """

    def test_fewer_transactions_than_pairs(
        self, flat_group, aisha, rohan, priya, meera, sam, memberships, make_expense,
    ):
        # Expense 1: Aisha pays Rs.4000, split among 4 active people
        make_expense(
            paid_by=aisha,
            amount=Decimal('4000'),
            expense_date=date(2026, 3, 1),
            splits={
                aisha: Decimal('1000'),
                rohan: Decimal('1000'),
                priya: Decimal('1000'),
                meera: Decimal('1000'),
            },
        )

        # Expense 2: Rohan pays Rs.2000 for Priya and Meera
        make_expense(
            paid_by=rohan,
            amount=Decimal('2000'),
            expense_date=date(2026, 3, 5),
            splits={
                priya: Decimal('1000'),
                meera: Decimal('1000'),
            },
        )

        calc = BalanceCalculator(flat_group.id)
        balances = calc.get_group_balances()
        plan = calc.get_settlement_plan()

        # Count debtors and creditors
        debtors = [uid for uid, bal in balances.items() if bal < 0]
        creditors = [uid for uid, bal in balances.items() if bal > 0]

        # Maximum naive pairs would be len(debtors) * len(creditors)
        max_pairs = len(debtors) * len(creditors)

        # Greedy algorithm should produce fewer or equal transactions
        assert len(plan) <= max_pairs, (
            f'Settlement plan has {len(plan)} transactions, '
            f'but max pairs is {max_pairs}'
        )

        # Verify all transaction amounts are positive
        for txn in plan:
            assert txn['amount'] > 0

        # Verify the plan settles all debts:
        # Sum of all transaction amounts from debtors should equal their total debt
        plan_total = sum(txn['amount'] for txn in plan)
        total_debt = sum(-balances[uid] for uid in debtors)
        assert plan_total == total_debt, (
            f'Plan total {plan_total} != total debt {total_debt}'
        )


# ===================================================================
# 7. Negative amount (refund)
# ===================================================================

@pytest.mark.django_db
class TestNegativeAmountRefund:
    """
    Expense: USD -30 parasailing refund, converted to INR at 82.67 = -Rs.2480.10
    (rounded to -Rs.2480 for simplicity).
    Split equally among 4 people. Each person's split = -Rs.620 (credit back).

    A refund REDUCES what the payer is owed and REDUCES what participants owe.
    """

    def test_refund_reduces_balances(
        self, flat_group, aisha, rohan, priya, meera, memberships, make_expense,
    ):
        # First: a normal expense so there are existing balances to reduce
        make_expense(
            paid_by=aisha,
            amount=Decimal('4000'),
            expense_date=date(2026, 3, 1),
            splits={
                aisha: Decimal('1000'),
                rohan: Decimal('1000'),
                priya: Decimal('1000'),
                meera: Decimal('1000'),
            },
            description='Goa parasailing',
        )

        # Now: the refund (negative amount, is_refund=True)
        # The payer "gets back" Rs.2480, reducing what others owe them
        make_expense(
            paid_by=aisha,
            amount=Decimal('-2480'),
            expense_date=date(2026, 3, 5),
            splits={
                aisha: Decimal('-620'),  # Each person's share is negative (credit)
                rohan: Decimal('-620'),
                priya: Decimal('-620'),
                meera: Decimal('-620'),
            },
            split_type='equal',
            is_refund=True,
            currency='USD',
            amount_inr=Decimal('-2480'),
            exchange_rate_used=Decimal('82.666667'),
            description='Parasailing refund',
        )

        calc = BalanceCalculator(flat_group.id)
        balances = calc.get_group_balances()

        # Original balances: Aisha +3000, others -1000 each
        # Refund effect on payer: Aisha credited -2480 (active total of splits)
        #   → +3000 + (-2480) = +520 ... but she also has her own negative split
        # Refund effect on splits: each person gets +620 (negative split reversed)
        #   Aisha: +3000 + (-2480) - (-620) = +3000 - 2480 + 620 = +1140
        #   Actually let me recalc:
        #   Expense 1: Aisha gets +4000 (active total), -1000 (own split) = +3000 net
        #              Rohan: -1000, Priya: -1000, Meera: -1000
        #   Expense 2 (refund): active total = -620*4 = -2480
        #              Aisha gets -2480 (payer credit), -(-620) own split = +620
        #              Net from refund for Aisha: -2480 + 620 = -1860
        #              Rohan: -(-620) = +620 from refund
        #              Priya: +620, Meera: +620
        #   Final: Aisha = 3000 + (-1860) = 1140? No wait...
        #
        # Let me think step by step with the code logic:
        # For expense 2 (refund), amount_inr = -2480:
        #   active_total = sum of active splits = -620 + -620 + -620 + -620 = -2480
        #   balances[aisha] += -2480  (payer credit: negative because it's a refund)
        #   balances[aisha] -= -620 = +620  (own split subtracted: double negative = positive)
        #   balances[rohan] -= -620 = +620
        #   balances[priya] -= -620 = +620
        #   balances[meera] -= -620 = +620
        #
        # Combined with expense 1:
        #   Aisha: +4000 - 1000 + (-2480) + 620 = +1140
        #   Rohan: -1000 + 620 = -380
        #   Priya: -1000 + 620 = -380
        #   Meera: -1000 + 620 = -380

        assert balances[aisha.id] == Decimal('1140.00')
        assert balances[rohan.id] == Decimal('-380.00')
        assert balances[priya.id] == Decimal('-380.00')
        assert balances[meera.id] == Decimal('-380.00')

        # Zero-sum check: 1140 - 380 - 380 - 380 = 0
        assert sum(balances.values()) == Decimal('0.00')

    def test_standalone_refund(
        self, flat_group, aisha, rohan, priya, meera, memberships, make_expense,
    ):
        """A refund with no prior expense: everyone gets credit."""
        make_expense(
            paid_by=aisha,
            amount=Decimal('-2480'),
            expense_date=date(2026, 3, 5),
            splits={
                aisha: Decimal('-620'),
                rohan: Decimal('-620'),
                priya: Decimal('-620'),
                meera: Decimal('-620'),
            },
            is_refund=True,
            amount_inr=Decimal('-2480'),
            description='Standalone refund',
        )

        calc = BalanceCalculator(flat_group.id)
        balances = calc.get_group_balances()

        # Payer (Aisha) is credited -2480 (refund she issues)
        # Her own split: -(-620) = +620
        # Net for Aisha: -2480 + 620 = -1860 (she owes because she refunded)
        assert balances[aisha.id] == Decimal('-1860.00')

        # Each participant gets +620 credit
        assert balances[rohan.id] == Decimal('620.00')
        assert balances[priya.id] == Decimal('620.00')
        assert balances[meera.id] == Decimal('620.00')

        # Zero-sum: -1860 + 620 + 620 + 620 = 0
        assert sum(balances.values()) == Decimal('0.00')


# ===================================================================
# Bonus: User breakdown test
# ===================================================================

@pytest.mark.django_db
class TestUserBreakdown:
    """Verify get_user_breakdown returns correct running balance entries."""

    def test_breakdown_matches_final_balance(
        self, flat_group, aisha, rohan, priya, memberships, make_expense,
    ):
        make_expense(
            paid_by=aisha,
            amount=Decimal('3000'),
            expense_date=date(2026, 3, 1),
            splits={aisha: Decimal('1000'), rohan: Decimal('1000'), priya: Decimal('1000')},
        )
        make_expense(
            paid_by=rohan,
            amount=Decimal('1500'),
            expense_date=date(2026, 3, 10),
            splits={aisha: Decimal('500'), rohan: Decimal('500'), priya: Decimal('500')},
        )

        calc = BalanceCalculator(flat_group.id)
        group_balances = calc.get_group_balances()
        breakdown = calc.get_user_breakdown(rohan.id)

        # The breakdown's final_balance should match the group balance.
        # Note: Rohan's net is exactly 0 across these 2 expenses
        # (paid 1500 in exp2, owes 1000+500 = 1500 total), so he may
        # not appear in group_balances (zeros are filtered out).
        expected = group_balances.get(rohan.id, Decimal('0.00'))
        assert Decimal(str(breakdown['final_balance'])) == expected

        # Should have exactly 2 entries (2 expenses)
        expense_entries = [e for e in breakdown['entries'] if e.get('type') != 'SETTLEMENT']
        assert len(expense_entries) == 2

        # Entries should be chronologically sorted
        dates = [e['date'] for e in breakdown['entries']]
        assert dates == sorted(dates)
