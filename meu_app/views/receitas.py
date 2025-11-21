# -*- coding: utf-8 -*-
from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from ..models import Receita, Paciente, Medico
from ..serializers import ReceitaSerializer
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django.http import HttpResponse, JsonResponse
from django.core.files.base import ContentFile
from django.utils import timezone
from django.core.mail import EmailMessage
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
import hashlib
import os
import json
import uuid
import base64
from datetime import datetime
from io import BytesIO

# ReportLab imports
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

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
    REPORTLAB_AVAILABLE = True
except Exception as e:
    print(f"ReportLab import error: {e}")
    canvas = None
    A4 = None
    ImageReader = None
    REPORTLAB_AVAILABLE = False
try:
    import qrcode
except Exception:
    qrcode = None
try:
    from weasyprint import HTML, CSS
except Exception:
    HTML = None
    CSS = None
try:
    from pyhanko import sign
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import signers, fields
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.timestamps import HTTPTimeStamper
except Exception:
    sign = None
    IncrementalPdfFileWriter = None
    signers = None
    fields = None
    PdfFileReader = None
    HTTPTimeStamper = None
# NOVO: extrair dados do certificado PKCS#12 (sem persistir a senha)
try:
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography import x509
except Exception:
    pkcs12 = None
    x509 = None

# Importar serviços de assinatura digital
try:
    from ..services.digital_signature_service import digital_signature_service
    from ..services.certificate_manager import certificate_manager
    DIGITAL_SIGNATURE_AVAILABLE = True
except ImportError:
    DIGITAL_SIGNATURE_AVAILABLE = False

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

    def create(self, request, *args, **kwargs):
        """
        Sobrescreve o método create para automaticamente finalizar a receita
        quando ela é criada e enviada
        """
        # Chamar o método create padrão
        response = super().create(request, *args, **kwargs)
        
        if response.status_code == 201:  # Se a receita foi criada com sucesso
            receita_data = response.data
            receita_id = receita_data.get('id')
            
            if receita_id:
                try:
                    # Buscar a receita recém-criada
                    receita = Receita.objects.get(id=receita_id)
                    
                    # Marcar como assinada automaticamente (finalizada)
                    receita.assinada = True
                    # Preferir o médico da consulta; se não houver, usar o usuário atual
                    try:
                        medico_user = getattr(getattr(receita.consulta, 'medico', None), 'user', None)
                    except Exception:
                        medico_user = None
                    receita.assinada_por = medico_user or request.user
                    receita.assinada_em = timezone.now()
                    receita.carimbo_tempo = timezone.now().isoformat()
                    
                    # Salvar as alterações
                    receita.save()
                    
                    # Atualizar os dados de resposta
                    serializer = self.get_serializer(receita)
                    response.data = serializer.data
                    
                except Receita.DoesNotExist:
                    # Se por algum motivo a receita não for encontrada, continuar normalmente
                    pass
        
        return response

    def update(self, request, *args, **kwargs):
        """
        Sobrescreve o método update para permitir atualizações de assinatura
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        # Se está tentando atualizar campos de assinatura, verificar permissões
        data = request.data
        signature_fields = ['assinada', 'assinada_por', 'assinada_em', 'algoritmo_assinatura', 'hash_documento']
        is_signature_update = any(field in data for field in signature_fields)
        
        if is_signature_update:
            user = request.user
            if not (hasattr(user, 'medico') and user.medico):
                return Response({'error': 'Apenas médicos podem atualizar status de assinatura'}, status=403)
            
            # Se está marcando como assinada, definir campos automaticamente
            if data.get('assinada') is True:
                data['assinada_por'] = user.id
                data['assinada_em'] = timezone.now().isoformat()
                if not data.get('carimbo_tempo'):
                    data['carimbo_tempo'] = timezone.now().isoformat()
        
        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        return Response(serializer.data)

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

    # --- AÇÃO DE ASSINATURA ---
    @action(detail=True, methods=['post', 'put', 'patch'], url_path='assinar')
    def assinar(self, request, pk=None):
        """
        Endpoint para marcar receita como assinada
        POST/PUT/PATCH /api/receitas/{id}/assinar/
        """
        receita = self.get_object()
        
        # Verificar se o usuário tem permissão (deve ser médico)
        user = request.user
        if not (hasattr(user, 'medico') and user.medico):
            return Response({'error': 'Apenas médicos podem assinar receitas'}, status=403)
        
        # Atualizar campos de assinatura
        receita.assinada = True
        receita.assinada_por = user
        receita.assinada_em = timezone.now()
        
        # Atualizar outros campos se fornecidos
        data = request.data
        if data.get('algoritmo_assinatura'):
            receita.algoritmo_assinatura = data.get('algoritmo_assinatura')
        
        if data.get('hash_documento'):
            receita.hash_documento = data.get('hash_documento')
        
        if data.get('carimbo_tempo'):
            receita.carimbo_tempo = data.get('carimbo_tempo')
        else:
            receita.carimbo_tempo = timezone.now().isoformat()
        
        # Salvar no banco de dados
        receita.save()
        
        # Retornar dados atualizados
        serializer = self.get_serializer(receita)
        return Response({
            'success': True,
            'message': 'Receita assinada com sucesso',
            'receita': serializer.data
        })

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

    @action(detail=True, methods=['get'], url_path='verificar', permission_classes=[])
    def verificar(self, request, pk=None):
        """Ação pública para verificar uma receita sem autenticação"""
        try:
            receita = Receita.objects.select_related(
                'consulta', 'consulta__paciente', 'consulta__medico'
            ).get(pk=pk)
            
            serializer = self.get_serializer(receita)
            return Response(serializer.data)
        except Receita.DoesNotExist:
            return Response(
                {'detail': 'Receita não encontrada'}, 
                status=404
            )


# --- ENDPOINT DE ASSINATURA DIGITAL (Fluxo A1/PFX Server-Side) ---
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def assinar_documento(request):
    """
    Endpoint POST /api/assinatura/assinar/
    
    Implementa o fluxo de assinatura digital no servidor (Server-Side) para certificados A1/PFX.
    
    Recebe via FormData (multipart/form-data):
    - file: O arquivo PDF (blob) da receita, já gerado
    - pfx_file: O arquivo de certificado do médico (A1, .pfx ou .p12)
    - pfx_password: A senha (o "PIN" do arquivo) para destravar o certificado
    
    Retorna:
    - PDF assinado digitalmente com carimbo de tempo (PAdES)
    """
    from rest_framework.parsers import MultiPartParser
    from django.http import HttpResponse
    from io import BytesIO
    
    # Verificar se as bibliotecas necessárias estão disponíveis
    if not all([signers, HTTPTimeStamper, sign]):
        return Response({
            'status': 'error', 
            'message': 'Bibliotecas de assinatura digital não estão disponíveis no servidor.'
        }, status=500)
    
    # Restrição: somente médicos podem assinar
    user = request.user
    if not (getattr(user, 'role', None) == 'medico' or getattr(user, 'medico', None)):
        return Response({
            'status': 'error', 
            'message': 'Apenas médicos podem assinar receitas.'
        }, status=403)

    try:
        # 1. Receber os Dados
        pdf_file = request.data.get('file')
        pfx_file = request.data.get('pfx_file') 
        pfx_password = request.data.get('pfx_password')
        
        # Validar se todos os 3 campos estão presentes
        if not pdf_file:
            return Response({
                'status': 'error', 
                'message': 'Arquivo PDF não foi enviado.'
            }, status=400)
            
        if not pfx_file:
            return Response({
                'status': 'error', 
                'message': 'Arquivo de certificado PFX não foi enviado.'
            }, status=400)
            
        if not pfx_password:
            return Response({
                'status': 'error', 
                'message': 'Senha do certificado PFX não foi fornecida.'
            }, status=400)

        # 2. Carregar o Certificado (Validação do PIN)
        try:
            # Ler os bytes do PFX
            pfx_bytes = pfx_file.read()
            password_bytes = pfx_password.encode('utf-8')
            
            # Carregar o assinante usando pyHanko
            signer = signers.SimpleSigner.load_pkcs12(
                pfx_file=BytesIO(pfx_bytes), 
                passphrase=password_bytes
            )
            
        except Exception as e:
            # Se a senha (pfx_password) estiver errada, o load_pkcs12 falhará
            return Response({
                'status': 'error', 
                'message': 'PIN do certificado inválido ou arquivo PFX corrompido.'
            }, status=400)

        # 3. Adicionar Carimbo de Tempo (Timestamp)
        try:
            # Para garantir a validade da assinatura (LTV), configure um carimbo de tempo
            timestamper = HTTPTimeStamper('http://timestamp.digicert.com')
        except Exception:
            # Se falhar, continua sem timestamp
            timestamper = None

        # 4. Assinar o PDF
        try:
            # Ler os bytes do PDF original
            pdf_bytes_in = pdf_file.read()
            
            # Chamar a função principal do pyHanko para assinar
            pdf_signed = sign_pdf(
                pdf_in=pdf_bytes_in,
                signer=signer,
                signature_meta=signers.PdfSignatureMetadata(
                    field_name="AssinaturaMedico",
                    reason="Prescrição de receita"
                ),
                timestamper=timestamper
            )
            
        except Exception as e:
            return Response({
                'status': 'error', 
                'message': f'Erro ao assinar o PDF: {str(e)}'
            }, status=500)

        # 5. Responder ao Frontend
        # Em vez de salvar em um arquivo, devolva o PDF assinado diretamente na resposta HTTP
        response = HttpResponse(
            pdf_signed.getbuffer(), 
            content_type="application/pdf"
        )
        response["Content-Disposition"] = "inline; filename=receita_assinada.pdf"
        return response
        
    except Exception as e:
        return Response({
            'status': 'error', 
            'message': f'Erro interno do servidor: {str(e)}'
        }, status=500)


def sign_pdf(pdf_in, signer, signature_meta, timestamper=None):
    """
    Função auxiliar para assinar PDF usando pyHanko
    
    Args:
        pdf_in: bytes do PDF original
        signer: SimpleSigner do pyHanko
        signature_meta: PdfSignatureMetadata
        timestamper: HTTPTimeStamper (opcional)
    
    Returns:
        BytesIO: PDF assinado
    """
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import signers
    from io import BytesIO
    
    # Preparar PDF para assinatura
    pdf_reader = PdfFileReader(BytesIO(pdf_in))
    writer = IncrementalPdfFileWriter(pdf_reader)
    
    # Configurar metadados da assinatura com timestamp se disponível
    if timestamper:
        signature_meta.timestamper = timestamper
    
    # Criar assinador PDF
    pdf_signer = signers.PdfSigner(
        signature_meta=signature_meta,
        signer=signer
    )
    
    # Assinar PDF
    output_buffer = BytesIO()
    pdf_signer.sign_pdf(writer, output=output_buffer)
    
    return output_buffer


@csrf_exempt
def gerar_receita_assinada(request):
    """
    API Endpoint: POST /api/gerar-receita/
    
    Gera e assina digitalmente uma receita médica a partir de dados JSON.
    
    Fluxo:
    1. Recebe dados JSON da receita
    2. Gera QR Code de verificação único
    3. Monta HTML da receita com QR Code
    4. Converte HTML para PDF usando WeasyPrint
    5. Assina digitalmente o PDF usando PyHanko
    6. Retorna PDF assinado
    
    Payload JSON esperado:
    {
        "paciente_nome": "João Silva",
        "paciente_cpf": "123.456.789-00",
        "paciente_nascimento": "15/03/1985",
        "medico_nome": "Dr. Maria Santos",
        "medico_crm": "123456-SP",
        "medicamentos": [
            {
                "nome": "Paracetamol 500mg",
                "posologia": "1 comprimido de 8 em 8 horas",
                "quantidade": "15 comprimidos"
            }
        ],
        "observacoes": "Tomar após as refeições"
    }
    """
    
    # Verificar se as bibliotecas necessárias estão disponíveis
    # WeasyPrint é preferido, mas ReportLab pode ser usado como fallback
    pdf_library_available = HTML is not None or REPORTLAB_AVAILABLE
    
    if not all([qrcode, pdf_library_available]):
        return JsonResponse({
            'error': 'Bibliotecas necessárias não estão instaladas no servidor',
            'missing': [
                'qrcode' if not qrcode else None,
                'weasyprint ou reportlab' if not pdf_library_available else None,
            ]
        }, status=500)
    
    try:
        # Parse dos dados JSON
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body.decode('utf-8'))
            except UnicodeDecodeError:
                # Fallback para latin-1 se UTF-8 falhar
                data = json.loads(request.body.decode('latin-1'))
        else:
            data = request.data
        
        # Validar dados obrigatórios
        required_fields = ['paciente_nome', 'medico_nome', 'medico_crm']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return JsonResponse({
                'error': f'Campos obrigatórios ausentes: {", ".join(missing_fields)}'
            }, status=400)
        
        # Gerar ID único para a receita
        receita_id = str(uuid.uuid4())
        
        # Gerar URL de verificação única
        base_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
        verification_url = f"{base_url}/verificar/{receita_id}"
        
        # 1. Gerar QR Code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(verification_url)
        qr.make(fit=True)
        
        # Converter QR Code para Base64
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_buffer = BytesIO()
        qr_img.save(qr_buffer, format='PNG')
        qr_base64 = base64.b64encode(qr_buffer.getvalue()).decode()
        qr_data_uri = f"data:image/png;base64,{qr_base64}"
        
        # 2. Montar HTML da receita
        html_content = gerar_html_receita(data, qr_data_uri, receita_id)
        
        # 3. Converter HTML para PDF
        pdf_buffer = BytesIO()
        
        # Usar ReportLab como biblioteca principal (mais confiável no Windows)
        if REPORTLAB_AVAILABLE:
            pdf_bytes = gerar_pdf_com_reportlab(data, qr_data_uri, receita_id)
        elif HTML is not None:
            # Fallback para WeasyPrint se ReportLab não estiver disponível
            try:
                HTML(string=html_content).write_pdf(pdf_buffer)
                pdf_bytes = pdf_buffer.getvalue()
            except Exception as e:
                print(f"Erro com WeasyPrint: {e}")
                raise Exception("Erro na geração do PDF com WeasyPrint")
        else:
            raise Exception("Nenhuma biblioteca de PDF disponível")
        
        # 4. Assinar digitalmente o PDF
        certificate_path = getattr(settings, 'DIGITAL_CERTIFICATE_PATH', None)
        certificate_password = getattr(settings, 'DIGITAL_CERTIFICATE_PASSWORD', None)
        
        if certificate_path and certificate_password and os.path.exists(certificate_path):
            try:
                signed_pdf = assinar_pdf_com_pyhanko(
                    pdf_bytes, 
                    certificate_path, 
                    certificate_password
                )
                pdf_bytes = signed_pdf
            except Exception as e:
                # Se falhar na assinatura, continua com PDF não assinado
                print(f"Erro na assinatura digital: {e}")
        
        # 5. Retornar PDF
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="receita_{receita_id}.pdf"'
        
        return response
        
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'JSON inválido no corpo da requisição'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'error': f'Erro interno do servidor: {str(e)}'
        }, status=500)


# Função removida - agora implementada em pdf_generator.py
    
    # Gerar HTML da receita
    html_content = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Receita Médica - {receita_id}</title>
        <style>
            @page {{
                size: A4;
                margin: 2cm;
            }}
            
            body {{
                font-family: 'Arial', sans-serif;
                font-size: 12px;
                line-height: 1.4;
                color: #333;
                margin: 0;
                padding: 0;
            }}
            
            .header {{
                text-align: center;
                border-bottom: 2px solid #2c5aa0;
                padding-bottom: 15px;
                margin-bottom: 20px;
            }}
            
            .clinica-nome {{
                font-size: 18px;
                font-weight: bold;
                color: #2c5aa0;
                margin-bottom: 5px;
            }}
            
            .clinica-info {{
                font-size: 10px;
                color: #666;
            }}
            
            .medico-info {{
                background-color: #f8f9fa;
                padding: 10px;
                border-radius: 5px;
                margin-bottom: 15px;
            }}
            
            .paciente-info {{
                background-color: #e8f4f8;
                padding: 10px;
                border-radius: 5px;
                margin-bottom: 15px;
            }}
            
            .medicamentos {{
                margin-bottom: 20px;
            }}
            
            .medicamento {{
                border: 1px solid #ddd;
                padding: 10px;
                margin-bottom: 10px;
                border-radius: 5px;
            }}
            
            .medicamento-nome {{
                font-weight: bold;
                color: #2c5aa0;
                font-size: 14px;
            }}
            
            .footer {{
                margin-top: 30px;
                display: flex;
                justify-content: space-between;
                align-items: flex-end;
            }}
            
            .qr-code {{
                text-align: center;
            }}
            
            .qr-code img {{
                width: 80px;
                height: 80px;
            }}
            
            .assinatura {{
                text-align: center;
                border-top: 1px solid #333;
                padding-top: 5px;
                width: 200px;
            }}
            
            .receita-id {{
                font-size: 10px;
                color: #666;
                text-align: center;
                margin-top: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="clinica-nome">{clinica_nome}</div>
            <div class="clinica-info">
                {clinica_endereco}<br>
                Tel: {clinica_telefone}
            </div>
        </div>
        
        <div class="medico-info">
            <strong>Médico:</strong> {medico_nome}<br>
            <strong>CRM:</strong> {medico_crm}<br>
            <strong>Especialidade:</strong> {medico_especialidade}
        </div>
        
        <div class="paciente-info">
            <strong>Paciente:</strong> {paciente_nome}<br>
            {f'<strong>CPF:</strong> {paciente_cpf}<br>' if paciente_cpf else ''}
            {f'<strong>Data de Nascimento:</strong> {paciente_nascimento}<br>' if paciente_nascimento else ''}
            {f'<strong>Endereço:</strong> {paciente_endereco}<br>' if paciente_endereco else ''}
        </div>
        
        <div class="medicamentos">
            <h3>PRESCRIÇÃO MÉDICA</h3>
    """
    
    # Adicionar medicamentos
    if medicamentos:
        for i, med in enumerate(medicamentos, 1):
            nome = med.get('nome', '')
            posologia = med.get('posologia', '')
            quantidade = med.get('quantidade', '')
            obs_med = med.get('observacoes', '')
            
            html_content += f"""
            <div class="medicamento">
                <div class="medicamento-nome">{i}. {nome}</div>
                {f'<strong>Posologia:</strong> {posologia}<br>' if posologia else ''}
                {f'<strong>Quantidade:</strong> {quantidade}<br>' if quantidade else ''}
                {f'<strong>Observações:</strong> {obs_med}<br>' if obs_med else ''}
            </div>
            """
    else:
        html_content += """
        <div class="medicamento">
            <div class="medicamento-nome">Medicamento não especificado</div>
        </div>
        """
    
    # Finalizar HTML
    html_content += f"""
        </div>
        
        {f'<div><strong>Observações Gerais:</strong><br>{observacoes}</div>' if observacoes else ''}
        
        <div class="footer">
            <div class="qr-code">
                <img src="{qr_data_uri}" alt="QR Code de Verificação">
                <div style="font-size: 8px; margin-top: 5px;">Verificação Digital</div>
            </div>
            
            <div class="assinatura">
                {medico_nome}<br>
                CRM: {medico_crm}
            </div>
        </div>
        
        <div class="receita-id">
            Receita ID: {receita_id} | Data: {data_atual}
        </div>
    </body>
    </html>
    """
    
    return html_content


def assinar_pdf_com_pyhanko(pdf_bytes, certificate_path, certificate_password):
    """Assina o PDF usando PyHanko com certificado e timestamp"""
    
    # Carregar certificado
    with open(certificate_path, 'rb') as cert_file:
        cert_data = cert_file.read()
    
    # Criar signer
    signer = signers.SimpleSigner.load_pkcs12(
        pfx_data=cert_data,
        passphrase=certificate_password.encode('utf-8')
    )
    
    # Configurar timestamp (opcional)
    timestamper = None
    timestamp_url = getattr(settings, 'TIMESTAMP_URL', 'http://timestamp.digicert.com')
    if timestamp_url:
        try:
            timestamper = HTTPTimeStamper(timestamp_url)
        except Exception:
            timestamper = None
    
    # Preparar PDF para assinatura
    pdf_reader = PdfFileReader(BytesIO(pdf_bytes))
    writer = IncrementalPdfFileWriter(pdf_reader)
    
    # Configurar metadados da assinatura
    signature_meta = signers.PdfSignatureMetadata(
        field_name='Signature',
        md_algorithm='sha256',
        timestamper=timestamper
    )
    
    # Criar assinador PDF
    pdf_signer = signers.PdfSigner(
        signature_meta=signature_meta,
        signer=signer,
        md_algorithm='sha256'
    )
    
    # Assinar PDF
    output_buffer = BytesIO()
    pdf_signer.sign_pdf(writer, output=output_buffer)
    
    return output_buffer.getvalue()


@csrf_exempt
def simple_pdf_generator(request):
    """
    Endpoint simples para gerar PDF sem autenticação
    """
    try:
        # Parse JSON data
        if request.body:
            data = json.loads(request.body.decode('utf-8'))
        else:
            data = {}
        
        # Create PDF
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        
        # Add content to PDF (removing special characters)
        p.drawString(100, 750, "RECEITA MÉDICA")
        p.drawString(100, 720, "=" * 50)
        
        # Doctor info
        medico = data.get('medico', {})
        p.drawString(100, 680, f"Médico: {medico.get('nome', 'N/A')}")
        p.drawString(100, 660, f"CRM: {medico.get('crm', 'N/A')}")
        p.drawString(100, 640, f"Especialidade: {medico.get('especialidade', 'N/A')}")
        
        # Patient info
        paciente = data.get('paciente', {})
        p.drawString(100, 600, f"Paciente: {paciente.get('nome', 'N/A')}")
        p.drawString(100, 580, f"Idade: {paciente.get('idade', 'N/A')}")
        p.drawString(100, 560, f"CPF: {paciente.get('cpf', 'N/A')}")
        
        # Medications
        medicamentos = data.get('medicamentos', [])
        y_pos = 520
        p.drawString(100, y_pos, "MEDICAMENTOS:")
        y_pos -= 20
        
        for med in medicamentos:
            p.drawString(120, y_pos, f"• {med.get('nome', 'N/A')} - {med.get('dosagem', 'N/A')}")
            y_pos -= 15
            p.drawString(140, y_pos, f"Frequência: {med.get('frequencia', 'N/A')}")
            y_pos -= 15
            p.drawString(140, y_pos, f"Duração: {med.get('duracao', 'N/A')}")
            y_pos -= 25
        
        # Observations
        observacoes = data.get('observacoes', '')
        if observacoes:
            p.drawString(100, y_pos, f"Observações: {observacoes}")
        
        p.showPage()
        p.save()
        
        # Return PDF
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="receita.pdf"'
        
        return response
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# Função auxiliar para gerar HTML da receita
# Função auxiliar para assinar PDF com pyHanko
def assinar_pdf_com_pyhanko(pdf_bytes, cert_path, cert_password):
    """
    Assina um PDF usando pyHanko com certificado e senha
    """
    try:
        # Carregar certificado
        with open(cert_path, 'rb') as cert_file:
            cert_data = cert_file.read()
        
        # Criar signer
        signer = signers.SimpleSigner.load_pkcs12(
            pfx_data=cert_data,
            passphrase=cert_password.encode('utf-8') if cert_password else None
        )
        
        # Configurar timestamper (opcional)
        timestamper = None
        try:
            timestamper = HTTPTimeStamper('http://timestamp.digicert.com')
        except:
            pass  # Continuar sem timestamp se não conseguir conectar
        
        # Preparar PDF para assinatura
        pdf_reader = PdfFileReader(BytesIO(pdf_bytes))
        writer = IncrementalPdfFileWriter(pdf_reader)
        
        # Configurar metadados da assinatura
        signature_meta = signers.PdfSignatureMetadata(
            field_name='Signature',
            md_algorithm='sha256',
            timestamper=timestamper
        )
        
        # Criar assinador PDF
        pdf_signer = signers.PdfSigner(
            signature_meta=signature_meta,
            signer=signer,
            md_algorithm='sha256'
        )
        
        # Assinar PDF
        output_buffer = BytesIO()
        pdf_signer.sign_pdf(writer, output=output_buffer)
        
        return output_buffer.getvalue()
    
    except Exception as e:
        raise Exception(f"Erro ao assinar PDF: {str(e)}")


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def assinar_receita(request):
    """
    Endpoint para assinar receita médica
    POST /api/assinar-receita/
    
    Atualiza o status de assinatura da receita no banco de dados
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método não permitido'}, status=405)
    
    try:
        # Parse dos dados JSON
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body.decode('utf-8'))
            except UnicodeDecodeError:
                data = json.loads(request.body.decode('latin-1'))
        else:
            data = request.data if hasattr(request, 'data') else {}
        
        # Obter ID da receita
        receita_id = data.get('receita_id') or data.get('id') or data.get('receitaId')
        if not receita_id:
            return JsonResponse({'error': 'ID da receita é obrigatório'}, status=400)
        
        # Buscar a receita no banco
        try:
            receita = Receita.objects.get(pk=receita_id)
        except Receita.DoesNotExist:
            return JsonResponse({'error': 'Receita não encontrada'}, status=404)
        
        # Verificar se o usuário tem permissão (deve ser médico)
        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'error': 'Usuário não autenticado'}, status=401)
        
        # Verificar se é médico
        if not (hasattr(user, 'medico') and user.medico):
            return JsonResponse({'error': 'Apenas médicos podem assinar receitas'}, status=403)
        
        # Atualizar campos de assinatura
        receita.assinada = True
        receita.assinada_por = user
        receita.assinada_em = timezone.now()
        
        # Atualizar outros campos se fornecidos
        if data.get('algoritmo_assinatura'):
            receita.algoritmo_assinatura = data.get('algoritmo_assinatura')
        
        if data.get('hash_documento'):
            receita.hash_documento = data.get('hash_documento')
        
        if data.get('carimbo_tempo'):
            receita.carimbo_tempo = data.get('carimbo_tempo')
        else:
            receita.carimbo_tempo = timezone.now().isoformat()
        
        # Salvar no banco de dados
        receita.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Receita assinada com sucesso',
            'receita_id': receita.id,
            'assinada': receita.assinada,
            'assinada_em': receita.assinada_em.isoformat() if receita.assinada_em else None,
            'assinada_por': receita.assinada_por.username if receita.assinada_por else None
        })
        
    except Exception as e:
        return JsonResponse({'error': f'Erro interno: {str(e)}'}, status=500)


@csrf_exempt
@api_view(['GET', 'POST'])
@permission_classes([permissions.AllowAny])
def test_pdf_endpoint(request):
    """
    Endpoint de teste para geração de PDF sem autenticação
    """
    if request.method == 'GET':
        return JsonResponse({'message': 'Endpoint de teste funcionando!', 'method': 'GET'})
    elif request.method == 'POST':
        try:
            # Implementação simplificada de geração de PDF
            from django.http import HttpResponse
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            from io import BytesIO
            import json
            
            # Tentar ler dados JSON se fornecidos
            data = {}
            if request.body:
                # Parse JSON data with proper encoding handling
                if request.body:
                    try:
                        # Try UTF-8 first
                        body_str = request.body.decode('utf-8')
                    except UnicodeDecodeError:
                        # Fallback to latin-1 if UTF-8 fails
                        body_str = request.body.decode('latin-1')
                    
                    data = json.loads(body_str)
                else:
                    data = {}
                
                # Create PDF
                buffer = BytesIO()
                p = canvas.Canvas(buffer, pagesize=letter)
                
                # Add content to PDF (removing special characters)
                p.drawString(100, 750, "RECEITA MEDICA")
                p.drawString(100, 720, "=" * 50)
                
                # Doctor info
                medico = data.get('medico', {})
                p.drawString(100, 680, f"Medico: {medico.get('nome', 'N/A')}")
                p.drawString(100, 660, f"CRM: {medico.get('crm', 'N/A')}")
                p.drawString(100, 640, f"Especialidade: {medico.get('especialidade', 'N/A')}")
                
                # Patient info
                paciente = data.get('paciente', {})
                p.drawString(100, 600, f"Paciente: {paciente.get('nome', 'N/A')}")
                p.drawString(100, 580, f"Idade: {paciente.get('idade', 'N/A')}")
                p.drawString(100, 560, f"CPF: {paciente.get('cpf', 'N/A')}")
                
                # Medications
                medicamentos = data.get('medicamentos', [])
                y_pos = 520
                p.drawString(100, y_pos, "MEDICAMENTOS:")
                y_pos -= 20
                
                for med in medicamentos:
                    p.drawString(120, y_pos, f"• {med.get('nome', 'N/A')} - {med.get('dosagem', 'N/A')}")
                    y_pos -= 15
                    p.drawString(140, y_pos, f"Frequencia: {med.get('frequencia', 'N/A')}")
                    y_pos -= 15
                    p.drawString(140, y_pos, f"Duracao: {med.get('duracao', 'N/A')}")
                    y_pos -= 25
                
                # Observations
                observacoes = data.get('observacoes', '')
                if observacoes:
                    p.drawString(100, y_pos, f"Observacoes: {observacoes}")
            
            p.showPage()
            p.save()
            
            # Return PDF
            buffer.seek(0)
            response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="receita.pdf"'
            return response
            
        except Exception as e:
            return JsonResponse({'error': f'Erro no teste: {str(e)}'}, status=500)
    
    return JsonResponse({'error': 'Método não permitido'}, status=405)


def safe_text(text):
    """
    Função auxiliar para garantir que o texto seja seguro para PDF
    """
    if not text:
        return ''
    
    # Garantir que é string
    if not isinstance(text, str):
        text = str(text)
    
    # Remover caracteres problemáticos e normalizar
    import unicodedata
    text = unicodedata.normalize('NFKD', text)
    
    # Substituir caracteres especiais problemáticos
    replacements = {
        'ã': 'a', 'á': 'a', 'à': 'a', 'â': 'a', 'ä': 'a',
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
        'õ': 'o', 'ó': 'o', 'ò': 'o', 'ô': 'o', 'ö': 'o',
        'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
        'ç': 'c', 'ñ': 'n',
        'Ã': 'A', 'Á': 'A', 'À': 'A', 'Â': 'A', 'Ä': 'A',
        'É': 'E', 'È': 'E', 'Ê': 'E', 'Ë': 'E',
        'Í': 'I', 'Ì': 'I', 'Î': 'I', 'Ï': 'I',
        'Õ': 'O', 'Ó': 'O', 'Ò': 'O', 'Ô': 'O', 'Ö': 'O',
        'Ú': 'U', 'Ù': 'U', 'Û': 'U', 'Ü': 'U',
        'Ç': 'C', 'Ñ': 'N'
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    return text


def gerar_pdf_com_reportlab(data, qr_data_uri, receita_id):
    """
    Gera PDF profissional usando ReportLab com formatação médica completa
    """
    from datetime import datetime
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    import base64
    import tempfile
    import os
    
    buffer = BytesIO()
    
    # Criar documento com margens profissionais
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72
    )
    
    # Estilos personalizados
    styles = getSampleStyleSheet()
    
    # Estilo para título principal
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=30,
        alignment=TA_CENTER,
        textColor=colors.darkblue,
        fontName='Helvetica-Bold'
    )
    
    # Estilo para subtítulos
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=12,
        spaceBefore=20,
        textColor=colors.darkblue,
        fontName='Helvetica-Bold'
    )
    
    # Estilo para texto normal
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=6,
        fontName='Helvetica'
    )
    
    # Estilo para informações importantes
    info_style = ParagraphStyle(
        'CustomInfo',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=4,
        fontName='Helvetica',
        textColor=colors.black
    )
    
    # Lista de elementos do documento
    story = []
    
    # Cabeçalho com informações da clínica
    clinica_nome = safe_text(data.get('clinica_nome', 'CLINICA MEDICA TCC'))
    clinica_endereco = safe_text(data.get('clinica_endereco', 'Rua das Flores, 123 - Centro - Sao Paulo/SP'))
    clinica_telefone = safe_text(data.get('clinica_telefone', '(11) 1234-5678'))
    clinica_email = safe_text(data.get('clinica_email', 'contato@clinicatcc.com.br'))
    
    # Título principal
    story.append(Paragraph("RECEITA MEDICA", title_style))
    
    # Informações da clínica em tabela
    clinica_data = [
        [clinica_nome],
        [clinica_endereco],
        [f"Tel: {clinica_telefone} | Email: {clinica_email}"],
        [f"Receita No: {receita_id} | Data: {datetime.now().strftime('%d/%m/%Y as %H:%M')}"]
    ]
    
    clinica_table = Table(clinica_data, colWidths=[6*inch])
    clinica_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.lightgrey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
    ]))
    
    story.append(clinica_table)
    story.append(Spacer(1, 20))
    
    # Informações do médico
    story.append(Paragraph("DADOS DO MEDICO", subtitle_style))
    
    medico_nome = safe_text(data.get('medico_nome', ''))
    medico_crm = safe_text(data.get('medico_crm', ''))
    medico_especialidade = safe_text(data.get('medico_especialidade', 'Clinica Geral'))
    medico_telefone = safe_text(data.get('medico_telefone', ''))
    
    medico_data = [
        ['Nome:', medico_nome],
        ['CRM:', medico_crm],
        ['Especialidade:', medico_especialidade],
    ]
    
    if medico_telefone:
        medico_data.append(['Telefone:', medico_telefone])
    
    medico_table = Table(medico_data, colWidths=[1.5*inch, 4.5*inch])
    medico_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    
    story.append(medico_table)
    story.append(Spacer(1, 15))
    
    # Informações do paciente
    story.append(Paragraph("DADOS DO PACIENTE", subtitle_style))
    
    paciente_nome = safe_text(data.get('paciente_nome', ''))
    paciente_cpf = safe_text(data.get('paciente_cpf', ''))
    paciente_nascimento = safe_text(data.get('paciente_nascimento', ''))
    paciente_telefone = safe_text(data.get('paciente_telefone', ''))
    
    paciente_data = [
        ['Nome:', paciente_nome],
        ['CPF:', paciente_cpf],
    ]
    
    if paciente_nascimento:
        paciente_data.append(['Data de Nascimento:', paciente_nascimento])
    if paciente_telefone:
        paciente_data.append(['Telefone:', paciente_telefone])
    
    paciente_table = Table(paciente_data, colWidths=[1.5*inch, 4.5*inch])
    paciente_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    
    story.append(paciente_table)
    story.append(Spacer(1, 20))
    
    # Medicamentos prescritos
    story.append(Paragraph("MEDICAMENTOS PRESCRITOS", subtitle_style))
    
    medicamentos = data.get('medicamentos', [])
    
    if medicamentos:
        # Cabeçalho da tabela de medicamentos
        med_data = [['#', 'Medicamento', 'Posologia', 'Quantidade']]
        
        for i, med in enumerate(medicamentos, 1):
            nome = safe_text(med.get('nome', ''))
            posologia = safe_text(med.get('posologia', ''))
            quantidade = safe_text(med.get('quantidade', ''))
            duracao = safe_text(med.get('duracao', ''))
            
            # Adicionar duração à posologia se disponível
            posologia_completa = posologia
            if duracao:
                posologia_completa += f" por {duracao}"
            
            med_data.append([str(i), nome, posologia_completa, quantidade])
        
        med_table = Table(med_data, colWidths=[0.5*inch, 2.5*inch, 2*inch, 1*inch])
        med_table.setStyle(TableStyle([
            # Cabeçalho
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            
            # Dados
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # Numeração centralizada
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Bordas
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            
            # Padding
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(med_table)
    else:
        story.append(Paragraph("Nenhum medicamento prescrito.", normal_style))
    
    story.append(Spacer(1, 20))
    
    # Observações
    observacoes = safe_text(data.get('observacoes', ''))
    if observacoes:
        story.append(Paragraph("OBSERVACOES MEDICAS", subtitle_style))
        story.append(Paragraph(observacoes, normal_style))
        story.append(Spacer(1, 20))
    
    # QR Code e informações de verificação
    story.append(Paragraph("VERIFICACAO DE AUTENTICIDADE", subtitle_style))
    
    # Informações de verificação sem QR code por enquanto
    verify_info = f"""
    Código de Verificação: {receita_id}
    
    Para verificar a autenticidade desta receita,
    acesse o sistema de verificação online.
    
    Data de emissão: {datetime.now().strftime('%d/%m/%Y às %H:%M')}
    """
    
    story.append(Paragraph(verify_info, normal_style))
    
    # Rodapé com assinatura
    story.append(Spacer(1, 30))
    
    assinatura_data = [
        ["_" * 50],
        [f"Dr(a). {medico_nome}"],
        [f"CRM: {medico_crm}"],
        [f"Especialidade: {medico_especialidade}"]
    ]
    
    assinatura_table = Table(assinatura_data, colWidths=[3*inch])
    assinatura_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    
    story.append(assinatura_table)
    
    # Gerar PDF
    doc.build(story)
    
    buffer.seek(0)
    return buffer.getvalue()


# ViewSet para ReceitaItem
from ..models import ReceitaItem, Medicamento
from ..serializers import ReceitaItemSerializer, MedicamentoSerializer

class ReceitaItemViewSet(viewsets.ModelViewSet):
    """ViewSet para gerenciar itens de receita"""
    queryset = ReceitaItem.objects.select_related('receita', 'medicamento').all()
    serializer_class = ReceitaItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['receita', 'medicamento']
    search_fields = ['medicamento__nome', 'dose', 'frequencia', 'duracao', 'observacoes']
    ordering_fields = ['id', 'receita', 'medicamento']
    ordering = ['id']

class MedicamentoViewSet(viewsets.ModelViewSet):
    """ViewSet para gerenciar medicamentos"""
    queryset = Medicamento.objects.filter(ativo=True).order_by('nome')
    serializer_class = MedicamentoSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['apresentacao', 'fabricante', 'ativo']
    search_fields = ['nome', 'apresentacao', 'concentracao', 'fabricante']
    ordering_fields = ['nome', 'apresentacao', 'concentracao']
    ordering = ['nome']
