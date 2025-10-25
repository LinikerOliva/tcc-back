from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser
from rest_framework import status, permissions

# cryptography imports
try:
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID
except Exception:
    pkcs12 = None
    NameOID = None

from datetime import datetime
import traceback

class ValidateCertificateView(APIView):
    """
    POST /assinatura/certificado/
    Valida senha do certificado A1 (.pfx/.p12) e retorna dados básicos.
    - Não persiste o arquivo nem a senha.
    - Em caso de senha inválida, retorna 400 com mensagem clara.
    """
    parser_classes = (MultiPartParser,)
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # Permite múltiplos aliases para maior compatibilidade com o front
        certificate_file = (
            request.FILES.get('certificate') or
            request.FILES.get('certificado') or
            request.FILES.get('pfx') or
            request.FILES.get('arquivo') or
            None
        )
        password = (
            request.data.get('password') or
            request.data.get('senha') or
            request.data.get('passphrase') or
            request.data.get('pfx_password') or
            None
        )

        if certificate_file is None or not password:
            return Response({
                'error': 'Arquivo (.pfx/.p12) e senha são obrigatórios.'
            }, status=status.HTTP_400_BAD_REQUEST)

        if pkcs12 is None:
            return Response({
                'error': 'Biblioteca cryptography não disponível no servidor.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            # Lê o arquivo em memória
            pfx_data = certificate_file.read()
            # Tenta abrir usando a senha fornecida
            private_key, certificate, additional = pkcs12.load_key_and_certificates(
                pfx_data,
                password.encode('utf-8')
            )

            if not private_key or not certificate:
                return Response({
                    'error': 'Certificado ou chave privada não encontrados no arquivo PFX.'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Extrai dados
            subject_name = None
            issuer_name = None
            try:
                subject_name = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
            except Exception:
                subject_name = str(certificate.subject.rfc4514_string())
            try:
                issuer_name = certificate.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
            except Exception:
                issuer_name = str(certificate.issuer.rfc4514_string())

            # Datas (compatíveis com versões da cryptography)
            valid_from = getattr(certificate, 'not_valid_before', None)
            valid_to = getattr(certificate, 'not_valid_after', None)
            # Algumas versões expõem *_utc; mantenha fallback
            valid_from = getattr(certificate, 'not_valid_before_utc', valid_from)
            valid_to = getattr(certificate, 'not_valid_after_utc', valid_to)

            def _iso(dt: datetime):
                try:
                    return dt.isoformat()
                except Exception:
                    return str(dt)

            return Response({
                'status': 'sucesso',
                'owner_name': subject_name,
                'issuer_name': issuer_name,
                'valid_from': _iso(valid_from) if valid_from else None,
                'valid_to': _iso(valid_to) if valid_to else None,
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            # Erros comuns: senha inválida ou MAC verification falhou
            msg = str(e).lower()
            if 'decryption failed' in msg or 'mac verification failed' in msg or 'invalid password' in msg:
                return Response({'error': 'Senha do certificado inválida.'}, status=status.HTTP_400_BAD_REQUEST)
            # Outros ValueError relacionados ao arquivo
            return Response({'error': f'Erro ao processar o certificado: {str(e)[:100]}'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Log para depuração
            print('Erro inesperado na validação de certificado:', e)
            print(traceback.format_exc())
            return Response({'error': f'Erro inesperado no servidor: {str(e)[:100]}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)