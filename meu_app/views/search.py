from rest_framework import viewsets, permissions
from rest_framework.response import Response
from django.db.models import Q
from ..models import Paciente
from ..serializers import PacienteBriefSerializer

class BuscarPacientesViewSet(viewsets.ViewSet):
    """ViewSet para busca de pacientes"""
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        query = request.query_params.get('q', '')
        status_filter = request.query_params.get('status', 'todos')

        queryset = Paciente.objects.select_related('user').all()

        if query:
            queryset = queryset.filter(
                Q(user__first_name__icontains=query) |
                Q(user__last_name__icontains=query) |
                Q(user__cpf__icontains=query)
            )

        if status_filter == 'ativo':
            queryset = queryset.filter(user__is_active=True)
        elif status_filter == 'inativo':
            queryset = queryset.filter(user__is_active=False)

        serializer = PacienteBriefSerializer(queryset, many=True)
        return Response(serializer.data)