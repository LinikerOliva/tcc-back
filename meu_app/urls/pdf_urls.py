# -*- coding: utf-8 -*-
from django.urls import path
from ..views.pdf_generator import GerarReceitaPDFView

urlpatterns = [
    path('medicos/me/receitas/gerar-documento/', GerarReceitaPDFView.as_view(), name='gerar_receita_pdf'),
]