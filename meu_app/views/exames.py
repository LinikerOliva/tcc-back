from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from ..models import Exame
from ..serializers import ExameSerializer, ExameListSerializer

class ExameViewSet(viewsets.ModelViewSet):
    queryset = Exame.objects.select_related('paciente__user', 'medico_solicitante__user', 'tipo_exame').all()
    serializer_class = ExameSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['paciente', 'medico_solicitante', 'status', 'tipo_exame', 'clinica_realizacao']
    search_fields = ['observacoes', 'resultado', 'paciente__user__first_name', 'paciente__user__last_name']
    ordering_fields = ['data_solicitacao', 'status']

    def get_queryset(self):
        queryset = super().get_queryset()
        paciente_id = self.request.query_params.get('paciente', None)
        medico_id = self.request.query_params.get('medico', None)
        medico_solicitante_id = self.request.query_params.get('medico_solicitante', None)
        status_param = self.request.query_params.get('status', None)
        if paciente_id:
            queryset = queryset.filter(paciente_id=paciente_id)
        if medico_id or medico_solicitante_id:
            queryset = queryset.filter(medico_solicitante_id=medico_id or medico_solicitante_id)
        if status_param:
            queryset = queryset.filter(status=status_param.lower())
        return queryset.order_by('-data_solicitacao')

    def get_serializer_class(self):
        if self.action == 'list':
            return ExameListSerializer
        return ExameSerializer