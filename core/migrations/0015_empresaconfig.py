from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_salidatour_duracion"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmpresaConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre_empresa", models.CharField(default="TortugaTur", max_length=150)),
                ("ruc", models.CharField(blank=True, default="", max_length=30)),
                ("direccion", models.CharField(blank=True, default="", max_length=255)),
                ("telefono", models.CharField(blank=True, default="", max_length=50)),
                ("correo", models.EmailField(blank=True, default="", max_length=254)),
            ],
            options={
                "verbose_name": "Configuracion de Empresa",
                "verbose_name_plural": "Configuracion de Empresa",
            },
        ),
    ]
