"""
Expenses, Settlements, and Balances Views
"""

from datetime import date, datetime
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.expenses.models import Expense, Settlement
from apps.groups.models import Group, GroupMember
from apps.users.models import User
from apps.users.serializers import UserSerializer
from apps.expenses.serializers import (
    ExpenseCreateSerializer,
    ExpenseSerializer,
    SettlementCreateSerializer,
    SettlementSerializer,
)
from services.balance_calculator import BalanceCalculator


class ExpenseListCreateView(APIView):
    """
    GET /api/groups/{id}/expenses/ — Paginated & filtered expenses.
    POST /api/groups/{id}/expenses/ — Create a new expense.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        group = get_object_or_404(Group, pk=pk)

        # Verify membership
        is_member = GroupMember.objects.filter(group=group, user=request.user).exists()
        if not is_member and not request.user.is_staff:
            return Response(
                {
                    'error': 'You are not a member of this group.',
                    'code': 'NOT_GROUP_MEMBER',
                    'details': {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        queryset = Expense.objects.filter(group=group, is_deleted=False, is_settlement=False)

        # Filtering
        from_date = request.query_params.get('from_date')
        if from_date:
            queryset = queryset.filter(expense_date__gte=from_date)

        to_date = request.query_params.get('to_date')
        if to_date:
            queryset = queryset.filter(expense_date__lte=to_date)

        paid_by = request.query_params.get('paid_by')
        if paid_by:
            queryset = queryset.filter(paid_by_id=paid_by)

        split_type = request.query_params.get('split_type')
        if split_type:
            queryset = queryset.filter(split_type=split_type)

        # Pagination
        paginator = PageNumberPagination()
        paginator.page_size = 25
        page = paginator.paginate_queryset(queryset, request, view=self)
        if page is not None:
            serializer = ExpenseSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = ExpenseSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, pk):
        group = get_object_or_404(Group, pk=pk)

        # Verify membership
        is_member = GroupMember.objects.filter(group=group, user=request.user).exists()
        if not is_member and not request.user.is_staff:
            return Response(
                {
                    'error': 'You are not a member of this group.',
                    'code': 'NOT_GROUP_MEMBER',
                    'details': {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ExpenseCreateSerializer(
            data=request.data,
            context={'group_id': group.id, 'request_user': request.user}
        )
        serializer.is_valid(raise_exception=True)
        expense = serializer.save()

        return Response(
            ExpenseSerializer(expense).data,
            status=status.HTTP_201_CREATED,
        )


class ExpenseDetailView(APIView):
    """
    GET /api/groups/{id}/expenses/{eid}/ — Get expense.
    PUT /api/groups/{id}/expenses/{eid}/ — Update description/date/notes (NOT amount/splits).
    DELETE /api/groups/{id}/expenses/{eid}/ — Soft delete expense.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, eid):
        group = get_object_or_404(Group, pk=pk)
        # Verify membership
        is_member = GroupMember.objects.filter(group=group, user=request.user).exists()
        if not is_member and not request.user.is_staff:
            return Response(
                {
                    'error': 'You are not a member of this group.',
                    'code': 'NOT_GROUP_MEMBER',
                    'details': {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        expense = get_object_or_404(Expense, group=group, pk=eid, is_deleted=False)
        return Response(ExpenseSerializer(expense).data, status=status.HTTP_200_OK)

    def put(self, request, pk, eid):
        group = get_object_or_404(Group, pk=pk)
        # Verify membership
        is_member = GroupMember.objects.filter(group=group, user=request.user).exists()
        if not is_member and not request.user.is_staff:
            return Response(
                {
                    'error': 'You are not a member of this group.',
                    'code': 'NOT_GROUP_MEMBER',
                    'details': {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        expense = get_object_or_404(Expense, group=group, pk=eid, is_deleted=False)

        # Fields allowed to edit: description, expense_date, notes
        description = request.data.get('description', expense.description)
        notes = request.data.get('notes', expense.notes)
        expense_date_str = request.data.get('expense_date')

        expense.description = description
        expense.notes = notes

        if expense_date_str:
            try:
                expense_date = datetime.strptime(expense_date_str, '%Y-%m-%d').date()
                # If date changed, validate that all members are still active on new date
                for split in expense.splits.all():
                    mships = GroupMember.objects.filter(group_id=group.id, user_id=split.user_id)
                    if not any(m.is_active_on(expense_date) for m in mships):
                        return Response(
                            {
                                'error': f"User {split.user.name} is not active on new date {expense_date_str}.",
                                'code': 'VALIDATION_ERROR',
                                'details': {'expense_date': ['User is not active on new date.']},
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                expense.expense_date = expense_date
            except ValueError:
                return Response(
                    {
                        'error': 'Invalid date format. Use YYYY-MM-DD.',
                        'code': 'VALIDATION_ERROR',
                        'details': {'expense_date': ['Invalid date format. Use YYYY-MM-DD.']},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Do not allow updating amount/splits/split_type directly. Warn if they try.
        if 'total_amount' in request.data or 'splits' in request.data or 'split_type' in request.data:
            # We don't error, we just silently ignore or we can raise a warning. The spec says:
            # "PUT allows editing description, date, notes (not amount/splits — those require delete+recreate to maintain audit trail)"
            # Let's just ignore them.
            pass

        expense.save()
        return Response(ExpenseSerializer(expense).data, status=status.HTTP_200_OK)

    def delete(self, request, pk, eid):
        group = get_object_or_404(Group, pk=pk)
        # Verify membership
        is_member = GroupMember.objects.filter(group=group, user=request.user).exists()
        if not is_member and not request.user.is_staff:
            return Response(
                {
                    'error': 'You are not a member of this group.',
                    'code': 'NOT_GROUP_MEMBER',
                    'details': {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        expense = get_object_or_404(Expense, group=group, pk=eid, is_deleted=False)
        expense.is_deleted = True
        expense.save()
        return Response({'message': 'Expense deleted successfully.'}, status=status.HTTP_200_OK)


class GroupBalancesView(APIView):
    """
    GET /api/groups/{id}/balances/ — Returns net balances for all members.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        group = get_object_or_404(Group, pk=pk)
        # Verify membership
        is_member = GroupMember.objects.filter(group=group, user=request.user).exists()
        if not is_member and not request.user.is_staff:
            return Response(
                {
                    'error': 'You are not a member of this group.',
                    'code': 'NOT_GROUP_MEMBER',
                    'details': {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        as_of_date_str = request.query_params.get('as_of_date')
        as_of_date = None
        if as_of_date_str:
            try:
                as_of_date = datetime.strptime(as_of_date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {
                        'error': 'Invalid date format. Use YYYY-MM-DD.',
                        'code': 'VALIDATION_ERROR',
                        'details': {'as_of_date': ['Invalid date format. Use YYYY-MM-DD.']},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        calculator = BalanceCalculator(group.id)
        net_balances = calculator.get_group_balances(as_of_date=as_of_date)

        # Get all users who are members of this group
        member_users = User.objects.filter(group_memberships__group=group).distinct()
        balances_list = []
        for u in member_users:
            balance_val = float(net_balances.get(u.id, 0.0))
            if balance_val > 0.005:
                status_label = 'owed'
            elif balance_val < -0.005:
                status_label = 'owes'
            else:
                status_label = 'settled'

            balances_list.append({
                'user_id': u.id,
                'name': u.name,
                'email': u.email,
                'avatar_color': u.avatar_color,
                'net_balance_inr': balance_val,
                'status': status_label,
            })

        # Calculate Group Total Spent & Currency Breakdown
        expenses = Expense.objects.filter(group=group, is_deleted=False, is_settlement=False)
        if as_of_date:
            expenses = expenses.filter(expense_date__lte=as_of_date)

        from django.db.models import Sum
        group_total = expenses.aggregate(total=Sum('amount_inr'))['total'] or 0.0

        currency_breakdown = {}
        for item in expenses.values('currency').annotate(sum_amount=Sum('total_amount')):
            currency_breakdown[item['currency']] = float(item['sum_amount'])

        return Response(
            {
                'as_of_date': as_of_date_str or date.today().isoformat(),
                'balances': balances_list,
                'group_total_spent_inr': float(group_total),
                'currency_breakdown': currency_breakdown,
            },
            status=status.HTTP_200_OK,
        )


class GroupSettlementPlanView(APIView):
    """
    GET /api/groups/{id}/settlement-plan/ — Returns the optimized settlement plan.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        group = get_object_or_404(Group, pk=pk)
        # Verify membership
        is_member = GroupMember.objects.filter(group=group, user=request.user).exists()
        if not is_member and not request.user.is_staff:
            return Response(
                {
                    'error': 'You are not a member of this group.',
                    'code': 'NOT_GROUP_MEMBER',
                    'details': {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        calculator = BalanceCalculator(group.id)
        plan_txs = calculator.get_settlement_plan()

        # Fetch all user info
        users = {u.id: u for u in User.objects.filter(group_memberships__group=group).distinct()}
        transactions = []
        total_outstanding = 0.0

        for tx in plan_txs:
            from_uid = tx['from_user_id']
            to_uid = tx['to_user_id']
            amt = float(tx['amount'])

            from_u = users.get(from_uid)
            to_u = users.get(to_uid)

            if not from_u or not to_u:
                # If they are guests or not in the member list currently loaded, fetch them
                if not from_u:
                    from_u = User.objects.get(pk=from_uid)
                if not to_u:
                    to_u = User.objects.get(pk=to_uid)

            total_outstanding += amt
            transactions.append({
                'from_user': {
                    'id': from_u.id,
                    'name': from_u.name,
                    'avatar_color': from_u.avatar_color,
                },
                'to_user': {
                    'id': to_u.id,
                    'name': to_u.name,
                    'avatar_color': to_u.avatar_color,
                },
                'amount_inr': amt,
                'description': f"{from_u.name} pays {to_u.name} ₹{amt:,.2f}",
            })

        return Response(
            {
                'transactions': transactions,
                'total_outstanding': total_outstanding,
            },
            status=status.HTTP_200_OK,
        )


class MemberBreakdownView(APIView):
    """
    GET /api/groups/{id}/members/{user_id}/breakdown/ — Returns the audit trail for a user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, user_id):
        group = get_object_or_404(Group, pk=pk)
        # Verify membership of request sender
        is_member = GroupMember.objects.filter(group=group, user=request.user).exists()
        if not is_member and not request.user.is_staff:
            return Response(
                {
                    'error': 'You are not a member of this group.',
                    'code': 'NOT_GROUP_MEMBER',
                    'details': {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        calculator = BalanceCalculator(group.id)
        breakdown = calculator.get_user_breakdown(user_id)
        return Response(breakdown, status=status.HTTP_200_OK)


class SettlementListCreateView(APIView):
    """
    GET /api/groups/{id}/settlements/ — Returns all settlements.
    POST /api/groups/{id}/settlements/ — Creates a new settlement.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        group = get_object_or_404(Group, pk=pk)
        # Verify membership
        is_member = GroupMember.objects.filter(group=group, user=request.user).exists()
        if not is_member and not request.user.is_staff:
            return Response(
                {
                    'error': 'You are not a member of this group.',
                    'code': 'NOT_GROUP_MEMBER',
                    'details': {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        settlements = Settlement.objects.filter(group=group).order_by('-settled_at')
        serializer = SettlementSerializer(settlements, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, pk):
        group = get_object_or_404(Group, pk=pk)
        # Verify membership
        is_member = GroupMember.objects.filter(group=group, user=request.user).exists()
        if not is_member and not request.user.is_staff:
            return Response(
                {
                    'error': 'You are not a member of this group.',
                    'code': 'NOT_GROUP_MEMBER',
                    'details': {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SettlementCreateSerializer(
            data=request.data,
            context={'group_id': group.id, 'request_user': request.user}
        )
        serializer.is_valid(raise_exception=True)
        settlement = serializer.save()

        # Recalculate balances for the two affected users and return them
        calculator = BalanceCalculator(group.id)
        net_balances = calculator.get_group_balances()

        affected_balances = []
        for uid in [settlement.paid_by_id, settlement.paid_to_id]:
            u = User.objects.get(pk=uid)
            balance_val = float(net_balances.get(uid, 0.0))
            if balance_val > 0.005:
                status_label = 'owed'
            elif balance_val < -0.005:
                status_label = 'owes'
            else:
                status_label = 'settled'

            affected_balances.append({
                'user_id': u.id,
                'name': u.name,
                'email': u.email,
                'avatar_color': u.avatar_color,
                'net_balance_inr': balance_val,
                'status': status_label,
            })

        return Response(
            {
                'settlement': SettlementSerializer(settlement).data,
                'balances': affected_balances,
            },
            status=status.HTTP_201_CREATED,
        )


class DebugBalanceTraceView(APIView):
    """
    GET /api/groups/{id}/debug/balance-trace/{user_id}/ — Step-by-step balance audit.
    Requires staff role OR requesting user to match user_id.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, user_id):
        # Access control
        if not request.user.is_staff and request.user.id != user_id:
            return Response(
                {
                    'error': 'You do not have permission to view this user\'s trace.',
                    'code': 'PERMISSION_DENIED',
                    'details': {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        group = get_object_or_404(Group, pk=pk)
        calculator = BalanceCalculator(group.id)
        trace_data = calculator.get_user_breakdown(user_id)
        return Response(trace_data, status=status.HTTP_200_OK)
