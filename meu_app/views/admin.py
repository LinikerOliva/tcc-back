from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from ..models import SolicitacaoMedico

@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def admin_dashboard(request):
    counts = {
        'solicitacoes_pendentes': SolicitacaoMedico.objects.filter(status='pendente').count(),
        'solicitacoes_aprovadas': SolicitacaoMedico.objects.filter(status='aprovada').count(),
        'solicitacoes_rejeitadas': SolicitacaoMedico.objects.filter(status='rejeitada').count(),
    }
    return Response(counts)

@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def admin_solicitacoes_list(request):
    from ..serializers import SolicitacaoMedicoSerializer
    qs = SolicitacaoMedico.objects.all().order_by('-created_at')
    serializer = SolicitacaoMedicoSerializer(qs, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def admin_solicitacao_detail(request, pk):
    from ..serializers import SolicitacaoMedicoSerializer
    obj = get_object_or_404(SolicitacaoMedico, pk=pk)
    serializer = SolicitacaoMedicoSerializer(obj)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def admin_solicitacao_aprovar(request, pk):
    obj = get_object_or_404(SolicitacaoMedico, pk=pk)
    obj.status = 'aprovada'
    obj.save(update_fields=['status'])
    return Response({'detail': 'Solicitação aprovada.'})

@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def admin_solicitacao_rejeitar(request, pk):
    obj = get_object_or_404(SolicitacaoMedico, pk=pk)
    obj.status = 'rejeitada'
    obj.save(update_fields=['status'])
    return Response({'detail': 'Solicitação rejeitada.'})