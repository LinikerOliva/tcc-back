from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from ..models import User
from ..serializers import UserSerializer

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['username', 'email', 'first_name', 'last_name', 'cpf']
    ordering_fields = ['date_joined', 'first_name', 'last_name', 'username']

    def _is_admin(self, user):
        return getattr(user, 'is_staff', False) or getattr(user, 'role', None) == 'admin'

    def list(self, request, *args, **kwargs):
        user = request.user
        if not self._is_admin(user):
            return Response({'detail': 'Permissão negada'}, status=status.HTTP_403_FORBIDDEN)
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=['patch'])
    def editar(self, request, pk=None):
        obj = self.get_object()
        requester = request.user
        if not (self._is_admin(requester) or str(obj.id) == str(requester.id)):
            return Response({'detail': 'Permissão negada'}, status=status.HTTP_403_FORBIDDEN)
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        obj = self.get_object()
        requester = request.user
        if not (self._is_admin(requester) or str(obj.id) == str(requester.id)):
            return Response({'detail': 'Permissão negada'}, status=status.HTTP_403_FORBIDDEN)
        partial = True
        serializer = self.get_serializer(obj, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def partial_update(self, request, *args, **kwargs):
        obj = self.get_object()
        requester = request.user
        if not (self._is_admin(requester) or str(obj.id) == str(requester.id)):
            return Response({'detail': 'Permissão negada'}, status=status.HTTP_403_FORBIDDEN)
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='remover-em-massa')
    def remover_em_massa(self, request):
        user = request.user
        if not self._is_admin(user):
            return Response({'detail': 'Permissão negada'}, status=status.HTTP_403_FORBIDDEN)
        ids = request.data.get('ids', [])
        if not isinstance(ids, list) or not ids:
            return Response({'detail': 'Informe uma lista "ids" com pelo menos um ID.'}, status=status.HTTP_400_BAD_REQUEST)
        ids_to_delete = [i for i in ids if str(i) != str(user.id)]
        skipped_self = len(ids) != len(ids_to_delete)
        qs = User.objects.filter(id__in=ids_to_delete)
        to_delete = list(qs.values_list('id', flat=True))
        deleted_count = qs.delete()[0] if to_delete else 0
        return Response({
            'requested': len(ids),
            'skipped_self': skipped_self,
            'deleted_count': deleted_count,
            'deleted_ids': [str(i) for i in to_delete],
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        if not self._is_admin(request.user):
            return Response({'detail': 'Permissão negada'}, status=status.HTTP_403_FORBIDDEN)
        obj = self.get_object()
        if str(obj.id) == str(request.user.id):
            return Response({'detail': 'Não é possível excluir a própria conta.'}, status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)
