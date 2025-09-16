from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from django.conf import settings
from django.utils.crypto import get_random_string
from ..models import User, Paciente, Medico

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def register_view(request):
    from ..serializers import UserSerializer
    serializer = UserSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        # Cria perfil de médico pendente, caso role seja 'medico'
        role_in = (serializer.validated_data.get('role') or request.data.get('role') or '').lower()
        if role_in == 'medico':
            crm = request.data.get('crm') or ''
            Medico.objects.get_or_create(user=user, defaults={'crm': crm, 'status': 'pendente'})
        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role
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
        Paciente.objects.get_or_create(user=user)
    elif role == 'medico':
        crm = request.data.get('crm') or ''
        Medico.objects.get_or_create(user=user, defaults={'crm': crm, 'status': 'pendente'})
    token, _ = Token.objects.get_or_create(user=user)
    return Response({
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role
        },
        'token': token.key,
        'message': 'Conta criada e login via Google realizado com sucesso!'
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