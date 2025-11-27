from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from django.shortcuts import render
from ..models import Consulta, Medico, Paciente, MedicoPaciente, Receita, ReceitaItem
from ..serializers import ConsultaSerializer, ConsultaListSerializer, ConsultaCreateSerializer
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, permission_classes

# Adiciona import do cliente Gemini (módulo local)
try:
    from . import ai_gemini
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

    @action(detail=True, methods=['post'], url_path='finalizar-ia')
    def finalizar_ia(self, request, pk=None):
        """Finaliza a consulta e retorna preenchimento sugerido pela IA.
        Espera payload: {
          transcript: string,
          extracted?: object,
          form?: object
        }
        """
        consulta = self.get_object()
        consulta.status = 'concluida'
        consulta.save()

        data = request.data or {}
        transcript = (data.get('transcript') or '').strip()
        extracted = data.get('extracted') or {}
        form = data.get('form') or {}

        if not transcript:
            out = {
                'status': 'concluida',
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
            out['queixa'] = limpar_lixo_ia(limpar_queixa(out.get('queixa') or ''))
            return Response(out, status=status.HTTP_200_OK)

        contexto = {
            'consulta_id': str(consulta.id),
            'paciente_id': consulta.paciente_id,
            'medico_id': consulta.medico_id,
            'extracted': extracted,
            'form': form,
        }

        if ai_gemini is None:
            out = {
                'status': 'concluida',
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
            out['queixa'] = limpar_lixo_ia(limpar_queixa(out.get('queixa') or ''))
            return Response(out, status=status.HTTP_200_OK)

        try:
            result = ai_gemini.summarize_transcript(transcript, contexto)
        except Exception as e:
            out = {
                'status': 'concluida',
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
            try:
                from . import ai_gemini as _ai
                off = _ai._offline_structured(transcript)
                out['queixa'] = off.get('queixa') or out.get('queixa') or ''
                out['medicamentos'] = off.get('medicamentos') or out.get('medicamentos') or ''
                out['posologia'] = off.get('posologia') or out.get('posologia') or ''
                out['historia_doenca_atual'] = off.get('historia_doenca_atual') or out.get('historia_doenca_atual') or ''
                out['diagnostico_principal'] = off.get('diagnostico_principal') or out.get('diagnostico_principal') or ''
                out['conduta'] = off.get('conduta') or out.get('conduta') or ''
            except Exception:
                pass
            out['queixa'] = limpar_lixo_ia(limpar_queixa(out.get('queixa') or ''))
            return Response(out, status=status.HTTP_200_OK)

        def g(obj, keys, default=""):
            for k in keys:
                if isinstance(obj, dict) and k in obj and obj[k] is not None:
                    return obj[k]
            return default

        normalized = {
            'status': 'concluida',
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
        try:
            from . import ai_gemini as _ai
            off = _ai._offline_structured(transcript)
            if not normalized['queixa'] or 'bom dia' in (normalized['queixa'] or '').lower():
                normalized['queixa'] = off.get('queixa') or normalized['queixa']
            if not normalized['medicamentos']:
                normalized['medicamentos'] = off.get('medicamentos') or ''
            if not normalized['posologia']:
                normalized['posologia'] = off.get('posologia') or ''
            if not normalized['historia_doenca_atual']:
                normalized['historia_doenca_atual'] = off.get('historia_doenca_atual') or ''
            if not normalized['diagnostico_principal']:
                normalized['diagnostico_principal'] = off.get('diagnostico_principal') or ''
            if not normalized['conduta']:
                normalized['conduta'] = off.get('conduta') or ''
        except Exception:
            pass
        normalized['queixa'] = limpar_lixo_ia(limpar_queixa(normalized.get('queixa') or ''))
        return Response(normalized, status=status.HTTP_200_OK)

# --- UI (HTML) ---

def consultas_page(request):
    """Renderiza a tela (UI) de Consultas para uso no navegador."""
    return render(request, 'consultas.html', {})


def limpar_queixa(texto_queixa: str) -> str:
    frases_proibidas = [
        "Bom dia, tudo bem?",
        "O que te traz aqui hoje?",
        "Olá, doutor",
        "Bom dia doutor",
        "Tudo bem?"
    ]
    s = (texto_queixa or "").strip()
    low = s.lower()
    for frase in frases_proibidas:
        if frase.lower() in low:
            return ""
    if low.startswith("bom dia"):
        s2 = s[len("bom dia"):]
        s2 = s2.replace("tudo bem?", "")
        return s2.strip(",. ")
    return s

def limpar_lixo_ia(texto: str) -> str:
    if not texto:
        return ""
    texto_lower = texto.lower().strip()
    frases_proibidas = [
        "bom dia", "boa tarde", "boa noite",
        "o que te traz aqui", "tudo bem",
        "ola doutor", "olá doutor"
    ]
    for frase in frases_proibidas:
        if frase in texto_lower and len(texto) < 50:
            novo_texto = texto_lower.replace(frase, "").replace("?", "").strip()
            if len(novo_texto) < 5:
                return ""
    return texto

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def criar_consulta_e_receita(request):
    payload = request.data or {}
    dados = payload.get('dados', {})
    texto = payload.get('texto', '')

    data_str = dados.get('data')
    data_dt = parse_datetime(data_str) if isinstance(data_str, str) else data_str
    if data_dt is None:
        data_dt = timezone.now()

    with transaction.atomic():
        consulta = Consulta.objects.create(
            paciente_id=dados.get('paciente_id'),
            medico_id=dados.get('medico_id'),
            data_hora=data_dt,
            data=data_dt,
            motivo=dados.get('queixa_principal') or 'Motivo não informado',
            observacoes=dados.get('observacoes') or '',
            queixa_principal=limpar_lixo_ia(limpar_queixa(dados.get('queixa_principal', ''))),
            historia_doenca=dados.get('historia_doenca', ''),
            diagnostico=dados.get('diagnostico', ''),
            conduta=dados.get('conduta', ''),
            resumo_clinico=dados.get('resumo_clinico', ''),
        )

        receita = Receita.objects.create(
            consulta=consulta,
            status='PENDENTE'
        )

        itens = []
        try:
            if ai_gemini:
                itens = ai_gemini.extract_prescription_items(texto) or []
        except Exception:
            itens = []

        for item in itens:
            ReceitaItem.objects.create(
                receita=receita,
                medicamento=item.get('medicamento', ''),
                posologia=item.get('posologia', ''),
                quantidade=item.get('quantidade') or None,
            )

    return Response({'receita_id': str(receita.id)})
