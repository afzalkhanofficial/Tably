"""
Serializers for the importer app.
"""

from rest_framework import serializers

from apps.importer.models import ImportAnomaly, ImportSession


class ImportAnomalySerializer(serializers.ModelSerializer):
    """Serializer for individual import anomalies."""

    class Meta:
        model = ImportAnomaly
        fields = [
            'id',
            'row_number',
            'anomaly_type',
            'description',
            'raw_row_data',
            'suggested_fix',
            'action_taken',
            'requires_user_approval',
            'resolved',
            'resolution_choice',
            'resolution_value',
            'resolved_by',
            'resolved_at',
        ]
        read_only_fields = [
            'id', 'row_number', 'anomaly_type', 'description',
            'raw_row_data', 'suggested_fix', 'action_taken',
            'requires_user_approval',
        ]


class ImportSessionSerializer(serializers.ModelSerializer):
    """Serializer for import session overview."""
    anomalies = ImportAnomalySerializer(many=True, read_only=True)

    class Meta:
        model = ImportSession
        fields = [
            'id',
            'filename',
            'group',
            'imported_by',
            'imported_at',
            'status',
            'total_rows',
            'auto_imported_count',
            'auto_fixed_count',
            'pending_review_count',
            'skipped_count',
            'anomalies',
        ]
        read_only_fields = fields


class ImportSessionSummarySerializer(serializers.ModelSerializer):
    """Lighter serializer without nested anomalies — for list views."""

    class Meta:
        model = ImportSession
        fields = [
            'id',
            'filename',
            'group',
            'imported_by',
            'imported_at',
            'status',
            'total_rows',
            'auto_imported_count',
            'auto_fixed_count',
            'pending_review_count',
            'skipped_count',
        ]
        read_only_fields = fields


class AnomalyResolveSerializer(serializers.Serializer):
    """Validates the body of POST /resolve/ endpoint."""
    choice = serializers.ChoiceField(
        choices=['keep', 'skip', 'set_value'],
        help_text=(
            "'keep' — commit the row as-is. "
            "'skip' — discard the row. "
            "'set_value' — override specific fields and commit."
        ),
    )
    value = serializers.JSONField(
        required=False,
        default=dict,
        help_text="Field overrides when choice='set_value'. E.g. {'paid_by': 'Rohan'}.",
    )
