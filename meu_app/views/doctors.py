from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from ..models import Medico, MedicoPaciente, Consulta
from ..serializers import MedicoSerializer, PacienteSerializer, ConsultaSerializer
from rest_framework import permissions
from ..models import Medico, Secretaria

class IsMedicoOrSecretaria(permissions.BasePermission):
    def has_permission(self, request, view):
        role = getattr(request.user, 'role', None)
        return role in ('medico', 'admin', 'secretaria')

    def has_object_permission(self, request, view, obj):
        role = getattr(request.user, 'role', None)
        if role in ('medico', 'admin'):
            return True
        if role == 'secretaria':
            try:
                secretaria = Secretaria.objects.get(user=request.user)
            except Secretaria.DoesNotExist:
                return False
            return obj in secretaria.medicos.all()
        return False

class MedicoViewSet(viewsets.ModelViewSet):
    queryset = Medico.objects.select_related('user').prefetch_related('especialidades', 'clinicas').all()
    serializer_class = MedicoSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['clinicas', 'especialidades', 'ativo', 'user', 'user__id']
    search_fields = ['user__first_name', 'user__last_name', 'crm', 'user__cpf', 'user__username']
    ordering_fields = ['experiencia_anos', 'user__first_name', 'user__last_name']

    @action(detail=False, methods=['get', 'patch'])
    def me(self, request):
        """
        GET: retorna o médico do usuário autenticado (404 se não existir)
        PATCH: atualização parcial do médico do usuário autenticado (404 se não existir)
        """
        medico = Medico.objects.select_related('user').prefetch_related('especialidades', 'clinicas').filter(user=request.user).first()

        if request.method.lower() == 'get':
            if not medico:
                return Response({'detail': 'Médico não encontrado para o usuário autenticado.'}, status=status.HTTP_404_NOT_FOUND)
            serializer = self.get_serializer(medico)
            return Response(serializer.data)

        # PATCH
        if not medico:
            return Response({'detail': 'Médico não encontrado para o usuário autenticado.'}, status=status.HTTP_404_NOT_FOUND)

        allowed_fields = {
            'crm',
            'biografia',
            'formacao',
            'experiencia_anos',
            'valor_consulta',
            'ativo',
            'especialidades',
            'clinicas',
        }
        data_clean = {k: v for k, v in request.data.items() if k in allowed_fields}
        serializer = self.get_serializer(medico, data=data_clean, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def pacientes(self, request, pk=None):
        """Lista pacientes vinculados ao médico"""
        medico = self.get_object()
        vinculos = MedicoPaciente.objects.filter(medico=medico, ativo=True).select_related('paciente__user')
        pacientes = [v.paciente for v in vinculos]
        serializer = PacienteSerializer(pacientes, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def consultas_hoje(self, request, pk=None):
        """Lista consultas do médico para hoje"""
        medico = self.get_object()
        from datetime import date
        hoje = date.today()
        consultas = (
            Consulta.objects.select_related('medico__user', 'paciente__user')
            .filter(medico=medico, data_hora__date=hoje)
            .order_by('data_hora')
        )
        serializer = ConsultaSerializer(consultas, many=True)
        return Response(serializer.data)

    def get_permissions(self):
        if self.action in ('me', 'pacientes', 'consultas_hoje'):
            return [IsMedicoOrSecretaria()]
        return super().get_permissions()

    @action(detail=False, methods=['get'])
    def me(self, request):
        # permite secretária selecionar médico via query param ?medico_id=...
        from ..serializers import MedicoSerializer
        role = getattr(request.user, 'role', None)
        medico = None
        if role == 'medico':
            medico = Medico.objects.filter(user=request.user).first()
        elif role == 'secretaria':
            medico_id = request.query_params.get('medico') or request.query_params.get('medico_id')
            if medico_id:
                try:
                    cand = Medico.objects.get(pk=medico_id)
                except Medico.DoesNotExist:
                    cand = None
                if cand:
                    try:
                        sec = request.user.secretaria
                        if cand in sec.medicos.all():
                            medico = cand
                    except Exception:
                        medico = None
        if not medico:
            return Response({'detail': 'Médico não encontrado'}, status=404)
        return Response(MedicoSerializer(medico).data)

    @action(detail=False, methods=['get'])
    def consultas_hoje(self, request):
        # similar: secretária precisa passar medico_id de um médico vinculado
        from django.utils import timezone
        from ..serializers import ConsultaListSerializer
        role = getattr(request.user, 'role', None)
        if role == 'medico':
            medico = Medico.objects.filter(user=request.user).first()
        elif role == 'secretaria':
            medico_id = request.query_params.get('medico') or request.query_params.get('medico_id')
            medico = None
            if medico_id:
                try:
                    cand = Medico.objects.get(pk=medico_id)
                except Medico.DoesNotExist:
                    cand = None
                if cand and cand in request.user.secretaria.medicos.all():
                    medico = cand
        else:
            medico = None
        if not medico:
            return Response({'detail': 'Médico não encontrado'}, status=404)
        hoje = timezone.localdate()
        consultas = medico.consultas.filter(data_hora__date=hoje).order_by('data_hora')
        return Response(ConsultaListSerializer(consultas, many=True).data)