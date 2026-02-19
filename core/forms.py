from django import forms
from .models import Destino

class DestinoForm(forms.ModelForm):
    class Meta:
        model = Destino
        # Solo estos dos campos existen en tu modelo Destino
        fields = ['nombre', 'imagen_url'] 
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'w-full p-3 border border-slate-200 rounded-xl outline-none focus:border-primary',
                'placeholder': 'Ej. Isla Santa Cruz'
            }),
            'imagen_url': forms.URLInput(attrs={
                'class': 'w-full p-3 border border-slate-200 rounded-xl outline-none focus:border-primary',
                'placeholder': 'https://link-de-la-imagen.jpg'
            }),
        }


#destinotour
from django import forms
from .models import Destino, Tour

class TourForm(forms.ModelForm):
    class Meta:
        model = Tour
        fields = ['nombre', 'destino', 'descripcion', 'precio', 'precio_adulto', 'precio_nino', 'lemonsqueezy_variant_id', 'cupo_maximo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'w-full p-3 border border-slate-200 rounded-xl outline-none focus:border-primary', 'placeholder': 'Nombre del Tour'}),
            'destino': forms.Select(attrs={'class': 'w-full p-3 border border-slate-200 rounded-xl outline-none focus:border-primary'}),
            'descripcion': forms.Textarea(attrs={'class': 'w-full p-3 border border-slate-200 rounded-xl outline-none focus:border-primary', 'rows': 3}),
            'precio': forms.NumberInput(attrs={'class': 'w-full p-3 border border-slate-200 rounded-xl outline-none focus:border-primary', 'step': '0.01'}),
            'precio_adulto': forms.NumberInput(attrs={'class': 'w-full p-3 border border-slate-200 rounded-xl outline-none focus:border-primary', 'step': '0.01'}),
            'precio_nino': forms.NumberInput(attrs={'class': 'w-full p-3 border border-slate-200 rounded-xl outline-none focus:border-primary', 'step': '0.01'}),
            'lemonsqueezy_variant_id': forms.TextInput(attrs={'class': 'w-full p-3 border border-slate-200 rounded-xl outline-none focus:border-primary', 'placeholder': 'Ej. 987654'}),
            'cupo_maximo': forms.NumberInput(attrs={'class': 'w-full p-3 border border-slate-200 rounded-xl outline-none focus:border-primary'}),
        }

#logueo
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
import re

class RegistroTuristaForm(UserCreationForm):
    # Asegúrate de incluir estos campos si no los tenías
    first_name = forms.CharField(label="Nombre", required=True)
    email = forms.EmailField(label="Correo Electrónico", required=True)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'email']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data.get("first_name", "").strip()
        user.email = self.cleaned_data.get("email", "").strip().lower()
        if commit:
            user.save()
        return user

    def clean_password1(self):
        password = self.cleaned_data.get("password1")
        
        # 1. Validar longitud mínima
        if len(password) < 8:
            raise ValidationError("La contraseña debe tener al menos 8 caracteres.")
        
        # 2. Validar caracteres especiales
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            raise ValidationError("La contraseña debe incluir al menos un carácter especial (ej: @, #, $, !).")
            
        return password
    
#formulario
from django import forms

class ContactoForm(forms.Form):
    # Asegúrate de que las opciones del Select coincidan con lo que quieres
    OPCIONES_ASUNTO = [
        ('Reservas', 'Reservas'),
        ('Pagos', 'Pagos y Facturación'),
        ('Quejas', 'Quejas y Sugerencias'),
        ('Otros', 'Otros'),
    ]
    
    nombre = forms.CharField(max_length=100)
    email = forms.EmailField()
    asunto = forms.ChoiceField(choices=OPCIONES_ASUNTO)
    mensaje = forms.CharField(widget=forms.Textarea)
