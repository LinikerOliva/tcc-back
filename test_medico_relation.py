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
    # Verificar médicos
    print("=== MÉDICOS CADASTRADOS ===")
    medicos_response = requests.get(f"{base_url}/medicos/", headers=headers)
    if medicos_response.status_code == 200:
        medicos_data = medicos_response.json()
        medicos_list = medicos_data.get('results', medicos_data) if isinstance(medicos_data, dict) else medicos_data
        print(f"Total de médicos: {len(medicos_list)}")
        
        for medico in medicos_list:
            print(f"- Médico ID: {medico.get('id')}")
            print(f"  User ID: {medico.get('user', {}).get('id')}")
            print(f"  Username: {medico.get('user', {}).get('username')}")
            print(f"  Nome: {medico.get('user', {}).get('first_name')} {medico.get('user', {}).get('last_name')}")
            print()
    else:
        print(f"Erro ao obter médicos: {medicos_response.status_code}")
        print(medicos_response.text)
    
    # Verificar receitas diretamente no banco (sem filtros de permissão)
    print("=== TODAS AS RECEITAS (ADMIN VIEW) ===")
    # Vou tentar acessar como admin se possível
    receitas_response = requests.get(f"{base_url}/receitas/", headers=headers)
    if receitas_response.status_code == 200:
        receitas_data = receitas_response.json()
        receitas_list = receitas_data.get('results', receitas_data) if isinstance(receitas_data, dict) else receitas_data
        print(f"Total de receitas encontradas: {len(receitas_list)}")
        
        if receitas_list:
            print("Última receita criada:")
            print(f"- ID: {receitas_list[0].get('id')}")
            print(f"- Consulta ID: {receitas_list[0].get('consulta', {}).get('id')}")
            print(f"- Médico da consulta: {receitas_list[0].get('consulta', {}).get('medico', {}).get('user', {}).get('username')}")
            print(f"- Medicamentos: {receitas_list[0].get('medicamentos')}")
    else:
        print(f"Erro ao obter receitas: {receitas_response.status_code}")

except Exception as e:
    print(f"Erro na requisição: {e}")