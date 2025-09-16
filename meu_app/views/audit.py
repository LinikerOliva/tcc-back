from rest_framework import viewsets, permissions, filters, mixins
from django_filters.rest_framework import DjangoFilterBackend
from ..models import AuditLog
from ..serializers import AuditLogSerializer

class AuditLogViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related('user').all()
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['user', 'action', 'entity', 'entity_id', 'status', 'ip_address']
    search_fields = ['action', 'entity', 'metadata', 'ip_address', 'user_agent']
    ordering_fields = ['created_at', 'action']
    http_method_names = ['get', 'post', 'head', 'options']
