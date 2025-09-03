from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import *

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'is_active')
    list_filter = ('role', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'cpf')
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Informações Adicionais', {
            'fields': ('role', 'cpf', 'telefone', 'data_nascimento', 'endereco')
        }),
    )

@admin.register(Especialidade)
class EspecialidadeAdmin(admin.ModelAdmin):
    list_display = ('nome', 'created_at')
    search_fields = ('nome',)

@admin.register(Medico)
class MedicoAdmin(admin.ModelAdmin):
    list_display = ('user', 'crm', 'ativo', 'experiencia_anos')
    list_filter = ('ativo', 'especialidades')
    search_fields = ('user__first_name', 'user__last_name', 'crm')
    filter_horizontal = ('especialidades',)

@admin.register(Paciente)
class PacienteAdmin(admin.ModelAdmin):
    list_display = ('user', 'tipo_sanguineo', 'idade')
    list_filter = ('tipo_sanguineo',)
    search_fields = ('user__first_name', 'user__last_name', 'user__cpf')

@admin.register(Consulta)
class ConsultaAdmin(admin.ModelAdmin):
    list_display = ('paciente', 'medico', 'data_hora', 'status', 'tipo')
    list_filter = ('status', 'tipo', 'data_hora')
    search_fields = ('paciente__user__first_name', 'medico__user__first_name')
    date_hierarchy = 'data_hora'

@admin.register(Prontuario)
class ProntuarioAdmin(admin.ModelAdmin):
    list_display = ('consulta', 'diagnostico_principal', 'created_at')
    search_fields = ('consulta__paciente__user__first_name', 'diagnostico_principal')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(TipoExame)
class TipoExameAdmin(admin.ModelAdmin):
    list_display = ('nome', 'categoria', 'ativo')
    list_filter = ('categoria', 'ativo')
    search_fields = ('nome',)

@admin.register(Exame)
class ExameAdmin(admin.ModelAdmin):
    list_display = ('tipo_exame', 'paciente', 'medico_solicitante', 'status', 'data_solicitacao')
    list_filter = ('status', 'tipo_exame__categoria', 'data_solicitacao')
    search_fields = ('paciente__user__first_name', 'tipo_exame__nome')
    date_hierarchy = 'data_solicitacao'

@admin.register(Receita)
class ReceitaAdmin(admin.ModelAdmin):
    list_display = ('consulta', 'validade', 'created_at')
    search_fields = ('consulta__paciente__user__first_name',)
    date_hierarchy = 'created_at'

@admin.register(Agendamento)
class AgendamentoAdmin(admin.ModelAdmin):
    list_display = ('medico', 'data_hora_inicio', 'data_hora_fim', 'disponivel')
    list_filter = ('disponivel', 'data_hora_inicio')
    search_fields = ('medico__user__first_name',)
    date_hierarchy = 'data_hora_inicio'

@admin.register(HistoricoMedico)
class HistoricoMedicoAdmin(admin.ModelAdmin):
    list_display = ('paciente', 'updated_at')
    search_fields = ('paciente__user__first_name',)

@admin.register(Notificacao)
class NotificacaoAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'tipo', 'titulo', 'lida', 'created_at')
    list_filter = ('tipo', 'lida', 'created_at')
    search_fields = ('usuario__first_name', 'titulo')
    date_hierarchy = 'created_at'

@admin.register(MedicoPaciente)
class MedicoPacienteAdmin(admin.ModelAdmin):
    list_display = ('medico', 'paciente', 'data_vinculo', 'ativo')
    list_filter = ('ativo', 'data_vinculo')
    search_fields = ('medico__user__first_name', 'paciente__user__first_name')

from .models import DigitalCertificate, PatientAccessChallenge

@admin.register(DigitalCertificate)
class DigitalCertificateAdmin(admin.ModelAdmin):
    list_display = ('owner', 'tipo', 'label', 'fingerprint', 'is_active', 'valid_from', 'valid_to', 'created_at')
    list_filter = ('tipo', 'is_active')
    search_fields = ('owner__first_name', 'owner__last_name', 'fingerprint', 'label')

@admin.register(PatientAccessChallenge)
class PatientAccessChallengeAdmin(admin.ModelAdmin):
    list_display = ('paciente', 'challenge_type', 'expires_at', 'is_used', 'created_at')
    list_filter = ('challenge_type', 'is_used')
    search_fields = ('paciente__user__first_name', 'paciente__user__last_name')
