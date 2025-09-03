from rest_framework import serializers
from django.contrib.auth.hashers import make_password
from .models import *
from .models import SolicitacaoMedico

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)
    clinica = serializers.PrimaryKeyRelatedField(queryset=Clinica.objects.all(), required=False, allow_null=True)
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role', 'clinica', 'cpf', 'telefone', 'data_nascimento', 'endereco', 'password', 'password_confirm']
        extra_kwargs = {
            'password': {'write_only': True},
            'password_confirm': {'write_only': True}
        }
    
    def validate(self, attrs):
        password = attrs.get('password')
        password_confirm = attrs.get('password_confirm')
        if password is not None or password_confirm is not None:
            if password != password_confirm:
                raise serializers.ValidationError("As senhas não coincidem.")
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        validated_data['password'] = make_password(validated_data['password'])
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        validated_data.pop('password_confirm', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.password = make_password(password)
        instance.save()
        return instance

class EspecialidadeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Especialidade
        fields = '__all__'

# >>> MOVER/INSERIR ESTA CLASSE AQUI <<<
class ClinicaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Clinica
        fields = '__all__'
# >>> FIM DA INSERÇÃO <<<

class MedicoSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    especialidades = EspecialidadeSerializer(many=True, read_only=True)
    id = serializers.ReadOnlyField(source="pk")
    clinicas = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Medico
        fields = '__all__'

    def get_clinicas(self, obj):
        from .models import Clinica
        # serializa clinicas como objetos completos
        return ClinicaSerializer(obj.clinicas.all(), many=True).data

# --- NOVO: SecretariaSerializer ---
class SecretariaSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    id = serializers.ReadOnlyField(source="pk")
    medicos = serializers.PrimaryKeyRelatedField(queryset=Medico.objects.all(), many=True, required=False)
    clinicas = serializers.PrimaryKeyRelatedField(queryset=Clinica.objects.all(), many=True, required=False)

    class Meta:
        model = Secretaria
        fields = '__all__'

    def create(self, validated_data):
        medicos = validated_data.pop('medicos', [])
        clinicas = validated_data.pop('clinicas', [])
        instance = super().create(validated_data)
        if medicos:
            instance.medicos.set(medicos)
        if clinicas:
            instance.clinicas.set(clinicas)
        return instance

    def update(self, instance, validated_data):
        medicos = validated_data.pop('medicos', None)
        clinicas = validated_data.pop('clinicas', None)
        instance = super().update(instance, validated_data)
        if medicos is not None:
            instance.medicos.set(medicos)
        if clinicas is not None:
            instance.clinicas.set(clinicas)
        return instance
# --- FIM NOVO ---

class PacienteSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    idade = serializers.ReadOnlyField()
    id = serializers.ReadOnlyField(source="pk")
    
    class Meta:
        model = Paciente
        fields = '__all__'

class ConsultaSerializer(serializers.ModelSerializer):
    medico = MedicoSerializer(read_only=True)
    paciente = PacienteSerializer(read_only=True)
    clinica = ClinicaSerializer(read_only=True)
    
    class Meta:
        model = Consulta
        fields = '__all__'

# Região mais abaixo do arquivo - classes: TipoExameSerializer, ExameSerializer
class ProntuarioSerializer(serializers.ModelSerializer):
    consulta = ConsultaSerializer(read_only=True)
    
    class Meta:
        model = Prontuario
        fields = '__all__'

class TipoExameSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoExame
        fields = '__all__'

class ExameSerializer(serializers.ModelSerializer):
    tipo_exame = TipoExameSerializer(read_only=True)
    paciente = PacienteSerializer(read_only=True)
    medico_solicitante = MedicoSerializer(read_only=True)
    clinica_realizacao = ClinicaSerializer(read_only=True)
    
    class Meta:
        model = Exame
        fields = '__all__'

class ReceitaSerializer(serializers.ModelSerializer):
    consulta = ConsultaSerializer(read_only=True)
    itens = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Receita
        fields = '__all__'

    def get_itens(self, obj):
        return ReceitaItemSerializer(obj.itens.all(), many=True).data

class HistoricoMedicoSerializer(serializers.ModelSerializer):
    paciente = PacienteSerializer(read_only=True)
    
    class Meta:
        model = HistoricoMedico
        fields = '__all__'

class NotificacaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notificacao
        fields = '__all__'


# Serializers mais leves para listagens
class UserBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email']

class PacienteBriefSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField(source="pk")
    user = UserBriefSerializer(read_only=True)

    class Meta:
        model = Paciente
        fields = ['id', 'user', 'tipo_sanguineo', 'peso', 'altura', 'alergias', 'condicoes_cronicas']

class MedicoBriefSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField(source="pk")
    user = UserBriefSerializer(read_only=True)

    class Meta:
        model = Medico
        fields = ['id', 'user', 'crm']

class ConsultaListSerializer(serializers.ModelSerializer):
    medico = MedicoBriefSerializer(read_only=True)
    paciente = PacienteBriefSerializer(read_only=True)
    class Meta:
        model = Consulta
        fields = ['id', 'data_hora', 'status', 'tipo', 'motivo', 'medico', 'paciente']

class ExameListSerializer(serializers.ModelSerializer):
    tipo_exame = TipoExameSerializer(read_only=True)
    paciente = PacienteBriefSerializer(read_only=True)
    medico_solicitante = MedicoBriefSerializer(read_only=True)
    # Campos derivados/seguros:
    data_agendamento = serializers.SerializerMethodField()
    resultado_url = serializers.SerializerMethodField()
    clinica_realizacao = ClinicaSerializer(read_only=True)

    class Meta:
        model = Exame
        fields = [
            'id',
            'tipo_exame',
            'status',
            'data_solicitacao',
            'data_agendamento',
            'paciente',
            'medico_solicitante',
            'resultado_url',
            'clinica_realizacao',
        ]

    def get_data_agendamento(self, obj):
        # não quebra se o modelo não tiver este campo
        return getattr(obj, 'data_agendamento', None)

    def get_resultado_url(self, obj):
        file_attr = getattr(obj, 'arquivo_resultado', None)
        if not file_attr:
            return None
        url = getattr(file_attr, 'url', None) or str(file_attr)
        request = getattr(self, 'context', {}).get('request') if hasattr(self, 'context') else None
        if request:
            try:
                return request.build_absolute_uri(url)
            except Exception:
                return url
        return url

class ProntuarioListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prontuario
        fields = ['id', 'diagnostico_principal', 'cid10', 'conduta', 'data_retorno', 'consulta']

class AuditLogListSerializer(serializers.ModelSerializer):
    user = UserBriefSerializer(read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            'id', 'created_at', 'user', 'action', 'entity', 'entity_id', 'status', 'ip_address'
        ]

class AuditLogSerializer(serializers.ModelSerializer):
    user = UserBriefSerializer(read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            'id', 'created_at', 'user', 'action', 'entity', 'entity_id',
            'status', 'ip_address', 'user_agent', 'metadata'
        ]


class SolicitacaoMedicoSerializer(serializers.ModelSerializer):
    # Campos calculados para o Admin do front
    nome = serializers.SerializerMethodField(read_only=True)
    email = serializers.SerializerMethodField(read_only=True)
    tipo = serializers.SerializerMethodField(read_only=True)  # sempre "medico"
    dataEnvio = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = SolicitacaoMedico
        fields = [
            'id', 'tipo', 'nome', 'email',
            'crm', 'especialidade', 'instituicao_formacao', 'ano_formacao',
            'residencia', 'instituicao_residencia', 'ano_residencia',
            'experiencia', 'motivacao',
            'diploma_medicina', 'certificado_residencia', 'comprovante_experiencia',
            'status', 'dataEnvio',
        ]
        read_only_fields = ['status', 'dataEnvio']

    def get_tipo(self, obj):
        return 'medico'

    def get_nome(self, obj):
        return obj.user.get_full_name() or obj.user.username

    def get_email(self, obj):
        return obj.user.email

    def create(self, validated_data):
        """
        Aceita campos camelCase vindos do front e arquivos multipart.
        """
        request = self.context.get('request')
        data = request.data if request else {}

        # Mapear camelCase -> snake_case do modelo
        mapped = {
            'crm': data.get('crm'),
            'especialidade': data.get('especialidade'),
            'instituicao_formacao': data.get('instituicaoFormacao'),
            'ano_formacao': data.get('anoFormacao'),
            'residencia': data.get('residencia'),
            'instituicao_residencia': data.get('instituicaoResidencia'),
            'ano_residencia': data.get('anoResidencia'),
            'experiencia': data.get('experiencia'),
            'motivacao': data.get('motivacao'),
        }

        files = request.FILES if request else {}
        if files.get('diplomaMedicina'):
            mapped['diploma_medicina'] = files.get('diplomaMedicina')
        if files.get('certificadoResidencia'):
            mapped['certificado_residencia'] = files.get('certificadoResidencia')
        if files.get('comprovanteExperiencia'):
            mapped['comprovante_experiencia'] = files.get('comprovanteExperiencia')

        # Remove None para evitar erros de tipo
        mapped = {k: v for k, v in mapped.items() if v not in (None, '')}

        user = request.user if request else None
        return SolicitacaoMedico.objects.create(user=user, status='pending', **mapped)

# --- ADIÇÕES PARA DESAFIO DE ACESSO (PIN/OTP/QR) E CERTIFICADOS ---

class PatientAccessChallengeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientAccessChallenge
        fields = ['id', 'challenge_type', 'expires_at', 'is_used', 'created_at']

class DigitalCertificateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DigitalCertificate
        fields = [
            'id', 'owner', 'label', 'tipo', 'provider', 'fingerprint',
            'subject', 'issuer', 'valid_from', 'valid_to', 'arquivo',
            'a3_reference', 'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'owner', 'created_at']

class AgendamentoSerializer(serializers.ModelSerializer):
    medico = MedicoBriefSerializer(read_only=True)

    class Meta:
        model = Agendamento
        fields = ['id', 'medico', 'data_hora_inicio', 'data_hora_fim', 'disponivel', 'observacoes']

class ConsultaCreateSerializer(serializers.ModelSerializer):
    medico = serializers.PrimaryKeyRelatedField(queryset=Medico.objects.all())
    paciente = serializers.PrimaryKeyRelatedField(queryset=Paciente.objects.all(), required=False)

    class Meta:
        model = Consulta
        fields = ['medico', 'paciente', 'data_hora', 'duracao_minutos', 'tipo', 'motivo', 'observacoes']

    def validate_tipo(self, value):
        # Normaliza aliases vindos do front
        aliases = {
            'primeira': 'primeira_consulta',
            'primeira_consulta': 'primeira_consulta',
            'retorno': 'retorno',
            'urgencia': 'urgencia',
            'rotina': 'rotina',
        }
        v = (value or '').strip().lower()
        if v not in aliases:
            raise serializers.ValidationError("Tipo inválido. Use: primeira_consulta, retorno, urgencia, rotina.")
        return aliases[v]
class MedicamentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Medicamento
        fields = '__all__'

class ReceitaItemSerializer(serializers.ModelSerializer):
    medicamento = MedicamentoSerializer(read_only=True)

    class Meta:
        model = ReceitaItem
        fields = ['id', 'medicamento', 'dose', 'frequencia', 'duracao', 'observacoes']
