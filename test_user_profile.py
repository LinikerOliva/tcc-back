#!/usr/bin/env python3
import requests
import json

# Configurações
base_url = "http://127.0.0.1:8000/api"
token = "d273dfa5a597e2263bd0fffa66438b79e3513a50"

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Token {token}"
}

try:
    # Verificar perfil do usuário
    print("=== PERFIL DO USUÁRIO ===")
    user_response = requests.get(f"{base_url}/auth/users/me/", headers=headers)
    if user_response.status_code == 200:
        user_data = user_response.json()
        print(f"Usuário: {user_data.get('username')}")
        print(f"Role: {user_data.get('role')}")
        print(f"ID: {user_data.get('id')}")
        print(f"Tem paciente: {'paciente' in user_data}")
        print(f"Tem médico: {'medico' in user_data}")
    else:
        print(f"Erro ao obter perfil: {user_response.status_code}")
    
    # Verificar receitas sem filtros
    print("\n=== RECEITAS (SEM FILTROS) ===")
    receitas_response = requests.get(f"{base_url}/receitas/", headers=headers)
    if receitas_response.status_code == 200:
        receitas_data = receitas_response.json()
        print(f"Total de receitas: {receitas_data.get('count', len(receitas_data.get('results', [])))}")
        if receitas_data.get('results'):
            print("Primeira receita:")
            print(json.dumps(receitas_data['results'][0], indent=2))
    else:
        print(f"Erro ao obter receitas: {receitas_response.status_code}")
        print(receitas_response.text)
    
    # Verificar receitas com filtro de médico
    print("\n=== RECEITAS (FILTRO MÉDICO) ===")
    receitas_medico_response = requests.get(f"{base_url}/receitas/?medico_id=b0c00303-107f-42d3-ab59-3a57ea0a9ee5", headers=headers)
    if receitas_medico_response.status_code == 200:
        receitas_medico_data = receitas_medico_response.json()
        print(f"Total de receitas do médico: {receitas_medico_data.get('count', len(receitas_medico_data.get('results', [])))}")
    else:
        print(f"Erro ao obter receitas do médico: {receitas_medico_response.status_code}")

except Exception as e:
    print(f"Erro na requisição: {e}")