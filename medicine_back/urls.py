from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from meu_app.views.auth import password_reset_redirect

urlpatterns = [
    path('reset/<uidb64>/<token>/', password_reset_redirect, name='password_reset_confirm'),
    path('', include('django.contrib.auth.urls')),  # adiciona rotas de reset/confirm padrão
    path('admin/', admin.site.urls),
    path('api/', include('meu_app.urls')),
]

# Servir arquivos de mídia em desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
