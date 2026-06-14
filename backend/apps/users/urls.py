"""
URL Routing for User Auth endpoints
"""

from django.urls import path

from apps.users.views import JWTRefreshView, LoginView, MeView, RegisterView

app_name = 'users'

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/refresh/', JWTRefreshView.as_view(), name='token_refresh'),
    path('auth/me/', MeView.as_view(), name='me'),
]
