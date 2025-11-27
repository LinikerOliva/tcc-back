from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from ..models import Paciente, MedicoPaciente, Consulta, Receita
from ..serializers import PacienteSerializer, MedicoSerializer, ConsultaListSerializer, ReceitaSerializer

class PacienteViewSet(viewsets.ModelViewSet):
    queryset = Paciente.objects.select_related('user').all()
    serializer_class = PacienteSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['user__first_name', 'user__last_name', 'user__cpf', 'user__username', 'alergias', 'condicoes_cronicas']
    ordering_fields = ['user__first_name', 'user__last_name', 'user__date_joined']
    filterset_fields = ['user__is_active', 'tipo_sanguineo', 'user', 'user__id', 'user__username', 'user__cpf']

    @action(detail=False, methods=['get', 'patch'])
    def me(self, request):
        """
        GET: retorna o paciente do usuário autenticado (cria se não existe)
        PATCH: atualiza parcialmente o paciente do usuário; cria se não existir
        """
        paciente = Paciente.objects.select_related('user').filter(user=request.user).first()

        if request.method.lower() == 'get':
            if not paciente:
                paciente = Paciente.objects.create(user=request.user)
            serializer = self.get_serializer(paciente)
            return Response(serializer.data)

        # PATCH
        allowed_fields = {
            'tipo_sanguineo', 'peso', 'altura', 'alergias', 'condicoes_cronicas',
            'medicamentos_uso', 'contato_emergencia_nome', 'contato_emergencia_telefone',
            'plano_saude', 'numero_carteirinha'
        }
        data_clean = {k: v for k, v in request.data.items() if k in allowed_fields}

        if not paciente:
            serializer = self.get_serializer(data=data_clean, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        serializer = self.get_serializer(paciente, data=data_clean, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def medicos(self, request, pk=None):
        """Lista médicos vinculados ao paciente"""
        paciente = self.get_object()
        vinculos = (
            MedicoPaciente.objects.filter(paciente=paciente, ativo=True)
            .select_related('medico__user')
            .prefetch_related('medico__especialidades')
        )
        medicos = [v.medico for v in vinculos]
        serializer = MedicoSerializer(medicos, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def proximas_consultas(self, request, pk=None):
        """Lista próximas consultas do paciente"""
        paciente = self.get_object()
        from datetime import datetime
        agora = datetime.now()
        consultas = (
            Consulta.objects.select_related('medico__user', 'paciente__user')
            .filter(paciente=paciente, data_hora__gte=agora, status__in=['agendada', 'confirmada'])
            .order_by('data_hora')[:5]
        )
        serializer = ConsultaListSerializer(consultas, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def receitas(self, request, pk=None):
        """Lista receitas do paciente (com itens)"""
        paciente = self.get_object()
        qs = (
            Receita.objects
            .select_related('consulta', 'consulta__paciente', 'consulta__medico')
            .prefetch_related('itens')
            .filter(consulta__paciente=paciente)
            .order_by('-created_at')
        )
        serializer = ReceitaSerializer(qs, many=True)
        return Response(serializer.data)
