from django.core.management import call_command
from django.db import migrations


def create_login_cache_table(apps, schema_editor):
    call_command(
        'createcachetable',
        'django_cache',
        database=schema_editor.connection.alias,
        verbosity=0,
    )


def drop_login_cache_table(apps, schema_editor):
    table = schema_editor.connection.ops.quote_name('django_cache')
    schema_editor.execute(f'DROP TABLE IF EXISTS {table}')


class Migration(migrations.Migration):

    dependencies = [
        ('ErrandM8App', '0002_profile_otp_attempts_alter_profile_otp_code_and_more'),
    ]

    operations = [
        migrations.RunPython(create_login_cache_table, drop_login_cache_table),
    ]
