#!/usr/bin/env python
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medicine_back.settings')
django.setup()

from meu_app.models import *
from django.contrib.auth import get_user_model
from datetime import datetime

User = get_user_model()

# Get test doctor
user = User.objects.get(username='testdoctor')
medico = user.medico

# Get or create a patient
paciente = Paciente.objects.first()
if not paciente:
    # Create a test patient
    patient_user = User.objects.create_user(
        username='testpatient',
        email='patient@test.com',
        first_name='Test',
        last_name='Patient'
    )
    paciente = Paciente.objects.create(
        user=patient_user,
        cpf='12345678901',
        telefone='11999999999'
    )

# Create consultation
consulta = Consulta.objects.create(
    medico=medico,
    paciente=paciente,
    data_hora=datetime.now(),
    status='agendada',
    motivo='Consulta de teste'
)

# Create prescription
from datetime import timedelta
import hashlib

receita = Receita.objects.create(
    consulta=consulta,
    medicamentos='Paracetamol 500mg',
    posologia='1 comprimido de 8 em 8 horas por 3 dias',
    observacoes='Tomar após as refeições',
    validade=datetime.now().date() + timedelta(days=30),
    # Campos de assinatura digital
    assinada=True,
    assinada_por=medico.user,
    assinada_em=datetime.now(),
    algoritmo_assinatura='SHA-256',
    hash_documento=hashlib.sha256(b'test_document_content').hexdigest(),
    carimbo_tempo=datetime.now().isoformat()
)

print(f'Receita criada com sucesso!')
print(f'ID: {receita.id}')
print(f'Assinada: {receita.assinada}')
print(f'Hash do documento: {receita.hash_documento}')
print(f'Médico: {medico.user.username}')
print(f'Paciente: {paciente.user.username}')
print(f'URL de verificação: http://localhost:5175/verificar/{receita.id}')