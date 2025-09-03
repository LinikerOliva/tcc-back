from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
import re

from meu_app.models import (
    Paciente, Medico, Clinica, Consulta, Prontuario, TipoExame, Exame
)

SEED_TAG = "SEED-LINIKER"
DEFAULT_ADMIN_PASSWORD = "Admin123!"
DEFAULT_MEDICO_PASSWORD = "Medico123!"


def split_name(fullname: str):
    parts = (fullname or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def make_unique_username(base: str, User):
    base = re.sub(r"[^a-zA-Z0-9_]", "", (base or "user").lower())[:20] or "user"
    candidate = base
    suffix = 1
    while User.objects.filter(username__iexact=candidate).exists():
        candidate = f"{base[:15]}{suffix}"
        suffix += 1
    return candidate


def make_unique_cpf(base_cpf: str, User):
    # base no formato XXX.XXX.XXX-YY. Se ocupado, tenta variar YY.
    if not re.match(r"^\d{3}\.\d{3}\.\d{3}-\d{2}$", base_cpf):
        base_cpf = "111.222.333-00"
    prefix = base_cpf[:-2]  # "111.222.333-"
    for yy in range(0, 100):
        candidate = f"{prefix}{yy:02d}"
        if not User.objects.filter(cpf=candidate).exists():
            return candidate
    # fallback caso todos estejam ocupados (muito improvável)
    return f"999.999.999-{timezone.now().strftime('%S')}"


class Command(BaseCommand):
    help = "Cria/verifica dados de Liniker Oliva e insere consultas, exame e prontuário (idempotente)."

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        now = timezone.now()

        # 1) Usuário "Liniker Oliva" (admin@example.com)
        first_name, last_name = split_name("Liniker Oliva")
        email = "admin@example.com"

        user_defaults = {
            "username": make_unique_username("liniker", User),
            "first_name": first_name,
            "last_name": last_name,
            "role": "paciente",  # se criar novo
            "cpf": make_unique_cpf("111.222.333-00", User),
        }
        user, created_user = User.objects.get_or_create(email=email, defaults=user_defaults)
        if created_user:
            user.set_password(DEFAULT_ADMIN_PASSWORD)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Usuário criado: {user.username} ({email})"))
        else:
            # Ajustes se necessário
            updated = False
            if not user.first_name and first_name:
                user.first_name = first_name
                updated = True
            if not user.last_name and last_name:
                user.last_name = last_name
                updated = True
            if not user.cpf:
                user.cpf = make_unique_cpf("111.222.333-00", User)
                updated = True
            # Não forço trocar a role se já existir outra (ex.: admin)
            if not user.role:
                user.role = "paciente"
                updated = True
            if updated:
                user.save()
                self.stdout.write(self.style.WARNING(f"Usuário atualizado: {user.username}"))

        # 2) Perfil de Paciente
        paciente, created_paciente = Paciente.objects.get_or_create(
            user=user,
            defaults={
                "tipo_sanguineo": "O+",
                "alergias": "",
                "condicoes_cronicas": "",
                "medicamentos_uso": "",
            },
        )
        if created_paciente:
            self.stdout.write(self.style.SUCCESS("Perfil de Paciente criado."))

        # 3) Clínica
        clinica, created_clinica = Clinica.objects.get_or_create(
            nome=f"Clínica Central {SEED_TAG}",
            defaults={
                "tipo": "Clínica Geral",
                "cnpj": "00.000.000/0000-00",
                "telefone": "(11) 1111-2222",
                "email": "clinica.seed@example.com",
                "endereco": "Rua Exemplo, 123",
                "cidade": "São Paulo",
                "estado": "SP",
            },
        )
        if created_clinica:
            self.stdout.write(self.style.SUCCESS(f"Clínica criada: {clinica.nome}"))

        # 4) Médico
        medico_email = "medico.seed@example.com"
        medico_user, medico_user_created = User.objects.get_or_create(
            email=medico_email,
            defaults={
                "username": make_unique_username("medico_seed", User),
                "first_name": "Médico",
                "last_name": "Seed",
                "role": "medico",
                "cpf": make_unique_cpf("222.333.444-00", User),
            },
        )
        if medico_user_created:
            medico_user.set_password(DEFAULT_MEDICO_PASSWORD)
            medico_user.save()
            self.stdout.write(self.style.SUCCESS(f"Usuário médico criado: {medico_user.username}"))

        medico, medico_created = Medico.objects.get_or_create(
            user=medico_user,
            defaults={
                "crm": "CRM-SEED-0001",
                "biografia": f"Médico criado pelo {SEED_TAG}",
                "formacao": "Universidade Seed",
                "experiencia_anos": 5,
                "valor_consulta": 200.00,
                "ativo": True,
            },
        )
        if medico_created:
            self.stdout.write(self.style.SUCCESS("Perfil de Médico criado."))
        # Vincular médico à clínica (se ainda não vinculado)
        if clinica not in medico.clinicas.all():
            medico.clinicas.add(clinica)

        # 5) Consultas
        # 5.1 Concluída (1 semana atrás)
        consulta_concluida = (
            Consulta.objects.filter(
                paciente=paciente,
                medico=medico,
                status="concluida",
                observacoes__icontains=SEED_TAG,
            )
            .order_by("-data_hora")
            .first()
        )
        if not consulta_concluida:
            consulta_concluida = Consulta.objects.create(
                paciente=paciente,
                medico=medico,
                data_hora=now - timedelta(days=7, hours=2),
                duracao_minutos=40,
                status="concluida",
                tipo="primeira_consulta",
                motivo=f"Avaliação geral {SEED_TAG}",
                observacoes=f"Consulta de seed {SEED_TAG}",
                valor=250.00,
                clinica=clinica,
            )
            self.stdout.write(self.style.SUCCESS("Consulta concluída criada."))

        # 5.2 Agendada (3 dias à frente)
        consulta_agendada = (
            Consulta.objects.filter(
                paciente=paciente,
                medico=medico,
                status="agendada",
                observacoes__icontains=SEED_TAG,
            )
            .order_by("-data_hora")
            .first()
        )
        if not consulta_agendada:
            consulta_agendada = Consulta.objects.create(
                paciente=paciente,
                medico=medico,
                data_hora=now + timedelta(days=3),
                duracao_minutos=30,
                status="agendada",
                tipo="retorno",
                motivo=f"Retorno pós-prontuário {SEED_TAG}",
                observacoes=f"Consulta de seed agendada {SEED_TAG}",
                valor=200.00,
                clinica=clinica,
            )
            self.stdout.write(self.style.SUCCESS("Consulta agendada criada."))

        # 6) Prontuário para a concluída
        prontuario, prontuario_created = Prontuario.objects.get_or_create(
            consulta=consulta_concluida,
            defaults={
                "queixa_principal": "Cansaço ocasional",
                "historia_doenca_atual": "Sintomas há 2 semanas, piora ao esforço.",
                "historia_patologica_pregressa": "Sem comorbidades relevantes.",
                "historia_familiar": "Pai com hipertensão.",
                "historia_social": "Sedentário, dieta irregular.",
                "medicamentos_uso": "Nenhum",
                "alergias": "Nenhuma conhecida",
                "exame_geral": "Bom estado geral",
                "sistema_cardiovascular": "Bulhas normofonéticas",
                "sistema_respiratorio": "MV+ sem ruídos adventícios",
                "sistema_digestivo": "Sem alterações",
                "sistema_neurologico": "Sem déficits focais",
                "outros_sistemas": "Sem alterações",
                "diagnostico_principal": f"Viral inespecífico {SEED_TAG}",
                "diagnosticos_secundarios": "",
                "cid10": "B34.9",
                "conduta": "Hidratação, repouso e reavaliação em 7 dias.",
                "prescricao": "Sintomáticos se necessário.",
                "exames_solicitados": "Hemograma completo.",
                "orientacoes": "Retornar em caso de piora.",
                "data_retorno": (now + timedelta(days=7)).date(),
            },
        )
        if prontuario_created:
            self.stdout.write(self.style.SUCCESS("Prontuário criado."))

        # 7) Tipo de Exame + Exame (Hemograma)
        tipo_exame, tipo_created = TipoExame.objects.get_or_create(
            nome="Hemograma",
            defaults={
                "categoria": "laboratorial",
                "descricao": f"Hemograma completo {SEED_TAG}",
                "preparo": "Jejum não obrigatório.",
                "valor_referencia": 50.00,
                "ativo": True,
            },
        )
        if tipo_created:
            self.stdout.write(self.style.SUCCESS("TipoExame 'Hemograma' criado."))

        exame = (
            Exame.objects.filter(
                paciente=paciente,
                consulta=consulta_concluida,
                tipo_exame=tipo_exame,
                observacoes__icontains=SEED_TAG,
            )
            .order_by("-data_solicitacao")
            .first()
        )
        if not exame:
            exame = Exame.objects.create(
                paciente=paciente,
                medico_solicitante=medico,
                consulta=consulta_concluida,
                tipo_exame=tipo_exame,
                status="realizado",
                data_agendamento=consulta_concluida.data_hora + timedelta(days=1),
                data_realizacao=consulta_concluida.data_hora + timedelta(days=2),
                clinica_realizacao=clinica,
                observacoes=f"Exame realizado conforme solicitação. {SEED_TAG}",
                resultado="Parâmetros dentro da normalidade.",
                valor=80.00,
            )
            self.stdout.write(self.style.SUCCESS("Exame (Hemograma) criado."))

        # Resumo
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("===== RESUMO SEED ====="))
        self.stdout.write(f"Usuário: {user.get_full_name()} | email={user.email} | username={user.username} | role={user.role}")
        self.stdout.write(f"Paciente: {paciente.user.get_full_name()}")
        self.stdout.write(f"Clínica: {clinica.nome}")
        self.stdout.write(f"Médico: {medico.user.get_full_name()} | CRM={medico.crm}")
        self.stdout.write(f"Consulta concluída: {consulta_concluida.data_hora} | tipo={consulta_concluida.tipo} | clinica={consulta_concluida.clinica}")
        self.stdout.write(f"Consulta agendada: {consulta_agendada.data_hora} | tipo={consulta_agendada.tipo} | clinica={consulta_agendada.clinica}")
        self.stdout.write(f"Prontuário: {'criado' if prontuario_created else 'já existia'}")
        self.stdout.write(f"Exame: {exame.tipo_exame.nome} | status={exame.status} | clinica={exame.clinica_realizacao}")
        self.stdout.write(self.style.SUCCESS("========================"))