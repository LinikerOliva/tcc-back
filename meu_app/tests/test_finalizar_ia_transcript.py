from django.test import TestCase
from rest_framework.test import APIClient
from ..models import User, Medico, Paciente, Consulta


TRANSCRIPT = (
    "Bom dia, tudo bem? O que te traz aqui hoje?\n\n"
    "Olha, eu tô com uma dor de cabeça muito forte e sentindo a minha garganta arranhando bastante.\n\n"
    "Entendi. Isso começou quando mais ou menos?\n\n"
    "Começou faz uns dois dias. Ontem à noite tive um pouco de febre também, medi e deu 38 graus. O corpo tá bem mole.\n\n"
    "Certo, vou te examinar... É, olhando aqui a orofaringe está bem hiperemiada, bem vermelha, mas sem placas de pus. O pulmão está limpo. Parece ser um quadro viral mesmo, uma faringite aguda.\n\n"
    "É algo grave? Preciso de antibiótico?\n\n"
    "Não, fique tranquilo. Como é viral, antibiótico não resolve. O tratamento agora é sintomático. O segredo é repouso relativo por uns 3 dias e muita hidratação, beba bastante água. Evite friagem e ar condicionado muito forte.\n\n"
    "Tá certo. Posso tomar algo pra dor e pra febre?\n\n"
    "Sim, vou deixar prescrito. Você vai tomar Dipirona Monohidratada.\n\n"
    "Como eu tomo?\n\n"
    "Pode tomar um comprimido de 500mg. Você repete a cada 6 horas, mas só se tiver dor ou febre. Se não tiver sentindo nada, não precisa tomar."
)


class FinalizarIATest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.med_user = User.objects.create_user(username='med', password='pass', role='medico', cpf='333.333.333-33')
        self.pac_user = User.objects.create_user(username='pac', password='pass', role='paciente', cpf='444.444.444-44')
        self.medico = Medico.objects.create(user=self.med_user, crm='CRM999')
        self.paciente = Paciente.objects.create(user=self.pac_user)
        self.consulta = Consulta.objects.create(
            medico=self.medico,
            paciente=self.paciente,
            data_hora='2025-11-27T12:00:00Z',
            motivo='Teste IA',
            observacoes='',
        )
        self.client.force_authenticate(user=self.med_user)

    def test_finalizar_ia_offline_structured(self):
        url = f"/api/consultas/{self.consulta.id}/finalizar-ia/"
        resp = self.client.post(url, {'transcript': TRANSCRIPT}, format='json')
        self.assertEqual(resp.status_code, 200)
        data = resp.data
        print('DEBUG_DATA', data)
        self.assertIn('queixa', data)
        self.assertNotIn('Bom dia', data['queixa'])
        self.assertTrue('dor de cabeça' in data['queixa'].lower() or 'garganta' in data['queixa'].lower())
        self.assertIn('faringite', data.get('diagnostico_principal', '').lower())
        self.assertIn('repouso', data.get('conduta', '').lower())
        self.assertIn('hidrata', data.get('conduta', '').lower())
