"""
Serializers for the expenses app.
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from rest_framework import serializers

from apps.expenses.models import CURRENCY_CHOICES, Expense, ExpenseSplit, SPLIT_TYPE_CHOICES, Settlement
from apps.groups.models import GroupMember
from apps.importer.fx_client import FXClient
from apps.users.models import User
from apps.users.serializers import UserSerializer


class ExpenseSplitSerializer(serializers.ModelSerializer):
    """Serializer for individual expense splits."""
    user = UserSerializer(read_only=True)
    user_id = serializers.IntegerField(source='user.id', read_only=True)

    class Meta:
        model = ExpenseSplit
        fields = ['user_id', 'user', 'amount_owed']
        read_only_fields = fields


class ExpenseSerializer(serializers.ModelSerializer):
    """Detailed serializer for expense objects."""
    paid_by = UserSerializer(read_only=True)
    splits = ExpenseSplitSerializer(many=True, read_only=True)

    class Meta:
        model = Expense
        fields = [
            'id',
            'description',
            'expense_date',
            'total_amount',
            'currency',
            'amount_inr',
            'exchange_rate_used',
            'exchange_rate_date',
            'paid_by',
            'split_type',
            'is_settlement',
            'is_refund',
            'is_deleted',
            'notes',
            'splits',
            'created_at',
        ]
        read_only_fields = fields


class ExpenseCreateSplitInputSerializer(serializers.Serializer):
    """Validates the splits array in expense creation request."""
    user_id = serializers.IntegerField()
    value = serializers.FloatField(required=False, default=1.0)


class ExpenseCreateSerializer(serializers.Serializer):
    """Validates and creates an Expense with its splits."""
    description = serializers.CharField(max_length=500)
    expense_date = serializers.DateField()
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.ChoiceField(choices=CURRENCY_CHOICES, default='INR')
    paid_by = serializers.IntegerField()
    split_type = serializers.ChoiceField(choices=SPLIT_TYPE_CHOICES)
    splits = ExpenseCreateSplitInputSerializer(many=True)
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        group_id = self.context.get('group_id')
        expense_date = attrs['expense_date']
        paid_by_id = attrs['paid_by']

        # Validate paid_by user exists
        try:
            attrs['paid_by_obj'] = User.objects.get(pk=paid_by_id)
        except User.DoesNotExist:
            raise serializers.ValidationError({"paid_by": "Payer user does not exist."})

        # Validate payer is member of group
        payer_memberships = GroupMember.objects.filter(group_id=group_id, user_id=paid_by_id)
        if not payer_memberships.exists():
            raise serializers.ValidationError({"paid_by": "Payer is not a member of the group."})
        if not any(m.is_active_on(expense_date) for m in payer_memberships):
            raise serializers.ValidationError({"paid_by": f"Payer is not an active member on {expense_date}."})

        # Validate splits is not empty
        split_inputs = attrs.get('splits', [])
        if not split_inputs:
            raise serializers.ValidationError({"splits": "Splits list cannot be empty."})

        # Validate all split users exist and are active in the group on the expense date
        unique_user_ids = set()
        for idx, s in enumerate(split_inputs):
            uid = s['user_id']
            if uid in unique_user_ids:
                raise serializers.ValidationError({"splits": f"Duplicate user_id {uid} in splits."})
            unique_user_ids.add(uid)

            # Validate user exists
            try:
                s['user_obj'] = User.objects.get(pk=uid)
            except User.DoesNotExist:
                raise serializers.ValidationError({"splits": f"User {uid} in splits does not exist."})

            # Validate active membership on expense date
            mships = GroupMember.objects.filter(group_id=group_id, user_id=uid)
            if not mships.exists():
                raise serializers.ValidationError({"splits": f"User {uid} is not a member of the group."})
            if not any(m.is_active_on(expense_date) for m in mships):
                raise serializers.ValidationError({"splits": f"User {uid} is not an active member on {expense_date}."})

        return attrs

    def create(self, validated_data):
        group_id = self.context.get('group_id')
        request_user = self.context.get('request_user')

        total_amount = validated_data['total_amount']
        currency = validated_data['currency']
        expense_date = validated_data['expense_date']
        split_type = validated_data['split_type']
        split_inputs = validated_data['splits']
        paid_by_obj = validated_data['paid_by_obj']
        notes = validated_data['notes']
        description = validated_data['description']

        # 1. Fetch FX rate if currency != INR
        exchange_rate_used = None
        exchange_rate_date = None
        if currency != 'INR':
            fx_client = FXClient()
            try:
                rate = fx_client.get_rate(currency, 'INR', expense_date.isoformat())
                amount_inr = (total_amount * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                exchange_rate_used = rate
                exchange_rate_date = expense_date
            except Exception as e:
                # Fallback to hardcoded rate or raise error
                # Frankfurt fallback
                rates = {'USD': Decimal('83.50'), 'EUR': Decimal('90.00'), 'GBP': Decimal('105.00')}
                rate = rates.get(currency, Decimal('1.00'))
                amount_inr = (total_amount * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                exchange_rate_used = rate
                exchange_rate_date = expense_date
        else:
            amount_inr = total_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # 2. Compute individual split amounts in INR
        shares = {}
        if split_type == 'equal':
            count = len(split_inputs)
            base_share = (amount_inr / count).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            for s in split_inputs:
                shares[s['user_id']] = base_share

        elif split_type == 'unequal':
            total_val = Decimal('0')
            for s in split_inputs:
                val = Decimal(str(s.get('value', 0))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                shares[s['user_id']] = val
                total_val += val
            if total_val != amount_inr:
                raise serializers.ValidationError({
                    "splits": f"Sum of unequal splits ({total_val}) must equal total amount in INR ({amount_inr})."
                })

        elif split_type == 'percentage':
            total_pct = Decimal('0')
            for s in split_inputs:
                pct = Decimal(str(s.get('value', 0)))
                total_pct += pct
                shares[s['user_id']] = (pct / Decimal('100') * amount_inr).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if abs(total_pct - 100) > Decimal('0.01'):
                raise serializers.ValidationError({
                    "splits": f"Percentages must sum to exactly 100% (got {total_pct}%)."
                })

        elif split_type == 'share':
            total_shares = sum(Decimal(str(s.get('value', 0))) for s in split_inputs)
            if total_shares <= 0:
                raise serializers.ValidationError({
                    "splits": "Total shares ratio must be greater than zero."
                })
            for s in split_inputs:
                ratio = Decimal(str(s.get('value', 0)))
                shares[s['user_id']] = (ratio / total_shares * amount_inr).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # 3. Rounding adjustment: add remainder to payer's split
        sum_shares = sum(shares.values())
        remainder = amount_inr - sum_shares
        if remainder != 0:
            payer_id = paid_by_obj.id
            if payer_id in shares:
                shares[payer_id] += remainder
            else:
                # Add to first split's user
                first_uid = split_inputs[0]['user_id']
                shares[first_uid] += remainder

        # 4. Save Expense and Splits
        expense = Expense.objects.create(
            group_id=group_id,
            description=description,
            total_amount=total_amount,
            currency=currency,
            amount_inr=amount_inr,
            exchange_rate_used=exchange_rate_used,
            exchange_rate_date=exchange_rate_date,
            paid_by=paid_by_obj,
            expense_date=expense_date,
            split_type=split_type,
            notes=notes,
            created_by=request_user,
        )

        for s in split_inputs:
            uid = s['user_id']
            ExpenseSplit.objects.create(
                expense=expense,
                user_id=uid,
                amount_owed=shares[uid],
            )

        return expense


class SettlementSerializer(serializers.ModelSerializer):
    """Serializer for Settlement objects."""
    paid_by = UserSerializer(read_only=True)
    paid_to = UserSerializer(read_only=True)

    class Meta:
        model = Settlement
        fields = [
            'id',
            'paid_by',
            'paid_to',
            'amount',
            'currency',
            'amount_inr',
            'notes',
            'settled_at',
        ]
        read_only_fields = fields


class SettlementCreateSerializer(serializers.Serializer):
    """Validates and creates a Settlement."""
    paid_by = serializers.IntegerField()
    paid_to = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.ChoiceField(choices=CURRENCY_CHOICES, default='INR')
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        group_id = self.context.get('group_id')
        paid_by_id = attrs['paid_by']
        paid_to_id = attrs['paid_to']
        amount = attrs['amount']

        if paid_by_id == paid_to_id:
            raise serializers.ValidationError("Payer and recipient must be different users.")

        if amount <= 0:
            raise serializers.ValidationError("Settlement amount must be positive.")

        # Validate paid_by
        try:
            attrs['paid_by_obj'] = User.objects.get(pk=paid_by_id)
        except User.DoesNotExist:
            raise serializers.ValidationError({"paid_by": "Payer does not exist."})

        # Validate paid_to
        try:
            attrs['paid_to_obj'] = User.objects.get(pk=paid_to_id)
        except User.DoesNotExist:
            raise serializers.ValidationError({"paid_to": "Recipient does not exist."})

        # Validate both are in the group
        for uid, role in [(paid_by_id, "Payer"), (paid_to_id, "Recipient")]:
            m = GroupMember.objects.filter(group_id=group_id, user_id=uid)
            if not m.exists():
                raise serializers.ValidationError({uid: f"{role} is not a member of the group."})

        return attrs

    def create(self, validated_data):
        group_id = self.context.get('group_id')
        request_user = self.context.get('request_user')

        paid_by_obj = validated_data['paid_by_obj']
        paid_to_obj = validated_data['paid_to_obj']
        amount = validated_data['amount']
        currency = validated_data['currency']
        notes = validated_data['notes']

        # Convert amount to INR (Settlements are typically INR, but if foreign we apply standard rule)
        exchange_rate_used = Decimal('1.00')
        if currency != 'INR':
            fx_client = FXClient()
            try:
                rate = fx_client.get_rate(currency, 'INR', date.today().isoformat())
                amount_inr = (amount * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            except Exception:
                rates = {'USD': Decimal('83.50'), 'EUR': Decimal('90.00'), 'GBP': Decimal('105.00')}
                rate = rates.get(currency, Decimal('1.00'))
                amount_inr = (amount * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            amount_inr = amount

        settlement = Settlement.objects.create(
            group_id=group_id,
            paid_by=paid_by_obj,
            paid_to=paid_to_obj,
            amount=amount,
            currency=currency,
            amount_inr=amount_inr,
            notes=notes,
            created_by=request_user,
        )

        return settlement
