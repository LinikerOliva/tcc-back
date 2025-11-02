#!/usr/bin/env python3
import os
import sys
import django

# Configurar Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'medicine_back.settings')
django.setup()

from django.contrib.auth import get_user_model
from meu_app.models import Medico, Receita

User = get_user_model()

def test_user_medico_relation():
    print("=== TESTE DE RELACIONAMENTO USER-MEDICO ===")
    
    # Buscar o usuário drjoao
    try:
        user = User.objects.get(username='drjoao')
        print(f"Usuário encontrado: {user.username} (ID: {user.id})")
        print(f"Role: {user.role}")
        
        # Testar acesso ao médico
        print("\n--- Testando user.medico ---")
        try:
            medico = user.medico
            print(f"✅ user.medico funciona: {medico}")
            print(f"   Médico ID: {medico.id}")
            print(f"   CRM: {medico.crm}")
        except Exception as e:
            print(f"❌ Erro ao acessar user.medico: {e}")
        
        # Testar hasattr
        print(f"\n--- hasattr(user, 'medico'): {hasattr(user, 'medico')}")
        
        # Testar se o médico existe diretamente
        print("\n--- Buscando médico diretamente ---")
        try:
            medico_direto = Medico.objects.get(user=user)
            print(f"✅ Médico encontrado diretamente: {medico_direto}")
        except Medico.DoesNotExist:
            print("❌ Médico não encontrado diretamente")
        except Exception as e:
            print(f"❌ Erro ao buscar médico diretamente: {e}")
            
        # Testar filtro de receitas
        print("\n--- Testando filtro de receitas ---")
        try:
            if hasattr(user, 'medico') and user.medico:
                receitas = Receita.objects.filter(consulta__medico=user.medico)
                print(f"✅ Receitas encontradas: {receitas.count()}")
                for receita in receitas:
                    print(f"   - Receita ID: {receita.id}")
            else:
                print("❌ user.medico não está disponível para filtro")
        except Exception as e:
            print(f"❌ Erro ao filtrar receitas: {e}")
            
        # Listar todas as receitas
        print("\n--- Todas as receitas no sistema ---")
        todas_receitas = Receita.objects.all()
        print(f"Total de receitas: {todas_receitas.count()}")
        for receita in todas_receitas:
            print(f"   - Receita ID: {receita.id}")
            print(f"     Consulta ID: {receita.consulta.id}")
            print(f"     Médico: {receita.consulta.medico}")
            print(f"     Medicamentos: {receita.medicamentos}")
            
    except User.DoesNotExist:
        print("❌ Usuário drjoao não encontrado")
    except Exception as e:
        print(f"❌ Erro geral: {e}")

if __name__ == "__main__":
    test_user_medico_relation()