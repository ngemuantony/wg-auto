# Generated migration for fixing key generation issue

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wireguard', '0004_wireguardserver_alter_wireguardpeer_options_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='wireguardserver',
            name='private_key_encrypted',
            field=models.TextField(blank=True, default='', help_text='Server private key (encrypted)'),
        ),
        migrations.AlterField(
            model_name='wireguardserver',
            name='public_key',
            field=models.CharField(blank=True, default='', help_text='Server public key', max_length=255),
        ),
    ]
