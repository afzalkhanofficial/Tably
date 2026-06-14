"""
URL patterns for the importer app.
"""

from django.urls import path

from apps.importer.views import (
    AnomalyResolveView,
    CSVImportView,
    ImportAnomalyListView,
    ImportReportView,
    ImportSessionDetailView,
)

app_name = 'importer'

urlpatterns = [
    # Upload CSV into a group
    path(
        'groups/<int:group_id>/import/',
        CSVImportView.as_view(),
        name='csv-import',
    ),

    # Session detail (status + anomalies + summary)
    path(
        'import/<int:session_id>/',
        ImportSessionDetailView.as_view(),
        name='session-detail',
    ),

    # Unresolved anomalies (paginated)
    path(
        'import/<int:session_id>/anomalies/',
        ImportAnomalyListView.as_view(),
        name='anomaly-list',
    ),

    # Resolve a single anomaly
    path(
        'import/<int:session_id>/anomalies/<int:anomaly_id>/resolve/',
        AnomalyResolveView.as_view(),
        name='anomaly-resolve',
    ),

    # Full import report
    path(
        'import/<int:session_id>/report/',
        ImportReportView.as_view(),
        name='import-report',
    ),
]
