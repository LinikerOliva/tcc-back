#!/usr/bin/env python3
"""
Gerenciador de Certificados para Assinatura Digital
Cria e gerencia certificados de teste
"""

import os
import uuid
from datetime import datetime, timedelta
from django.conf import settings
import logging

# Bibliotecas para certificados
try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID, ExtensionOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False
    logging.warning("Cryptography não disponível - geração de certificados desabilitada")

logger = logging.getLogger(__name__)

class CertificateManager:
    """Gerenciador de certificados digitais"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.certificates_dir = os.path.join(settings.BASE_DIR, 'certificates')
        self.ensure_certificates_dir()
    
    def ensure_certificates_dir(self):
        """Garante que o diretório de certificados existe"""
        if not os.path.exists(self.certificates_dir):
            os.makedirs(self.certificates_dir)
            self.logger.info(f"Diretório de certificados criado: {self.certificates_dir}")
    
    def generate_test_certificate(self, doctor_name="Dr. Teste", doctor_crm="123456-SP", password="teste123"):
        """Gera um certificado de teste para assinatura digital"""
        try:
            if not CRYPTOGRAPHY_AVAILABLE:
                raise Exception("Cryptography não disponível")
            
            self.logger.info(f"Gerando certificado de teste para {doctor_name}")
            
            # 1. Gerar chave privada RSA
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
            )
            
            # 2. Criar informações do certificado
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "São Paulo"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "São Paulo"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Sistema Médico TCC"),
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Certificados de Teste"),
                x509.NameAttribute(NameOID.COMMON_NAME, doctor_name),
                x509.NameAttribute(NameOID.EMAIL_ADDRESS, f"teste@medico.com"),
            ])
            
            # 3. Criar certificado
            cert = x509.CertificateBuilder().subject_name(
                subject
            ).issuer_name(
                issuer
            ).public_key(
                private_key.public_key()
            ).serial_number(
                x509.random_serial_number()
            ).not_valid_before(
                datetime.utcnow()
            ).not_valid_after(
                datetime.utcnow() + timedelta(days=365)
            ).add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("localhost"),
                    x509.DNSName("sistema-medico.local"),
                ]),
                critical=False,
            ).add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=True,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            ).sign(private_key, hashes.SHA256())
            
            # 4. Gerar nomes dos arquivos
            timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
            base_name = f"certificado-medico-{timestamp}"
            
            pfx_path = os.path.join(self.certificates_dir, f"{base_name}.pfx")
            pem_path = os.path.join(self.certificates_dir, f"{base_name}.pem")
            key_path = os.path.join(self.certificates_dir, f"{base_name}-key.pem")
            info_path = os.path.join(self.certificates_dir, f"{base_name}-info.txt")
            
            # 5. Salvar certificado PKCS#12 (PFX)
            pfx_data = pkcs12.serialize_key_and_certificates(
                name=doctor_name.encode(),
                key=private_key,
                cert=cert,
                cas=None,
                encryption_algorithm=serialization.BestAvailableEncryption(password.encode())
            )
            
            with open(pfx_path, 'wb') as f:
                f.write(pfx_data)
            
            # 6. Salvar certificado PEM
            with open(pem_path, 'wb') as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            
            # 7. Salvar chave privada PEM
            with open(key_path, 'wb') as f:
                f.write(private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.BestAvailableEncryption(password.encode())
                ))
            
            # 8. Salvar informações do certificado
            cert_info = f"""Certificado de Teste - Sistema Médico TCC
===========================================

Médico: {doctor_name}
CRM: {doctor_crm}
Data de Criação: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
Validade: {cert.not_valid_after.strftime('%d/%m/%Y %H:%M:%S')}
Senha: {password}

Arquivos Gerados:
- Certificado PFX: {base_name}.pfx
- Certificado PEM: {base_name}.pem  
- Chave Privada: {base_name}-key.pem

ATENÇÃO: Este é um certificado de TESTE.
NÃO deve ser usado em produção!
"""
            
            with open(info_path, 'w', encoding='utf-8') as f:
                f.write(cert_info)
            
            result = {
                'success': True,
                'pfx_path': pfx_path,
                'pem_path': pem_path,
                'key_path': key_path,
                'info_path': info_path,
                'password': password,
                'doctor_name': doctor_name,
                'doctor_crm': doctor_crm,
                'valid_until': cert.not_valid_after.isoformat()
            }
            
            self.logger.info(f"Certificado de teste criado: {pfx_path}")
            return result
            
        except Exception as e:
            self.logger.error(f"Erro ao gerar certificado: {e}")
            raise
    
    def list_certificates(self):
        """Lista todos os certificados disponíveis"""
        try:
            certificates = []
            
            if not os.path.exists(self.certificates_dir):
                return certificates
            
            for filename in os.listdir(self.certificates_dir):
                if filename.endswith('.pfx'):
                    cert_path = os.path.join(self.certificates_dir, filename)
                    info_path = cert_path.replace('.pfx', '-info.txt')
                    
                    cert_info = {
                        'filename': filename,
                        'path': cert_path,
                        'size': os.path.getsize(cert_path),
                        'created': datetime.fromtimestamp(os.path.getctime(cert_path)).isoformat()
                    }
                    
                    # Ler informações se disponível
                    if os.path.exists(info_path):
                        try:
                            with open(info_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                                # Extrair informações básicas
                                for line in content.split('\n'):
                                    if line.startswith('Médico:'):
                                        cert_info['doctor_name'] = line.split(':', 1)[1].strip()
                                    elif line.startswith('CRM:'):
                                        cert_info['doctor_crm'] = line.split(':', 1)[1].strip()
                                    elif line.startswith('Senha:'):
                                        cert_info['password'] = line.split(':', 1)[1].strip()
                        except Exception:
                            pass
                    
                    certificates.append(cert_info)
            
            return sorted(certificates, key=lambda x: x['created'], reverse=True)
            
        except Exception as e:
            self.logger.error(f"Erro ao listar certificados: {e}")
            return []
    
    def get_default_certificate(self):
        """Retorna o certificado padrão mais recente"""
        certificates = self.list_certificates()
        if certificates:
            return certificates[0]  # Mais recente
        return None

    def get_certificate_path(self, filename):
        """
        Retorna o caminho completo para um certificado específico
        """
        try:
            cert_path = os.path.join(self.certificates_dir, filename)
            if os.path.exists(cert_path):
                return cert_path
            return None
        except Exception as e:
            self.logger.error(f"Erro ao obter caminho do certificado: {e}")
            return None

# Instância global do gerenciador
certificate_manager = CertificateManager()