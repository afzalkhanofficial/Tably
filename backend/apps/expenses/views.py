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
    GET /api/groups/{pk}/debug/balance-trace/{user_id}/
    Returns a step-by-step JSON trace of how a user's balance is calculated.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, user_id):
        from decimal import Decimal, ROUND_HALF_UP
        from apps.users.models import User
        from apps.expenses.models import Expense, Settlement
        from services.balance_calculator import BalanceCalculator

        # Check permissions: only requesting user themselves or staff
        if request.user.id != user_id and not request.user.is_staff:
            return Response(
                {
                    'error': 'You do not have permission to view this debug trace.',
                    'code': 'PERMISSION_DENIED',
                    'details': {}
                },
                status=status.HTTP_403_FORBIDDEN
            )

        user = get_object_or_404(User, id=user_id)
        group = get_object_or_404(Group, id=pk)

        # Initialize the balance calculator to reuse membership verification helper
        calculator = BalanceCalculator(group.id)

        # Fetch non-deleted, non-settlement expenses sorted chronologically
        expenses_qs = Expense.objects.filter(
            group_id=group.id,
            is_deleted=False,
            is_settlement=False
        ).prefetch_related('splits').order_by('expense_date', 'id')

        # Fetch all settlements sorted chronologically
        settlements_qs = Settlement.objects.filter(
            group_id=group.id
        ).order_by('settled_at', 'id')

        # Combine items chronologically
        items = []
        for exp in expenses_qs:
            items.append({
                'type': 'expense',
                'date': exp.expense_date,
                'id_sort': exp.id,
                'obj': exp
            })
        for setl in settlements_qs:
            items.append({
                'type': 'settlement',
                'date': setl.settled_at.date(),
                'id_sort': setl.id,
                'obj': setl
            })

        # Sort combined list chronologically
        items.sort(key=lambda x: (x['date'], x['id_sort']))

        calculation_steps = []
        running_balance = Decimal('0')
        step_num = 1

        for item in items:
            if item['type'] == 'expense':
                exp = item['obj']
                # Check if the user is active on this expense date
                user_active = calculator._is_member_active_on(user_id, exp.expense_date)
                
                # Check if user is payer or participant
                is_payer = (exp.paid_by_id == user_id)
                user_split = None
                for split in exp.splits.all():
                    if split.user_id == user_id:
                        user_split = split
                        break

                # Count active participants for this expense
                active_splits = [
                    s for s in exp.splits.all()
                    if calculator._is_member_active_on(s.user_id, exp.expense_date)
                ]
                participants_count = len(active_splits)
                active_total = sum(s.amount_owed for s in active_splits)

                # If the user was not active on this date, skip
                if not user_active:
                    continue

                # If user is not the payer and not in splits, this expense has no effect
                if not is_payer and not user_split:
                    continue

                role = 'PAYER' if is_payer else 'PARTICIPANT'
                your_share_inr = user_split.amount_owed if user_split else Decimal('0')

                # Calculate effect
                if is_payer:
                    effect_on_balance = active_total - your_share_inr
                else:
                    effect_on_balance = -your_share_inr

                running_balance += effect_on_balance

                # Build explanation text for 'your_share_calculation'
                your_share_calculation = ""
                if user_split:
                    if exp.split_type == 'equal':
                        your_share_calculation = f"{exp.amount_inr:.0f} ÷ {participants_count} = {your_share_inr:.0f}"
                    elif exp.split_type == 'unequal':
                        your_share_calculation = f"Unequal split: individual share is {your_share_inr:.0f}"
                    elif exp.split_type == 'percentage':
                        pct = (your_share_inr / exp.amount_inr * Decimal('100')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
                        your_share_calculation = f"Percentage split: {pct}% of {exp.amount_inr:.0f} = {your_share_inr:.0f}"
                    elif exp.split_type == 'share':
                        amounts = [s.amount_owed for s in active_splits if s.amount_owed > 0]
                        min_amt = min(amounts) if amounts else Decimal('1')
                        if min_amt > 0:
                            share_val = round(your_share_inr / min_amt)
                            total_shares_val = sum(round(s.amount_owed / min_amt) for s in active_splits)
                            your_share_calculation = f"Share split: {share_val} of {total_shares_val} shares = {your_share_inr:.0f}"
                        else:
                            your_share_calculation = f"Share split: individual share is {your_share_inr:.0f}"
                else:
                    your_share_calculation = "Not a participant in this expense"

                # Generate note
                payer_name = exp.paid_by.name if exp.paid_by else "Unknown"
                if is_payer:
                    note = f"{user.name} paid {exp.description.lower()}, others owe {user.name} proportionally"
                else:
                    note = f"{payer_name} paid, {user.name} owes ₹{your_share_inr:,.2f} to {payer_name}"

                calculation_steps.append({
                    "step": step_num,
                    "expense_id": exp.id,
                    "date": str(exp.expense_date),
                    "description": exp.description,
                    "role": role,
                    "total_amount_inr": float(exp.amount_inr),
                    "split_type": exp.split_type,
                    "participants_count": participants_count,
                    "your_share_calculation": your_share_calculation,
                    "your_share_inr": float(your_share_inr),
                    "effect_on_balance": float(effect_on_balance),
                    "running_balance": float(running_balance.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
                    "note": note
                })
                step_num += 1

            elif item['type'] == 'settlement':
                settlement = item['obj']
                is_settlement_payer = (settlement.paid_by_id == user_id)
                is_settlement_recipient = (settlement.paid_to_id == user_id)

                if not is_settlement_payer and not is_settlement_recipient:
                    continue

                role = 'SETTLEMENT_PAYER' if is_settlement_payer else 'SETTLEMENT_RECIPIENT'
                
                if is_settlement_payer:
                    effect_on_balance = settlement.amount_inr
                    payer_name = user.name
                    recipient_name = settlement.paid_to.name
                    note = f"{user.name} paid {recipient_name} ₹{settlement.amount_inr:,.2f}, reducing debt"
                else:
                    effect_on_balance = -settlement.amount_inr
                    payer_name = settlement.paid_by.name
                    recipient_name = user.name
                    note = f"{payer_name} paid {user.name} ₹{settlement.amount_inr:,.2f}, reducing amount owed"

                running_balance += effect_on_balance

                calculation_steps.append({
                    "step": step_num,
                    "expense_id": None,
                    "date": str(settlement.settled_at.date()),
                    "description": f"Settlement: {payer_name} paid {recipient_name}",
                    "role": role,
                    "total_amount_inr": float(settlement.amount_inr),
                    "split_type": "settlement",
                    "participants_count": 2,
                    "your_share_calculation": f"Settlement payment of {settlement.amount_inr}",
                    "your_share_inr": float(settlement.amount_inr),
                    "effect_on_balance": float(effect_on_balance),
                    "running_balance": float(running_balance.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
                    "note": note
                })
                step_num += 1

        final_balance = float(running_balance.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        
        if final_balance > 0:
            interpretation = f"{user.name} is owed ₹{abs(final_balance):,.2f} by the group collectively"
        elif final_balance < 0:
            interpretation = f"{user.name} owes ₹{abs(final_balance):,.2f} to the group collectively"
        else:
            interpretation = f"{user.name} is fully settled with the group"

        return Response({
            "user": {"id": user.id, "name": user.name},
            "group": {"id": group.id, "name": group.name},
            "calculation_steps": calculation_steps,
            "final_balance": final_balance,
            "interpretation": interpretation
        }, status=status.HTTP_200_OK)
