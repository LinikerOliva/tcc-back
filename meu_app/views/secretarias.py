from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from ..models import Secretaria, Medico, Clinica
from ..serializers import SecretariaSerializer, MedicoBriefSerializer, ClinicaSerializer


class IsAdminOrSecretaria(permissions.BasePermission):
    def has_permission(self, request, view):
        role = getattr(request.user, 'role', None)
        return role in ('secretaria', 'admin')


class SecretariaViewSet(viewsets.ModelViewSet):
    queryset = Secretaria.objects.select_related('user').prefetch_related('medicos', 'clinicas').all()
    serializer_class = SecretariaSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSecretaria]

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'role', None) == 'admin':
            return self.queryset
        # Secretaria só enxerga a si mesma
        return self.queryset.filter(user=user)

    @action(detail=False, methods=['get'])
    def me(self, request):
        user = request.user
        if getattr(user, 'role', None) not in ('secretaria', 'admin'):
            return Response({'detail': 'Sem permissão'}, status=status.HTTP_403_FORBIDDEN)
        if getattr(user, 'role', None) == 'secretaria':
            secretaria, _ = Secretaria.objects.get_or_create(user=user)
            data = self.get_serializer(secretaria).data
            return Response(data)
        # admin pode inspecionar via ?user_id=
        uid = request.query_params.get('user_id')
        if not uid:
            return Response({'detail': 'Informe user_id para admin.'}, status=status.HTTP_400_BAD_REQUEST)
        sec = get_object_or_404(Secretaria, user_id=uid)
        return Response(self.get_serializer(sec).data)

    # ===== Vínculos com Médicos =====
    @action(detail=False, methods=['get'], url_path='medicos')
    def listar_medicos(self, request):
        secretaria = getattr(request.user, 'secretaria', None)
        if not secretaria and getattr(request.user, 'role', None) == 'admin':
            sec_id = request.query_params.get('secretaria_id')
            secretaria = get_object_or_404(Secretaria, id=sec_id) if sec_id else None
        if not secretaria:
            return Response({'detail': 'Secretaria não encontrada para o usuário.'}, status=status.HTTP_404_NOT_FOUND)
        qs = secretaria.medicos.select_related('user').all()
        return Response(MedicoBriefSerializer(qs, many=True).data)

    @action(detail=False, methods=['post'], url_path='medicos/vincular')
    def vincular_medico(self, request):
        secretaria = getattr(request.user, 'secretaria', None)
        if not secretaria:
            return Response({'detail': 'Secretaria não encontrada para o usuário.'}, status=status.HTTP_404_NOT_FOUND)
        medico_id = request.data.get('medico_id')
        if not medico_id:
            return Response({'detail': 'Campo medico_id é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            medico = Medico.objects.get(pk=medico_id)
        except Medico.DoesNotExist:
            return Response({'detail': 'Médico não encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        secretaria.medicos.add(medico)
        return Response({'detail': 'Médico vinculado com sucesso.'})

    @action(detail=False, methods=['post'], url_path='medicos/remover')
    def remover_medico(self, request):
        secretaria = getattr(request.user, 'secretaria', None)
        if not secretaria:
            return Response({'detail': 'Secretaria não encontrada para o usuário.'}, status=status.HTTP_404_NOT_FOUND)
        medico_id = request.data.get('medico_id')
        if not medico_id:
            return Response({'detail': 'Campo medico_id é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            medico = Medico.objects.get(pk=medico_id)
        except Medico.DoesNotExist:
            return Response({'detail': 'Médico não encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        secretaria.medicos.remove(medico)
        return Response({'detail': 'Médico desvinculado com sucesso.'})

    # ===== Vínculos com Clínicas =====
    @action(detail=False, methods=['get'], url_path='clinicas')
    def listar_clinicas(self, request):
        secretaria = getattr(request.user, 'secretaria', None)
        if not secretaria and getattr(request.user, 'role', None) == 'admin':
            sec_id = request.query_params.get('secretaria_id')
            secretaria = get_object_or_404(Secretaria, id=sec_id) if sec_id else None
        if not secretaria:
            return Response({'detail': 'Secretaria não encontrada para o usuário.'}, status=status.HTTP_404_NOT_FOUND)
        qs = secretaria.clinicas.all()
        # reuso de ClinicaSerializer completo
        return Response(ClinicaSerializer(qs, many=True).data)

    @action(detail=False, methods=['post'], url_path='clinicas/vincular')
    def vincular_clinica(self, request):
        secretaria = getattr(request.user, 'secretaria', None)
        if not secretaria:
            return Response({'detail': 'Secretaria não encontrada para o usuário.'}, status=status.HTTP_404_NOT_FOUND)
        clinica_id = request.data.get('clinica_id')
        if not clinica_id:
            return Response({'detail': 'Campo clinica_id é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            clinica = Clinica.objects.get(pk=clinica_id)
        except Clinica.DoesNotExist:
            return Response({'detail': 'Clínica não encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        secretaria.clinicas.add(clinica)
        return Response({'detail': 'Clínica vinculada com sucesso.'})

    @action(detail=False, methods=['post'], url_path='clinicas/remover')
    def remover_clinica(self, request):
        secretaria = getattr(request.user, 'secretaria', None)
        if not secretaria:
            return Response({'detail': 'Secretaria não encontrada para o usuário.'}, status=status.HTTP_404_NOT_FOUND)
        clinica_id = request.data.get('clinica_id')
        if not clinica_id:
            return Response({'detail': 'Campo clinica_id é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            clinica = Clinica.objects.get(pk=clinica_id)
        except Clinica.DoesNotExist:
            return Response({'detail': 'Clínica não encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        secretaria.clinicas.remove(clinica)
        return Response({'detail': 'Clínica desvinculada com sucesso.'})