from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from ..models import Prontuario
from ..serializers import ProntuarioSerializer, ProntuarioListSerializer

class ProntuarioViewSet(viewsets.ModelViewSet):
    queryset = Prontuario.objects.select_related('consulta__paciente__user', 'consulta__medico__user').all()
    serializer_class = ProntuarioSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['consulta__paciente', 'consulta__medico']
    search_fields = [
        'diagnostico_principal', 'cid10', 'conduta',
        'consulta__paciente__user__first_name', 'consulta__paciente__user__last_name'
    ]
    ordering_fields = ['created_at', 'updated_at']
    # Define uma ordenação padrão para evitar UnorderedObjectListWarning em paginação
    ordering = ['-created_at', '-id']

    def get_serializer_class(self):
        if self.action == 'list':
            return ProntuarioListSerializer
        return ProntuarioSerializer