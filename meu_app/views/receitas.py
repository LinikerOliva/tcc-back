from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from ..models import Receita
from ..serializers import ReceitaSerializer

class ReceitaViewSet(viewsets.ModelViewSet):
    queryset = Receita.objects.select_related('consulta', 'paciente', 'medico').prefetch_related('itens').all()
    serializer_class = ReceitaSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['consulta', 'paciente', 'medico']
    search_fields = ['observacoes', 'diagnostico'] if hasattr(Receita, 'diagnostico') else ['observacoes']
    ordering_fields = ['created_at'] if hasattr(Receita, 'created_at') else ['id']

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if hasattr(user, 'paciente'):
            qs = qs.filter(paciente=user.paciente)
        elif hasattr(user, 'medico'):
            qs = qs.filter(medico=user.medico)
        consulta_id = self.request.query_params.get('consulta_id')
        paciente_id = self.request.query_params.get('paciente_id')
        medico_id = self.request.query_params.get('medico_id')
        if consulta_id:
            qs = qs.filter(consulta_id=consulta_id)
        if paciente_id:
            qs = qs.filter(paciente_id=paciente_id)
        if medico_id:
            qs = qs.filter(medico_id=medico_id)
        return qs