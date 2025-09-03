from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from ..models import Clinica, Paciente, Exame, Agendamento, Consulta, TipoExame, Medico
from ..serializers import ClinicaSerializer, PacienteSerializer, AgendamentoSerializer, TipoExameSerializer, PacienteBriefSerializer
from rest_framework.decorators import action
from rest_framework import permissions
from ..models import Clinica, Secretaria, Medico, Paciente
from ..serializers import MedicoBriefSerializer, PacienteBriefSerializer

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def clinica_tipos_exame(request):
    # Lista tipos de exame ativos com filtros opcionais por categoria e busca
    qs = TipoExame.objects.filter(ativo=True)
    categoria = request.query_params.get('categoria')
    termo = request.query_params.get('q') or request.query_params.get('search')
    if categoria:
        qs = qs.filter(categoria=categoria)
    if termo:
        qs = qs.filter(Q(nome__icontains=termo) | Q(descricao__icontains=termo))
    serializer = TipoExameSerializer(qs, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def clinica_pacientes(request):
    # Lista pacientes relacionados à clínica do usuário (role=clinica) ou de uma clínica informada (admin)
    user = request.user
    clinica = None
    if getattr(user, 'role', None) == 'clinica' and getattr(user, 'clinica', None):
        clinica = user.clinica
    elif getattr(user, 'role', None) == 'admin':
        clinica_id = request.query_params.get('clinica_id')
        if clinica_id:
            clinica = Clinica.objects.filter(id=clinica_id).first()
    if not clinica:
        return Response({'detail': 'Clínica não definida para o usuário.'}, status=status.HTTP_403_FORBIDDEN)

    paciente_ids = set()
    paciente_ids.update(Consulta.objects.filter(clinica=clinica).values_list('paciente_id', flat=True))
    paciente_ids.update(Exame.objects.filter(clinica_realizacao=clinica).values_list('paciente_id', flat=True))

    pacientes = (
        Paciente.objects.select_related('user').filter(user__id__in=paciente_ids)
        if paciente_ids else Paciente.objects.none()
    )
    serializer = PacienteBriefSerializer(pacientes, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def clinica_calendario(request):
    # Retorna agendamentos dos médicos vinculados à clínica do usuário, suportando filtros start/end
    user = request.user
    clinica = None
    if getattr(user, 'role', None) == 'clinica' and getattr(user, 'clinica', None):
        clinica = user.clinica
    elif getattr(user, 'role', None) == 'admin':
        clinica_id = request.query_params.get('clinica_id')
        if clinica_id:
            clinica = Clinica.objects.filter(id=clinica_id).first()
    if not clinica:
        return Response({'detail': 'Clínica não definida para o usuário.'}, status=status.HTTP_403_FORBIDDEN)

    qs = Agendamento.objects.select_related('medico__user').filter(medico__clinicas=clinica)
    start = request.query_params.get('start')
    end = request.query_params.get('end')
    if start:
        dt_start = parse_datetime(start)
        if dt_start:
            qs = qs.filter(data_hora_fim__gte=dt_start)
    if end:
        dt_end = parse_datetime(end)
        if dt_end:
            qs = qs.filter(data_hora_inicio__lte=dt_end)
    serializer = AgendamentoSerializer(qs, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)

class ClinicaViewSet(viewsets.ModelViewSet):
    queryset = Clinica.objects.all()
    serializer_class = ClinicaSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['nome']
    search_fields = ['nome', 'endereco']
    ordering_fields = ['nome']

    @action(detail=False, methods=['get'])
    def me(self, request):
        clinica_id = getattr(getattr(request.user, 'clinica', None), 'id', None)
        if not clinica_id:
            return Response({'detail': 'Usuário não associado a uma clínica.'}, status=404)
        obj = get_object_or_404(Clinica, id=clinica_id)
        serializer = self.get_serializer(obj)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def usuarios(self, request, pk=None):
        clinica = self.get_object()
        pacientes = Paciente.objects.filter(clinica=clinica)
        serializer = PacienteSerializer(pacientes, many=True)
        return Response({'pacientes': serializer.data})

    @action(detail=True, methods=['get'])
    def dashboard(self, request, pk=None):
        clinica = self.get_object()
        dados = {
            'agendamentos': Agendamento.objects.filter(medico__clinicas=clinica).count(),
            'pacientes': Paciente.objects.filter(clinica=clinica).count(),
        }
        return Response(dados)

    # === Novo: Grupo de Médicos da Clínica ===
    def _can_manage_clinic(self, request, clinica: Clinica) -> bool:
        # Admin pode tudo; usuário com role=clinica só pode gerenciar a própria clínica
        if getattr(request.user, 'role', None) == 'admin':
            return True
        if getattr(request.user, 'role', None) == 'clinica' and getattr(request.user, 'clinica_id', None):
            return request.user.clinica_id == str(clinica.id)
        return False

    @action(detail=True, methods=['get'], url_path='medicos')
    def listar_medicos(self, request, pk=None):
        clinica = self.get_object()
        from ..serializers import MedicoBriefSerializer  # import local para evitar ciclo
        medicos_qs = Medico.objects.select_related('user').filter(clinicas=clinica)
        serializer = MedicoBriefSerializer(medicos_qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='medicos/adicionar')
    def adicionar_medico(self, request, pk=None):
        clinica = self.get_object()
        if not self._can_manage_clinic(request, clinica):
            return Response({'detail': 'Sem permissão para gerenciar esta clínica.'}, status=status.HTTP_403_FORBIDDEN)

        medico_id = request.data.get('medico_id')
        if not medico_id:
            return Response({'detail': 'Campo "medico_id" é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            medico = Medico.objects.get(pk=medico_id)
        except Medico.DoesNotExist:
            return Response({'detail': 'Médico não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        if clinica in medico.clinicas.all():
            return Response({'detail': 'Médico já está vinculado à clínica.'}, status=status.HTTP_200_OK)
        medico.clinicas.add(clinica)
        return Response({'detail': 'Médico adicionado à clínica com sucesso.'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='medicos/remover')
    def remover_medico(self, request, pk=None):
        clinica = self.get_object()
        if not self._can_manage_clinic(request, clinica):
            return Response({'detail': 'Sem permissão para gerenciar esta clínica.'}, status=status.HTTP_403_FORBIDDEN)

        medico_id = request.data.get('medico_id')
        if not medico_id:
            return Response({'detail': 'Campo "medico_id" é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            medico = Medico.objects.get(pk=medico_id)
        except Medico.DoesNotExist:
            return Response({'detail': 'Médico não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        if clinica not in medico.clinicas.all():
            return Response({'detail': 'Médico não está vinculado a esta clínica.'}, status=status.HTTP_400_BAD_REQUEST)
        medico.clinicas.remove(clinica)
        return Response({'detail': 'Médico removido da clínica com sucesso.'}, status=status.HTTP_200_OK)


class IsClinicaOrSecretaria(permissions.BasePermission):
    def has_permission(self, request, view):
        role = getattr(request.user, 'role', None)
        return role in ('clinica', 'admin', 'secretaria')

# Dentro de ClinicaViewSet existente adicionar ações, mantendo compatibilidade
try:
    from .clinics import ClinicaViewSet  # self-import guard
except Exception:
    ClinicaViewSet = None

if ClinicaViewSet:
    if not hasattr(ClinicaViewSet, 'medicos_secretaria'):
        @action(detail=False, methods=['get'], permission_classes=[IsClinicaOrSecretaria])
        def medicos_secretaria(self, request):
            role = getattr(request.user, 'role', None)
            medicos = Medico.objects.none()
            if role == 'clinica':
                try:
                    clinica = request.user.clinica
                except Exception:
                    clinica = None
                if clinica:
                    medicos = clinica.medicos.all()
            elif role == 'secretaria':
                try:
                    sec = request.user.secretaria
                    medicos = sec.medicos.all()
                except Exception:
                    medicos = Medico.objects.none()
            return Response(MedicoBriefSerializer(medicos, many=True).data)

        ClinicaViewSet.medicos_secretaria = medicos_secretaria