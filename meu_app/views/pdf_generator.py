from django.http import HttpResponse, JsonResponse
from django.views import View
from io import BytesIO
import base64
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from datetime import datetime
import json
import qrcode
import uuid

class GerarReceitaPDFView(View):
    """View para gerar PDF de receitas médicas"""
    
    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            receita_id = data.get('receita_id', str(uuid.uuid4()))
            
            # Gerar QR Code para verificação
            qr_data_uri = self.gerar_qr_code(receita_id)
            
            # Gerar PDF
            pdf_bytes = self.gerar_pdf(data, qr_data_uri, receita_id)
            
            # Retornar PDF
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="receita-{receita_id}.pdf"'
            return response
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    def gerar_qr_code(self, receita_id):
        """Gera QR Code para verificação da receita"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        verification_url = f"https://medicine-front.vercel.app/verificar/{receita_id}"
        qr.add_data(verification_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        
        # Converter para data URI
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return f"data:image/png;base64,{img_base64}"
    
    def gerar_pdf(self, data, qr_data_uri, receita_id):
        """Gera PDF da receita usando ReportLab"""
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        
        # Extrair dados
        clinica_nome = data.get('clinica_nome', 'Clínica Médica')
        clinica_endereco = data.get('clinica_endereco', '')
        clinica_telefone = data.get('clinica_telefone', '')
        medico_nome = data.get('medico_nome', '')
        medico_crm = data.get('medico_crm', '')
        medico_especialidade = data.get('medico_especialidade', '')
        paciente_nome = data.get('paciente_nome', '')
        paciente_cpf = data.get('paciente_cpf', '')
        paciente_nascimento = data.get('paciente_nascimento', '')
        paciente_endereco = data.get('paciente_endereco', '')
        medicamentos = data.get('medicamentos', [])
        observacoes = data.get('observacoes', '')
        data_atual = datetime.now().strftime('%d/%m/%Y')
        
        # Cabeçalho
        p.setFont("Helvetica-Bold", 16)
        p.drawString(50, height - 50, clinica_nome)
        
        # Informações da clínica
        p.setFont("Helvetica", 10)
        p.drawString(50, height - 70, clinica_endereco)
        p.drawString(50, height - 85, f"Tel: {clinica_telefone}")
        
        # Linha separadora
        p.line(50, height - 95, width - 50, height - 95)
        
        # Informações do médico
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, height - 120, "MÉDICO")
        p.setFont("Helvetica", 12)
        p.drawString(50, height - 140, f"Nome: {medico_nome}")
        p.drawString(50, height - 155, f"CRM: {medico_crm}")
        p.drawString(50, height - 170, f"Especialidade: {medico_especialidade}")
        
        # Informações do paciente
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, height - 200, "PACIENTE")
        p.setFont("Helvetica", 12)
        p.drawString(50, height - 220, f"Nome: {paciente_nome}")
        if paciente_cpf:
            p.drawString(50, height - 235, f"CPF: {paciente_cpf}")
        if paciente_nascimento:
            p.drawString(50, height - 250, f"Data de Nascimento: {paciente_nascimento}")
        if paciente_endereco:
            p.drawString(50, height - 265, f"Endereço: {paciente_endereco}")
        
        # Medicamentos
        y_pos = height - 300
        p.setFont("Helvetica-Bold", 14)
        p.drawString(50, y_pos, "PRESCRIÇÃO MÉDICA")
        y_pos -= 25
        
        if medicamentos:
            for i, med in enumerate(medicamentos, 1):
                nome = med.get('nome', '')
                posologia = med.get('posologia', '')
                quantidade = med.get('quantidade', '')
                obs_med = med.get('observacoes', '')
                
                p.setFont("Helvetica-Bold", 12)
                p.drawString(50, y_pos, f"{i}. {nome}")
                y_pos -= 15
                
                p.setFont("Helvetica", 10)
                if posologia:
                    p.drawString(70, y_pos, f"Posologia: {posologia}")
                    y_pos -= 15
                if quantidade:
                    p.drawString(70, y_pos, f"Quantidade: {quantidade}")
                    y_pos -= 15
                if obs_med:
                    p.drawString(70, y_pos, f"Observações: {obs_med}")
                    y_pos -= 15
                
                y_pos -= 10  # Espaço entre medicamentos
        else:
            p.setFont("Helvetica", 12)
            p.drawString(50, y_pos, "Medicamento não especificado")
            y_pos -= 20
        
        # Observações gerais
        if observacoes:
            y_pos -= 10
            p.setFont("Helvetica-Bold", 12)
            p.drawString(50, y_pos, "Observações Gerais:")
            y_pos -= 15
            
            p.setFont("Helvetica", 10)
            # Quebrar texto longo em múltiplas linhas
            max_width = width - 100
            words = observacoes.split()
            line = ""
            for word in words:
                test_line = line + " " + word if line else word
                if p.stringWidth(test_line, "Helvetica", 10) < max_width:
                    line = test_line
                else:
                    p.drawString(50, y_pos, line)
                    y_pos -= 15
                    line = word
            if line:
                p.drawString(50, y_pos, line)
        
        # Adicionar QR Code
        if qr_data_uri:
            try:
                qr_img = ImageReader(BytesIO(base64.b64decode(qr_data_uri.split(',')[1])))
                p.drawImage(qr_img, width - 100, 50, 80, 80)
                p.setFont("Helvetica", 8)
                p.drawString(width - 120, 40, "Verificação Digital")
            except Exception as e:
                print(f"Erro ao adicionar QR Code: {e}")
        
        # Assinatura
        p.line(width/2 - 100, 100, width/2 + 100, 100)
        p.setFont("Helvetica", 10)
        p.drawCentredString(width/2, 90, f"{medico_nome}")
        p.drawCentredString(width/2, 75, f"CRM: {medico_crm}")
        
        # ID da receita e data
        p.setFont("Helvetica", 8)
        p.drawCentredString(width/2, 30, f"Receita ID: {receita_id} | Data: {data_atual}")
        
        p.save()
        buffer.seek(0)
        return buffer.getvalue()