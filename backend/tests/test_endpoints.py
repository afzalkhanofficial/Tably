"""
Integration Tests for all REST API Endpoints
"""

import pytest
from datetime import date
from decimal import Decimal
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.models import User
from apps.groups.models import Group, GroupMember
from apps.expenses.models import Expense, ExpenseSplit, Settlement


@pytest.fixture
def auth_client(db):
    """Returns an APIClient and a pre-created authenticated user."""
    client = APIClient()
    user = User.objects.create_user(
        email="test_user@example.com",
        name="Test User",
        password="password123",
    )
    # Log in
    response = client.post(
        reverse('users:login'),
        {'email': 'test_user@example.com', 'password': 'password123'},
        format='json'
    )
    assert response.status_code == status.HTTP_200_OK
    token = response.data['tokens']['access']
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client, user


@pytest.mark.django_db
def test_auth_endpoints(db):
    client = APIClient()

    # 1. Register
    reg_url = reverse('users:register')
    response = client.post(
        reg_url,
        {
            'email': 'new_user@example.com',
            'name': 'New User',
            'password': 'password123',
            'password_confirm': 'password123',
        },
        format='json'
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert 'tokens' in response.data
    assert response.data['user']['email'] == 'new_user@example.com'

    # Registration passwords mismatch validation
    response = client.post(
        reg_url,
        {
            'email': 'bad_user@example.com',
            'name': 'Bad User',
            'password': 'password123',
            'password_confirm': 'mismatch',
        },
        format='json'
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data['code'] == 'VALIDATION_ERROR'

    # 2. Login
    login_url = reverse('users:login')
    response = client.post(
        login_url,
        {
            'email': 'new_user@example.com',
            'password': 'password123',
        },
        format='json'
    )
    assert response.status_code == status.HTTP_200_OK
    assert 'tokens' in response.data
    refresh_token = response.data['tokens']['refresh']
    access_token = response.data['tokens']['access']

    # 3. Token Refresh
    refresh_url = reverse('users:token_refresh')
    response = client.post(
        refresh_url,
        {'refresh': refresh_token},
        format='json'
    )
    assert response.status_code == status.HTTP_200_OK
    assert 'access' in response.data

    # 4. GET Me profile (Authenticated)
    me_url = reverse('users:me')
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
    response = client.get(me_url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data['email'] == 'new_user@example.com'
    assert 'groups' in response.data


@pytest.mark.django_db
def test_group_lifecycle(auth_client):
    client, user = auth_client

    # 1. Create Group
    group_url = reverse('groups:group-list-create')
    response = client.post(
        group_url,
        {'name': 'Flat 202', 'description': 'Our flat sharing group'},
        format='json'
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data['name'] == 'Flat 202'
    group_id = response.data['id']

    # Creator should automatically be an active member
    assert GroupMember.objects.filter(group_id=group_id, user=user, left_at__isnull=True).exists()

    # 2. List Groups
    response = client.get(group_url)
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 1
    assert response.data[0]['name'] == 'Flat 202'
    assert response.data[0]['member_count'] == 1

    # 3. Add Member
    other_user = User.objects.create_user(
        email="other@example.com",
        name="Other Member",
        password="password123"
    )
    member_url = reverse('groups:group-add-member', kwargs={'pk': group_id})
    response = client.post(
        member_url,
        {'user_id': other_user.id, 'joined_at': '2026-01-01'},
        format='json'
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert len(response.data['members']) == 2

    # 4. Detail Group
    detail_url = reverse('groups:group-detail', kwargs={'pk': group_id})
    response = client.get(detail_url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data['name'] == 'Flat 202'
    assert len(response.data['members']) == 2

    # 5. Mark Member as Departed
    depart_url = reverse(
        'groups:group-member-depart',
        kwargs={'pk': group_id, 'user_id': other_user.id}
    )

    # Validate departure date cannot be before join date (invalid first)
    response = client.patch(
        depart_url,
        {'left_at': '2025-01-01'},  # joined on 2026-01-01
        format='json'
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    # Valid departure date
    response = client.patch(
        depart_url,
        {'left_at': '2026-06-01'},
        format='json'
    )
    assert response.status_code == status.HTTP_200_OK

    # Check that member is no longer active
    member_record = GroupMember.objects.get(group_id=group_id, user=other_user)
    assert member_record.left_at == date(2026, 6, 1)


@pytest.mark.django_db
def test_expense_settlement_and_balance_flow(auth_client):
    client, user = auth_client

    # Setup group
    group = Group.objects.create(name="Flat Group", created_by=user)
    GroupMember.objects.create(group=group, user=user, joined_at=date(2026, 1, 1))

    # Add second member
    member2 = User.objects.create_user(
        email="member2@example.com",
        name="Member Two",
        password="password123"
    )
    GroupMember.objects.create(group=group, user=member2, joined_at=date(2026, 1, 1))

    # 1. Create Expense (Equal split)
    expense_url = reverse('expenses:expense-list-create', kwargs={'pk': group.id})
    response = client.post(
        expense_url,
        {
            'description': 'Internet Bill',
            'expense_date': '2026-02-15',
            'total_amount': 1500.00,
            'currency': 'INR',
            'paid_by': user.id,
            'split_type': 'equal',
            'splits': [
                {'user_id': user.id},
                {'user_id': member2.id},
            ]
        },
        format='json'
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data['amount_inr'] == '1500.00'
    expense_id = response.data['id']

    # Verify Splits
    splits = ExpenseSplit.objects.filter(expense_id=expense_id)
    assert splits.count() == 2
    assert splits.get(user=user).amount_owed == Decimal('750.00')
    assert splits.get(user=member2).amount_owed == Decimal('750.00')

    # 2. List Expenses
    response = client.get(expense_url)
    assert response.status_code == status.HTTP_200_OK
    # Pagination envelope
    assert 'results' in response.data
    assert len(response.data['results']) == 1

    # 3. GET Expense Detail
    detail_url = reverse('expenses:expense-detail', kwargs={'pk': group.id, 'eid': expense_id})
    response = client.get(detail_url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data['description'] == 'Internet Bill'

    # 4. PUT Expense
    response = client.put(
        detail_url,
        {'description': 'Updated Internet Bill', 'notes': 'Split equally'},
        format='json'
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data['description'] == 'Updated Internet Bill'

    # 5. GET Group Balances
    balances_url = reverse('expenses:group-balances', kwargs={'pk': group.id})
    response = client.get(balances_url)
    assert response.status_code == status.HTTP_200_OK
    # Payer gets +1500 - 750 = +750. Member2 gets -750.
    balances = {b['user_id']: b for b in response.data['balances']}
    assert balances[user.id]['net_balance_inr'] == 750.00
    assert balances[user.id]['status'] == 'owed'
    assert balances[member2.id]['net_balance_inr'] == -750.00
    assert balances[member2.id]['status'] == 'owes'

    # 6. GET Settlement Plan
    plan_url = reverse('expenses:group-settlement-plan', kwargs={'pk': group.id})
    response = client.get(plan_url)
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data['transactions']) == 1
    assert response.data['transactions'][0]['from_user']['id'] == member2.id
    assert response.data['transactions'][0]['to_user']['id'] == user.id
    assert response.data['transactions'][0]['amount_inr'] == 750.00

    # 7. GET Member Breakdown
    breakdown_url = reverse(
        'expenses:member-breakdown',
        kwargs={'pk': group.id, 'user_id': member2.id}
    )
    response = client.get(breakdown_url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data['final_balance'] == -750.00
    assert len(response.data['entries']) == 1

    # 8. POST Settlement
    settlements_url = reverse('expenses:settlement-list-create', kwargs={'pk': group.id})
    response = client.post(
        settlements_url,
        {
            'paid_by': member2.id,
            'paid_to': user.id,
            'amount': 750.00,
            'currency': 'INR',
            'notes': 'Paid back my share',
        },
        format='json'
    )
    assert response.status_code == status.HTTP_201_CREATED
    # Settlement endpoint returns updated balances for affected users
    updated_balances = {b['user_id']: b for b in response.data['balances']}
    assert updated_balances[user.id]['net_balance_inr'] == 0.00
    assert updated_balances[user.id]['status'] == 'settled'

    # 9. GET Settlements List
    response = client.get(settlements_url)
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 1
    assert response.data[0]['amount'] == '750.00'

    # 10. Debug Balance Trace (access control)
    trace_url_other = reverse(
        'expenses:debug-balance-trace',
        kwargs={'pk': group.id, 'user_id': member2.id}
    )
    response = client.get(trace_url_other)
    assert response.status_code == status.HTTP_403_FORBIDDEN

    trace_url_own = reverse(
        'expenses:debug-balance-trace',
        kwargs={'pk': group.id, 'user_id': user.id}
    )
    response = client.get(trace_url_own)
    assert response.status_code == status.HTTP_200_OK
    assert response.data['final_balance'] == 0.0

    # 11. DELETE Expense (Soft-delete)
    response = client.delete(detail_url)
    assert response.status_code == status.HTTP_200_OK
    assert Expense.objects.get(pk=expense_id).is_deleted is True
