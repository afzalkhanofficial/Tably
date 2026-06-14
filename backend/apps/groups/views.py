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
