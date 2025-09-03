from django.db import migrations

TABLE = 'meu_app_paciente'


def copy_user_to_id(apps, schema_editor):
    cursor = schema_editor.connection.cursor()
    # Copy user_id into id for all rows to keep FKs consistent
    cursor.execute(f"UPDATE {TABLE} SET id = user_id")


class Migration(migrations.Migration):
    dependencies = [
        ('meu_app', '0008_fix_paciente_id_schema'),
    ]

    operations = [
        migrations.RunPython(copy_user_to_id, migrations.RunPython.noop),
    ]