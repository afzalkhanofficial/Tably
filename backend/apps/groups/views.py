"""
Group management API views.
"""

from datetime import datetime
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.groups.models import Group, GroupMember
from apps.groups.serializers import (
    AddMemberSerializer,
    GroupCreateSerializer,
    GroupDetailSerializer,
    GroupListSerializer,
)


class GroupListCreateView(APIView):
    """
    GET /api/groups/ — List all groups the user is a member of.
    POST /api/groups/ — Create a new group. Creator becomes admin/member.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        # Get groups where the user is a member
        memberships = GroupMember.objects.filter(user=user).values_list('group_id', flat=True)
        groups = Group.objects.filter(id__in=memberships).order_by('-created_at')
        serializer = GroupListSerializer(groups, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = GroupCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        group = serializer.save()
        # Return detail-level serializer info
        return Response(GroupDetailSerializer(group).data, status=status.HTTP_201_CREATED)


class GroupDetailView(APIView):
    """
    GET /api/groups/{id}/ — Get detailed view of group including members list.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        group = get_object_or_404(Group, pk=pk)
        # Verify requesting user is a member of the group
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

        serializer = GroupDetailSerializer(group)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GroupMemberListCreateView(APIView):
    """
    POST /api/groups/{id}/members/ — Add a user to the group.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        group = get_object_or_404(Group, pk=pk)
        # Verify requester is a member of the group
        is_member = GroupMember.objects.filter(group=group, user=request.user).exists()
        if not is_member and not request.user.is_staff:
            return Response(
                {
                    'error': 'Only members can add users to this group.',
                    'code': 'NOT_GROUP_MEMBER',
                    'details': {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = AddMemberSerializer(data=request.data, context={'group_id': group.id})
        serializer.is_valid(raise_exception=True)

        user_obj = serializer.validated_data['user_obj']
        joined_at = serializer.validated_data['joined_at']

        # Add user
        member = GroupMember.objects.create(
            group=group,
            user=user_obj,
            joined_at=joined_at,
        )

        return Response(
            GroupDetailSerializer(group).data,
            status=status.HTTP_201_CREATED,
        )


class GroupMemberDepartView(APIView):
    """
    PATCH /api/groups/{id}/members/{user_id}/ — Mark a member as departed.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk, user_id):
        group = get_object_or_404(Group, pk=pk)

        # Verify requester is a member of the group
        is_member = GroupMember.objects.filter(group=group, user=request.user).exists()
        if not is_member and not request.user.is_staff:
            return Response(
                {
                    'error': 'Only members can manage memberships.',
                    'code': 'NOT_GROUP_MEMBER',
                    'details': {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Get active membership for the user
        member = get_object_or_404(GroupMember, group=group, user_id=user_id, left_at__isnull=True)

        left_at_str = request.data.get('left_at')
        if not left_at_str:
            return Response(
                {
                    'error': 'left_at date is required.',
                    'code': 'VALIDATION_ERROR',
                    'details': {'left_at': ['This field is required.']},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            left_at = datetime.strptime(left_at_str, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {
                    'error': 'Invalid date format. Use YYYY-MM-DD.',
                    'code': 'VALIDATION_ERROR',
                    'details': {'left_at': ['Invalid date format. Use YYYY-MM-DD.']},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate left_at is not before joined_at
        if left_at < member.joined_at:
            return Response(
                {
                    'error': f'Departure date ({left_at}) cannot be before join date ({member.joined_at}).',
                    'code': 'VALIDATION_ERROR',
                    'details': {'left_at': ['Departure date cannot be before join date.']},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Save departure
        member.left_at = left_at
        member.save()

        return Response(
            GroupDetailSerializer(group).data,
            status=status.HTTP_200_OK,
        )


class GroupBalanceTraceView(APIView):
    """
    GET /api/groups/{id}/debug/balance-trace/{user_id}/
    Returns a step-by-step JSON trace of how a user's balance is calculated.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, id, user_id):
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
        group = get_object_or_404(Group, id=id)

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

                # If the user was not active on this date, skip (sam joined april, march expense has no effect)
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
                        # Find greatest common divisor or estimate ratio
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

