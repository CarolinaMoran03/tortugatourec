from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone



from django.db import models

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Destino(models.Model):
    nombre = models.CharField(max_length=100)
    imagen_url = models.URLField("Imagen (URL)", max_length=500)

    def __str__(self):
        return self.nombre

class Tour(models.Model):
    nombre = models.CharField(max_length=150)
    destino = models.ForeignKey(Destino, on_delete=models.CASCADE, related_name="tours")
    descripcion = models.TextField()
    precio = models.DecimalField(max_digits=8, decimal_places=2)
    lemonsqueezy_variant_id = models.CharField(max_length=50, blank=True, default="")
    # Nota: Los campos cupo_maximo y disponibles aquí suelen ser una referencia general
    cupo_maximo = models.PositiveIntegerField(default=15)
    cupos_disponibles = models.PositiveIntegerField(default=15)

    def __str__(self):
        return f"{self.nombre} - {self.destino.nombre}"

class SalidaTour(models.Model):
    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name="salidas")
    fecha = models.DateField()
    # --- CAMBIO: Se agrega el horario ---
    hora = models.TimeField(null=True, blank=True) 
    cupo_maximo = models.PositiveIntegerField()
    cupos_disponibles = models.PositiveIntegerField()

    def __str__(self):
        # Mostramos la hora en el string para identificarla en el admin
        hora_str = self.hora.strftime('%H:%M') if self.hora else "Sin hora"
        return f"{self.tour.nombre} - {self.fecha} ({hora_str})"

    def hay_cupo(self, adultos, ninos):
        total = adultos + ninos
        return self.cupos_disponibles >= total

class Reserva(models.Model):
    # --- CAMBIO: Se agrega "pagada" a los ESTADOS ---
    ESTADOS = (
        ("pendiente", "Pendiente"),
        ("confirmada", "Confirmada"),
        ("pagada", "Pagada"),
        ("cancelada", "Cancelada"),
    )

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    salida = models.ForeignKey(SalidaTour, on_delete=models.CASCADE, related_name="reservas")
    adultos = models.PositiveIntegerField()
    ninos = models.PositiveIntegerField()
    total_pagar = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
    fecha_reserva = models.DateTimeField(default=timezone.now)

    # Datos del cliente
    nombre = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=150)
    correo = models.EmailField()
    telefono = models.CharField(max_length=30)
    identificacion = models.CharField(max_length=50)

    def total_personas(self):
        return self.adultos + self.ninos


class Pago(models.Model):
    PROVEEDORES = (
        ("lemonsqueezy", "Lemon Squeezy"),
        ("paypal", "PayPal"),
    )
    ESTADOS = (
        ("created", "Created"),
        ("approved", "Approved"),
        ("paid", "Paid"),
        ("failed", "Failed"),
        ("canceled", "Canceled"),
    )

    reserva = models.ForeignKey(Reserva, on_delete=models.CASCADE, related_name="pagos")
    proveedor = models.CharField(max_length=20, choices=PROVEEDORES)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="created")
    moneda = models.CharField(max_length=3, default="USD")
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    external_id = models.CharField(max_length=120, blank=True)
    checkout_url = models.URLField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-creado_en",)

    def __str__(self):
        return f"{self.proveedor} #{self.id} - Reserva {self.reserva_id}"

# Los modelos Ticket y Resena se mantienen igual...

class Ticket(models.Model):
    reserva = models.OneToOneField(Reserva, on_delete=models.CASCADE, related_name="ticket")
    codigo = models.CharField(max_length=50, unique=True)
    fecha_emision = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Ticket {self.codigo}"


class Resena(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name="resenas")
    puntuacion = models.PositiveIntegerField()  # 1 a 5
    comentario = models.TextField()
    fecha = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.tour.nombre} - {self.puntuacion}⭐"
