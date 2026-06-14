from django.conf import settings
from django.db import models


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------
IMPORT_STATUS = [
    ('processing', 'Processing'),
    ('pending_review', 'Pending User Review'),
    ('complete', 'Complete'),
    ('failed', 'Failed'),
]

ANOMALY_TYPES = [
    ('EXACT_DUPLICATE', 'Exact Duplicate'),
    ('CONFLICTING_DUPLICATE', 'Conflicting Duplicate'),
    ('AMOUNT_FORMAT', 'Amount Format Error'),
    ('NAME_FUZZY_MATCH', 'Name Fuzzy Match'),
    ('MISSING_PAID_BY', 'Missing Payer'),
    ('SETTLEMENT_PATTERN', 'Settlement Detected'),
    ('PERCENTAGE_SUM_ERROR', 'Percentage Sum ≠ 100%'),
    ('FOREIGN_CURRENCY', 'Foreign Currency Converted'),
    ('UNKNOWN_MEMBER', 'Unknown Member in Split'),
    ('NEGATIVE_AMOUNT', 'Negative Amount (Refund)'),
    ('NONSTANDARD_DATE', 'Non-standard Date Format'),
    ('MISSING_CURRENCY', 'Missing Currency'),
    ('ZERO_AMOUNT', 'Zero Amount'),
    ('AMBIGUOUS_DATE', 'Ambiguous Date Format'),
    ('MEMBER_POST_DEPARTURE', 'Member Included After Departure'),
    ('SPLIT_TYPE_CONFLICT', 'Split Type vs Details Conflict'),
    ('DECIMAL_PRECISION', 'Excessive Decimal Precision'),
]

ANOMALY_ACTIONS = [
    ('AUTO_FIXED', 'Auto Fixed — No Review Needed'),
    ('AUTO_IMPORTED', 'Imported Clean'),
    ('SKIPPED', 'Skipped'),
    ('PENDING_USER', 'Awaiting User Decision'),
    ('USER_RESOLVED', 'Resolved by User'),
]


# ---------------------------------------------------------------------------
# Import Session
# ---------------------------------------------------------------------------
class ImportSession(models.Model):
    filename = models.CharField(max_length=255)
    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
    )
    imported_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20, choices=IMPORT_STATUS, default='processing',
    )
    total_rows = models.IntegerField(default=0)
    auto_imported_count = models.IntegerField(default=0)
    auto_fixed_count = models.IntegerField(default=0)
    pending_review_count = models.IntegerField(default=0)
    skipped_count = models.IntegerField(default=0)

    class Meta:
        db_table = 'import_sessions'

    def __str__(self):
        return f"Import {self.pk}: {self.filename} ({self.status})"


# ---------------------------------------------------------------------------
# Import Anomaly
# ---------------------------------------------------------------------------
class ImportAnomaly(models.Model):
    session = models.ForeignKey(
        ImportSession, on_delete=models.CASCADE, related_name='anomalies',
    )
    row_number = models.IntegerField()
    anomaly_type = models.CharField(max_length=50, choices=ANOMALY_TYPES)
    description = models.TextField()                # Human-readable explanation
    raw_row_data = models.JSONField()               # The original CSV row as dict
    suggested_fix = models.JSONField(null=True, blank=True)  # What we'd do auto
    action_taken = models.CharField(max_length=30, choices=ANOMALY_ACTIONS)
    requires_user_approval = models.BooleanField(default=False)
    resolved = models.BooleanField(default=False)
    resolution_choice = models.CharField(max_length=50, blank=True)
    resolution_value = models.JSONField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='anomalies_resolved',
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'import_anomalies'
        ordering = ['row_number']

    def __str__(self):
        return f"Row {self.row_number}: {self.anomaly_type} ({self.action_taken})"
