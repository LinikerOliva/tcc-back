from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
import uuid

class User(AbstractUser):
    """Modelo de usuário customizado"""
    ROLE_CHOICES = [
        ('medico', 'Médico'),
        ('paciente', 'Paciente'),
        ('admin', 'Administrador'),
        ('clinica', 'Clínica'),  # <- novo papel
        ('secretaria', 'Secretária(o)'),  # <- NOVO PAPEL
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    # Usuário pode (opcionalmente) estar vinculado a uma clínica
    clinica = models.ForeignKey('Clinica', on_delete=models.SET_NULL, null=True, blank=True, related_name='usuarios')
    cpf = models.CharField(max_length=14, unique=True, validators=[
        RegexValidator(regex=r'^\d{3}\.\d{3}\.\d{3}-\d{2}$', message='CPF deve estar no formato XXX.XXX.XXX-XX')
    ])
    telefone = models.CharField(max_length=15, blank=True)
    data_nascimento = models.DateField(null=True, blank=True)
    endereco = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    # >>> NOVO: MFA (TOTP)
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret = models.CharField(max_length=64, blank=True)  # Base32 (ex.: para TOTP)
    mfa_backup_codes = models.JSONField(default=list, blank=True)  # Ideal armazenar hashes
    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"

class Especialidade(models.Model):
    """Especialidades médicas"""
    nome = models.CharField(max_length=100, unique=True)
    descricao = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Especialidade"
        verbose_name_plural = "Especialidades"

    def __str__(self):
        return self.nome

# Novo modelo de clínica
class Clinica(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nome = models.CharField(max_length=150)
    tipo = models.CharField(max_length=100, blank=True)  # ex.: "Clínica de Imagem", "Laboratório"
    cnpj = models.CharField(max_length=18, blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    endereco = models.TextField(blank=True)
    cidade = models.CharField(max_length=100, blank=True)
    estado = models.CharField(max_length=2, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Clínica"
        verbose_name_plural = "Clínicas"

    def __str__(self):
        return self.nome

class Medico(models.Model):
    """Perfil específico do médico"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    crm = models.CharField(max_length=20, unique=True)
    especialidades = models.ManyToManyField(Especialidade, related_name='medicos')
    biografia = models.TextField(blank=True)
    formacao = models.TextField(blank=True)
    experiencia_anos = models.PositiveIntegerField(default=0)
    valor_consulta = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    ativo = models.BooleanField(default=True)
    clinicas = models.ManyToManyField('Clinica', related_name='medicos', blank=True)
    # --- NOVO: status de aprovação do médico ---
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('aprovado', 'Aprovado'),
        ('reprovado', 'Reprovado'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente')

    # --- NOVO: Configuração de template e logo do médico ---
    template_config = models.JSONField(null=True, blank=True, default=dict)
    logo = models.ImageField(upload_to='logos/medicos/', null=True, blank=True)


    class Meta:
        verbose_name = "Médico"
        verbose_name_plural = "Médicos"

    def __str__(self):
        return f"Dr(a). {self.user.get_full_name()} - CRM: {self.crm}"

class Paciente(models.Model):
    """Perfil específico do paciente"""
    TIPO_SANGUINEO_CHOICES = [
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
    ]
    
    # Agora Paciente tem ID próprio e o vínculo com User é opcional
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    cpf = models.CharField(
        max_length=14,
        unique=True,
        null=True,
        blank=True,
        validators=[RegexValidator(regex=r'^\d{3}\.\d{3}\.\d{3}-\d{2}$', message='CPF deve estar no formato XXX.XXX.XXX-XX')]
    )
    tipo_sanguineo = models.CharField(max_length=3, choices=TIPO_SANGUINEO_CHOICES, blank=True)
    peso = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    altura = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    alergias = models.TextField(blank=True, help_text="Liste as alergias conhecidas")
    condicoes_cronicas = models.TextField(blank=True, help_text="Condições crônicas conhecidas")
    medicamentos_uso = models.TextField(blank=True, help_text="Medicamentos em uso contínuo")
    contato_emergencia_nome = models.CharField(max_length=100, blank=True)
    contato_emergencia_telefone = models.CharField(max_length=15, blank=True)
    plano_saude = models.CharField(max_length=100, blank=True)
    numero_carteirinha = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name = "Paciente"
        verbose_name_plural = "Pacientes"

    def __str__(self):
        if self.user:
            nome = self.user.get_full_name() or self.user.username
        else:
            nome = self.cpf or str(self.id)
        return f"{nome}"

    @property
    def idade(self):
        if self.user and self.user.data_nascimento:
            from datetime import date
            today = date.today()
            return today.year - self.user.data_nascimento.year - (
                (today.month, today.day) < (self.user.data_nascimento.month, self.user.data_nascimento.day)
            )
        return None

class MedicoPaciente(models.Model):
    """Relacionamento entre médico e paciente"""
    medico = models.ForeignKey(Medico, on_delete=models.CASCADE, related_name='pacientes_vinculados')
    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name='medicos_vinculados')
    data_vinculo = models.DateTimeField(auto_now_add=True)
    ativo = models.BooleanField(default=True)
    observacoes = models.TextField(blank=True)

    class Meta:
        unique_together = ['medico', 'paciente']
        verbose_name = "Vínculo Médico-Paciente"
        verbose_name_plural = "Vínculos Médico-Paciente"

    def __str__(self):
        return f"{self.medico} -> {self.paciente}"

class Consulta(models.Model):
    """Consultas médicas"""
    STATUS_CHOICES = [
        ('agendada', 'Agendada'),
        ('confirmada', 'Confirmada'),
        ('cancelada', 'Cancelada'),
        ('concluida', 'Concluída'),
    ]
    TIPO_CHOICES = [
        ('primeira_consulta', 'Primeira Consulta'),
        ('retorno', 'Retorno'),
        ('urgencia', 'Urgência'),
        ('rotina', 'Rotina'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    medico = models.ForeignKey(Medico, on_delete=models.CASCADE, related_name='consultas')
    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name='consultas')
    data_hora = models.DateTimeField()
    duracao_minutos = models.PositiveIntegerField(default=30)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='agendada')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='primeira_consulta')
    motivo = models.TextField(help_text="Motivo da consulta")
    observacoes = models.TextField(blank=True)
    valor = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    clinica = models.ForeignKey('Clinica', on_delete=models.SET_NULL, null=True, blank=True, related_name='consultas')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # >>> NOVO: Assinatura Digital da consulta
    assinatura_hash = models.CharField(max_length=128, blank=True)
    assinatura_algoritmo = models.CharField(max_length=50, blank=True)  # ex.: SHA256withRSA
    assinatura_carimbo_tempo = models.CharField(max_length=256, blank=True)  # token TSA (base64/JSON)
    assinada_por = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='consultas_assinadas')
    assinada_em = models.DateTimeField(null=True, blank=True)
    documento_assinado = models.FileField(upload_to='assinaturas/consultas/', null=True, blank=True)

    class Meta:
        verbose_name = "Consulta"
        verbose_name_plural = "Consultas"
        ordering = ['-data_hora']

    def __str__(self):
        return f"Consulta: {self.paciente} com {self.medico} em {self.data_hora.strftime('%d/%m/%Y %H:%M')}"

class Prontuario(models.Model):
    """Prontuário médico da consulta"""
    consulta = models.OneToOneField(Consulta, on_delete=models.CASCADE, related_name='prontuario')
    
    # Anamnese
    queixa_principal = models.TextField()
    historia_doenca_atual = models.TextField()
    historia_patologica_pregressa = models.TextField(blank=True)
    historia_familiar = models.TextField(blank=True)
    historia_social = models.TextField(blank=True)
    medicamentos_uso = models.TextField(blank=True)
    alergias = models.TextField(blank=True)
    
    # Exame Físico
    pressao_arterial = models.CharField(max_length=20, blank=True)
    frequencia_cardiaca = models.CharField(max_length=10, blank=True)
    temperatura = models.CharField(max_length=10, blank=True)
    saturacao_oxigenio = models.CharField(max_length=10, blank=True)
    peso = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    altura = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    exame_geral = models.TextField(blank=True)
    sistema_cardiovascular = models.TextField(blank=True)
    sistema_respiratorio = models.TextField(blank=True)
    sistema_digestivo = models.TextField(blank=True)
    sistema_neurologico = models.TextField(blank=True)
    outros_sistemas = models.TextField(blank=True)
    
    # Diagnóstico e Conduta
    diagnostico_principal = models.TextField()
    diagnosticos_secundarios = models.TextField(blank=True)
    cid10 = models.CharField(max_length=10, blank=True, help_text="Código CID-10")
    conduta = models.TextField()
    prescricao = models.TextField(blank=True)
    exames_solicitados = models.TextField(blank=True)
    orientacoes = models.TextField(blank=True)
    data_retorno = models.DateField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Prontuário"
        verbose_name_plural = "Prontuários"

    def __str__(self):
        return f"Prontuário - {self.consulta}"

class TipoExame(models.Model):
    """Tipos de exames disponíveis"""
    CATEGORIA_CHOICES = [
        ('laboratorial', 'Laboratorial'),
        ('imagem', 'Imagem'),
        ('cardiologico', 'Cardiológico'),
        ('neurologico', 'Neurológico'),
        ('outros', 'Outros'),
    ]
    
    nome = models.CharField(max_length=100)
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES)
    descricao = models.TextField(blank=True)
    preparo = models.TextField(blank=True, help_text="Instruções de preparo para o exame")
    valor_referencia = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Tipo de Exame"
        verbose_name_plural = "Tipos de Exames"

    def __str__(self):
        return f"{self.nome} ({self.get_categoria_display()})"

class Exame(models.Model):
    """Exames médicos"""
    STATUS_CHOICES = [
        ('solicitado', 'Solicitado'),
        ('agendado', 'Agendado'),
        ('realizado', 'Realizado'),
        ('cancelado', 'Cancelado'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name='exames')
    medico_solicitante = models.ForeignKey(Medico, on_delete=models.CASCADE, related_name='exames_solicitados')
    consulta = models.ForeignKey(Consulta, on_delete=models.CASCADE, related_name='exames', null=True, blank=True)
    tipo_exame = models.ForeignKey(TipoExame, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='solicitado')
    data_solicitacao = models.DateTimeField(auto_now_add=True)
    data_agendamento = models.DateTimeField(null=True, blank=True)
    data_realizacao = models.DateTimeField(null=True, blank=True)
    clinica_realizacao = models.ForeignKey('Clinica', on_delete=models.SET_NULL, null=True, blank=True, related_name='exames')
    observacoes = models.TextField(blank=True)
    resultado = models.TextField(blank=True)
    arquivo_resultado = models.FileField(upload_to='exames/', blank=True, null=True)
    valor = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Assinatura de laudo
    assinatura_hash = models.CharField(max_length=128, blank=True)
    assinatura_algoritmo = models.CharField(max_length=50, blank=True)
    assinatura_carimbo_tempo = models.CharField(max_length=256, blank=True)
    assinado_por = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='exames_assinados')
    assinado_em = models.DateTimeField(null=True, blank=True)
    laudo_assinado = models.FileField(upload_to='assinaturas/exames/', null=True, blank=True)

    class Meta:
        verbose_name = "Exame"
        verbose_name_plural = "Exames"
        ordering = ['-data_solicitacao']

    def __str__(self):
        return f"Exame {self.tipo_exame} - {self.paciente}"

class Receita(models.Model):
    """Receitas médicas"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    consulta = models.ForeignKey(Consulta, on_delete=models.CASCADE, related_name='receitas')
    medicamentos = models.TextField(help_text="Lista de medicamentos prescritos")
    posologia = models.TextField(help_text="Instruções de uso")
    observacoes = models.TextField(blank=True)
    validade = models.DateField(help_text="Data de validade da receita")
    created_at = models.DateTimeField(auto_now_add=True)

    # Assinatura da receita
    hash_documento = models.CharField(max_length=128, blank=True)
    algoritmo_assinatura = models.CharField(max_length=50, blank=True)
    carimbo_tempo = models.CharField(max_length=256, blank=True)
    assinada_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='receitas_assinadas')
    assinada_em = models.DateTimeField(null=True, blank=True)
    arquivo_assinado = models.FileField(upload_to='assinaturas/receitas/', null=True, blank=True)
    # NOVO: status booleano de assinatura
    assinada = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Receita"
        verbose_name_plural = "Receitas"

    def __str__(self):
        return f"Receita - {self.consulta}"

class Medicamento(models.Model):
    """Catálogo de medicamentos"""
    nome = models.CharField(max_length=150)
    apresentacao = models.CharField(max_length=100, blank=True)  # ex: comprimido, cápsula, solução
    concentracao = models.CharField(max_length=100, blank=True)  # ex: 500 mg, 10 mg/mL
    fabricante = models.CharField(max_length=100, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Medicamento"
        verbose_name_plural = "Medicamentos"
        unique_together = [('nome', 'apresentacao', 'concentracao')]

    def __str__(self):
        return f"{self.nome} {self.concentracao} ({self.apresentacao})"

class ReceitaItem(models.Model):
    """Itens de uma receita"""
    receita = models.ForeignKey(Receita, on_delete=models.CASCADE, related_name='itens')
    medicamento = models.ForeignKey(Medicamento, on_delete=models.PROTECT, related_name='itens')
    dose = models.CharField(max_length=100, blank=True)        # ex: 1 comprimido
    frequencia = models.CharField(max_length=100, blank=True)  # ex: 8/8h
    duracao = models.CharField(max_length=100, blank=True)     # ex: 7 dias
    observacoes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Item de Receita"
        verbose_name_plural = "Itens de Receita"

    def __str__(self):
        return f"{self.medicamento} - {self.dose}, {self.frequencia}, {self.duracao}"

class Agendamento(models.Model):
    """Slots de agendamento do médico"""
    medico = models.ForeignKey(Medico, on_delete=models.CASCADE, related_name='agendamentos')
    data_hora_inicio = models.DateTimeField()
    data_hora_fim = models.DateTimeField()
    disponivel = models.BooleanField(default=True)
    observacoes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Agendamento"
        verbose_name_plural = "Agendamentos"
        unique_together = ['medico', 'data_hora_inicio']

    def __str__(self):
        return f"{self.medico} - {self.data_hora_inicio}"

class HistoricoMedico(models.Model):
    """Histórico médico consolidado do paciente"""
    paciente = models.OneToOneField(Paciente, on_delete=models.CASCADE, related_name='historico_medico')
    doencas_previas = models.TextField(blank=True)
    cirurgias_previas = models.TextField(blank=True)
    hospitalizacoes = models.TextField(blank=True)
    vacinas = models.TextField(blank=True)
    historia_familiar = models.TextField(blank=True)
    habitos = models.TextField(blank=True, help_text="Tabagismo, etilismo, atividade física, etc.")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Histórico Médico"
        verbose_name_plural = "Históricos Médicos"

    def __str__(self):
        return f"Histórico - {self.paciente}"

class Notificacao(models.Model):
    """Notificações do sistema"""
    TIPO_CHOICES = [
        ('consulta_agendada', 'Consulta Agendada'),
        ('consulta_cancelada', 'Consulta Cancelada'),
        ('exame_disponivel', 'Exame Disponível'),
        ('lembrete_consulta', 'Lembrete de Consulta'),
        ('sistema', 'Sistema'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notificacoes')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    titulo = models.CharField(max_length=200)
    mensagem = models.TextField()
    lida = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Notificação"
        verbose_name_plural = "Notificações"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.tipo} - {self.titulo}"

class AuditLog(models.Model):
    """Registros de auditoria"""
    STATUS_CHOICES = [
        ('success', 'Sucesso'),
        ('fail', 'Falha'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=100)             # ex: login, create, update, approve, reject
    entity = models.CharField(max_length=100, blank=True) # ex: Consulta, Exame, Solicitacao
    entity_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='success')
    metadata = models.JSONField(blank=True, null=True)
    ip_address = models.CharField(max_length=45, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Auditoria"
        verbose_name_plural = "Auditorias"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.created_at} - {self.action} ({self.status})"

class SolicitacaoMedico(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('approved', 'Aprovada'),
        ('rejected', 'Rejeitada'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='solicitacoes_medico')

    # Dados profissionais e comprovações
    crm = models.CharField(max_length=20)
    especialidade = models.CharField(max_length=100, blank=True)
    instituicao_formacao = models.CharField(max_length=150, blank=True)
    ano_formacao = models.CharField(max_length=4, blank=True)
    residencia = models.CharField(max_length=150, blank=True)
    instituicao_residencia = models.CharField(max_length=150, blank=True)
    ano_residencia = models.CharField(max_length=4, blank=True)
    experiencia = models.TextField(blank=True)
    motivacao = models.TextField(blank=True)

    # Uploads
    diploma_medicina = models.FileField(upload_to='solicitacoes/diplomas/', blank=True, null=True)
    certificado_residencia = models.FileField(upload_to='solicitacoes/certificados/', blank=True, null=True)
    comprovante_experiencia = models.FileField(upload_to='solicitacoes/experiencia/', blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Novos campos para auditoria de aprovação/rejeição
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='solicitacoes_medico_aprovadas'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='solicitacoes_medico_rejeitadas'
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Solicitação Médico - {self.user} ({self.status})"

class PatientAccessChallenge(models.Model):
    """Desafio de acesso temporário ao prontuário do paciente"""
    TYPE_CHOICES = [
        ('pin', 'PIN'),
        ('otp', 'OTP'),
        ('qrcode', 'QR Code'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name='challenges')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='challenges_criados')
    challenge_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    code_hash = models.CharField(max_length=128)  # Armazenar hash (ex.: SHA256 do código+salt)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    meta = models.JSONField(default=dict, blank=True, help_text="Metadados opcionais (ex.: salt, tentativa, ip)")

    class Meta:
        verbose_name = "Desafio de Acesso ao Prontuário"
        verbose_name_plural = "Desafios de Acesso ao Prontuário"
        indexes = [
            models.Index(fields=['paciente', 'challenge_type', 'is_used']),
        ]

    def __str__(self):
        return f"Challenge {self.challenge_type} - {self.paciente}"

class DigitalCertificate(models.Model):
    """Certificados digitais (A1/A3) dos usuários"""
    TIPO_CHOICES = [
        ('A1', 'A1'),
        ('A3', 'A3'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='certificados')
    label = models.CharField(max_length=120, blank=True)
    tipo = models.CharField(max_length=2, choices=TIPO_CHOICES)
    provider = models.CharField(max_length=50, blank=True, help_text="ex.: local, token, cloud")
    fingerprint = models.CharField(max_length=128, blank=True)
    subject = models.CharField(max_length=255, blank=True)
    issuer = models.CharField(max_length=255, blank=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)
    arquivo = models.FileField(upload_to='certificados/', null=True, blank=True, help_text="Apenas para A1")
    a3_reference = models.CharField(max_length=120, blank=True, help_text="Identificador do token/leitora para A3")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Certificado Digital"
        verbose_name_plural = "Certificados Digitais"

    def __str__(self):
        return f"{self.label or self.owner} ({self.tipo})"

# --- NOVO MODELO: Secretaria ---
class Secretaria(models.Model):
    """Perfil de Secretária(o) que dá suporte ao(s) médico(s) e/ou clínica(s)."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    medicos = models.ManyToManyField(Medico, related_name='secretarias', blank=True)
    clinicas = models.ManyToManyField(Clinica, related_name='secretarias', blank=True)
    ativo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Secretária(o)'
        verbose_name_plural = 'Secretárias(os)'

    def __str__(self):
        return f"Secretária(o): {self.user.get_full_name() or self.user.username}"
