from django.conf import settings
from django.db import models


class Group(models.Model):
    """A shared flat / expense group."""
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_groups',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'groups'

    def __str__(self):
        return self.name


class GroupMember(models.Model):
    """
    Time-scoped membership. joined_at and left_at define the EXACT window
    during which an expense can affect this member's balance.

    Example: Sam joined 2026-04-08. Any expense before that date does NOT
    appear in Sam's balance, even if his name is in the CSV split_with column.

    Example: Meera left 2026-03-28. Row 36 (April groceries) includes her name
    as an error — the importer removes her and recalculates.
    """
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name='members',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='group_memberships',
    )
    joined_at = models.DateField()
    left_at = models.DateField(null=True, blank=True)
    # left_at = None means currently active member

    class Meta:
        db_table = 'group_members'
        unique_together = [['group', 'user', 'joined_at']]
        # Allows same person to leave and rejoin (different joined_at)

    def is_active_on(self, date):
        """Returns True if this member was active on the given date."""
        if date < self.joined_at:
            return False
        if self.left_at and date > self.left_at:
            return False
        return True

    def __str__(self):
        status = 'active' if self.left_at is None else f'left {self.left_at}'
        return f"{self.user} in {self.group} ({status})"
