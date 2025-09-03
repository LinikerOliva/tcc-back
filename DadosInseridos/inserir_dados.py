import os
import sys
from pathlib import Path

# Garante que o projeto esteja no sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Tenta configurar o DJANGO_SETTINGS_MODULE considerando a inconsistência observada
SETTINGS_CANDIDATES = [
    "medicine-back.settings",  # conforme asgi.py / wsgi.py
    "medicine_back.settings",  # conforme manage.py
]

django_setup_done = False
last_error = None

for candidate in SETTINGS_CANDIDATES:
    try:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", candidate)
        import django  # noqa: E402
        django.setup()
        print(f"[OK] Django inicializado com settings: {candidate}")
        django_setup_done = True
        break
    except Exception as e:
        last_error = e
        # Limpa para tentar o próximo
        if "DJANGO_SETTINGS_MODULE" in os.environ:
            del os.environ["DJANGO_SETTINGS_MODULE"]

if not django_setup_done:
    raise RuntimeError(
        f"Falha ao inicializar o Django. Verifique o nome do módulo de settings. Último erro: {last_error}"
    )

from django.db import transaction  # noqa: E402
from meu_app.models import (  # noqa: E402
    User,
    Clinica,
    Especialidade,
    Medico,
    Paciente,
)

@transaction.atomic
def main():
    print("Inserindo dados de exemplo...")

    # 1) Especialidades para o médico (ManyToMany)
    cardio, _ = Especialidade.objects.get_or_create(
        nome="Cardiologia", defaults={"descricao": "Especialidade do coração."}
    )
    clin_geral, _ = Especialidade.objects.get_or_create(
        nome="Clínica Geral", defaults={"descricao": "Atendimento clínico geral."}
    )

    # 2) Clínica
    clinica, created = Clinica.objects.get_or_create(
        nome="Clínica Saúde Total",
        defaults={
            "tipo": "Clínica de Imagem",
            "cnpj": "12.345.678/0001-90",
            "telefone": "(11) 99999-0000",
            "email": "contato@saudetotal.com",
            "endereco": "Av. Central, 1000",
            "cidade": "São Paulo",
            "estado": "SP",
        },
    )
    print(f"Clínica: {clinica.nome} ({'criada' if created else 'já existia'})")

    # 3) Médico (User + Medico)
    # User do médico
    medico_user, created = User.objects.get_or_create(
        username="drjoao",
        defaults={
            "first_name": "João",
            "last_name": "Silva",
            "email": "dr.joao@exemplo.com",
            "role": "medico",
            "cpf": "111.222.333-44",  # formato validado por regex
            "telefone": "(11) 98888-7777",
            "endereco": "Rua das Flores, 123",
        },
    )
    if created:
        medico_user.set_password("Medico123!")
        medico_user.save()
    print(f"Médico (User): {medico_user.get_full_name()} ({'criado' if created else 'já existia'})")

    # Perfil Medico
    medico, created = Medico.objects.get_or_create(
        user=medico_user,
        defaults={
            "crm": "CRM-12345",
            "biografia": "Cardiologista com experiência em clínica e hospital.",
            "formacao": "USP",
            "experiencia_anos": 10,
            "valor_consulta": 300.00,
            "ativo": True,
        },
    )
    # Vincula especialidades e clínica
    medico.especialidades.set([cardio, clin_geral])
    medico.clinicas.set([clinica])
    print(f"Perfil Médico: {medico} ({'criado' if created else 'já existia'})")

    # 4) Pacientes (2)
    # Paciente 1
    paciente1_user, created = User.objects.get_or_create(
        username="maria",
        defaults={
            "first_name": "Maria",
            "last_name": "Oliveira",
            "email": "maria@exemplo.com",
            "role": "paciente",
            "cpf": "222.333.444-55",
            "telefone": "(11) 97777-6666",
            "endereco": "Rua A, 10",
        },
    )
    if created:
        paciente1_user.set_password("Paciente123!")
        paciente1_user.save()
    paciente1, created_p1 = Paciente.objects.get_or_create(
        user=paciente1_user,
        defaults={
            "tipo_sanguineo": "O+",
            "peso": 65.5,
            "altura": 1.65,
            "alergias": "Poeira",
            "condicoes_cronicas": "Nenhuma",
        },
    )
    print(f"Paciente 1: {paciente1} ({'criado' if created_p1 else 'já existia'})")

    # Paciente 2
    paciente2_user, created = User.objects.get_or_create(
        username="carlos",
        defaults={
            "first_name": "Carlos",
            "last_name": "Santos",
            "email": "carlos@exemplo.com",
            "role": "paciente",
            "cpf": "333.444.555-66",
            "telefone": "(11) 96666-5555",
            "endereco": "Rua B, 20",
        },
    )
    if created:
        paciente2_user.set_password("Paciente123!")
        paciente2_user.save()
    paciente2, created_p2 = Paciente.objects.get_or_create(
        user=paciente2_user,
        defaults={
            "tipo_sanguineo": "A+",
            "peso": 78.2,
            "altura": 1.78,
            "alergias": "",
            "condicoes_cronicas": "Rinite alérgica",
        },
    )
    print(f"Paciente 2: {paciente2} ({'criado' if created_p2 else 'já existia'})")

    print("\nConcluído com sucesso!")

if __name__ == "__main__":
    main()