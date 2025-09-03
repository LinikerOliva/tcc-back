from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from ..models import Agendamento, Medico
from ..serializers import AgendamentoSerializer

class AgendamentoViewSet(viewsets.ModelViewSet):
    queryset = Agendamento.objects.select_related('medico__user').all()
    serializer_class = AgendamentoSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['medico', 'disponivel']
    search_fields = ['medico__user__first_name', 'medico__user__last_name', 'observacoes']
    ordering_fields = ['data_hora_inicio', 'data_hora_fim', 'created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        role = getattr(user, 'role', None)
        if role == 'medico':
            medico = Medico.objects.filter(user=user).first()
            if not medico:
                return Agendamento.objects.none()
            qs = qs.filter(medico=medico)
        return qs