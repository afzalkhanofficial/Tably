"""
URL Routing for Expenses app endpoints.
"""

from django.urls import path

from apps.expenses.views import (
    DebugBalanceTraceView,
    ExpenseDetailView,
    ExpenseListCreateView,
    GroupBalancesView,
    GroupSettlementPlanView,
    MemberBreakdownView,
    SettlementListCreateView,
)

app_name = 'expenses'

urlpatterns = [
    # Expenses List / Create
    path('groups/<int:pk>/expenses/', ExpenseListCreateView.as_view(), name='expense-list-create'),

    # Expense Detail / Edit / Delete
    path('groups/<int:pk>/expenses/<int:eid>/', ExpenseDetailView.as_view(), name='expense-detail'),

    # Group Balances
    path('groups/<int:pk>/balances/', GroupBalancesView.as_view(), name='group-balances'),

    # Group Settlement Plan
    path('groups/<int:pk>/settlement-plan/', GroupSettlementPlanView.as_view(), name='group-settlement-plan'),

    # Member Balance Breakdown
    path('groups/<int:pk>/members/<int:user_id>/breakdown/', MemberBreakdownView.as_view(), name='member-breakdown'),

    # Settlements List / Create
    path('groups/<int:pk>/settlements/', SettlementListCreateView.as_view(), name='settlement-list-create'),

    # Debug Balance Trace
    path('groups/<int:pk>/debug/balance-trace/<int:user_id>/', DebugBalanceTraceView.as_view(), name='debug-balance-trace'),
]
