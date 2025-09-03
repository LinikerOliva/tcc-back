from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from django.shortcuts import render
from ..models import Consulta, Medico, Paciente, MedicoPaciente
from ..serializers import ConsultaSerializer, ConsultaListSerializer, ConsultaCreateSerializer

class ConsultaViewSet(viewsets.ModelViewSet):
    queryset = Consulta.objects.select_related('medico__user', 'paciente__user').all()
    serializer_class = ConsultaSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['medico', 'paciente', 'status', 'tipo', 'clinica']
    search_fields = [
        'motivo', 'observacoes',
        'paciente__user__first_name', 'paciente__user__last_name',
        'medico__user__first_name', 'medico__user__last_name'
    ]
    ordering_fields = ['data_hora', 'status', 'tipo', 'created_at']

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        role = getattr(user, 'role', None)
        if role == 'paciente':
            paciente = Paciente.objects.filter(user=user).first()
            if not paciente:
                return Consulta.objects.none()
            queryset = queryset.filter(paciente=paciente)
        elif role == 'medico':
            medico = Medico.objects.filter(user=user).first()
            if not medico:
                return Consulta.objects.none()
            queryset = queryset.filter(medico=medico)
        elif role == 'secretaria':
            # secretária precisa informar o médico alvo e ter vínculo
            medico_id = self.request.query_params.get('medico') or self.request.query_params.get('medico_id')
            if not medico_id:
                return Consulta.objects.none()
            try:
                alvo = Medico.objects.get(pk=medico_id)
            except Medico.DoesNotExist:
                return Consulta.objects.none()
            try:
                sec = user.secretaria
            except Exception:
                return Consulta.objects.none()
            if alvo not in sec.medicos.all():
                return Consulta.objects.none()
            queryset = queryset.filter(medico=alvo)
        else:
            # admin ou outros: mantém queryset amplo
            pass

        # Filtros adicionais por querystring (aplicados dentro do escopo)
        qp = self.request.query_params
        medico_id = qp.get('medico') or qp.get('medico_id') or qp.get('medico__id')
        paciente_id = qp.get('paciente') or qp.get('paciente_id') or qp.get('paciente__id')
        status_param = qp.get('status')
        data_str = qp.get('data') or qp.get('date') or qp.get('dia') or qp.get('data__date')

        if medico_id and role != 'secretaria':
            queryset = queryset.filter(medico_id=medico_id)
        if paciente_id:
            queryset = queryset.filter(paciente_id=paciente_id)
        if status_param:
            s = status_param.lower()
            if s == 'realizada':
                s = 'concluida'
            queryset = queryset.filter(status=s)
        if data_str:
            queryset = queryset.filter(data_hora__date=data_str)

        return queryset.order_by('-data_hora')

    def get_serializer_class(self):
        if self.action == 'list':
            return ConsultaListSerializer
        if self.action in ('create', 'update', 'partial_update'):
            return ConsultaCreateSerializer
        return ConsultaSerializer

    def perform_create(self, serializer):
        """
        Ao criar uma consulta, garante que exista um vínculo ativo entre o médico e o paciente.
        """
        instance = serializer.save()
        MedicoPaciente.objects.get_or_create(
            medico=instance.medico,
            paciente=instance.paciente,
            defaults={'ativo': True}
        )

    @action(detail=True, methods=['post'])
    def iniciar(self, request, pk=None):
        """Inicia uma consulta"""
        consulta = self.get_object()
        consulta.status = 'em_andamento'
        consulta.save()
        return Response({'status': 'Consulta iniciada'})

    @action(detail=True, methods=['post'])
    def finalizar(self, request, pk=None):
        """Finaliza uma consulta"""
        consulta = self.get_object()
        consulta.status = 'concluida'
        consulta.save()
        return Response({'status': 'Consulta finalizada'})

# --- UI (HTML) ---

def consultas_page(request):
    """Renderiza a tela (UI) de Consultas para uso no navegador."""
    return render(request, 'consultas.html', {})