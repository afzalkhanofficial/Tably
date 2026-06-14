"""
URL routing for Groups app
"""

from django.urls import path

from apps.groups.views import (
    GroupDetailView,
    GroupListCreateView,
    GroupMemberDepartView,
    GroupMemberListCreateView,
)

app_name = 'groups'

urlpatterns = [
    # List and Create Groups
    path('groups/', GroupListCreateView.as_view(), name='group-list-create'),

    # Detail Group
    path('groups/<int:pk>/', GroupDetailView.as_view(), name='group-detail'),

    # Add Member to Group
    path('groups/<int:pk>/members/', GroupMemberListCreateView.as_view(), name='group-add-member'),

    # Mark Member Departed
    path('groups/<int:pk>/members/<int:user_id>/', GroupMemberDepartView.as_view(), name='group-member-depart'),
]
