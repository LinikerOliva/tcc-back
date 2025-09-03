import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

SETTINGS_CANDIDATES = [
    "medicine-back.settings",
    "medicine_back.settings",
]

for candidate in SETTINGS_CANDIDATES:
    try:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", candidate)
        import django
        django.setup()
        print(f"[OK] Django inicializado com settings: {candidate}")
        break
    except Exception:
        if "DJANGO_SETTINGS_MODULE" in os.environ:
            del os.environ["DJANGO_SETTINGS_MODULE"]
else:
    raise RuntimeError("Falha ao inicializar o Django")

from django.db import connection

with connection.cursor() as cursor:
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.execute("PRAGMA foreign_key_check;")
    rows = cursor.fetchall()

if not rows:
    print("Nenhuma violação de chave estrangeira encontrada.")
else:
    print("Violações de FK encontradas (tabela, rowid, tabela_referenciada, coluna):")
    for r in rows:
        print(r)