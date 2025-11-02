#!/usr/bin/env python3
"""
Script para testar o endpoint de geração de PDF
"""
import requests
import json

def test_pdf_endpoint():
    url = "http://localhost:8000/api/gerar-receita/"
    
    payload = {
        "paciente_nome": "João Silva",
        "paciente_cpf": "123.456.789-00",
        "paciente_nascimento": "15/03/1985",
        "medico_nome": "Dr. Maria Santos",
        "medico_crm": "123456-SP",
        "medicamentos": [
            {
                "nome": "Paracetamol 500mg",
                "posologia": "1 comprimido de 8 em 8 horas",
                "quantidade": "15 comprimidos"
            }
        ],
        "observacoes": "Tomar após as refeições"
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        print("Testando endpoint de geração de PDF...")
        print(f"URL: {url}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(url, json=payload, headers=headers)
        
        print(f"Status Code: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            # Salvar PDF
            with open("teste_receita_gerada.pdf", "wb") as f:
                f.write(response.content)
            print("PDF gerado com sucesso! Salvo como 'teste_receita_gerada.pdf'")
        else:
            print(f"Erro: {response.text}")
            
    except Exception as e:
        print(f"Erro na requisição: {e}")

if __name__ == "__main__":
    test_pdf_endpoint()