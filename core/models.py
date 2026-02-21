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
    precio_adulto = models.DecimalField(max_digits=8, decimal_places=2, default=0, blank=True)
    precio_nino = models.DecimalField(max_digits=8, decimal_places=2, default=0, blank=True)
    lemonsqueezy_variant_id = models.CharField(max_length=50, blank=True, default="")
    # Nota: Los campos cupo_maximo y disponibles aquí suelen ser una referencia general
    cupo_maximo = models.PositiveIntegerField(default=15)
    cupos_disponibles = models.PositiveIntegerField(default=15)

    def __str__(self):
        return f"{self.nombre} - {self.destino.nombre}"

    def precio_adulto_final(self):
        return self.precio_adulto if self.precio_adulto and self.precio_adulto > 0 else self.precio

    def precio_nino_final(self):
        return self.precio_nino if self.precio_nino and self.precio_nino > 0 else self.precio

class SalidaTour(models.Model):
    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name="salidas")
    fecha = models.DateField()
    # --- CAMBIO: Se agrega el horario ---
    hora = models.TimeField(null=True, blank=True) 
    cupo_maximo = models.PositiveIntegerField()
    cupos_disponibles = models.PositiveIntegerField()
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="salidas_creadas")

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
        ("bloqueada_por_agencia", "Bloqueada por Agencia"),
    )

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    salida = models.ForeignKey(SalidaTour, on_delete=models.CASCADE, related_name="reservas")
    adultos = models.PositiveIntegerField()
    ninos = models.PositiveIntegerField()
    total_pagar = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=30, choices=ESTADOS, default="pendiente")
    fecha_reserva = models.DateTimeField(default=timezone.now)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reservas_creadas")
    
    # Nuevos campos para tracking de agencias
    archivo_agencia = models.FileField(upload_to='agencia_vouchers/', null=True, blank=True)
    codigo_agencia = models.CharField(max_length=50, null=True, blank=True)
    limite_pago_agencia = models.DateTimeField(null=True, blank=True)

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
        ("efectivo", "Efectivo"),
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

#imagenes
from django.db import models

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="perfil")
    foto = models.ImageField(upload_to="perfiles/", blank=True, null=True, help_text="Foto de perfil")
    telefono = models.CharField(max_length=20, blank=True, null=True)
    biografia = models.TextField(blank=True, null=True)
    is_agencia = models.BooleanField(default=False, verbose_name="Es agencia de tours", help_text="Si se activa, el usuario podrá bloquear reservas por 15 días")

    def __str__(self):
        return f"Perfil de {self.user.username}"

class Galeria(models.Model):
    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name='fotos', null=True, blank=True)
    imagen = models.ImageField(upload_to='galeria_tours/', blank=True, null=True, help_text="Sube una foto local (desde tu PC)")
    imagen_url = models.URLField(max_length=500, blank=True, null=True, help_text="O pega el enlace de Drive/Photos/Internet")
    fecha_agregada = models.DateTimeField(auto_now_add=True)

    def obtener_imagen_url(self):
        if self.imagen:
            return self.imagen.url
        
        if self.imagen_url:
            import re
            # Si es un link de Google Drive (tipo /file/d/ID/view)
            m = re.search(r'/file/d/([a-zA-Z0-9_-]+)', self.imagen_url)
            if m:
                return f"https://drive.google.com/uc?export=view&id={m.group(1)}"
            
            # Si es un link de Google Drive (tipo /open?id=ID)
            m2 = re.search(r'id=([a-zA-Z0-9_-]+)', self.imagen_url)
            if m2 and 'drive.google.com' in self.imagen_url:
                return f"https://drive.google.com/uc?export=view&id={m2.group(1)}"
            
            return self.imagen_url
        return ""

    def __str__(self):
        return f"Foto de {self.tour.nombre if self.tour else 'Galería'} - {self.fecha_agregada.strftime('%Y-%m-%d')}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        try:
            old_inst = Galeria.objects.get(pk=self.pk) if not is_new else None
        except Galeria.DoesNotExist:
            old_inst = None

        super().save(*args, **kwargs)

        if self.imagen:
            # Solo si se acaba de crear el registro, o si cambió la imagen frente al anterior
            if is_new or (old_inst and old_inst.imagen != self.imagen):
                self._aplicar_marca_agua()

    def _aplicar_marca_agua(self):
        try:
            from PIL import Image, ImageDraw, ImageFont
            import os

            if not self.imagen or not getattr(self.imagen, 'path', None):
                return
            
            filepath = self.imagen.path
            if not os.path.exists(filepath):
                return
                
            img = Image.open(filepath)
            original_mode = img.mode
            img = img.convert('RGBA')

            txt = Image.new('RGBA', img.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(txt)
            
            text = "TortugaTur"
            width, height = img.size
            fontsize = max(int(width / 20), 12)  # Letra pequeña (1/20 del ancho)

            try:
                import platform
                if platform.system() == "Windows":
                    font = ImageFont.truetype("arialbd.ttf", fontsize) # Arial bold
                else:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", fontsize)
            except Exception:
                try:
                    if platform.system() == "Windows":
                        font = ImageFont.truetype("arial.ttf", fontsize)
                    else:
                        font = font = ImageFont.load_default()
                except Exception:
                    font = ImageFont.load_default()

            try:
                if hasattr(draw, "textbbox"):
                    text_bbox = draw.textbbox((0, 0), text, font=font)
                    text_width = text_bbox[2] - text_bbox[0]
                    text_height = text_bbox[3] - text_bbox[1]
                else:
                    text_width, text_height = draw.textsize(text, font=font)
            except Exception:
                text_width, text_height = (fontsize * len(text) // 1.5, fontsize)

            # Margen inferior derecho
            margin_right = int(width * 0.03)
            margin_bottom = int(height * 0.03)
            x = width - text_width - margin_right
            y = height - text_height - margin_bottom

            # Sombra y Contorno grueso para asegurar lectura
            color_sombra = (0, 0, 0, 200)
            offsets = [(2,2), (-2,-2), (2,-2), (-2,2), (2,0), (-2,0), (0,2), (0,-2)]
            for ox, oy in offsets:
                draw.text((x + ox, y + oy), text, font=font, fill=color_sombra)
                
            # Texto principal en tono ligeramente translúcido
            color_texto = (255, 255, 255, 180)
            draw.text((x, y), text, font=font, fill=color_texto)

            watermarked = Image.alpha_composite(img, txt)
            
            if filepath.lower().endswith(('.jpg', '.jpeg')):
                watermarked = watermarked.convert('RGB')
                watermarked.save(filepath, quality=90)
            else:
                watermarked = watermarked.convert(original_mode)
                watermarked.save(filepath)

        except Exception as e:
            print(f"Error al aplicar marca de agua: {e}")
