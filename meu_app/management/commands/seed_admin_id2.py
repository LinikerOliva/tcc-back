from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from datetime import timedelta

from meu_app.models import (
    Paciente, Medico, Clinica, Consulta, Prontuario, TipoExame, Exame
)

SEED_TAG = "SEED-ADMIN-ID2"
DEFAULT_MEDICO_PASSWORD = "Medico123!"


class Command(BaseCommand):
    help = "Cria dados de exemplo vinculados ao usuário admin (id=2): paciente, consultas, prontuário e exame. Idempotente."

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        now = timezone.now()

        try:
            # Ajuste: usar o primeiro usuário com role='admin' quando id=2 não existir
            user = User.objects.filter(role='admin').order_by('date_joined').first()
            if not user:
                self.stdout.write(self.style.ERROR("Nenhum usuário com role=admin encontrado."))
                return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Erro ao buscar admin: {e}"))
            return

        self.stdout.write(f"Usuário alvo: {user.username} (id={user.id}, role={getattr(user, 'role', None)})")

        # 1) Garante perfil de Paciente (mesmo que seja admin)
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
            self.stdout.write(self.style.SUCCESS("Perfil de Paciente criado para o admin."))

        # 2) Clínica de apoio
        clinica, created_clinica = Clinica.objects.get_or_create(
            nome=f"Clínica Admin Seed",
            defaults={
                "tipo": "Clínica Geral",
                "cnpj": "00.000.000/0002-00",
                "telefone": "(11) 2222-3333",
                "email": "clinica.adminseed@example.com",
                "endereco": "Rua Admin Seed, 42",
                "cidade": "São Paulo",
                "estado": "SP",
            },
        )
        if created_clinica:
            self.stdout.write(self.style.SUCCESS(f"Clínica criada: {clinica.nome}"))

        # 3) Médico (usa um existente, senão cria um)
        medico = Medico.objects.select_related('user').first()
        if not medico:
            # cria um usuário médico simples
            base_username = "medico_adminseed"
            uname = base_username
            suffix = 1
            while User.objects.filter(username=uname).exists():
                uname = f"{base_username}{suffix}"
                suffix += 1

            medico_user = User.objects.create(
                username=uname,
                first_name="Médico",
                last_name="AdminSeed",
                email=f"{uname}@example.com",
                role="medico",
                cpf=f"555.666.777-{timezone.now().strftime('%S')}",
            )
            medico_user.set_password(DEFAULT_MEDICO_PASSWORD)
            medico_user.save()

            medico = Medico.objects.create(
                user=medico_user,
                crm="CRM-ADMSEED-0001",
                biografia="Médico criado para seed do admin id=2.",
                formacao="Universidade AdminSeed",
                experiencia_anos=7,
                valor_consulta=180.00,
                ativo=True,
            )
            self.stdout.write(self.style.SUCCESS("Perfil de Médico de seed criado."))

        # Vincular médico à clinica
        if clinica not in medico.clinicas.all():
            medico.clinicas.add(clinica)

        # 4) Consulta concluída (1 semana atrás)
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
                data_hora=now - timedelta(days=7, hours=1),
                duracao_minutos=40,
                status="concluida",
                tipo="primeira_consulta",
                motivo=f"Avaliação geral {SEED_TAG}",
                observacoes=f"Consulta de seed {SEED_TAG}",
                valor=250.00,
                clinica=clinica,
            )
            self.stdout.write(self.style.SUCCESS("Consulta concluída criada."))

        # 5) Prontuário desta consulta
        prontuario, prontuario_created = Prontuario.objects.get_or_create(
            consulta=consulta_concluida,
            defaults={
                "queixa_principal": "Cansaço leve",
                "historia_doenca_atual": "Sintomas há alguns dias, melhora com repouso.",
                "historia_patologica_pregressa": "Sem comorbidades importantes.",
                "historia_familiar": "Sem antecedentes relevantes.",
                "historia_social": "Trabalho em escritório.",
                "medicamentos_uso": "Nenhum",
                "alergias": "Nenhuma",
                "exame_geral": "Estado geral bom",
                "sistema_cardiovascular": "Ritmo regular",
                "sistema_respiratorio": "MV+",
                "sistema_digestivo": "Sem dor",
                "sistema_neurologico": "Sem alterações",
                "outros_sistemas": "Sem alterações",
                "diagnostico_principal": f"Viral inespecífico {SEED_TAG}",
                "diagnosticos_secundarios": "",
                "cid10": "B34.9",
                "conduta": "Hidratação e repouso",
                "prescricao": "Sintomáticos se necessário",
                "exames_solicitados": "Hemograma",
                "orientacoes": "Retornar se piora",
                "data_retorno": (now + timedelta(days=10)).date(),
            },
        )
        if prontuario_created:
            self.stdout.write(self.style.SUCCESS("Prontuário criado."))

        # 6) Tipo de Exame + Exame
        tipo_exame, _ = TipoExame.objects.get_or_create(
            nome="Hemograma",
            defaults={
                "categoria": "laboratorial",
                "descricao": f"Hemograma completo {SEED_TAG}",
                "preparo": "Jejum não obrigatório.",
                "valor_referencia": 50.00,
                "ativo": True,
            },
        )

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
                consulta=consulta_concluida,
                tipo_exame=tipo_exame,
                medico_solicitante=medico,
                status="realizado",
                resultado="Dentro dos padrões.",
                observacoes=f"Exame de seed {SEED_TAG}",
                clinica_realizacao=clinica,
            )
            self.stdout.write(self.style.SUCCESS("Exame criado."))

        # 7) Outra consulta agendada (futuro)
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
                data_hora=now + timedelta(days=5),
                duracao_minutos=30,
                status="agendada",
                tipo="retorno",
                motivo=f"Reavaliação {SEED_TAG}",
                observacoes=f"Consulta de seed agendada {SEED_TAG}",
                valor=180.00,
                clinica=clinica,
            )
            self.stdout.write(self.style.SUCCESS("Consulta agendada criada."))

        self.stdout.write(self.style.SUCCESS("Seed concluído com sucesso para o admin id=2."))