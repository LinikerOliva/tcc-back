from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from datetime import timedelta

from meu_app.models import (
    Paciente, Medico, Clinica, Consulta, Especialidade
)

DEFAULT_MEDICO_USERNAME = "drjoao"
DEFAULT_MEDICO_EMAIL = "dr.joao@exemplo.com"
DEFAULT_MEDICO_PASSWORD = "Medico123!"

DEFAULT_PACIENTE_USERNAME = "ana"
DEFAULT_PACIENTE_EMAIL = "ana@exemplo.com"
DEFAULT_PACIENTE_PASSWORD = "Paciente123!"

class Command(BaseCommand):
    help = "Garante que existam um paciente e duas consultas vinculadas ao médico 'drjoao'. Idempotente."

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        now = timezone.now()

        # 1) Médico Dr. João (User + Medico + Clinica)
        medico_user, created_user = User.objects.get_or_create(
            username=DEFAULT_MEDICO_USERNAME,
            defaults={
                "first_name": "João",
                "last_name": "Silva",
                "email": DEFAULT_MEDICO_EMAIL,
                "role": "medico",
                "cpf": "111.222.333-44",
                "telefone": "(11) 98888-7777",
                "endereco": "Rua das Flores, 123",
            },
        )
        if created_user:
            medico_user.set_password(DEFAULT_MEDICO_PASSWORD)
            medico_user.save()
            self.stdout.write(self.style.SUCCESS(f"Usuário médico criado: {medico_user.username}"))

        clinica, created_clinica = Clinica.objects.get_or_create(
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
        if created_clinica:
            self.stdout.write(self.style.SUCCESS(f"Clínica criada: {clinica.nome}"))

        medico, created_medico = Medico.objects.get_or_create(
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
        # Vincula ao menos uma especialidade e a clínica
        esp, _ = Especialidade.objects.get_or_create(
            nome="Clínica Geral", defaults={"descricao": "Atendimento clínico geral."}
        )
        medico.especialidades.add(esp)
        if clinica not in medico.clinicas.all():
            medico.clinicas.add(clinica)
        if created_medico:
            self.stdout.write(self.style.SUCCESS("Perfil de Médico criado/vinculado."))

        # 2) Paciente "Ana"
        paciente_user, created_pu = User.objects.get_or_create(
            username=DEFAULT_PACIENTE_USERNAME,
            defaults={
                "first_name": "Ana",
                "last_name": "Souza",
                "email": DEFAULT_PACIENTE_EMAIL,
                "role": "paciente",
                "cpf": "555.666.777-88",
                "telefone": "(11) 97777-6666",
                "endereco": "Rua C, 30",
            },
        )
        if created_pu:
            paciente_user.set_password(DEFAULT_PACIENTE_PASSWORD)
            paciente_user.save()
            self.stdout.write(self.style.SUCCESS(f"Usuário paciente criado: {paciente_user.username}"))

        paciente, created_paciente = Paciente.objects.get_or_create(
            user=paciente_user,
            defaults={
                "tipo_sanguineo": "O+",
                "peso": 64.2,
                "altura": 1.66,
                "alergias": "",
                "condicoes_cronicas": "",
            },
        )
        if created_paciente:
            self.stdout.write(self.style.SUCCESS("Perfil de Paciente criado."))

        # [WORKAROUND] Alinha PK do Paciente ao user_id quando necessário, para atender FKs pré-existentes
        try:
            # Evita operação se já estiver alinhado
            if str(paciente.pk) != str(paciente_user.pk):
                Paciente.objects.filter(pk=paciente.pk).update(id=paciente_user.pk)
                paciente = Paciente.objects.get(user=paciente_user)
                self.stdout.write(self.style.WARNING(
                    f"[WORKAROUND] Paciente.id realinhado ao user_id ({paciente.id}) para compatibilidade de FK."
                ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"[WORKAROUND] Falha ao realinhar Paciente.id: {e}"))

        # 3) Consultas
        consulta1 = (
            Consulta.objects.filter(
                paciente=paciente,
                medico=medico,
                status="agendada",
                motivo__icontains="(seed drjoao #1)",
            )
            .order_by("-data_hora")
            .first()
        )
        if not consulta1:
            Consulta.objects.create(
                paciente=paciente,
                medico=medico,
                data_hora=now + timedelta(days=2, hours=1),
                duracao_minutos=30,
                status="agendada",
                tipo="primeira_consulta",
                motivo="Acompanhamento rotina (seed drjoao #1)",
                observacoes="Criada por seed_drjoao_consultas",
                valor=300.00,
                clinica=clinica,
            )
            self.stdout.write(self.style.SUCCESS("Consulta agendada criada."))
        else:
            self.stdout.write(self.style.WARNING("Consulta agendada já existente. Pulando."))

        consulta2 = (
            Consulta.objects.filter(
                paciente=paciente,
                medico=medico,
                status="confirmada",
                motivo__icontains="(seed drjoao #2)",
            )
            .order_by("-data_hora")
            .first()
        )
        if not consulta2:
            Consulta.objects.create(
                paciente=paciente,
                medico=medico,
                data_hora=now + timedelta(days=7, hours=2),
                duracao_minutos=40,
                status="confirmada",
                tipo="retorno",
                motivo="Retorno pós-exames (seed drjoao #2)",
                observacoes="Criada por seed_drjoao_consultas",
                valor=320.00,
                clinica=clinica,
            )
            self.stdout.write(self.style.SUCCESS("Consulta confirmada criada."))
        else:
            self.stdout.write(self.style.WARNING("Consulta confirmada já existente. Pulando."))

        # Diagnóstico de FK dentro da mesma transação
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA foreign_keys=ON;")
                cursor.execute("PRAGMA foreign_key_check;")
                fk_rows = cursor.fetchall()
            if fk_rows:
                self.stdout.write(self.style.WARNING("[FK-DEBUG] Violações de FK detectadas antes do COMMIT:"))
                for r in fk_rows:
                    # Cada linha: (tabela, rowid, tabela_referenciada, coluna)
                    self.stdout.write(self.style.WARNING(f"[FK] {r}"))
            else:
                self.stdout.write(self.style.SUCCESS("[FK-DEBUG] Sem violações de FK pendentes antes do COMMIT."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"[FK-DEBUG] Falha ao checar FKs: {e}"))

        self.stdout.write(self.style.SUCCESS("Seed finalizado sem erros."))