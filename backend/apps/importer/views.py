"""
Import API Views
=================

Endpoints:

- ``POST   /api/groups/{group_id}/import/``                   Upload CSV
- ``GET    /api/import/{session_id}/``                        Session detail
- ``GET    /api/import/{session_id}/anomalies/``              Unresolved anomalies
- ``POST   /api/import/{session_id}/anomalies/{id}/resolve/`` Resolve anomaly
- ``GET    /api/import/{session_id}/report/``                 Full import report
"""

import json
import logging
from datetime import date

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.expenses.models import Expense
from apps.groups.models import Group, GroupMember
from apps.importer.models import ImportAnomaly, ImportSession
from apps.importer.parser import CSVParser
from apps.importer.serializers import (
    AnomalyResolveSerializer,
    ImportAnomalySerializer,
    ImportSessionSerializer,
    ImportSessionSummarySerializer,
)
from apps.importer.services import RowCommitter
from apps.users.models import User

logger = logging.getLogger(__name__)

MAX_CSV_SIZE = 5 * 1024 * 1024  # 5 MB


# ======================================================================
# Helpers
# ======================================================================

def _build_member_list(group: Group) -> list:
    """
    Build the member list that the anomaly detector expects.

    Returns list of dicts::

        [{'name': 'Aisha', 'user_id': 1, 'joined_at': date, 'left_at': date|None}, ...]
    """
    members = GroupMember.objects.filter(group=group).select_related('user')
    result = []
    for m in members:
        result.append({
            'name': m.user.name,
            'user_id': m.user_id,
            'joined_at': m.joined_at,
            'left_at': m.left_at,
        })
    # Also include users who aren't group members but are in the system
    # (guest users like Dev), so name matching still works
    member_user_ids = {m.user_id for m in members}
    guest_users = User.objects.exclude(id__in=member_user_ids).filter(
        is_staff=False, is_superuser=False,
    )
    for u in guest_users:
        result.append({
            'name': u.name,
            'user_id': u.id,
            'joined_at': None,
            'left_at': None,
        })
    return result


def _build_member_map(group: Group) -> dict:
    """
    Build ``{canonical_name_lower: User}`` for the RowCommitter.
    """
    member_map = {}
    for m in GroupMember.objects.filter(group=group).select_related('user'):
        member_map[m.user.name.lower()] = m.user
    # Include guest users too
    member_user_ids = set(member_map.values())
    for u in User.objects.filter(is_staff=False, is_superuser=False):
        if u.name.lower() not in member_map:
            member_map[u.name.lower()] = u
    return member_map


def _serialize_anomaly_result(anomaly) -> dict:
    """Convert an AnomalyResult dataclass to a JSON-safe dict."""
    return {
        'anomaly_type': anomaly.anomaly_type,
        'description': anomaly.description,
        'action': anomaly.action,
        'requires_user_approval': anomaly.requires_user_approval,
        'suggested_fix': anomaly.suggested_fix,
    }


# ======================================================================
# POST /api/groups/{group_id}/import/
# ======================================================================

class CSVImportView(APIView):
    """
    Upload a CSV file and import expenses into a group.

    Accepts ``multipart/form-data`` with a file field ``csv_file``.
    Validates file is ``.csv`` and ≤ 5 MB.

    Response: full import report with session ID, per-row results,
    and summary counts.
    """
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request, group_id):
        # --- Validate group exists ---
        group = get_object_or_404(Group, pk=group_id)

        # --- Validate file ---
        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            return Response(
                {
                    'error': 'No file uploaded.',
                    'code': 'NO_FILE',
                    'details': {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not csv_file.name.endswith('.csv'):
            return Response(
                {
                    'error': 'Only .csv files are accepted.',
                    'code': 'INVALID_FILE_TYPE',
                    'details': {'filename': csv_file.name},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if csv_file.size > MAX_CSV_SIZE:
            return Response(
                {
                    'error': f'File too large. Maximum size is 5 MB.',
                    'code': 'FILE_TOO_LARGE',
                    'details': {
                        'size_bytes': csv_file.size,
                        'max_bytes': MAX_CSV_SIZE,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Read CSV content ---
        try:
            csv_content = csv_file.read().decode('utf-8')
        except UnicodeDecodeError:
            return Response(
                {
                    'error': 'File is not valid UTF-8 text.',
                    'code': 'ENCODING_ERROR',
                    'details': {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Build member context ---
        member_list = _build_member_list(group)
        member_map = _build_member_map(group)

        # --- Parse CSV ---
        parser = CSVParser(
            group_id=group.id,
            group_members=member_list,
        )
        parse_result = parser.parse(csv_content)

        # --- Create ImportSession ---
        session = ImportSession.objects.create(
            filename=csv_file.name,
            group=group,
            imported_by=request.user,
            status='processing',
            total_rows=parse_result['total_rows'],
        )

        # --- Process each row ---
        committer = RowCommitter(group, session, member_map)
        auto_imported = 0
        auto_fixed = 0
        pending_review = 0
        skipped = 0
        committed_expenses = []

        for row_result in parse_result['results']:
            row_num = row_result['row_number']
            row_status = row_result['status']
            clean_row = row_result['clean_row']
            anomalies = row_result['anomalies']

            if row_status == 'CLEAN':
                # No anomalies — commit directly
                commit_result = committer.commit_row(
                    clean_row, row_num, anomalies,
                )
                committed_expenses.append({
                    'row_number': row_num,
                    'result': commit_result,
                })
                auto_imported += 1

            elif row_status == 'AUTO_FIXED':
                # Anomalies were auto-resolved — commit the clean row
                commit_result = committer.commit_row(
                    clean_row, row_num, anomalies,
                )
                committed_expenses.append({
                    'row_number': row_num,
                    'result': commit_result,
                })
                auto_fixed += 1

                # Record anomalies for audit trail
                for anomaly in anomalies:
                    ImportAnomaly.objects.create(
                        session=session,
                        row_number=row_num,
                        anomaly_type=anomaly.anomaly_type,
                        description=anomaly.description,
                        raw_row_data=row_result['original_row'],
                        suggested_fix=anomaly.suggested_fix,
                        action_taken=anomaly.action,
                        requires_user_approval=False,
                        resolved=True,
                        resolution_choice='auto_fixed',
                    )

            elif row_status == 'REQUIRES_APPROVAL':
                # Needs user decision — save anomalies as pending
                pending_review += 1
                for anomaly in anomalies:
                    ImportAnomaly.objects.create(
                        session=session,
                        row_number=row_num,
                        anomaly_type=anomaly.anomaly_type,
                        description=anomaly.description,
                        raw_row_data=row_result['original_row'],
                        suggested_fix=anomaly.suggested_fix,
                        action_taken=anomaly.action,
                        requires_user_approval=anomaly.requires_user_approval,
                        resolved=not anomaly.requires_user_approval,
                        resolution_choice=(
                            'auto_fixed'
                            if not anomaly.requires_user_approval
                            else ''
                        ),
                        # Store clean_row in resolution_value for later commit
                        resolution_value={
                            'clean_row': clean_row,
                            'row_status': row_status,
                        } if anomaly.requires_user_approval else None,
                    )

            elif row_status == 'SKIPPED':
                skipped += 1
                for anomaly in anomalies:
                    ImportAnomaly.objects.create(
                        session=session,
                        row_number=row_num,
                        anomaly_type=anomaly.anomaly_type,
                        description=anomaly.description,
                        raw_row_data=row_result['original_row'],
                        suggested_fix=anomaly.suggested_fix,
                        action_taken='SKIPPED',
                        requires_user_approval=False,
                        resolved=True,
                        resolution_choice='skipped',
                    )

        # --- Update session counts ---
        session.auto_imported_count = auto_imported
        session.auto_fixed_count = auto_fixed
        session.pending_review_count = pending_review
        session.skipped_count = skipped
        session.status = (
            'pending_review' if pending_review > 0 else 'complete'
        )
        session.save()

        # --- Build response ---
        response_data = {
            'session_id': session.id,
            'filename': session.filename,
            'status': session.status,
            'summary': {
                'total_rows': parse_result['total_rows'],
                'auto_imported': auto_imported,
                'auto_fixed': auto_fixed,
                'pending_review': pending_review,
                'skipped': skipped,
            },
            'committed_expenses': committed_expenses,
            'anomalies': ImportAnomalySerializer(
                session.anomalies.filter(requires_user_approval=True, resolved=False),
                many=True,
            ).data,
            'all_anomalies_summary': [
                _serialize_anomaly_result(a)
                for row_result in parse_result['results']
                for a in row_result['anomalies']
            ],
        }

        return Response(response_data, status=status.HTTP_201_CREATED)


# ======================================================================
# GET /api/import/{session_id}/
# ======================================================================

class ImportSessionDetailView(APIView):
    """
    Return session status with all anomalies and summary.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        session = get_object_or_404(ImportSession, pk=session_id)
        serializer = ImportSessionSerializer(session)
        return Response(serializer.data)


# ======================================================================
# GET /api/import/{session_id}/anomalies/
# ======================================================================

class ImportAnomalyListView(APIView):
    """
    Return paginated list of unresolved anomalies for a session.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        session = get_object_or_404(ImportSession, pk=session_id)
        anomalies = session.anomalies.filter(
            resolved=False,
            requires_user_approval=True,
        ).order_by('row_number')

        # Manual pagination (using DRF's default PAGE_SIZE from settings)
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 25))
        start = (page - 1) * page_size
        end = start + page_size

        total = anomalies.count()
        page_anomalies = anomalies[start:end]

        return Response({
            'session_id': session.id,
            'session_status': session.status,
            'total_unresolved': total,
            'page': page,
            'page_size': page_size,
            'results': ImportAnomalySerializer(page_anomalies, many=True).data,
        })


# ======================================================================
# POST /api/import/{session_id}/anomalies/{anomaly_id}/resolve/
# ======================================================================

class AnomalyResolveView(APIView):
    """
    Resolve a single anomaly.

    Body::

        {
            "choice": "keep" | "skip" | "set_value",
            "value": { ... }   // only for set_value
        }

    - ``keep``     : commit the row to DB using stored clean_row
    - ``skip``     : mark anomaly resolved with action SKIPPED
    - ``set_value``: override specified field(s) in clean_row and commit
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id, anomaly_id):
        session = get_object_or_404(ImportSession, pk=session_id)
        anomaly = get_object_or_404(
            ImportAnomaly, pk=anomaly_id, session=session,
        )

        if anomaly.resolved:
            return Response(
                {
                    'error': 'This anomaly has already been resolved.',
                    'code': 'ALREADY_RESOLVED',
                    'details': {
                        'resolved_at': str(anomaly.resolved_at),
                        'resolution_choice': anomaly.resolution_choice,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate request body
        serializer = AnomalyResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        choice = serializer.validated_data['choice']
        value = serializer.validated_data.get('value', {})

        if choice == 'skip':
            anomaly.resolved = True
            anomaly.resolution_choice = 'skip'
            anomaly.action_taken = 'SKIPPED'
            anomaly.resolved_by = request.user
            anomaly.resolved_at = timezone.now()
            anomaly.save()

        elif choice in ('keep', 'set_value'):
            # Retrieve the clean row stored during parsing
            clean_row = {}
            if anomaly.resolution_value and isinstance(anomaly.resolution_value, dict):
                clean_row = anomaly.resolution_value.get('clean_row', {})

            if not clean_row:
                # Fallback: use raw_row_data
                clean_row = dict(anomaly.raw_row_data)

            # Apply overrides for set_value
            if choice == 'set_value' and value:
                clean_row.update(value)

            # Commit the row
            group = session.group
            member_map = _build_member_map(group)
            committer = RowCommitter(group, session, member_map)

            # Reconstruct anomaly list for commit_row
            from apps.importer.anomaly_detector import AnomalyResult
            anomaly_results = []
            if anomaly.suggested_fix and anomaly.suggested_fix.get('import_as') == 'settlement':
                anomaly_results.append(AnomalyResult(
                    anomaly_type=anomaly.anomaly_type,
                    description=anomaly.description,
                    action=anomaly.action_taken,
                    requires_user_approval=False,
                    suggested_fix=anomaly.suggested_fix,
                ))

            commit_result = committer.commit_row(
                clean_row, anomaly.row_number, anomaly_results,
            )

            anomaly.resolved = True
            anomaly.resolution_choice = choice
            anomaly.resolution_value = {
                'overrides': value,
                'commit_result': commit_result,
            }
            anomaly.action_taken = 'USER_RESOLVED'
            anomaly.resolved_by = request.user
            anomaly.resolved_at = timezone.now()
            anomaly.save()

        # Also resolve other anomalies for the same row (same row_number)
        sibling_anomalies = ImportAnomaly.objects.filter(
            session=session,
            row_number=anomaly.row_number,
            resolved=False,
        ).exclude(pk=anomaly.pk)

        for sibling in sibling_anomalies:
            sibling.resolved = True
            sibling.resolution_choice = f'resolved_via_anomaly_{anomaly.pk}'
            sibling.action_taken = 'USER_RESOLVED'
            sibling.resolved_by = request.user
            sibling.resolved_at = timezone.now()
            sibling.save()

        # Check if all anomalies are now resolved → update session status
        unresolved = session.anomalies.filter(
            resolved=False,
            requires_user_approval=True,
        ).count()

        if unresolved == 0:
            session.status = 'complete'
            session.pending_review_count = 0
            session.save()

        return Response({
            'anomaly': ImportAnomalySerializer(anomaly).data,
            'session_status': session.status,
            'unresolved_count': unresolved,
        })


# ======================================================================
# GET /api/import/{session_id}/report/
# ======================================================================

class ImportReportView(APIView):
    """
    Return complete import report as JSON.

    Includes: session metadata, all anomalies with resolutions,
    all imported expenses.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        session = get_object_or_404(ImportSession, pk=session_id)

        # All anomalies (resolved and unresolved)
        all_anomalies = ImportAnomalySerializer(
            session.anomalies.all(), many=True,
        ).data

        # All expenses imported in this session
        expenses = Expense.objects.filter(
            import_session=session,
        ).select_related('paid_by').prefetch_related('splits__user')

        expense_list = []
        for exp in expenses:
            expense_list.append({
                'id': exp.id,
                'row_number': exp.import_row_ref,
                'description': exp.description,
                'expense_date': str(exp.expense_date),
                'paid_by': exp.paid_by.name if exp.paid_by else None,
                'total_amount': float(exp.total_amount),
                'currency': exp.currency,
                'amount_inr': float(exp.amount_inr),
                'split_type': exp.split_type,
                'is_refund': exp.is_refund,
                'is_settlement': exp.is_settlement,
                'splits': [
                    {
                        'user': s.user.name,
                        'amount_owed': float(s.amount_owed),
                    }
                    for s in exp.splits.all()
                ],
            })

        # Settlements imported in this session
        from apps.expenses.models import Settlement
        settlements = Settlement.objects.filter(
            import_row_ref__isnull=False,
            group=session.group,
        ).select_related('paid_by', 'paid_to')

        settlement_list = []
        for s in settlements:
            if hasattr(s, 'import_row_ref') and s.import_row_ref:
                settlement_list.append({
                    'id': s.id,
                    'row_number': s.import_row_ref,
                    'paid_by': s.paid_by.name,
                    'paid_to': s.paid_to.name,
                    'amount': float(s.amount),
                    'amount_inr': float(s.amount_inr),
                    'currency': s.currency,
                })

        report = {
            'session': ImportSessionSummarySerializer(session).data,
            'anomalies': {
                'total': len(all_anomalies),
                'resolved': sum(1 for a in all_anomalies if a.get('resolved')),
                'unresolved': sum(
                    1 for a in all_anomalies if not a.get('resolved')
                ),
                'items': all_anomalies,
            },
            'imported_expenses': {
                'total': len(expense_list),
                'items': expense_list,
            },
            'imported_settlements': {
                'total': len(settlement_list),
                'items': settlement_list,
            },
        }

        return Response(report)
