#!/usr/bin/env python3
import requests
import json

# Configurações
url = "http://127.0.0.1:8000/api/receitas/"
token = "d273dfa5a597e2263bd0fffa66438b79e3513a50"

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Token {token}"
}

data = {
    "consulta_id": "41b532cc-753f-4850-9c73-70736e40c955",
    "medicamentos": "Paracetamol 500mg",
    "posologia": "1 comprimido de 8/8h por 7 dias",
    "observacoes": "Tomar após as refeições",
    "validade": "2024-12-01"
}

try:
    print("Enviando requisição para criar receita...")
    print(f"URL: {url}")
    print(f"Headers: {headers}")
    print(f"Data: {json.dumps(data, indent=2)}")
    
    response = requests.post(url, headers=headers, json=data)
    
    print(f"\nStatus Code: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")
    
    if response.status_code == 201:
        print("✅ Receita criada com sucesso!")
        print(json.dumps(response.json(), indent=2))
    else:
        print("❌ Erro ao criar receita:")
        try:
            error_data = response.json()
            print(json.dumps(error_data, indent=2))
        except:
            print(response.text)
            
except Exception as e:
    print(f"Erro na requisição: {e}")