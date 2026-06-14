from django.conf import settings
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------
SPLIT_TYPE_CHOICES = [
    ('equal', 'Equal'),            # Each person pays the same amount
    ('unequal', 'Unequal'),        # Fixed rupee amounts per person
    ('percentage', 'Percentage'),  # Percentage of total per person
    ('share', 'Share Ratio'),      # Ratio-based (e.g. 2:1:1)
]

CURRENCY_CHOICES = [
    ('INR', 'Indian Rupee'),
    ('USD', 'US Dollar'),
    ('EUR', 'Euro'),
    ('GBP', 'British Pound'),
]


# ---------------------------------------------------------------------------
# Expense
# ---------------------------------------------------------------------------
class Expense(models.Model):
    group = models.ForeignKey(
        'groups.Group',
        on_delete=models.CASCADE,
        related_name='expenses',
    )
    description = models.CharField(max_length=500)

    # Original amount in original currency
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='INR')

    # Converted amount always in INR for balance calculations
    amount_inr = models.DecimalField(max_digits=12, decimal_places=2)
    # If currency != INR, store the rate used for auditability
    exchange_rate_used = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True,
    )
    exchange_rate_date = models.DateField(null=True, blank=True)

    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='expenses_paid',
        null=True,
        blank=True,
        # null=True allows "unknown payer" pending resolution
    )
    expense_date = models.DateField()
    split_type = models.CharField(max_length=20, choices=SPLIT_TYPE_CHOICES)

    # Flags
    is_settlement = models.BooleanField(default=False)
    # is_settlement: True for "Rohan paid Aisha back" type entries
    is_refund = models.BooleanField(default=False)
    # is_refund: True for negative amounts like parasailing refund
    is_deleted = models.BooleanField(default=False)
    # Soft delete — never hard delete for audit trail

    notes = models.TextField(blank=True)

    # Tracks which CSV row this came from, for anomaly tracing
    import_row_ref = models.IntegerField(null=True, blank=True)
    import_session = models.ForeignKey(
        'importer.ImportSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='expenses',
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='expenses_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'expenses'
        ordering = ['-expense_date', '-created_at']
        indexes = [
            models.Index(fields=['group', 'expense_date']),
            models.Index(fields=['group', 'is_deleted']),
            models.Index(fields=['paid_by']),
        ]

    def __str__(self):
        return f"{self.expense_date} | {self.description} | {self.currency} {self.total_amount}"


# ---------------------------------------------------------------------------
# Expense Split
# ---------------------------------------------------------------------------
class ExpenseSplit(models.Model):
    """
    One row per person per expense. This is the source of truth for
    how much each person owes on a given expense.

    amount_owed is ALWAYS in INR regardless of the original expense currency.
    This means balance calculations never need to touch exchange rates —
    they just sum amount_owed across all splits per user.
    """
    expense = models.ForeignKey(
        Expense,
        on_delete=models.CASCADE,
        related_name='splits',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='expense_splits',
    )
    amount_owed = models.DecimalField(max_digits=12, decimal_places=2)
    # amount_owed: always INR. For USD expenses this is converted amount / split count

    class Meta:
        db_table = 'expense_splits'
        unique_together = [['expense', 'user']]

    def __str__(self):
        return f"{self.user} owes ₹{self.amount_owed} on {self.expense}"


# ---------------------------------------------------------------------------
# Settlement
# ---------------------------------------------------------------------------
class Settlement(models.Model):
    """
    Records actual payments between members.
    Separate from expenses — a settlement REDUCES balances directly.
    """
    group = models.ForeignKey(
        'groups.Group',
        on_delete=models.CASCADE,
        related_name='settlements',
    )
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='settlements_paid',
    )
    paid_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='settlements_received',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    amount_inr = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.TextField(blank=True)
    settled_at = models.DateTimeField(default=timezone.now)
    import_row_ref = models.IntegerField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='settlements_created',
    )

    class Meta:
        db_table = 'settlements'
        ordering = ['-settled_at']

    def __str__(self):
        return f"{self.paid_by} → {self.paid_to}: ₹{self.amount_inr}"
