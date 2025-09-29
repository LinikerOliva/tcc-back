from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from ..models import Receita, Paciente, Medico
from ..serializers import ReceitaSerializer
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django.http import HttpResponse
from django.core.files.base import ContentFile
from django.utils import timezone
from django.core.mail import EmailMessage
import hashlib
import os

# Dependências para manipular PDF e QR (com fallback gracioso se não instaladas)
from io import BytesIO
try:
    import PyPDF2
except Exception:
    PyPDF2 = None
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
except Exception:
    canvas = None
    A4 = None
    ImageReader = None
try:
    import qrcode
except Exception:
    qrcode = None
# NOVO: extrair dados do certificado PKCS#12 (sem persistir a senha)
try:
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography import x509
except Exception:
    pkcs12 = None
    x509 = None

class ReceitaViewSet(viewsets.ModelViewSet):
    # Ajuste: seguir relações existentes (consulta -> paciente/medico)
    queryset = (
        Receita.objects
        .select_related('consulta', 'consulta__paciente', 'consulta__medico')
        .prefetch_related('itens')
        .all()
    )
    serializer_class = ReceitaSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    # Permitir filtrar atravessando as relações corretamente
    filterset_fields = ['consulta', 'consulta__paciente', 'consulta__medico']
    search_fields = ['observacoes', 'diagnostico'] if hasattr(Receita, 'diagnostico') else ['observacoes']
    ordering_fields = ['created_at'] if hasattr(Receita, 'created_at') else ['id']

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        # Escopo por papel do usuário (compatível com padrão existente)
        if hasattr(user, 'paciente') and user.paciente:
            qs = qs.filter(consulta__paciente=user.paciente)
        elif hasattr(user, 'medico') and user.medico:
            qs = qs.filter(consulta__medico=user.medico)
        else:
            # admin/clinica/secretaria: manter qs amplo; se houver regra, aplicar aqui
            pass

        # Filtros adicionais por query string (aceita múltiplos nomes comuns)
        qp = self.request.query_params
        consulta_id = qp.get('consulta') or qp.get('consulta_id')
        paciente_id = qp.get('paciente') or qp.get('paciente_id') or qp.get('consulta__paciente')
        medico_id = qp.get('medico') or qp.get('medico_id') or qp.get('consulta__medico')

        if consulta_id:
            qs = qs.filter(consulta_id=consulta_id)
        if paciente_id:
            qs = qs.filter(consulta__paciente_id=paciente_id)
        if medico_id:
            qs = qs.filter(consulta__medico_id=medico_id)
        
        return qs

    # --- AÇÕES AUXILIARES ---
    def _pick(self, data, *keys, default=None):
        for k in keys:
            if k in data and data.get(k):
                return data.get(k)
        return default

    def _update_assinatura(self, receita: Receita, content_bytes: bytes, filename: str, user):
        # Salvar arquivo e hash. NÃO marcar como assinada aqui.
        if content_bytes is not None and filename:
            receita.arquivo_assinado.save(filename, ContentFile(content_bytes), save=False)
        # Hash do documento
        try:
            h = hashlib.sha256(content_bytes or b"").hexdigest()
        except Exception:
            h = ""
        receita.hash_documento = h
        # Somente o endpoint de assinatura deve definir algoritmo_assinatura/assinada_por/assinada_em/assinada
        receita.carimbo_tempo = timezone.now().isoformat()

    # --- AÇÕES DE ENVIO ---
    @action(detail=True, methods=['post', 'put', 'get'], url_path='enviar')
    def enviar(self, request, pk=None):
        receita = self.get_object()
        # Regra: somente documentos ASSINADOS DIGITALMENTE são válidos para envio
        if not getattr(receita, 'assinada', False):
            return Response({'success': False, 'detail': 'Receita ainda não assinada digitalmente. Assine antes de enviar.'}, status=400)
        # Coleta parâmetros de múltiplos nomes aceitos pelo frontend
        email = self._pick(request.data, 'email', 'to', 'destinatario', 'paciente_email') or \
                self._pick(request.query_params, 'email', 'to', 'destinatario', 'paciente_email')
        formato = (self._pick(request.data, 'formato') or self._pick(request.query_params, 'formato') or 'pdf').lower()

        # Recupera o arquivo assinado do banco
        saved_bytes = None
        saved_name = None
        if receita.arquivo_assinado:
            saved_name = os.path.basename(getattr(receita.arquivo_assinado, 'name', '') or 'receita.pdf')
            try:
                with receita.arquivo_assinado.open('rb') as f:
                    saved_bytes = f.read()
            except Exception:
                saved_bytes = None

        # Garantir que há conteúdo assinado para anexar
        if saved_bytes is None:
            return Response({'success': False, 'detail': 'Nenhum arquivo assinado disponível para envio.'}, status=400)

        # Envio de email (se disponível). Não falhar caso backend de email não esteja configurado.
        sent = False
        if email and saved_bytes:
            try:
                subject = 'Receita Médica'
                body = 'Segue em anexo sua receita assinada.'
                msg = EmailMessage(subject=subject, body=body, to=[email])
                attach_name = saved_name or 'receita.pdf'
                msg.attach(attach_name, saved_bytes, 'application/pdf')
                msg.send(fail_silently=True)
                sent = True
            except Exception:
                sent = False

        serializer = self.get_serializer(receita)
        return Response({
            'success': True,
            'email_sent': bool(sent),
            'receita': serializer.data,
        })

    @action(detail=False, methods=['post', 'put', 'get'], url_path='enviar')
    def enviar_list(self, request):
        # Suporta /receitas/enviar/ com id nos parâmetros/corpo
        rid = self._pick(request.data, 'id', 'receita', 'receita_id', 'receitaId') or \
              self._pick(request.query_params, 'id', 'receita', 'receita_id', 'receitaId')
        if not rid:
            return Response({'detail': 'Parâmetro receita_id ausente.'}, status=400)
        try:
            receita = Receita.objects.get(pk=rid)
        except Receita.DoesNotExist:
            return Response({'detail': 'Receita não encontrada.'}, status=404)
        # Reencaminha para ação de detalhe reaproveitando a lógica
        self.kwargs['pk'] = str(receita.pk)
        return self.enviar(request, pk=str(receita.pk))


# --- ENDPOINT DE ASSINATURA (QR + assinatura PKCS#12 obrigatória) ---
@api_view(['POST', 'PUT'])
@permission_classes([permissions.IsAuthenticated])
def assinar_documento(request):
    """
    Assina um PDF de receita de forma profissional:
    - Adiciona uma página extra com QR contendo o ID da receita, médico e data.
    - Exige certificado PFX (.pfx/.p12) e senha para aplicar assinatura PKCS#7.
    - Inclui dados do certificado (sujeito, emissor, validade) na página carimbada.
    - Atualiza o registro da Receita quando receita_id for fornecido.
    """
    # Restrição: somente médicos podem assinar
    user = request.user
    if not (getattr(user, 'role', None) == 'medico' or getattr(user, 'medico', None)):
        return Response({'detail': 'Apenas médicos podem assinar receitas.'}, status=403)

    # Arquivo PDF recebido
    up = None
    for key in ['file', 'documento', 'pdf']:
        if key in request.FILES:
            up = request.FILES[key]
            break
    if up is None:
        return Response({'detail': 'Arquivo PDF não enviado.'}, status=400)

    original_name = getattr(up, 'name', None) or 'documento.pdf'
    base, ext = os.path.splitext(original_name)
    signed_name = f"{base}_assinado{ext or '.pdf'}"
    pdf_bytes = up.read()

    # Coletar metadados
    rid = request.data.get('receita_id') or request.data.get('receita') or request.data.get('id') or request.data.get('receitaId')
    reason = request.data.get('reason') or request.data.get('motivo') or 'Receita Médica'
    location = request.data.get('location') or request.data.get('local') or ''

    # Dados do médico (se disponíveis)
    medico_nome = None
    medico_crm = None
    try:
        if hasattr(user, 'medico') and user.medico:
            medico_nome = getattr(user.medico, 'nome', None) or getattr(user, 'get_full_name', lambda: None)()
            medico_crm = getattr(user.medico, 'crm', None)
    except Exception:
        pass

    # Certificado PFX e senha (obrigatórios)
    pfx_file = None
    for key in ['pfx', 'certificado', 'pkcs12']:
        if key in request.FILES:
            pfx_file = request.FILES[key]
            break
    pfx_password = request.data.get('pfx_password') or request.data.get('senha') or request.data.get('password')
    if pfx_file is None:
        return Response({'detail': 'Certificado digital (.pfx/.p12) é obrigatório.'}, status=400)
    if not pfx_password:
        return Response({'detail': 'Senha do certificado digital é obrigatória.'}, status=400)

    # Extrair dados do certificado (sujeito, emissor, validade)
    cert_subject = None
    cert_issuer = None
    cert_valid_from = None
    cert_valid_to = None
    cert_serial = None
    try:
        if pkcs12:
            p12_bytes = pfx_file.read()
            # Não persistir senha; usar apenas para carregar e assinar
            loaded = pkcs12.load_key_and_certificates(p12_bytes, pfx_password.encode('utf-8'))
            cert = loaded[1]
            if cert:
                cert_subject = cert.subject.rfc4514_string()
                cert_issuer = cert.issuer.rfc4514_string()
                try:
                    cert_valid_from = timezone.make_aware(cert.not_valid_before, timezone.get_current_timezone()).strftime('%Y-%m-%d %H:%M')
                    cert_valid_to = timezone.make_aware(cert.not_valid_after, timezone.get_current_timezone()).strftime('%Y-%m-%d %H:%M')
                except Exception:
                    cert_valid_from = getattr(cert, 'not_valid_before', None)
                    cert_valid_to = getattr(cert, 'not_valid_after', None)
                cert_serial = hex(getattr(cert, 'serial_number', 0))[2:]
            # Reposicionar arquivo para assinatura
            pfx_file.seek(0)
    except Exception:
        # Dados do certificado não puderam ser extraídos; seguir sem exibir detalhes
        try:
            pfx_file.seek(0)
        except Exception:
            pass

    # Gera página de QR e anexos (incluindo dados do certificado quando disponíveis)
    stamped_bytes = pdf_bytes
    try:
        if PyPDF2 and canvas and qrcode:
            # Construir uma página com QR e informações
            buf = BytesIO()
            page_size = A4 if A4 else None
            cw, ch = (page_size[0], page_size[1]) if page_size else (595.27, 841.89)  # A4 default pt
            c = canvas.Canvas(buf, pagesize=(cw, ch))
            # QR content
            qr_text = f"RECEITA:{rid}" if rid else f"RECEITA"
            qr_img = qrcode.make(qr_text)
            qr_reader = ImageReader(qr_img)
            qr_w = 140
            qr_h = 140
            margin = 36
            c.drawImage(qr_reader, margin, margin, width=qr_w, height=qr_h)
            # Text info
            c.setFont('Helvetica', 11)
            y = margin + qr_h
            c.drawString(margin, y + 12, f"Receita ID: {rid or 'N/D'}")
            if medico_nome or medico_crm:
                c.drawString(margin, y - 4, f"Médico: {medico_nome or ''}  CRM: {medico_crm or ''}")
            c.drawString(margin, y - 20, f"Assinado em: {timezone.now().strftime('%Y-%m-%d %H:%M')}  Local: {location}")
            c.drawString(margin, y - 36, f"Motivo: {reason}")
            # Dados do certificado
            if cert_subject:
                c.drawString(margin, y - 52, f"Certificado: {cert_subject}")
            if cert_issuer:
                c.drawString(margin, y - 68, f"Emissor: {cert_issuer}")
            if cert_valid_from and cert_valid_to:
                c.drawString(margin, y - 84, f"Validade: {cert_valid_from} até {cert_valid_to}")
            if cert_serial:
                c.drawString(margin, y - 100, f"Serial: {cert_serial}")
            c.showPage()
            c.save()
            buf.seek(0)
            extra_pdf = buf.getvalue()

            # Concatenar PDF original + página extra
            reader_main = PyPDF2.PdfReader(BytesIO(pdf_bytes))
            reader_extra = PyPDF2.PdfReader(BytesIO(extra_pdf))
            writer = PyPDF2.PdfWriter()
            for p in reader_main.pages:
                writer.add_page(p)
            for p in reader_extra.pages:
                writer.add_page(p)
            out = BytesIO()
            writer.write(out)
            stamped_bytes = out.getvalue()
    except Exception:
        stamped_bytes = pdf_bytes

    # Assinatura digital PKCS#12 (obrigatória)
    pkcs_ok = False
    signed_bytes = stamped_bytes
    try:
        from endesive import pdf as endesive_pdf
        p12 = pfx_file.read()
        dct = {
            'sigflags': 3,
            'contact': getattr(user, 'email', '') or '',
            'location': location,
            'signingdate': timezone.now().strftime("%Y%m%d%H%M%S+00'00'"),
            'reason': reason,
            # Caixa de assinatura (valores padrão em pontos)
            'signaturebox': (50, 50, 300, 120),
        }
        signed_bytes = endesive_pdf.cms.sign(stamped_bytes, p12, pfx_password, dct)
        pkcs_ok = True
    except Exception:
        pkcs_ok = False
        signed_bytes = stamped_bytes

    if not pkcs_ok:
        # Não retornar documento sem assinatura digital válida
        return Response({'detail': 'Falha ao aplicar assinatura digital. Verifique o certificado e a senha.'}, status=400)

    # Atualiza registro da Receita se houver rid
    if rid:
        try:
            receita = Receita.objects.get(pk=rid)
            # Atualiza e salva
            try:
                h = hashlib.sha256(signed_bytes or b"").hexdigest()
            except Exception:
                h = ""
            arquivo_nome = signed_name or f"receita_{rid}.pdf"
            receita.arquivo_assinado.save(arquivo_nome, ContentFile(signed_bytes), save=False)
            receita.hash_documento = h
            receita.algoritmo_assinatura = 'SHA256-RSA'
            receita.carimbo_tempo = timezone.now().isoformat()
            try:
                receita.assinada_por = getattr(user, 'pk', None) and user or None
            except Exception:
                receita.assinada_por = None
            receita.assinada_em = timezone.now()
            receita.assinada = True
            receita.save()
        except Receita.DoesNotExist:
            pass

    resp = HttpResponse(signed_bytes, content_type='application/pdf')
    resp['Content-Disposition'] = f"attachment; filename={signed_name}"
    return resp