"""
Authentication API Views
"""

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.groups.models import GroupMember
from apps.users.serializers import LoginSerializer, RegisterSerializer, UserSerializer


def get_tokens_for_user(user):
    """Generate JWT tokens for a user."""
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


class RegisterView(APIView):
    """
    POST /api/auth/register/
    Register a new user.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        tokens = get_tokens_for_user(user)
        return Response(
            {
                'user': UserSerializer(user).data,
                'tokens': tokens,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """
    POST /api/auth/login/
    Log in a user.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        tokens = get_tokens_for_user(user)
        return Response(
            {
                'user': UserSerializer(user).data,
                'tokens': tokens,
            },
            status=status.HTTP_200_OK,
        )


class JWTRefreshView(TokenRefreshView):
    """
    POST /api/auth/refresh/
    Wrap SimpleJWT TokenRefreshView to fit the exact response structure {access} or default.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        # The standard TokenRefreshView returns {'access': '...', 'refresh': '...'} if ROTATE_REFRESH_TOKENS is True.
        # SimpleJWT expects body to have {'refresh': '<refresh_token>'}
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            # SimpleJWT returns both tokens usually, but let's make sure 'access' is in the top level response
            return Response({'access': response.data['access']}, status=status.HTTP_200_OK)
        return response


class MeView(APIView):
    """
    GET /api/auth/me/
    Get current logged-in user profile, including their groups.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        # Retrieve groups this user is a member of
        memberships = GroupMember.objects.filter(user=user).select_related('group')
        groups_data = []
        for m in memberships:
            # Dynamically determine role
            role = 'admin' if m.group.created_by_id == user.id else 'member'
            groups_data.append({
                'id': m.group.id,
                'name': m.group.name,
                'role': role,
            })

        user_data = UserSerializer(user).data
        user_data['groups'] = groups_data
        return Response(user_data, status=status.HTTP_200_OK)
