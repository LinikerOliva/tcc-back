from .auth import *
from .users import *
from .doctors import MedicoViewSet
from .patients import PacienteViewSet
from .consultas import *
from .exames import ExameViewSet
from .prontuarios import ProntuarioViewSet
from .receitas import ReceitaViewSet, ReceitaItemViewSet, MedicamentoViewSet
from .clinics import *
from .solicitacoes import *
from .admin import *
from .agendamentos import AgendamentoViewSet
from .search import BuscarPacientesViewSet
from .audit import AuditLogViewSet
from .secretarias import SecretariaViewSet