"""
Serializers for the groups app.
"""

from datetime import date
from django.db.models import Max
from rest_framework import serializers

from apps.groups.models import Group, GroupMember
from apps.users.serializers import UserSerializer
from apps.users.models import User


class GroupListSerializer(serializers.ModelSerializer):
    """Serializer for group overview (list view)."""
    member_count = serializers.SerializerMethodField()
    last_expense_date = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ['id', 'name', 'description', 'created_at', 'member_count', 'last_expense_date']
        read_only_fields = fields

    def get_member_count(self, obj):
        return obj.members.count()

    def get_last_expense_date(self, obj):
        # Only non-deleted expenses
        max_date = obj.expenses.filter(is_deleted=False).aggregate(max_date=Max('expense_date'))['max_date']
        return max_date.isoformat() if max_date else None


class GroupMemberSerializer(serializers.ModelSerializer):
    """Serializer for GroupMember details."""
    user_id = serializers.IntegerField(source='user.id')
    name = serializers.CharField(source='user.name')
    email = serializers.EmailField(source='user.email')
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = GroupMember
        fields = ['user_id', 'name', 'email', 'joined_at', 'left_at', 'is_active']
        read_only_fields = fields

    def get_is_active(self, obj):
        return obj.left_at is None


class GroupDetailSerializer(serializers.ModelSerializer):
    """Serializer for detailed group view."""
    members = GroupMemberSerializer(many=True, read_only=True)
    expense_count = serializers.SerializerMethodField()
    total_spent_inr = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ['id', 'name', 'description', 'created_at', 'members', 'expense_count', 'total_spent_inr']
        read_only_fields = fields

    def get_expense_count(self, obj):
        return obj.expenses.filter(is_deleted=False).count()

    def get_total_spent_inr(self, obj):
        from django.db.models import Sum
        # Exclude settlements and deleted expenses
        total = obj.expenses.filter(
            is_deleted=False, is_settlement=False
        ).aggregate(total=Sum('amount_inr'))['total']
        return float(total) if total is not None else 0.0


class GroupCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a group."""

    class Meta:
        model = Group
        fields = ['id', 'name', 'description', 'created_at']
        read_only_fields = ['id', 'created_at']

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['created_by'] = request.user
        group = super().create(validated_data)
        # Automatically add creator as member with joined_at = today
        GroupMember.objects.create(
            group=group,
            user=request.user,
            joined_at=date.today(),
        )
        return group


class AddMemberSerializer(serializers.Serializer):
    """Serializer to add a member to a group."""
    user_id = serializers.IntegerField()
    joined_at = serializers.DateField(default=date.today)

    def validate(self, attrs):
        group_id = self.context.get('group_id')
        user_id = attrs['user_id']

        # Validate user exists
        try:
            attrs['user_obj'] = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            raise serializers.ValidationError({"user_id": "User does not exist."})

        # Validate not already active member
        # (meaning currently in the group with left_at is None)
        already_active = GroupMember.objects.filter(
            group_id=group_id,
            user_id=user_id,
            left_at__isnull=True,
        ).exists()
        if already_active:
            raise serializers.ValidationError({"user_id": "User is already an active member of this group."})

        return attrs
