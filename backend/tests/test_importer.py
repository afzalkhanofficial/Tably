"""
Unit & Integration Tests for the CSV Import Engine
===================================================

Tests the CSV parser, the 17 anomalies, the DB commit logic, and all 5 API endpoints.
"""

import os
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.expenses.models import Expense, ExpenseSplit, Settlement
from apps.groups.models import GroupMember
from apps.importer.models import ImportAnomaly, ImportSession
from apps.importer.parser import CSVParser


# ---------------------------------------------------------------------------
# Setup & Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client(db, aisha):
    """An authenticated API client using Aisha's credentials."""
    client = APIClient()
    # Log in by obtaining JWT token
    response = client.post(
        reverse('users:login'),
        {'email': 'aisha@test.com', 'password': 'test123'},
    )
    assert response.status_code == 200
    token = response.data['tokens']['access']
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


# Mock rates for fx client during testing to avoid hitting live network
@pytest.fixture(autouse=True)
def mock_fx_client():
    with patch('apps.importer.fx_client.requests.get') as mock_get:
        # Provide standard USD to INR rate
        mock_response = mock_get.return_value
        mock_response.status_code = 200
        mock_response.json.return_value = {'rates': {'INR': 84.50}}
        yield mock_get


# ---------------------------------------------------------------------------
# CSVParser Unit Tests
# ---------------------------------------------------------------------------

def test_parser_detects_all_anomalies(flat_group, memberships, aisha, rohan, priya, meera, sam, dev):
    """
    Feed a custom CSV containing all anomaly cases and verify they are correctly flagged.
    """
    csv_content = (
        "date,description,paid_by,amount,currency,split_type,split_with,split_details,notes\n"
        # 1 & 9. Exact duplicate & Conflicting duplicate
        "08-02-2026,Dinner at Marina Bites,Dev,3200,INR,equal,Aisha;Rohan;Priya;Dev,,\n"
        "08-02-2026,dinner - marina bites,Dev,3200,INR,equal,Aisha;Rohan;Priya;Dev,,\n"
        "11-03-2026,Dinner at Thalassa,Aisha,2400,INR,equal,Aisha;Rohan;Priya;Dev,,\n"
        "11-03-2026,Thalassa dinner,Rohan,2450,INR,equal,Aisha;Rohan;Priya;Dev,,\n"
        # 2. Amount format
        "10-02-2026,Electricity Feb,Aisha,\"1,200\",INR,equal,Aisha;Rohan;Priya;Meera,,\n"
        # 3. Name fuzzy match
        "14-02-2026,Movie night snacks,priya,640,INR,equal,Aisha;Rohan;Priya,,\n"
        # 4. Missing paid_by
        "22-02-2026,House cleaning supplies,,780,INR,equal,Aisha;Rohan;Priya;Meera,,\n"
        # 5. Settlement pattern
        "25-02-2026,Rohan paid Aisha back,Rohan,5000,INR,,Aisha,,\n"
        # 6. Percentage sum error
        "28-02-2026,Pizza Friday,Aisha,1440,INR,percentage,Aisha;Rohan;Priya;Meera,Aisha 30%; Rohan 30%; Priya 30%; Meera 20%,\n"
        # 7 & 10. Foreign currency & Negative amount
        "12-03-2026,Parasailing refund,Dev,-30,USD,equal,Aisha;Rohan;Priya;Dev,,\n"
        # 8. Unknown member
        "11-03-2026,Parasailing,Dev,150,USD,equal,Aisha;Rohan;Priya;Dev;Dev's friend Kabir,,\n"
        # 11. Non-standard date
        "Mar-14,Airport cab,rohan,1100,INR,equal,Aisha;Rohan;Priya;Dev,,\n"
        # 12. Missing currency
        "15-03-2026,Groceries DMart,Priya,2105,,equal,Aisha;Rohan;Priya;Meera,,\n"
        # 13. Zero amount
        "22-03-2026,Dinner order Swiggy,Priya,0,INR,equal,Aisha;Rohan;Priya;Meera,,\n"
        # 14. Ambiguous date
        "04-05-2026,Deep cleaning service,Rohan,2500,INR,equal,Aisha;Rohan;Priya,,\n"
        # 15. Member post departure
        "02-04-2026,Groceries BigBasket,Priya,2640,INR,equal,Aisha;Rohan;Priya;Meera,,\n"
        # 16. Split type conflict
        "18-04-2026,Furniture for common room,Aisha,12000,INR,equal,Aisha;Rohan;Priya;Sam,Aisha 1; Rohan 1; Priya 1; Sam 1,\n"
        # 17. Decimal precision
        "15-02-2026,Cylinder refill,Rohan,899.995,INR,equal,Aisha;Rohan;Priya;Meera,,\n"
    )

    # Convert memberships and guests to list of dicts for parser
    member_list = []
    for m in GroupMember.objects.filter(group=flat_group).select_related('user'):
        member_list.append({
            'name': m.user.name,
            'user_id': m.user_id,
            'joined_at': m.joined_at,
            'left_at': m.left_at,
        })
    # Add guest users (like dev)
    member_list.append({
        'name': dev.name,
        'user_id': dev.id,
        'joined_at': None,
        'left_at': None,
    })

    parser = CSVParser(group_id=flat_group.id, group_members=member_list)
    parse_result = parser.parse(csv_content)

    # Collect all anomaly types seen
    anomaly_types = []
    for res in parse_result['results']:
        for a in res['anomalies']:
            anomaly_types.append(a.anomaly_type)

    # Verify that all 17 distinct types were detected
    distinct_types = set(anomaly_types)
    assert 'EXACT_DUPLICATE' in distinct_types
    assert 'CONFLICTING_DUPLICATE' in distinct_types
    assert 'AMOUNT_FORMAT' in distinct_types
    assert 'NAME_FUZZY_MATCH' in distinct_types
    assert 'MISSING_PAID_BY' in distinct_types
    assert 'SETTLEMENT_PATTERN' in distinct_types
    assert 'PERCENTAGE_SUM_ERROR' in distinct_types
    assert 'FOREIGN_CURRENCY' in distinct_types
    assert 'UNKNOWN_MEMBER' in distinct_types
    assert 'NEGATIVE_AMOUNT' in distinct_types
    assert 'NONSTANDARD_DATE' in distinct_types
    assert 'MISSING_CURRENCY' in distinct_types
    assert 'ZERO_AMOUNT' in distinct_types
    assert 'AMBIGUOUS_DATE' in distinct_types
    assert 'MEMBER_POST_DEPARTURE' in distinct_types
    assert 'SPLIT_TYPE_CONFLICT' in distinct_types
    assert 'DECIMAL_PRECISION' in distinct_types


# ---------------------------------------------------------------------------
# API Integration Tests
# ---------------------------------------------------------------------------

def test_api_import_flow(db, api_client, flat_group, memberships, aisha, rohan, priya):
    """
    Test the full import lifecycle via the REST API endpoints.
    """
    # Create simple CSV content with clean, auto-fixed, and pending anomalies
    csv_data = (
        "date,description,paid_by,amount,currency,split_type,split_with,split_details,notes\n"
        "15-02-2026,Clean Rent,Aisha,48000,INR,equal,Aisha;Rohan;Priya,,\n"
        "20-02-2026,Formatted Amount,Aisha,\"1,200\",INR,equal,Aisha;Rohan;Priya,,\n" # Auto-fixed
        "22-02-2026,Missing Payer,,780,INR,equal,Aisha;Rohan;Priya,,needs manual paid_by\n" # Pending review
    )

    # 1. POST /api/groups/{group_id}/import/
    # Construct files payload
    import io
    csv_file = io.BytesIO(csv_data.encode('utf-8'))
    csv_file.name = 'expenses.csv'

    import_url = reverse('importer:csv-import', kwargs={'group_id': flat_group.id})
    response = api_client.post(import_url, {'csv_file': csv_file}, format='multipart')

    assert response.status_code == status.HTTP_201_CREATED
    assert 'session_id' in response.data
    session_id = response.data['session_id']
    assert response.data['status'] == 'pending_review'
    assert response.data['summary']['total_rows'] == 3
    assert response.data['summary']['auto_imported'] == 1
    assert response.data['summary']['auto_fixed'] == 1
    assert response.data['summary']['pending_review'] == 1

    # Verify Clean Rent and Formatted Amount got imported immediately
    assert Expense.objects.filter(description='Clean Rent').exists()
    assert Expense.objects.filter(description='Formatted Amount').exists()
    # Missing Payer is NOT imported yet because it requires manual approval
    assert not Expense.objects.filter(description='Missing Payer').exists()

    # 2. GET /api/import/{session_id}/
    detail_url = reverse('importer:session-detail', kwargs={'session_id': session_id})
    response = api_client.get(detail_url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data['status'] == 'pending_review'
    assert response.data['total_rows'] == 3

    # 3. GET /api/import/{session_id}/anomalies/
    anomalies_url = reverse('importer:anomaly-list', kwargs={'session_id': session_id})
    response = api_client.get(anomalies_url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data['total_unresolved'] == 1
    anomaly_id = response.data['results'][0]['id']
    assert response.data['results'][0]['anomaly_type'] == 'MISSING_PAID_BY'

    # 4. POST /api/import/{session_id}/anomalies/{anomaly_id}/resolve/
    # Case: set_value to Rohan
    resolve_url = reverse(
        'importer:anomaly-resolve',
        kwargs={'session_id': session_id, 'anomaly_id': anomaly_id}
    )
    response = api_client.post(
        resolve_url,
        {'choice': 'set_value', 'value': {'paid_by': 'Rohan'}},
        format='json'
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data['session_status'] == 'complete'
    assert response.data['unresolved_count'] == 0

    # Verify that the Missing Payer expense is now created with payer=Rohan
    missing_payer_expense = Expense.objects.get(description='Missing Payer')
    assert missing_payer_expense.paid_by == rohan

    # 5. GET /api/import/{session_id}/report/
    report_url = reverse('importer:import-report', kwargs={'session_id': session_id})
    response = api_client.get(report_url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data['session']['status'] == 'complete'
    # Report contains 3 imported expenses total
    assert len(response.data['imported_expenses']['items']) == 3
