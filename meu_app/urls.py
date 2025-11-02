# topo do arquivo (importações)
from django.urls import path, include
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from rest_framework.routers import DefaultRouter
from . import views  # manter para endpoints que ainda não foram divididos
from .views.receitas import assinar_documento, assinar_receita, gerar_receita_assinada, test_pdf_endpoint, simple_pdf_generator
from .views.certificados import ValidateCertificateView
from .views.pdf_generator import GerarReceitaPDFView
from .views import admin as admin_views
# from .views.certificates import generate_test_certificate, list_test_certificates, download_test_certificate

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
router.register(r'receitaitem', views.ReceitaItemViewSet)
router.register(r'medicamentos', views.MedicamentoViewSet)
router.register(r'buscar-pacientes', views.BuscarPacientesViewSet, basename='buscar-pacientes')
router.register(r'admin/auditoria', views.AuditLogViewSet, basename='admin-auditoria')
router.register(r'medicos/solicitacoes', views.SolicitacaoMedicoViewSet, basename='solicitacoes-medico')
# Alias adicional compatível com o frontend (evita conflito com /medicos/<pk>/)
router.register(r'solicitacoes/medicos', views.SolicitacaoMedicoViewSet, basename='solicitacoes-medico-alias')
# Alias adicional em singular para compatibilidade direta com .env
router.register(r'solicitacaomedico', views.SolicitacaoMedicoModelViewSet, basename='solicitacaomedico')
router.register(r'agendamentos', views.AgendamentoViewSet)
router.register(r'clinicas', views.ClinicaViewSet)  # <- novo
router.register(r'secretarias', views.SecretariaViewSet, basename='secretaria')

urlpatterns = [
    # IMPORTANTE: Endpoints específicos DEVEM vir ANTES do router para evitar conflitos
    
    # Endpoints de geração de PDF/documentos (múltiplos caminhos para compatibilidade)
    path('gerar-receita/', gerar_receita_assinada, name='gerar_receita_assinada'),
    path('receitas/documento/', gerar_receita_assinada, name='receitas_documento'),
    path('receitas/pdf/', gerar_receita_assinada, name='receitas_pdf'),
    path('receitas/preview/', gerar_receita_assinada, name='receitas_preview'),
    path('receitas/gerar-documento/', gerar_receita_assinada, name='receitas_gerar_documento'),
    path('receitas/gerar/', gerar_receita_assinada, name='receitas_gerar'),
    
    # Novo endpoint usando xhtml2pdf
    path('medicos/me/receitas/gerar-documento/', GerarReceitaPDFView.as_view(), name='gerar_receita_pdf_xhtml2pdf'),

    # --- ENDPOINTS DE ASSINATURA ---
    path('assinatura/assinar/', assinar_documento, name='assinatura-assinar'),
    path('assinar-receita/', assinar_receita, name='assinar-receita'),

    # Endpoint de teste sem autenticação
    path('test-pdf/', test_pdf_endpoint, name='test_pdf'),
    
    # Novo endpoint simples para PDF
    path('simple-pdf/', simple_pdf_generator, name='simple_pdf'),
    
    # Endpoint de teste sem autenticação
    path('test-auth/', lambda request: JsonResponse({'message': 'Test endpoint working', 'method': request.method}), name='test_auth'),
    
    # Novo endpoint de teste para PDF sem DRF
    path('test-pdf-simple/', csrf_exempt(lambda request: JsonResponse({'message': 'PDF test endpoint', 'method': request.method}) if request.method == 'GET' else JsonResponse({'message': 'PDF generation would happen here', 'data': json.loads(request.body) if request.body else None})), name='test_pdf_simple'),

    # --- ENDPOINT DE VALIDAÇÃO DE CERTIFICADO ---
    path('assinatura/certificado/', ValidateCertificateView.as_view(), name='validar-certificado'),

    # ROUTER DRF - DEVE VIR DEPOIS DOS ENDPOINTS ESPECÍFICOS
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
    # NOVO: Endpoint de usuário atual
    path('auth/users/me/', auth_views.current_user_view, name='current-user'),
    # NOVO: Endpoint REST para reset de senha
    path('password_reset/', auth_views.password_reset_api, name='password_reset'),
    # NOVO: Endpoint REST para confirmar reset de senha
    path('auth/password_reset_confirm/', auth_views.password_reset_confirm_api, name='password_reset_confirm'),

    # Stub: endpoint de relatórios/admin/solicitações (lista vazia para não quebrar o frontend)
    path('admin/dashboard/', admin_views.admin_dashboard, name='admin-dashboard'),
    path('admin/solicitacoes/', admin_views.admin_solicitacoes_list, name='admin-solicitacoes'),
    path('admin/solicitacoes/<uuid:pk>/', admin_views.admin_solicitacao_detail, name='admin-solicitacao-detail'),
    path('admin/solicitacoes/<uuid:pk>/aprovar/', admin_views.admin_solicitacao_aprovar, name='admin-solicitacao-aprovar'),
    path('admin/solicitacoes/<uuid:pk>/rejeitar/', admin_views.admin_solicitacao_rejeitar, name='admin-solicitacao-rejeitar'),

    # --- ENDPOINTS DE CERTIFICADOS DE TESTE (COMENTADOS - MÓDULO NÃO EXISTE) ---
    # path('certificates/generate/', generate_test_certificate, name='generate-test-certificate'),
    # path('certificates/list/', list_test_certificates, name='list-test-certificates'),
    # path('certificates/download/<str:filename>/', download_test_certificate, name='download-test-certificate'),
]
