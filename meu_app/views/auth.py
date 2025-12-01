from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from django.core.mail import send_mail
from django.contrib.auth.forms import PasswordResetForm
from django.conf import settings
from django.utils.crypto import get_random_string
from ..models import User, Paciente, Medico, SolicitacaoMedico
from pathlib import Path
import os
from django.shortcuts import redirect
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def register_view(request):
    from ..serializers import UserSerializer
    serializer = UserSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        role_in = (serializer.validated_data.get('role') or request.data.get('role') or '').lower()
        # Fluxo por papel
        if role_in == 'medico':
            # Bloqueia login até aprovação
            user.is_active = False
            user.save(update_fields=['is_active'])
            # Cria solicitação vinculada
            SolicitacaoMedico.objects.get_or_create(user=user, defaults={
                'status': 'pendente',
                'crm': request.data.get('crm') or ''
            })
            # Envia e-mail de recebimento
            try:
                send_mail(
                    subject='Cadastro de Médico recebido',
                    message='Recebemos seu cadastro como Médico. Aguarde a aprovação do administrador.',
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                    recipient_list=[user.email],
                    fail_silently=True,
                )
            except Exception:
                pass
            return Response({
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'role': user.role,
                    'is_active': user.is_active,
                },
                'message': 'Cadastro de médico recebido. Aguarde aprovação.'
            }, status=status.HTTP_201_CREATED)
        else:
            # Paciente: ativa e cria perfil
            user.is_active = True
            user.save(update_fields=['is_active'])
            Paciente.objects.get_or_create(user=user)
            token, _ = Token.objects.get_or_create(user=user)
            return Response({
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'role': user.role,
                    'is_active': user.is_active,
                },
                'token': token.key,
                'message': 'Usuário criado com sucesso!'
            }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login_view(request):
    identifier = request.data.get('username') or request.data.get('email') or request.data.get('identifier')
    password = request.data.get('password')
    if not identifier or not password:
        return Response({'error': 'Username/email e password são obrigatórios'}, status=status.HTTP_400_BAD_REQUEST)
    user = authenticate(username=identifier, password=password)
    if not user:
        user_obj = User.objects.filter(email__iexact=identifier).first()
        if user_obj:
            user = authenticate(username=user_obj.username, password=password)
    if user:
        if not getattr(user, 'is_active', True):
            return Response({'error': 'Cadastro em análise. Aguarde aprovação.'}, status=status.HTTP_403_FORBIDDEN)
        if getattr(user, 'role', None) == 'paciente':
            Paciente.objects.get_or_create(user=user)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role
            },
            'token': token.key,
            'message': 'Login realizado com sucesso!'
        }, status=status.HTTP_200_OK)
    else:
        return Response({'error': 'Credenciais inválidos'}, status=status.HTTP_401_UNAUTHORIZED)

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def google_login_view(request):
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
    except Exception:
        return Response({'error': 'Dependência google-auth não instalada.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    id_token_str = request.data.get('id_token')
    if not id_token_str:
        return Response({'error': 'id_token é obrigatório'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        idinfo = google_id_token.verify_oauth2_token(
            id_token_str,
            google_requests.Request(),
            settings.GOOGLE_OAUTH_CLIENT_ID
        )
        email = idinfo.get('email')
        email_verified = idinfo.get('email_verified', False)
        given_name = idinfo.get('given_name') or ''
        family_name = idinfo.get('family_name') or ''
        sub = idinfo.get('sub')
    except Exception as e:
        return Response({'error': f'ID token inválido: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

    if not email or not email_verified:
        return Response({'error': 'Email ausente ou não verificado pelo Google'}, status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.filter(email__iexact=email).first()
    if user:
        if not getattr(user, 'is_active', True):
            return Response({'error': 'Cadastro em análise. Aguarde aprovação.'}, status=status.HTTP_403_FORBIDDEN)
        if getattr(user, 'role', None) == 'paciente':
            Paciente.objects.get_or_create(user=user)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role
            },
            'token': token.key,
            'message': 'Login via Google realizado com sucesso!'
        }, status=status.HTTP_200_OK)

    cpf = request.data.get('cpf')
    if not cpf:
        return Response({
            'error': 'Primeiro acesso com Google requer CPF',
            'detail': 'Envie também o campo "cpf" no formato XXX.XXX.XXX-XX'
        }, status=status.HTTP_400_BAD_REQUEST)

    role = (request.data.get('role') or 'paciente').lower()

    base_username = (email.split('@')[0] or f'user_{sub}')[:20]
    candidate = base_username
    suffix = 1
    while User.objects.filter(username__iexact=candidate).exists():
        candidate = f"{base_username[:15]}{suffix}"
        suffix += 1

    user = User(
        username=candidate,
        email=email,
        first_name=given_name,
        last_name=family_name,
        role=role,
        cpf=cpf
    )
    user.set_unusable_password()
    try:
        user.save()
    except Exception as e:
        return Response({'error': 'Falha ao criar usuário', 'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    if role == 'paciente':
        user.is_active = True
        user.save(update_fields=['is_active'])
        Paciente.objects.get_or_create(user=user)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role,
            },
            'token': token.key,
            'message': 'Conta criada e login via Google realizado com sucesso!'
        }, status=status.HTTP_201_CREATED)
    elif role == 'medico':
        user.is_active = False
        user.save(update_fields=['is_active'])
        SolicitacaoMedico.objects.get_or_create(user=user, defaults={
            'status': 'pendente',
            'crm': request.data.get('crm') or ''
        })
        try:
            send_mail(
                subject='Cadastro de Médico recebido',
                message='Recebemos seu cadastro como Médico. Aguarde a aprovação do administrador.',
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                recipient_list=[user.email],
                fail_silently=True,
            )
        except Exception:
            pass
        return Response({
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role,
                'is_active': user.is_active,
            },
            'message': 'Cadastro de médico recebido. Aguarde aprovação.'
        }, status=status.HTTP_201_CREATED)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def mfa_setup(request):
    user = request.user
    if getattr(user, 'mfa_enabled', False) and getattr(user, 'mfa_secret', ''):
        issuer = getattr(settings, 'SECURITY', {}).get('MFA_ISSUER', 'TCC-Clinico')
        label = user.email or user.username
        secret = user.mfa_secret
        otpauth_uri = f'otpauth://totp/{issuer}:{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30'
        return Response({
            'detail': 'MFA já habilitado.',
            'secret': secret,
            'otpauth_uri': otpauth_uri,
            'enabled': True,
        }, status=status.HTTP_200_OK)
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
    secret = get_random_string(32, allowed_chars=alphabet)
    user.mfa_secret = secret
    user.mfa_enabled = False
    user.save(update_fields=['mfa_secret', 'mfa_enabled'])
    issuer = getattr(settings, 'SECURITY', {}).get('MFA_ISSUER', 'TCC-Clinico')
    label = user.email or user.username
    otpauth_uri = f'otpauth://totp/{issuer}:{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30'
    return Response({
        'detail': 'Secret gerado. Configure no seu app autenticador e verifique pelo endpoint /auth/mfa/verify.',
        'secret': secret,
        'otpauth_uri': otpauth_uri,
        'enabled': False,
    }, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def mfa_verify(request):
    return Response({
        'detail': 'Endpoint de verificação MFA ainda não implementado (placeholder).'
    }, status=status.HTTP_501_NOT_IMPLEMENTED)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def logout_view(request):
    try:
        token = Token.objects.get(user=request.user)
        token.delete()
    except Token.DoesNotExist:
        pass
    return Response({"detail": "Logout realizado com sucesso."}, status=status.HTTP_200_OK)

# NOVO: Endpoint para obter o usuário autenticado (/api/auth/users/me/)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def current_user_view(request):
    try:
        from ..serializers import UserSerializer
    except Exception:
        return Response({"detail": "Serializer não disponível"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    serializer = UserSerializer(request.user)
    return Response(serializer.data, status=status.HTTP_200_OK)

# NOVO: Endpoint REST para envio de e-mail de reset de senha

# Helper: garantir/criar templates de reset com conteúdo definido
def ensure_password_reset_templates():
    base_dir = Path(settings.BASE_DIR)
    reg_dir = base_dir / 'meu_app' / 'templates' / 'registration'
    reg_dir.mkdir(parents=True, exist_ok=True)
    subject_path = reg_dir / 'password_reset_subject.txt'
    email_path = reg_dir / 'password_reset_email.html'

    subject_content = "Redefinição de senha - Minha Plataforma"
    email_content = """<!doctype html>
<html lang=\"pt-BR\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"color-scheme\" content=\"light only\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Redefinição de senha</title>
    <style>
      body { font-family: Arial, sans-serif; color: #1f2937; line-height: 1.6; }
      .btn { display: inline-block; background-color: #2563eb; color: #fff; text-decoration: none; padding: 10px 16px; border-radius: 6px; }
      .muted { color: #6b7280; font-size: 13px; }
      .container { max-width: 600px; margin: 0 auto; padding: 12px; }
    </style>
  </head>
  <body>
    <div class=\"container\">
      <p>Olá,</p>
      <p>Recebemos uma solicitação para redefinir sua senha na <strong>Minha Plataforma</strong>.</p>
      <p>Para continuar com segurança, clique no botão abaixo:</p>
      <p>
        <a href=\"{{ frontend_base }}/redefinir-senha/{{ uid }}/{{ token }}\" style=\"display:inline-block;background-color:#2563eb;color:#ffffff !important;text-decoration:none;padding:10px 16px;border-radius:6px;\">Redefinir minha senha</a>
      </p>
      <p>Se preferir, copie e cole o link no navegador:</p>
      <p><a href=\"{{ frontend_base }}/redefinir-senha/{{ uid }}/{{ token }}\" style=\"color:#2563eb;text-decoration:underline;\">{{ frontend_base }}/redefinir-senha/{{ uid }}/{{ token }}</a></p>

      <p class=\"muted\">Se você não solicitou esta alteração, ignore este e‑mail. Não é necessária nenhuma ação.</p>
      <p class=\"muted\">Por segurança, este link expira em breve. Caso expire, solicite uma nova redefinição.</p>
      <p class=\"muted\">Atenciosamente,<br/>Equipe Minha Plataforma</p>
    </div>
  </body>
</html>
"""

    try:
        if not subject_path.exists() or subject_path.read_text(encoding="utf-8") != subject_content:
            subject_path.write_text(subject_content, encoding="utf-8")
        if not email_path.exists() or email_path.read_text(encoding="utf-8") != email_content:
            email_path.write_text(email_content, encoding="utf-8")
    except Exception as e:
        print(f"DEBUG: não foi possível garantir templates: {e}")

# Helper: imprimir o e-mail no console em ambiente local (DEBUG)
def print_last_email_to_console_if_debug():
    if not getattr(settings, 'DEBUG', False):
        return
    try:
        backend = (getattr(settings, 'EMAIL_BACKEND', '') or '').lower()
        file_dir = getattr(settings, 'EMAIL_FILE_PATH', None)
        if 'filebased' in backend and file_dir:
            directory = Path(file_dir)
            files = sorted(directory.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
            if files:
                content = files[0].read_text(encoding="utf-8", errors="ignore")
                print("=== Password Reset Email (DEBUG) ===")
                print(content)
    except Exception as e:
        print(f"DEBUG: falha ao imprimir email: {e}")

# Remover decoradores indevidos do redirect e manter como view Django simples
def password_reset_redirect(request, uidb64, token):
    frontend_base = (getattr(settings, 'FRONTEND_BASE_URL', None) or getattr(settings, 'FRONTEND_URL', None) or '').strip() or 'https://seu-projeto-trathea.vercel.app'
    frontend_base = frontend_base.rstrip('/')
    return redirect(f"{frontend_base}/redefinir-senha/{uidb64}/{token}")

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def password_reset_api(request):
    email = (request.data.get('email') or '').strip()
    if not email:
        return Response({"detail": "Campo 'email' é obrigatório."}, status=status.HTTP_400_BAD_REQUEST)

    # Remetente fixo: sempre usar DEFAULT_FROM_EMAIL
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)

    # Bases para links no email (evita NameError)
    frontend_base = getattr(settings, 'FRONTEND_BASE_URL', 'http://localhost:5175').rstrip('/')
    backend_base = getattr(settings, 'BACKEND_BASE_URL', 'http://127.0.0.1:8000').rstrip('/')

    # Garante templates atualizados/criados
    ensure_password_reset_templates()

    form = PasswordResetForm({'email': email})
    if not form.is_valid():
        # Para privacidade, responder 200 mesmo se email não existir (evita enumeração)
        return Response({"detail": "Se o email existir, enviaremos instruções para redefinir a senha."}, status=status.HTTP_200_OK)

    # Envia e-mail usando templates padrão
    try:
        form.save(
            request=request,
            use_https=request.is_secure(),
            from_email=from_email,
            subject_template_name='registration/password_reset_subject.txt',
            email_template_name='registration/password_reset_email.txt',
            html_email_template_name='registration/password_reset_email.html',
            extra_email_context={
                'frontend_base': frontend_base,
                'backend_base': backend_base,
            }
        )
        print_last_email_to_console_if_debug()
        return Response({"detail": "Email de redefinição enviado."}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"detail": "Falha ao enviar email de redefinição.", "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def password_reset_confirm_api(request):
    uidb64 = (request.data.get('uid') or request.data.get('uidb64') or '').strip()
    token = (request.data.get('token') or '').strip()
    new_password = (request.data.get('new_password') or request.data.get('password') or '').strip()

    if not uidb64 or not token or not new_password:
        return Response({"detail": "Campos 'uid', 'token' e 'new_password' são obrigatórios."}, status=status.HTTP_400_BAD_REQUEST)

    # Decodifica UID e busca usuário
    try:
        UserModel = get_user_model()
        uid = urlsafe_base64_decode(uidb64).decode()
        user = UserModel.objects.get(pk=uid)
    except Exception as e:
        return Response({"detail": "Link inválido.", "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # Valida token do Django
    if not default_token_generator.check_token(user, token):
        return Response({"detail": "Token inválido ou expirado."}, status=status.HTTP_400_BAD_REQUEST)

    # Valida força da senha
    try:
        validate_password(new_password, user=user)
    except Exception as ve:
        errors = getattr(ve, 'messages', [str(ve)])
        return Response({"detail": "Senha inválida.", "errors": errors}, status=status.HTTP_400_BAD_REQUEST)

    # Atualiza senha
    user.set_password(new_password)
    user.save(update_fields=['password'])

    # Revoga tokens existentes (se houver)
    try:
        Token.objects.filter(user=user).delete()
    except Exception:
        pass

    return Response({"detail": "Senha redefinida com sucesso."}, status=status.HTTP_200_OK)
