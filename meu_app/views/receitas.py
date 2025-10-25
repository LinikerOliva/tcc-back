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
        return Response({'status': 'error', 'message': 'Apenas médicos podem assinar receitas.'}, status=403)

    # Arquivo PDF recebido - aceita múltiplos nomes de campo
    up = None
    for key in ['file', 'documento', 'pdf', 'arquivo']:
        if key in request.FILES:
            up = request.FILES[key]
            break
    if up is None:
        return Response({'status': 'error', 'message': 'Arquivo PDF não enviado.'}, status=400)

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

    # Certificado PFX e senha (obrigatórios) - aceita múltiplos nomes de campo
    pfx_file = None
    for key in ['pfx', 'certificado', 'pkcs12', 'arquivo_pfx']:
        if key in request.FILES:
            pfx_file = request.FILES[key]
            break
    
    # Aceita múltiplos nomes para senha
    pfx_password = (request.data.get('pfx_password') or 
                   request.data.get('senha') or 
                   request.data.get('password') or 
                   request.data.get('senha_certificado'))
    
    if pfx_file is None:
        return Response({'status': 'error', 'message': 'Certificado digital (.pfx/.p12) é obrigatório.'}, status=400)
    if not pfx_password:
        return Response({'status': 'error', 'message': 'Senha do certificado digital é obrigatória.'}, status=400)

    # Extrair dados do certificado (sujeito, emissor, validade) e validar senha
    cert_subject = None
    cert_issuer = None
    cert_valid_from = None
    cert_valid_to = None
    cert_serial = None
    cert = None
    key = None
    
    try:
        if pkcs12:
            p12_bytes = pfx_file.read()
            # Validar senha do certificado
            try:
                loaded = pkcs12.load_key_and_certificates(p12_bytes, pfx_password.encode('utf-8'))
                key, cert, chain = loaded
                
                if cert is None or key is None:
                    return Response({'status': 'error', 'message': 'Certificado ou chave privada não encontrados no arquivo PFX.'}, status=400)
                
                # Extrair informações do certificado
                cert_subject = cert.subject.rfc4514_string()
                cert_issuer = cert.issuer.rfc4514_string()
                try:
                    cert_valid_from = timezone.make_aware(cert.not_valid_before, timezone.get_current_timezone()).strftime('%Y-%m-%d %H:%M')
                    cert_valid_to = timezone.make_aware(cert.not_valid_after, timezone.get_current_timezone()).strftime('%Y-%m-%d %H:%M')
                except Exception:
                    cert_valid_from = getattr(cert, 'not_valid_before', None)
                    cert_valid_to = getattr(cert, 'not_valid_after', None)
                cert_serial = hex(getattr(cert, 'serial_number', 0))[2:]
                
                # Validar se o certificado está dentro do período de validade
                from datetime import datetime, timezone as dt_timezone
                now = datetime.now(tz=dt_timezone.utc)
                not_before = cert.not_valid_before.replace(tzinfo=dt_timezone.utc)
                not_after = cert.not_valid_after.replace(tzinfo=dt_timezone.utc)
                if not (not_before <= now <= not_after):
                    return Response({'status': 'error', 'message': 'Certificado expirado ou ainda não válido.'}, status=400)
                
            except ValueError as e:
                # Erro específico de senha incorreta
                return Response({'status': 'error', 'message': 'Senha do certificado incorreta.'}, status=400)
            except Exception as e:
                # Outros erros de validação do certificado
                return Response({'status': 'error', 'message': f'Erro ao validar certificado: {str(e)[:100]}'}, status=400)
            
            # Reposicionar arquivo para assinatura
            pfx_file.seek(0)
    except Exception as e:
        # Erro geral ao processar o arquivo PFX
        return Response({'status': 'error', 'message': f'Erro ao processar arquivo PFX: {str(e)[:100]}'}, status=400)

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

    # Assinatura digital PKCS#12 usando pyHanko (obrigatória)
    pkcs_ok = False
    signed_bytes = stamped_bytes
    try:
        from pyhanko.pdf_utils.reader import PdfFileReader
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign import signers
        
        # Usar o certificado e chave já validados
        if cert and key:
            rdr = PdfFileReader(BytesIO(stamped_bytes))
            w = IncrementalPdfFileWriter(rdr)

            simple_signer = signers.SimpleSigner(
                private_key=key,
                cert=cert,
                other_certs=chain or [],
            )
            signature_meta = signers.SignatureMeta(
                field_name=None,
                reason=reason,
                location=location,
            )
            pdf_signer = signers.PdfSigner(
                signature_meta=signature_meta, 
                signer=simple_signer, 
                md_algorithm='sha256'
            )
            out = BytesIO()
            pdf_signer.sign_pdf(w, output=out)
            signed_bytes = out.getvalue()
            pkcs_ok = True
        else:
            return Response({'status': 'error', 'message': 'Certificado ou chave privada não disponível para assinatura.'}, status=400)
            
    except Exception as e:
        return Response({'status': 'error', 'message': f'Falha ao aplicar assinatura digital: {str(e)[:100]}'}, status=400)

    if not pkcs_ok:
        # Não retornar documento sem assinatura digital válida
        return Response({'status': 'error', 'message': 'Falha ao aplicar assinatura digital. Verifique o certificado e a senha.'}, status=400)

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
            return Response({'status': 'error', 'message': f'Receita {rid} não encontrada.'}, status=404)
        except Exception as e:
            return Response({'status': 'error', 'message': f'Erro ao salvar receita assinada: {str(e)[:100]}'}, status=500)

    # Verificar se o frontend quer resposta JSON
    want_json = (request.headers.get('Accept', '').lower().find('application/json') >= 0) or \
                (str(request.query_params.get('return', '')).lower() == 'json')
    
    if want_json:
        import base64
        return Response({
            'status': 'success',
            'message': 'Documento assinado com sucesso',
            'arquivo_assinado': base64.b64encode(signed_bytes).decode('ascii'),
            'filename': signed_name,
            'receita_id': rid
        })
    
    resp = HttpResponse(signed_bytes, content_type='application/pdf')
    resp['Content-Disposition'] = f"attachment; filename={signed_name}"
    return resp


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def assinar_receita(request):
    """
    Endpoint: /api/assinar-receita
    Assina PDF de receita (PAdES básico) com certificado A1 (.pfx + senha).
    Regras:
    - Não persiste certificado, chave ou senha.
    - Valida datas do certificado e extensões básicas, com logs de operação.
    - Retorna o PDF assinado (application/pdf) ou JSON com base64 quando solicitado.
    """
    logs = []
    try:
        user = request.user
        # Permite apenas médicos
        if not (getattr(user, 'role', None) == 'medico' or getattr(user, 'medico', None)):
            return Response({
                'status': 'error',
                'message': 'Apenas médicos podem assinar receitas.',
                'logs': ['Permissão negada: usuário não é médico']
            }, status=403)

        rid = request.data.get('id_receita') or request.data.get('receita_id') or request.data.get('receita')
        if not rid:
            return Response({
                'status': 'error',
                'message': 'Parâmetro id_receita é obrigatório.',
                'logs': ['id_receita ausente no formulário']
            }, status=400)

        # Arquivo PFX e senha
        pfx_up = request.FILES.get('arquivo_pfx')
        pfx_password = request.data.get('senha_certificado')
        if pfx_up is None:
            return Response({
                'status': 'error',
                'message': 'Arquivo .pfx (arquivo_pfx) é obrigatório.',
                'logs': ['arquivo_pfx não enviado']
            }, status=400)
        if not pfx_password:
            return Response({
                'status': 'error',
                'message': 'Senha do certificado (senha_certificado) é obrigatória.',
                'logs': ['senha_certificado não enviada']
            }, status=400)

        # Carrega receita
        try:
            receita = Receita.objects.select_related('consulta', 'consulta__medico').get(pk=rid)
        except Receita.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Receita não encontrada.',
                'logs': [f'Receita {rid} não existe']
            }, status=404)

        # Regra: somente o médico da consulta pode assinar
        try:
            medico_owner = getattr(receita.consulta, 'medico', None)
            if medico_owner and hasattr(user, 'medico') and user.medico:
                if medico_owner != user.medico:
                    return Response({
                        'status': 'error',
                        'message': 'Você não é o médico responsável por esta receita.',
                        'logs': ['Assinante diferente do médico da consulta']
                    }, status=403)
        except Exception:
            pass

        # Não permitir re-assinar inadvertidamente
        if getattr(receita, 'assinada', False) and getattr(receita, 'arquivo_assinado', None):
            return Response({
                'status': 'error',
                'message': 'Receita já assinada.',
                'logs': ['Operação bloqueada: receita já assinada']
            }, status=409)

        # Carregar PDF original da receita (deve ter sido gerado previamente)
        from django.conf import settings
        import os
        pdf_bytes = None

        def load_receita_pdf_bytes(receita_id):
            base_dir = getattr(settings, 'MEDIA_ROOT', None)
            candidates = []
            if base_dir:
                candidates.extend([
                    os.path.join(base_dir, 'receitas', f'{receita_id}.pdf'),
                    os.path.join(base_dir, 'receitas', f'receita_{receita_id}.pdf'),
                    os.path.join(base_dir, 'documentos', 'receitas', f'{receita_id}.pdf'),
                    os.path.join(base_dir, 'documentos', 'receitas', f'receita_{receita_id}.pdf'),
                ])
                # Busca por nomes contendo o ID
                for root, _, files in os.walk(os.path.join(base_dir, 'receitas')):
                    for fn in files:
                        if fn.lower().endswith('.pdf') and str(receita_id) in fn:
                            candidates.append(os.path.join(root, fn))
            for p in candidates:
                try:
                    if os.path.exists(p):
                        with open(p, 'rb') as f:
                            return f.read()
                except Exception:
                    continue
            return None

        pdf_bytes = load_receita_pdf_bytes(rid)
        if pdf_bytes is None:
            return Response({
                'status': 'error',
                'message': 'PDF da receita não encontrado.',
                'logs': [f'Arquivo PDF ausente para receita {rid}']
            }, status=404)

        # Abrir .pfx e validar certificado
        from cryptography.hazmat.primitives.serialization import pkcs12
        from cryptography import x509
        from datetime import datetime, timezone as dt_timezone
        try:
            pfx_data = pfx_up.read()
            logs.append('Certificado .pfx lido em memória')
            key, cert, chain = pkcs12.load_key_and_certificates(pfx_data, pfx_password.encode('utf-8'))
            if cert is None or key is None:
                return Response({
                    'status': 'error',
                    'message': 'Falha ao abrir .pfx: certificado ou chave ausente.',
                    'logs': ['pkcs12 retornou chave/certificado None']
                }, status=400)
            logs.append('Certificado carregado com sucesso')
        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Senha do certificado inválida ou .pfx corrompido.',
                'logs': [f'Falha ao abrir .pfx: {str(e)[:200]}']
            }, status=400)
        finally:
            try:
                pfx_up.seek(0)
            except Exception:
                pass

        # Validar validade
        try:
            now = datetime.now(tz=dt_timezone.utc)
            not_before = cert.not_valid_before.replace(tzinfo=dt_timezone.utc)
            not_after = cert.not_valid_after.replace(tzinfo=dt_timezone.utc)
            if not (not_before <= now <= not_after):
                return Response({
                    'status': 'error',
                    'message': 'Certificado expirado ou ainda não válido.',
                    'logs': [f'Janela de validade: {not_before} .. {not_after}']
                }, status=400)
            logs.append('Validade do certificado dentro do período')
        except Exception:
            logs.append('Não foi possível validar datas do certificado (prosseguindo)')

        # Validar extensões básicas
        try:
            bc = cert.extensions.get_extension_for_class(x509.BasicConstraints).value
            logs.append(f'BasicConstraints: ca={bc.ca}')
        except Exception:
            logs.append('BasicConstraints não presente')
        try:
            pol = cert.extensions.get_extension_for_class(x509.CertificatePolicies).value
            logs.append(f'CertificatePolicies: {len(pol)} políticas')
        except Exception:
            logs.append('CertificatePolicies não presente')

        # Assinar com pyhanko (PAdES básico)
        try:
            from io import BytesIO
            from pyhanko.pdf_utils.reader import PdfFileReader
            from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
            from pyhanko.sign import signers

            rdr = PdfFileReader(BytesIO(pdf_bytes))
            w = IncrementalPdfFileWriter(rdr)

            simple_signer = signers.SimpleSigner(
                private_key=key,
                cert=cert,
                other_certs=chain or [],
            )
            signature_meta = signers.SignatureMeta(
                field_name=None,
                reason='Receita Médica',
                location=getattr(receita.consulta, 'clinica', None) and str(receita.consulta.clinica) or '',
            )
            pdf_signer = signers.PdfSigner(signature_meta=signature_meta, signer=simple_signer, md_algorithm='sha256')
            out = BytesIO()
            pdf_signer.sign_pdf(w, output=out)
            signed_bytes = out.getvalue()
            logs.append('PDF assinado com PAdES básico (SHA-256)')
        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Falha na assinatura do PDF.',
                'logs': [f'Erro pyhanko: {str(e)[:200]}']
            }, status=500)

        # Atualizar registro da receita (sem persistir cert/chave/senha)
        try:
            import hashlib
            h = hashlib.sha256(signed_bytes or b'').hexdigest()
            nome_arquivo = f"receita_{rid}_assinado.pdf"
            receita.arquivo_assinado.save(nome_arquivo, ContentFile(signed_bytes), save=False)
            receita.hash_documento = h
            receita.algoritmo_assinatura = 'SHA256'
            receita.carimbo_tempo = timezone.now().isoformat()
            try:
                receita.assinada_por = user
            except Exception:
                receita.assinada_por = None
            receita.assinada_em = timezone.now()
            receita.assinada = True
            receita.save()
            logs.append('Assinatura final gerada e registrada na receita')
        except Exception as e:
            # Falha ao salvar arquivo; ainda retornar o PDF assinado
            logs.append(f'Falha ao salvar arquivo-assinado: {str(e)[:200]}')

        # Responder em PDF ou JSON base64
        want_json = (request.headers.get('Accept', '').lower().find('application/json') >= 0) or \
                    (str(request.query_params.get('return', '')).lower() == 'json')
        if want_json:
            import base64
            return Response({
                'status': 'success',
                'message': 'PDF assinado com sucesso',
                'arquivo_assinado': base64.b64encode(signed_bytes).decode('ascii'),
                'logs': logs,
            })
        resp = HttpResponse(signed_bytes, content_type='application/pdf')
        resp['Content-Disposition'] = f"attachment; filename=receita_{rid}_assinado.pdf"
        return resp
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Erro interno ao assinar a receita.',
            'logs': [str(e)[:200]]
        }, status=500)
