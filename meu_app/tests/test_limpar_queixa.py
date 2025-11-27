from django.test import TestCase
from ..views.consultas import limpar_queixa


class LimparQueixaTest(TestCase):
    def test_remove_saudacao_completa(self):
        self.assertEqual(limpar_queixa('Bom dia, tudo bem?'), '')

    def test_remove_inicio_bom_dia(self):
        self.assertEqual(limpar_queixa('Bom dia, estou com dor de garganta.'), 'estou com dor de garganta')

    def test_mantem_queixa_valida(self):
        self.assertEqual(limpar_queixa('Dor de cabeça'), 'Dor de cabeça')
