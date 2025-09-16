from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from django.utils import timezone
from ..models import Medico, Especialidade, SolicitacaoMedico
from ..serializers import SolicitacaoMedicoSerializer

class SolicitacaoMedicoViewSet(viewsets.ModelViewSet):
    queryset = Medico.objects.select_related('user').prefetch_related('especialidades', 'clinicas').all()
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]

    def get_queryset(self):
        qs = self.queryset
        request = self.request
        params = request.query_params

        # Filtros compatíveis
        clinica = params.get('clinica')
        if clinica:
            qs = qs.filter(clinicas__id=clinica)

        especialidade = params.get('especialidade')
        if especialidade:
            qs = qs.filter(especialidades__id=especialidade)

        status_param = (params.get('status') or '').strip().lower()
        if status_param:
            map_status = {
                'pending': 'pendente',
                'approved': 'aprovado',
                'rejected': 'reprovado',
                'rejeitado': 'reprovado',
            }
            qs = qs.filter(status=map_status.get(status_param, status_param))

        # Busca por nome/email se fornecido
        search = params.get('search')
        if search:
            s = search.strip()
            qs = qs.filter(Q(user__first_name__icontains=s) | Q(user__last_name__icontains=s) | Q(user__email__icontains=s))

        # Ordenação: usar data de criação do usuário padrão do Django
        return qs.order_by('-user__date_joined')

    def list(self, request, *args, **kwargs):
        items = [self._serialize_medico(m) for m in self.get_queryset()]
        return Response(items)

    def retrieve(self, request, pk=None, *args, **kwargs):
        try:
            obj = self.get_queryset().get(pk=pk)
        except Medico.DoesNotExist:
            return Response({'detail': 'Não encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(self._serialize_medico(obj))

    def create(self, request, *args, **kwargs):
        user = request.user
        crm = request.data.get('crm')
        if not crm:
            return Response({'crm': ['CRM é obrigatório.']}, status=status.HTTP_400_BAD_REQUEST)

        medico, created = Medico.objects.get_or_create(user=user, defaults={'crm': crm, 'status': 'pendente'})
        if not created:
            if medico.crm != crm:
                medico.crm = crm
            medico.status = 'pendente'
            medico.save(update_fields=['crm', 'status'])

        # Especialidades opcionais
        espec_ids = []
        if 'especialidades' in request.data:
            try:
                espec_ids = [e for e in request.data.getlist('especialidades') if e]
            except Exception:
                raw = request.data.get('especialidades')
                if isinstance(raw, (list, tuple)):
                    espec_ids = [x for x in raw if x]
        elif request.data.get('especialidade'):
            espec_ids = [request.data.get('especialidade')]
        if espec_ids:
            try:
                qs = Especialidade.objects.filter(id__in=espec_ids)
                medico.especialidades.set(qs)
            except Exception:
                pass

        return Response(self._serialize_medico(medico), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def _serialize_medico(self, obj: Medico):
        # status: converter "reprovado" -> "rejeitado" para compatibilidade do front
        status_out = 'rejeitado' if (obj.status or '').lower() == 'reprovado' else (obj.status or '')
        return {
            'id': str(obj.pk),
            'tipo': 'medico',
            'nome': obj.user.get_full_name() or obj.user.username,
            'email': obj.user.email,
            'crm': obj.crm,
            'status': status_out,
            'dataEnvio': getattr(obj.user, 'date_joined', None),
        }

# Novo ViewSet baseado no modelo SolicitacaoMedico para persistência real na tabela solicitacaomedico
class SolicitacaoMedicoModelViewSet(viewsets.ModelViewSet):
    queryset = SolicitacaoMedico.objects.select_related('user').all()
    serializer_class = SolicitacaoMedicoSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]

    def get_queryset(self):
        qs = self.queryset
        params = self.request.query_params

        status_param = (params.get('status') or '').strip().lower()
        if status_param:
            qs = qs.filter(status=status_param)

        search = params.get('search')
        if search:
            s = search.strip()
            qs = qs.filter(
                Q(user__first_name__icontains=s) |
                Q(user__last_name__icontains=s) |
                Q(user__email__icontains=s) |
                Q(crm__icontains=s)
            )

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        # garante associação ao usuário autenticado; o serializer já define status='pending'
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None, *args, **kwargs):
        try:
            obj = self.get_queryset().get(pk=pk)
        except SolicitacaoMedico.DoesNotExist:
            return Response({'detail': 'Não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        obj.status = 'approved'
        obj.approved_by = request.user
        obj.approved_at = timezone.now()
        # limpar rejeição anterior, se houver
        obj.rejected_by = None
        obj.rejected_at = None
        obj.rejection_reason = ''
        obj.save(update_fields=['status', 'approved_by', 'approved_at', 'rejected_by', 'rejected_at', 'rejection_reason'])

        data = self.get_serializer(obj).data
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None, *args, **kwargs):
        try:
            obj = self.get_queryset().get(pk=pk)
        except SolicitacaoMedico.DoesNotExist:
            return Response({'detail': 'Não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        motivo = request.data.get('motivo') or request.data.get('reason') or ''

        obj.status = 'rejected'
        obj.rejected_by = request.user
        obj.rejected_at = timezone.now()
        obj.rejection_reason = motivo
        # limpar aprovação anterior, se houver
        obj.approved_by = None
        obj.approved_at = None
        obj.save(update_fields=['status', 'rejected_by', 'rejected_at', 'rejection_reason', 'approved_by', 'approved_at'])

        data = self.get_serializer(obj).data
        return Response(data, status=status.HTTP_200_OK)