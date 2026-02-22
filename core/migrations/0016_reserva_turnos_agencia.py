from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_empresaconfig"),
    ]

    operations = [
        migrations.AddField(
            model_name="reserva",
            name="hora_turno_agencia",
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reserva",
            name="hora_turno_libre",
            field=models.TimeField(blank=True, null=True),
        ),
    ]

