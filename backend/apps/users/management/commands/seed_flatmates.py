"""
Management command to seed the database with sample flatmates and group.

Usage:
    python manage.py seed_flatmates

Creates:
- Group: "The Flat" (group_id=1)
- 6 users (5 GroupMembers + 1 guest user)
- Time-scoped memberships reflecting join/leave dates
"""
from datetime import date

from django.core.management.base import BaseCommand

from apps.groups.models import Group, GroupMember
from apps.users.models import User


AVATAR_COLORS = [
    '#EF4444',  # Red
    '#F97316',  # Orange
    '#EAB308',  # Yellow
    '#22C55E',  # Green
    '#3B82F6',  # Blue
    '#A855F7',  # Purple
]

FLATMATES = [
    {
        'email': 'aisha@flat.com',
        'name': 'Aisha',
        'password': 'flatmate123',
        'joined_at': date(2026, 2, 1),
        'left_at': None,
    },
    {
        'email': 'rohan@flat.com',
        'name': 'Rohan',
        'password': 'flatmate123',
        'joined_at': date(2026, 2, 1),
        'left_at': None,
    },
    {
        'email': 'priya@flat.com',
        'name': 'Priya',
        'password': 'flatmate123',
        'joined_at': date(2026, 2, 1),
        'left_at': None,
    },
    {
        'email': 'meera@flat.com',
        'name': 'Meera',
        'password': 'flatmate123',
        'joined_at': date(2026, 2, 1),
        'left_at': date(2026, 3, 28),
    },
    {
        'email': 'sam@flat.com',
        'name': 'Sam',
        'password': 'flatmate123',
        'joined_at': date(2026, 4, 8),
        'left_at': None,
    },
]

# Dev is a User but NOT a GroupMember.
# He participates in specific expenses (Goa trip) but does not have a flat balance.
GUEST_USER = {
    'email': 'dev@flat.com',
    'name': 'Dev',
    'password': 'flatmate123',
}


class Command(BaseCommand):
    help = 'Seed database with sample flatmates, group, and memberships'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('Seeding flatmates...'))

        # --- Create or get "The Flat" group ---
        group, created = Group.objects.get_or_create(
            pk=1,
            defaults={
                'name': 'The Flat',
                'description': 'Shared flat expense tracking group',
            },
        )
        status = 'Created' if created else 'Already exists'
        self.stdout.write(f'  Group "{group.name}" — {status}')

        # --- Create flatmate users + memberships ---
        for i, data in enumerate(FLATMATES):
            user, created = User.objects.get_or_create(
                email=data['email'],
                defaults={
                    'name': data['name'],
                    'avatar_color': AVATAR_COLORS[i],
                },
            )
            if created:
                user.set_password(data['password'])
                user.save()

            # Set created_by on group if this is the first user
            if i == 0 and group.created_by is None:
                group.created_by = user
                group.save(update_fields=['created_by'])

            membership, mem_created = GroupMember.objects.get_or_create(
                group=group,
                user=user,
                joined_at=data['joined_at'],
                defaults={'left_at': data['left_at']},
            )

            user_status = 'Created' if created else 'Already exists'
            mem_status = 'Created' if mem_created else 'Already exists'
            left_info = f', left {data["left_at"]}' if data['left_at'] else ''
            self.stdout.write(
                f'  {data["name"]:10s} ({data["email"]}) — '
                f'User: {user_status}, Membership: {mem_status}'
                f' (joined {data["joined_at"]}{left_info})'
            )

        # --- Create guest user (no group membership) ---
        guest, created = User.objects.get_or_create(
            email=GUEST_USER['email'],
            defaults={
                'name': GUEST_USER['name'],
                'avatar_color': AVATAR_COLORS[5],
            },
        )
        if created:
            guest.set_password(GUEST_USER['password'])
            guest.save()
        guest_status = 'Created' if created else 'Already exists'
        self.stdout.write(
            f'  {"Dev":10s} ({GUEST_USER["email"]}) — '
            f'User: {guest_status}, Membership: NONE (guest)'
        )

        self.stdout.write(self.style.SUCCESS('\n[OK] Seed complete!'))
