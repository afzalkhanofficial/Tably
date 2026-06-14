"""
Shared pytest fixtures for the flat expenses tracker test suite.

Creates the core test entities: users, group, and memberships that
mirror the seed data but are isolated per test via DB transactions.
"""
from datetime import date
from decimal import Decimal

import pytest

from apps.expenses.models import Expense, ExpenseSplit, Settlement
from apps.groups.models import Group, GroupMember
from apps.users.models import User


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@pytest.fixture
def aisha(db):
    return User.objects.create_user(
        email='aisha@test.com', name='Aisha', password='test123',
        avatar_color='#EF4444',
    )


@pytest.fixture
def rohan(db):
    return User.objects.create_user(
        email='rohan@test.com', name='Rohan', password='test123',
        avatar_color='#F97316',
    )


@pytest.fixture
def priya(db):
    return User.objects.create_user(
        email='priya@test.com', name='Priya', password='test123',
        avatar_color='#EAB308',
    )


@pytest.fixture
def meera(db):
    return User.objects.create_user(
        email='meera@test.com', name='Meera', password='test123',
        avatar_color='#22C55E',
    )


@pytest.fixture
def sam(db):
    return User.objects.create_user(
        email='sam@test.com', name='Sam', password='test123',
        avatar_color='#3B82F6',
    )


@pytest.fixture
def dev(db):
    """Dev is a guest user — participates in expenses but has NO group membership."""
    return User.objects.create_user(
        email='dev@test.com', name='Dev', password='test123',
        avatar_color='#A855F7',
    )


# ---------------------------------------------------------------------------
# Group + Memberships
# ---------------------------------------------------------------------------

@pytest.fixture
def flat_group(db, aisha):
    return Group.objects.create(name='The Flat', created_by=aisha)


@pytest.fixture
def memberships(flat_group, aisha, rohan, priya, meera, sam):
    """
    Create time-scoped memberships matching the seed data spec:
    - Aisha, Rohan, Priya: joined 2026-02-01, still active
    - Meera: joined 2026-02-01, left 2026-03-28
    - Sam: joined 2026-04-08, still active
    - Dev: NO membership (guest)
    """
    members = {
        'aisha': GroupMember.objects.create(
            group=flat_group, user=aisha,
            joined_at=date(2026, 2, 1), left_at=None,
        ),
        'rohan': GroupMember.objects.create(
            group=flat_group, user=rohan,
            joined_at=date(2026, 2, 1), left_at=None,
        ),
        'priya': GroupMember.objects.create(
            group=flat_group, user=priya,
            joined_at=date(2026, 2, 1), left_at=None,
        ),
        'meera': GroupMember.objects.create(
            group=flat_group, user=meera,
            joined_at=date(2026, 2, 1), left_at=date(2026, 3, 28),
        ),
        'sam': GroupMember.objects.create(
            group=flat_group, user=sam,
            joined_at=date(2026, 4, 8), left_at=None,
        ),
    }
    return members


# ---------------------------------------------------------------------------
# Expense helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def make_expense(flat_group, aisha):
    """
    Factory fixture to quickly create an expense with splits.

    Usage:
        expense = make_expense(
            paid_by=aisha,
            amount=Decimal('3000'),
            date=date(2026, 3, 1),
            splits={aisha: Decimal('1000'), rohan: Decimal('1000'), priya: Decimal('1000')},
        )
    """
    def _make(paid_by, amount, expense_date, splits, **kwargs):
        expense = Expense.objects.create(
            group=flat_group,
            description=kwargs.get('description', 'Test expense'),
            total_amount=amount,
            currency=kwargs.get('currency', 'INR'),
            amount_inr=kwargs.get('amount_inr', amount),
            paid_by=paid_by,
            expense_date=expense_date,
            split_type=kwargs.get('split_type', 'equal'),
            is_settlement=kwargs.get('is_settlement', False),
            is_refund=kwargs.get('is_refund', False),
            is_deleted=kwargs.get('is_deleted', False),
            exchange_rate_used=kwargs.get('exchange_rate_used'),
            exchange_rate_date=kwargs.get('exchange_rate_date'),
            created_by=paid_by,
        )
        for user, owed in splits.items():
            ExpenseSplit.objects.create(
                expense=expense, user=user, amount_owed=owed,
            )
        return expense

    return _make


@pytest.fixture
def make_settlement(flat_group):
    """Factory fixture to quickly create a settlement."""
    def _make(paid_by, paid_to, amount, **kwargs):
        return Settlement.objects.create(
            group=flat_group,
            paid_by=paid_by,
            paid_to=paid_to,
            amount=amount,
            amount_inr=kwargs.get('amount_inr', amount),
            currency=kwargs.get('currency', 'INR'),
            created_by=paid_by,
        )
    return _make
