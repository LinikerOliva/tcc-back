# topo do arquivo (importações)
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views  # manter para endpoints que ainda não foram divididos

auth_views = views
clinica_views = views
solicitacoes_views = views

router = DefaultRouter()
router.register(r'users', views.UserViewSet)
router.register(r'medicos', views.MedicoViewSet)
router.register(r'pacientes', views.PacienteViewSet)
router.register(r'consultas', views.ConsultaViewSet)
router.register(r'prontuarios', views.ProntuarioViewSet)
router.register(r'exames', views.ExameViewSet)
router.register(r'receitas', views.ReceitaViewSet)
router.register(r'buscar-pacientes', views.BuscarPacientesViewSet, basename='buscar-pacientes')
router.register(r'admin/auditoria', views.AuditLogViewSet, basename='admin-auditoria')
router.register(r'medicos/solicitacoes', views.SolicitacaoMedicoViewSet, basename='solicitacoes-medico')
router.register(r'agendamentos', views.AgendamentoViewSet)
router.register(r'clinicas', views.ClinicaViewSet)  # <- novo
router.register(r'secretarias', views.SecretariaViewSet, basename='secretaria')

urlpatterns = [
    # Ajuste: remover 'api/' antes do router, pois o projeto já prefixa com /api/
    path('', include(router.urls)),
    path('api-auth/', include('rest_framework.urls')),

    # --- NOVAS ROTAS (singular) /api/clinica/... ---
    path('clinica/tipos-exame/', clinica_views.clinica_tipos_exame, name='clinica-tipos-exame'),
    path('clinica/pacientes/', clinica_views.clinica_pacientes, name='clinica-pacientes'),
    path('clinica/calendario/', clinica_views.clinica_calendario, name='clinica-calendario'),
    # --- FIM NOVAS ROTAS ---

    # Endpoints de autenticação
    path('auth/register/', auth_views.register_view, name='register'),
    path('auth/login/', auth_views.login_view, name='login'),
    path('auth/google/', auth_views.google_login_view, name='google_login'),
    # MFA
    path('auth/mfa/setup/', auth_views.mfa_setup, name='mfa_setup'),
    path('auth/mfa/verify/', auth_views.mfa_verify, name='mfa_verify'),
    # Adiciona logout
    path('auth/logout/', auth_views.logout_view, name='logout'),
    # Stub: endpoint de relatórios/admin/solicitações (lista vazia para não quebrar o frontend)
    path('admin/dashboard/', views.admin_dashboard, name='admin-dashboard'),
    path('admin/solicitacoes/', solicitacoes_views.admin_solicitacoes_list, name='admin-solicitacoes'),
    path('admin/solicitacoes/<uuid:pk>/', solicitacoes_views.admin_solicitacao_detail, name='admin-solicitacao-detail'),
    path('admin/solicitacoes/<uuid:pk>/aprovar/', solicitacoes_views.admin_solicitacao_aprovar, name='admin-solicitacao-aprovar'),
    path('admin/solicitacoes/<uuid:pk>/rejeitar/', solicitacoes_views.admin_solicitacao_rejeitar, name='admin-solicitacao-rejeitar'),
]
