from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from ..models import SolicitacaoMedico
from ..serializers import SolicitacaoMedicoSerializer

class SolicitacaoMedicoViewSet(viewsets.ModelViewSet):
    queryset = SolicitacaoMedico.objects.select_related('user', 'clinica', 'especialidade').all()
    serializer_class = SolicitacaoMedicoSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['clinica', 'especialidade', 'status']
    search_fields = ['user__first_name', 'user__last_name', 'user__email']
    ordering_fields = ['created_at', 'status']