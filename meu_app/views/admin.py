from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from ..models import Medico


def _serialize_medico(obj: Medico):
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


@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def admin_dashboard(request):
    counts = {
        'solicitacoes_pendentes': Medico.objects.filter(status='pendente').count(),
        'solicitacoes_aprovadas': Medico.objects.filter(status='aprovado').count(),
        'solicitacoes_rejeitadas': Medico.objects.filter(status='reprovado').count(),
    }
    return Response(counts)


@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def admin_solicitacoes_list(request):
    qs = Medico.objects.select_related('user').all().order_by('-user__date_joined')
    items = [_serialize_medico(m) for m in qs]
    return Response(items)


@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def admin_solicitacao_detail(request, pk):
    obj = get_object_or_404(Medico.objects.select_related('user'), pk=pk)
    return Response(_serialize_medico(obj))


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def admin_solicitacao_aprovar(request, pk):
    obj = get_object_or_404(Medico, pk=pk)
    obj.status = 'aprovado'
    obj.save(update_fields=['status'])
    return Response({'detail': 'Solicitação aprovada.'}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def admin_solicitacao_rejeitar(request, pk):
    obj = get_object_or_404(Medico, pk=pk)
    obj.status = 'reprovado'
    obj.save(update_fields=['status'])
    return Response({'detail': 'Solicitação rejeitada.'}, status=status.HTTP_200_OK)