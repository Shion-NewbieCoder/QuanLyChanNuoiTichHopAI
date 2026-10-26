from rest_framework import filters, viewsets
from rest_framework.permissions import IsAuthenticated
from apps.users.permissions import RoleActionPermission
from config.filters import ExactFieldFilterBackend

from .models import CareLog, CareSchedule, FeedRecord, MedicineRecord
from .serializers import CareLogSerializer, CareScheduleSerializer, FeedRecordSerializer, MedicineRecordSerializer


class CareScheduleViewSet(viewsets.ModelViewSet):
    queryset = CareSchedule.objects.all()
    serializer_class = CareScheduleSerializer
    permission_classes = [IsAuthenticated, RoleActionPermission]
    permission_resource = "care"
    filter_backends = [filters.SearchFilter, ExactFieldFilterBackend, filters.OrderingFilter]
    search_fields = ["activity"]
    exact_filter_fields = ["herd", "status"]
    ordering_fields = ["scheduled_date", "activity"]


class CareLogViewSet(viewsets.ModelViewSet):
    queryset = CareLog.objects.all()
    serializer_class = CareLogSerializer
    permission_classes = [IsAuthenticated, RoleActionPermission]
    permission_resource = "care"
    filter_backends = [filters.SearchFilter, ExactFieldFilterBackend, filters.OrderingFilter]
    search_fields = ["activity", "notes"]
    exact_filter_fields = ["herd"]
    ordering_fields = ["recorded_at"]


class FeedRecordViewSet(viewsets.ModelViewSet):
    queryset = FeedRecord.objects.all()
    serializer_class = FeedRecordSerializer
    permission_classes = [IsAuthenticated, RoleActionPermission]
    permission_resource = "care"
    filter_backends = [filters.SearchFilter, ExactFieldFilterBackend, filters.OrderingFilter]
    search_fields = ["feed_type", "notes"]
    exact_filter_fields = ["herd"]
    ordering_fields = ["recorded_at", "quantity"]


class MedicineRecordViewSet(viewsets.ModelViewSet):
    queryset = MedicineRecord.objects.all()
    serializer_class = MedicineRecordSerializer
    permission_classes = [IsAuthenticated, RoleActionPermission]
    permission_resource = "care"
    filter_backends = [filters.SearchFilter, ExactFieldFilterBackend, filters.OrderingFilter]
    search_fields = ["medicine", "notes"]
    exact_filter_fields = ["herd"]
    ordering_fields = ["recorded_at", "dose"]
