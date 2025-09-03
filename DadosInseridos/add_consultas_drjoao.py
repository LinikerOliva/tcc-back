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

from django.utils import timezone  # noqa: E402
from datetime import timedelta  # noqa: E402
from meu_app.models import (  # noqa: E402
    User,
    Clinica,
    Medico,
    Paciente,
    MedicoPaciente,
    Consulta,
)


def main():
    from django.db import connection
    print("Inserindo paciente e consultas para o médico 'drjoao'...")

    medico_user = User.objects.filter(username="drjoao").first()
    if not medico_user:
        raise RuntimeError("Usuário 'drjoao' não encontrado. Execute DadosInseridos/inserir_dados.py antes.")

    medico = Medico.objects.filter(user=medico_user).first()
    if not medico:
        raise RuntimeError("Perfil Medico para 'drjoao' não encontrado.")

    # Clinica opcional (se existir a criada pelo script de inserção)
    # Deliberadamente não usadas nas criações para isolar erro de FK
    # clinica = Clinica.objects.filter(nome="Clínica Saúde Total").first()

    # Cria um novo paciente (User + Paciente)
    paciente_user, created_user = User.objects.get_or_create(
        username="ana",
        defaults={
            "first_name": "Ana",
            "last_name": "Lima",
            "email": "ana@exemplo.com",
            "role": "paciente",
            "cpf": "444.555.666-77",
            "telefone": "(11) 95555-4444",
            "endereco": "Rua das Acácias, 45",
        },
    )
    if created_user:
        paciente_user.set_password("Paciente123!")
        paciente_user.save()

    paciente, created_paciente = Paciente.objects.get_or_create(
        user=paciente_user,
        defaults={
            "tipo_sanguineo": "O+",
            "peso": 60.0,
            "altura": 1.62,
            "alergias": "Nenhuma conhecida",
            "condicoes_cronicas": "",
        },
    )

    print(f"[INFO] Medico user_id={medico_user.id} medico.pk={medico.pk}")
    print(f"[INFO] Paciente user_id={paciente_user.id} paciente.pk={paciente.pk}")

    # Verifica presença física nas tabelas via SQL bruto
    with connection.cursor() as cursor:
        # Garantir checagem de chaves-estrangeiras ativada (SQLite)
        cursor.execute("PRAGMA foreign_keys = ON;")
        # Verificações de existência
        cursor.execute("SELECT 1 FROM meu_app_medico WHERE user_id = %s", [str(medico.pk)])
        print("[CHK] Medico existe?", bool(cursor.fetchone()))
        cursor.execute("SELECT 1 FROM meu_app_paciente WHERE id = %s", [str(paciente.pk)])
        print("[CHK] Paciente existe?", bool(cursor.fetchone()))
        # Mostrar esquema da tabela de consultas
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='meu_app_consulta'")
        schema = cursor.fetchone()
        if schema:
            print("[SCHEMA] meu_app_consulta=\n", schema[0])

    # Vinculo MedicoPaciente é opcional para este seed; omitido para isolar erros

    agora = timezone.now()

    try:
        # Consulta 1: próxima (agendada) - mínimos campos
        consulta1 = Consulta.objects.create(
            medico=medico,
            paciente=paciente,
            data_hora=(agora + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0),
            motivo="Dor torácica leve há 2 dias",
        )
        print(f"[OK] Criada consulta1 {consulta1.id}")
    except Exception as e:
        print("[ERRO] Falha ao criar consulta1:", repr(e))
        raise

    try:
        # Consulta 2: retorno confirmado - mínimos campos
        consulta2 = Consulta.objects.create(
            medico=medico,
            paciente=paciente,
            data_hora=(agora + timedelta(days=7)).replace(hour=9, minute=30, second=0, microsecond=0),
            motivo="Retorno para avaliação de exames",
        )
        print(f"[OK] Criada consulta2 {consulta2.id}")
    except Exception as e:
        print("[ERRO] Falha ao criar consulta2:", repr(e))
        raise

    print("\nResumo do que foi criado/existente:")
    print(f"MEDICO_USER_ID={medico_user.id}")
    print(f"MEDICO_ID={medico.user_id}")
    print(f"PACIENTE_USER_ID={paciente_user.id}")
    print(f"PACIENTE_ID={paciente.id}")
    print(f"CONSULTA1_ID={consulta1.id}")
    print(f"CONSULTA2_ID={consulta2.id}")

    print("\nOK! Paciente e consultas adicionados/vinculados ao Dr. João.")


if __name__ == "__main__":
    main()