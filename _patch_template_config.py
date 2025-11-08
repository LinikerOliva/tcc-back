import io, sys, os
path_models = r"c:\Users\Artleywin\OneDrive\Documentos\GitHub\tcc-back\meu_app\models.py"
with open(path_models, 'r', encoding='utf-8') as f:
    content = f.read()

# Insert fields into Medico model after status field
insert_after = "status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente')"
if insert_after in content and 'template_config = models.JSONField(' not in content:
    addition = "\n\n    # --- NOVO: Configuração de template e logo do médico ---\n    template_config = models.JSONField(null=True, blank=True, default=dict)\n    logo = models.ImageField(upload_to='logos/medicos/', null=True, blank=True)\n"
    content = content.replace(insert_after, insert_after + addition)
    with open(path_models, 'w', encoding='utf-8') as f:
        f.write(content)
    print("models.py atualizado com campos de template_config e logo.")
else:
    print("models.py já contém os campos ou não encontrou ponto de inserção.")

# Patch views/doctors.py to add endpoint
path_views = r"c:\Users\Artleywin\OneDrive\Documentos\GitHub\tcc-back\meu_app\views\doctors.py"
with open(path_views, 'r', encoding='utf-8') as f:
    vcontent = f.read()

imports_to_add = "from django.core.files.base import ContentFile\nimport base64\nimport re\n"
if 'ContentFile' not in vcontent:
    vcontent = vcontent.replace('from ..models import Medico, Secretaria\n', 'from ..models import Medico, Secretaria\n' + imports_to_add)

if '@action(detail=False, methods=[' not in vcontent or 'url_path=\'template\'' not in vcontent:
    method_code = '''\n    @action(detail=False, methods=['post', 'get'], url_path='template')\n    def template(self, request):\n        """\n        GET: retorna template_config e logo do médico autenticado (ou do médico selecionado pela secretária)\n        POST: salva template_config (JSON) e logo (base64 data URL) para o médico\n        """\n        role = getattr(request.user, 'role', None)\n\n        medico = None\n        medico_id = request.data.get('medico_id') or request.query_params.get('medico') or request.query_params.get('medico_id')\n        if role == 'medico':\n            medico = Medico.objects.filter(user=request.user).first()\n        elif role == 'secretaria':\n            if medico_id:\n                try:\n                    cand = Medico.objects.get(pk=medico_id)\n                except Medico.DoesNotExist:\n                    cand = None\n                if cand and cand in request.user.secretaria.medicos.all():\n                    medico = cand\n        elif role == 'admin':\n            if medico_id:\n                medico = Medico.objects.filter(pk=medico_id).first()\n\n        if not medico:\n            return Response({'detail': 'Médico não encontrado'}, status=status.HTTP_404_NOT_FOUND)\n\n        if request.method.lower() == 'get':\n            logo_url = None\n            if getattr(medico, 'logo', None):\n                try:\n                    logo_url = request.build_absolute_uri(medico.logo.url)\n                except Exception:\n                    logo_url = str(medico.logo)\n            return Response({\n                'medico_id': str(medico.pk),\n                'template_config': getattr(medico, 'template_config', None) or {},\n                'doctor_logo_url': logo_url,\n            })\n\n        template_config = request.data.get('template_config')\n        doctor_logo = request.data.get('doctor_logo')\n\n        if isinstance(template_config, str):\n            try:\n                import json\n                template_config = json.loads(template_config)\n            except Exception:\n                template_config = None\n\n        if template_config is not None:\n            medico.template_config = template_config\n\n        if isinstance(doctor_logo, str) and doctor_logo.startswith('data:'):\n            try:\n                match = re.match(r"data:(.*?);base64,(.*)", doctor_logo)\n                if match:\n                    mime = match.group(1)\n                    b64 = match.group(2)\n                    ext = 'png'\n                    if 'jpeg' in mime or 'jpg' in mime:\n                        ext = 'jpg'\n                    elif 'gif' in mime:\n                        ext = 'gif'\n                    filename = f"medico_{medico.pk}.{ext}"\n                    medico.logo.save(filename, ContentFile(base64.b64decode(b64)), save=False)\n            except Exception:\n                pass\n\n        medico.save()\n\n        logo_url = None\n        if getattr(medico, 'logo', None):\n            try:\n                logo_url = request.build_absolute_uri(medico.logo.url)\n            except Exception:\n                logo_url = str(medico.logo)\n\n        return Response({\n            'medico_id': str(medico.pk),\n            'template_config': getattr(medico, 'template_config', None) or {},\n            'doctor_logo_url': logo_url,\n            'status': 'saved',\n        })\n'''
    # Append method inside class MedicoViewSet (at end of class)
    # Simple approach: find last occurrence of 'class MedicoViewSet' and insert before end of file
    if 'class MedicoViewSet' in vcontent:
        idx = vcontent.rfind('class MedicoViewSet')
        # Find class block end by last newline; append method at end of file (safe for Django)
        vcontent = vcontent + method_code
else:
    pass

with open(path_views, 'w', encoding='utf-8') as f:
    f.write(vcontent)
print("views/doctors.py atualizado com endpoint de template.")
