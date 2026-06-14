"""
Root URL configuration for the Flat Expenses Tracker API.
"""

from django.contrib import admin
from django.urls import include, path
from apps.core.views import health_check

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health_check, name='health-check'),

    # Users App (Register, Login, Token Refresh, Me)
    path('api/', include('apps.users.urls')),

    # Groups App (List, Detail, Members)
    path('api/', include('apps.groups.urls')),

    # Expenses App (Expenses, Balances, Settlements)
    path('api/', include('apps.expenses.urls')),

    # Importer (CSV upload, anomaly resolution, reports)
    path('api/', include('apps.importer.urls')),
]
