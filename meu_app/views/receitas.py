from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from ..models import Receita, Paciente, Medico
from ..serializers import ReceitaSerializer

class ReceitaViewSet(viewsets.ModelViewSet):
    # Ajuste: seguir relações existentes (consulta -> paciente/medico)
    queryset = (
        Receita.objects
        .select_related('consulta', 'consulta__paciente', 'consulta__medico')
        .prefetch_related('itens')
        .all()
    )
    serializer_class = ReceitaSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    # Permitir filtrar atravessando as relações corretamente
    filterset_fields = ['consulta', 'consulta__paciente', 'consulta__medico']
    search_fields = ['observacoes', 'diagnostico'] if hasattr(Receita, 'diagnostico') else ['observacoes']
    ordering_fields = ['created_at'] if hasattr(Receita, 'created_at') else ['id']

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        # Escopo por papel do usuário (compatível com padrão existente)
        if hasattr(user, 'paciente') and user.paciente:
            qs = qs.filter(consulta__paciente=user.paciente)
        elif hasattr(user, 'medico') and user.medico:
            qs = qs.filter(consulta__medico=user.medico)
        else:
            # admin/clinica/secretaria: manter qs amplo; se houver regra, aplicar aqui
            pass

        # Filtros adicionais por query string (aceita múltiplos nomes comuns)
        qp = self.request.query_params
        consulta_id = qp.get('consulta') or qp.get('consulta_id')
        paciente_id = qp.get('paciente') or qp.get('paciente_id') or qp.get('consulta__paciente')
        medico_id = qp.get('medico') or qp.get('medico_id') or qp.get('consulta__medico')

        if consulta_id:
            qs = qs.filter(consulta_id=consulta_id)
        if paciente_id:
            qs = qs.filter(consulta__paciente_id=paciente_id)
        if medico_id:
            qs = qs.filter(consulta__medico_id=medico_id)
        
        return qs