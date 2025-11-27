from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from ..models import User, Medico, Paciente, Receita, ReceitaItem


class PersistenciaConsultaReceitaTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.med_user = User.objects.create_user(username='med', password='pass', role='medico', cpf='111.111.111-11')
        self.pac_user = User.objects.create_user(username='pac', password='pass', role='paciente', cpf='222.222.222-22')
        self.medico = Medico.objects.create(user=self.med_user, crm='CRM123')
        self.paciente = Paciente.objects.create(user=self.pac_user)
        self.client.force_authenticate(user=self.med_user)

    def test_criar_consulta_e_receita(self):
        url = reverse('criar-consulta-e-receita')
        payload = {
            'dados': {
                'paciente_id': str(self.paciente.id),
                'medico_id': str(self.medico.user_id),
                'data': None,
                'queixa_principal': 'Dor de cabeça',
                'historia_doenca': 'Há 3 dias',
                'diagnostico': 'Cefaleia tensional',
                'conduta': 'Analgésico',
                'resumo_clinico': 'Paciente estável'
            },
            'texto': 'Vou receitar dipirona 500 mg, tomar 8/8h por 3 dias.'
        }
        resp = self.client.post(url, payload, format='json')
        self.assertEqual(resp.status_code, 200)
        rid = resp.data.get('receita_id')
        self.assertTrue(rid)
        receita = Receita.objects.get(pk=rid)
        self.assertEqual(receita.status, 'PENDENTE')
        itens = list(ReceitaItem.objects.filter(receita=receita))
        self.assertTrue(len(itens) >= 1)
