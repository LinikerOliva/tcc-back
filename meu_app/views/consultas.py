from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from django.shortcuts import render
from ..models import Consulta, Medico, Paciente, MedicoPaciente
from ..serializers import ConsultaSerializer, ConsultaListSerializer, ConsultaCreateSerializer

# Adiciona import do cliente Gemini (módulo local)
try:
    import ai_gemini
except Exception:
    ai_gemini = None

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

    @action(detail=True, methods=['post'])
    def sumarizar(self, request, pk=None):
        """
        Recebe a transcrição do diálogo, processa via Gemini e retorna JSON estruturado.
        Espera payload: {
          transcript: string,
          extracted?: object,
          form?: object
        }
        """
        consulta = self.get_object()
        data = request.data or {}
        transcript = (data.get('transcript') or '').strip()
        extracted = data.get('extracted') or {}
        form = data.get('form') or {}

        # Resposta rápida se não houver transcrição
        if not transcript:
            # Retorna dados do contexto como está (evita erro no front)
            out = {
                'queixa': extracted.get('queixa') or form.get('queixa_principal') or '',
                'historia_doenca_atual': extracted.get('historia') or form.get('historia_doenca_atual') or '',
                'diagnostico_principal': extracted.get('diagnostico') or form.get('diagnostico_principal') or '',
                'conduta': extracted.get('conduta') or form.get('conduta') or '',
                'medicamentos': extracted.get('medicamentos') or form.get('medicamentos_uso') or '',
                'posologia': extracted.get('posologia') or '',
                'alergias': form.get('alergias') or '',
                'pressao': extracted.get('pressao') or '',
                'frequencia_cardiaca': extracted.get('frequencia') or extracted.get('frequencia_cardiaca') or extracted.get('frequencia-cardiaca') or '',
                'temperatura': extracted.get('temperatura') or '',
                'saturacao': extracted.get('saturacao') or '',
            }
            return Response(out, status=status.HTTP_200_OK)

        contexto = {
            'consulta_id': str(consulta.id),
            'paciente_id': consulta.paciente_id,
            'medico_id': consulta.medico_id,
            'extracted': extracted,
            'form': form,
        }

        if ai_gemini is None:
            # SDK indisponível: apenas ecoa contexto mínimo
            out = {
                'queixa': extracted.get('queixa') or form.get('queixa_principal') or '',
                'historia_doenca_atual': extracted.get('historia') or form.get('historia_doenca_atual') or '',
                'diagnostico_principal': extracted.get('diagnostico') or form.get('diagnostico_principal') or '',
                'conduta': extracted.get('conduta') or form.get('conduta') or '',
                'medicamentos': extracted.get('medicamentos') or form.get('medicamentos_uso') or '',
                'posologia': extracted.get('posologia') or '',
                'alergias': form.get('alergias') or '',
                'pressao': extracted.get('pressao') or '',
                'frequencia_cardiaca': extracted.get('frequencia') or extracted.get('frequencia_cardiaca') or extracted.get('frequencia-cardiaca') or '',
                'temperatura': extracted.get('temperatura') or '',
                'saturacao': extracted.get('saturacao') or '',
                '_warning': 'ai_gemini módulo não disponível no servidor'
            }
            return Response(out, status=status.HTTP_200_OK)

        try:
            result = ai_gemini.summarize_transcript(transcript, contexto)
        except Exception as e:
            # Fallback resiliente com contexto mínimo
            out = {
                'queixa': extracted.get('queixa') or form.get('queixa_principal') or '',
                'historia_doenca_atual': extracted.get('historia') or form.get('historia_doenca_atual') or '',
                'diagnostico_principal': extracted.get('diagnostico') or form.get('diagnostico_principal') or '',
                'conduta': extracted.get('conduta') or form.get('conduta') or '',
                'medicamentos': extracted.get('medicamentos') or form.get('medicamentos_uso') or '',
                'posologia': extracted.get('posologia') or '',
                'alergias': form.get('alergias') or '',
                'pressao': extracted.get('pressao') or '',
                'frequencia_cardiaca': extracted.get('frequencia') or extracted.get('frequencia_cardiaca') or extracted.get('frequencia-cardiaca') or '',
                'temperatura': extracted.get('temperatura') or '',
                'saturacao': extracted.get('saturacao') or '',
                '_error': str(e)
            }
            return Response(out, status=status.HTTP_200_OK)

        # Normaliza o resultado para garantir chaves esperadas
        def g(obj, keys, default=""):
            for k in keys:
                if isinstance(obj, dict) and k in obj and obj[k] is not None:
                    return obj[k]
            return default

        normalized = {
            'queixa': g(result, ['queixa', 'queixa_principal', 'chief_complaint', 'chiefComplaint']),
            'historia_doenca_atual': g(result, ['historia_doenca_atual', 'historia', 'hda', 'history_of_present_illness', 'hpi']),
            'diagnostico_principal': g(result, ['diagnostico_principal', 'diagnostico', 'diagnosis', 'assessment']),
            'conduta': g(result, ['conduta', 'plano', 'plan']),
            'medicamentos': g(result, ['medicamentos', 'medicacoes', 'prescricao', 'prescription', 'medications']),
            'posologia': g(result, ['posologia', 'dosagem', 'dosage', 'dosage_instructions']),
            'alergias': g(result, ['alergias', 'allergies']),
            'pressao': g(result, ['pressao', 'pa', 'pressao_arterial']),
            'frequencia_cardiaca': g(result, ['frequencia_cardiaca', 'fc', 'frequencia-cardiaca', 'heart_rate']),
            'temperatura': g(result, ['temperatura', 'temp']),
            'saturacao': g(result, ['saturacao', 'spo2', 'oximetria']),
            '_raw': result,
        }
        return Response(normalized, status=status.HTTP_200_OK)

# --- UI (HTML) ---

def consultas_page(request):
    """Renderiza a tela (UI) de Consultas para uso no navegador."""
    return render(request, 'consultas.html', {})