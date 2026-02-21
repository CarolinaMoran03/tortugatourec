import json
import logging
import hmac
import hashlib
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import requests
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group, User
from django.core.mail import send_mail, EmailMessage, EmailMultiAlternatives
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import transaction
from .models import Destino, Tour, SalidaTour, Reserva, Pago, Resena, Ticket
from .utils import generar_ticket_pdf
from .forms import DestinoForm, TourForm, RegistroTuristaForm, ContactoForm, TuristaLoginForm

logger = logging.getLogger(__name__)

# ============================================
# VISTAS PÚBLICAS
# ============================================

def home(request):
    destinos = Destino.objects.all()
    tours_destacados = Tour.objects.all()[:3]
    currency_code, currency_rate = _currency_context(request)
    for tour in tours_destacados:
        display = _tour_price_display(tour, currency_rate)
        tour.precio_adulto_display = display["adulto"]
        tour.precio_nino_display = display["nino"]

    context = {
        "destinos": destinos,
        "tours_destacados": tours_destacados,
        "currency_code": currency_code,
        "currency_options": list(getattr(settings, "CURRENCY_RATES", {}).keys()),
    }

    return render(request, "core/home.html", context)

def tours(request):
    tours = Tour.objects.select_related("destino").all()
    destinos = Destino.objects.all()
    currency_code, currency_rate = _currency_context(request)
    for tour in tours:
        display = _tour_price_display(tour, currency_rate)
        tour.precio_adulto_display = display["adulto"]
        tour.precio_nino_display = display["nino"]

    context = {
        "tours": tours,
        "destinos": destinos,
        "currency_code": currency_code,
        "currency_options": list(getattr(settings, "CURRENCY_RATES", {}).keys()),
    }
    return render(request, "core/tours.html", context)

def _auto_generar_salidas_tour(tour, max_dias=30):
    if not (tour.hora_turno_1 or tour.hora_turno_2):
        return
        
    ahora = timezone.now()
    fecha_hoy = ahora.date()
    
    salidas_existentes = SalidaTour.objects.filter(tour=tour, fecha__gte=fecha_hoy)
    existentes = {}
    for s in salidas_existentes:
        if s.fecha not in existentes:
            existentes[s.fecha] = set()
        existentes[s.fecha].add(s.hora)
        
    nuevas_salidas = []
    for d in range(max_dias):
        fecha_iter = fecha_hoy + timedelta(days=d)
        
        if tour.hora_turno_1 and tour.hora_turno_1 not in existentes.get(fecha_iter, set()):
            nuevas_salidas.append(SalidaTour(
                tour=tour, fecha=fecha_iter, hora=tour.hora_turno_1,
                cupo_maximo=tour.cupo_maximo, cupos_disponibles=tour.cupo_maximo,
                duracion=tour.duracion
            ))
            
        if tour.hora_turno_2 and tour.hora_turno_2 not in existentes.get(fecha_iter, set()):
            nuevas_salidas.append(SalidaTour(
                tour=tour, fecha=fecha_iter, hora=tour.hora_turno_2,
                cupo_maximo=tour.cupo_maximo, cupos_disponibles=tour.cupo_maximo,
                duracion=tour.duracion
            ))
            
    if nuevas_salidas:
        SalidaTour.objects.bulk_create(nuevas_salidas)

def lista_tours(request):
    destino_id = request.GET.get("destino")
    fecha = request.GET.get("fecha")
    personas = request.GET.get("personas")

    if not (destino_id and fecha and personas):
        return render(request, "core/lista_tours.html", {"tours_con_salidas": {}})
        
    # Auto generar salidas para este destino antes de filtrar
    tours_destino = Tour.objects.filter(destino_id=destino_id)
    for t in tours_destino:
        _auto_generar_salidas_tour(t)

    salidas_brutas = SalidaTour.objects.filter(
        tour__destino_id=destino_id,
        fecha=fecha,
        cupos_disponibles__gte=int(personas)
    ).select_related('tour').order_by('hora')

    ahora = timezone.now()
    fecha_hoy = ahora.date()
    hora_actual = ahora.time()

    # Agrupamos por Tour y filtramos fechas/horas pasadas
    tours_con_salidas = {}
    for s in salidas_brutas:
        # Invalidar si la fecha de búsqueda ya pasó
        if s.fecha < fecha_hoy:
            continue
        # Invalidar si es hoy y la hora ya pasó
        if s.fecha == fecha_hoy and s.hora and s.hora < hora_actual:
            continue
            
        if s.tour not in tours_con_salidas:
            tours_con_salidas[s.tour] = []
        tours_con_salidas[s.tour].append(s)

    currency_code, currency_rate = _currency_context(request)
    for tour in tours_con_salidas.keys():
        display = _tour_price_display(tour, currency_rate)
        tour.precio_adulto_display = display["adulto"]
        tour.precio_nino_display = display["nino"]

    return render(request, "core/lista_tours.html", {
        "tours_con_salidas": tours_con_salidas,
        "fecha_busqueda": fecha,
        "personas": personas,
        "currency_code": currency_code,
        "currency_options": list(getattr(settings, "CURRENCY_RATES", {}).keys()),
    })

# ============================================
# DETALLE DEL TOUR Y RESERVA (ACTUALIZADO)
# ============================================

def tour_detalle(request, pk):
    tour = get_object_or_404(Tour, pk=pk)
    
    # Auto generar salidas para los proximos dias
    _auto_generar_salidas_tour(tour)
    
    # Filtrar solo salidas futuras con cupos disponibles (y que no haya pasado la hora si es hoy)
    ahora = timezone.now()
    fecha_hoy = ahora.date()
    hora_actual = ahora.time()
    
    salidas_brutas = SalidaTour.objects.filter(
        tour=tour, 
        cupos_disponibles__gt=0,
        fecha__gte=fecha_hoy
    ).order_by('fecha', 'hora')
    
    salidas = []
    for s in salidas_brutas:
        if s.fecha == fecha_hoy and s.hora and s.hora < hora_actual:
            continue
        salidas.append(s)

    if request.method == "POST":
        # Verificar si es una petición AJAX
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        try:
            salida_id = request.POST.get("salida")
            adultos = int(request.POST.get("adultos", 0))
            ninos = int(request.POST.get("ninos", 0))
            nombre = request.POST.get("nombre", "")
            telefono = request.POST.get("telefono", "")
            identificacion = request.POST.get("identificacion", "")

            # Validaciones
            es_agencia = hasattr(request.user, 'perfil') and request.user.perfil.is_agencia
            
            fecha_agencia = request.POST.get("fecha_agencia")

            if es_agencia and fecha_agencia:
                from datetime import datetime
                try:
                    fecha_obj = datetime.strptime(fecha_agencia, "%Y-%m-%d").date()
                except ValueError:
                    error_msg = "Formato de fecha inválido."
                    if is_ajax: return JsonResponse({'error': error_msg}, status=400)
                    messages.error(request, error_msg)
                    return redirect('tour_detalle', pk=pk)
                    
                if fecha_obj < fecha_hoy:
                    error_msg = "No puedes seleccionar una fecha en el pasado."
                    if is_ajax: return JsonResponse({'error': error_msg}, status=400)
                    messages.error(request, error_msg)
                    return redirect('tour_detalle', pk=pk)
                
                # Buscar o crear la salida
                salida = SalidaTour.objects.filter(tour=tour, fecha=fecha_obj).first()
                if not salida:
                    salida = SalidaTour.objects.create(
                        tour=tour,
                        fecha=fecha_obj,
                        hora=None,
                        cupo_maximo=16,
                        cupos_disponibles=16
                    )
            else:
                if not salida_id:
                    error_msg = "Debes seleccionar una fecha."
                    if is_ajax:
                        return JsonResponse({'error': error_msg}, status=400)
                    messages.error(request, error_msg)
                    return redirect('tour_detalle', pk=pk)

                salida = get_object_or_404(SalidaTour, id=salida_id, tour=tour)
                
                # Validar que la fecha y hora seleccionada no haya pasado al momento de enviar POST
                if salida.fecha < fecha_hoy or (salida.fecha == fecha_hoy and salida.hora and salida.hora < hora_actual):
                    error_msg = "Lo sentimos, el horario para este tour ya ha pasado. Por favor selecciona otra fecha u horario."
                    if is_ajax:
                        return JsonResponse({'error': error_msg}, status=400)
                    messages.error(request, error_msg)
                    return redirect('tour_detalle', pk=pk)

            total_personas = adultos + ninos

            if total_personas <= 0:
                error_msg = "Debes seleccionar al menos una persona."
                if is_ajax:
                    return JsonResponse({'error': error_msg}, status=400)
                messages.error(request, error_msg)
                return redirect('tour_detalle', pk=pk)

            if not salida.hay_cupo(adultos, ninos):
                error_msg = "No hay suficientes cupos disponibles para esta salida."
                if is_ajax:
                    return JsonResponse({'error': error_msg}, status=400)
                messages.error(request, error_msg)
                return redirect('tour_detalle', pk=pk)

            # Validar datos obligatorios solo si el usuario está autenticado
            if request.user.is_authenticated and not all([nombre, telefono, identificacion]):
                error_msg = "Completa todos tus datos personales."
                if is_ajax:
                    return JsonResponse({'error': error_msg}, status=400)
                messages.error(request, error_msg)
                return redirect('tour_detalle', pk=pk)

            if es_agencia:
                if total_personas > 16:
                    error_msg = "Las agencias solo pueden bloquear un máximo de 16 pasajeros por reserva."
                    if is_ajax:
                        return JsonResponse({'error': error_msg}, status=400)
                    messages.error(request, error_msg)
                    return redirect('tour_detalle', pk=pk)

                # Calcular total a pagar (adulto/niño) referencial
                precio_adulto = tour.precio_adulto_final()
                precio_nino = tour.precio_nino_final()
                total_pagar = (adultos * precio_adulto) + (ninos * precio_nino)

                # Calcular fecha límite (15 días a partir de hoy)
                fecha_limite = timezone.now() + timedelta(days=15)
                codigo_agencia = request.POST.get("codigo_agencia", "")
                
                if not codigo_agencia:
                    error_msg = "El código de agencia (VOUCHER) es obligatorio."
                    if is_ajax:
                        return JsonResponse({'error': error_msg}, status=400)
                    messages.error(request, error_msg)
                    return redirect('tour_detalle', pk=pk)
                    
                archivo_agencia = request.FILES.get("archivo_agencia")

                # Crear reserva bloqueada y descontar cupos
                with transaction.atomic():
                    salida = SalidaTour.objects.select_for_update().get(id=salida.id)
                    if salida.cupos_disponibles < total_personas:
                         raise ValueError("Cupos no disponibles")

                    reserva = Reserva.objects.create(
                        usuario=request.user,
                        salida=salida,
                        adultos=adultos,
                        ninos=ninos,
                        total_pagar=total_pagar,
                        nombre=nombre if nombre else request.user.first_name,
                        apellidos="",
                        correo=request.user.email,
                        telefono=telefono,
                        identificacion=identificacion,
                        estado="bloqueada_por_agencia",
                        codigo_agencia=codigo_agencia,
                        archivo_agencia=archivo_agencia,
                        limite_pago_agencia=fecha_limite
                    )

                    salida.cupos_disponibles -= total_personas
                    salida.save(update_fields=["cupos_disponibles"])

                msg = "¡Bloqueo exitoso! Tienes la responsabilidad de confirmar o cancelar esta reserva antes de la fecha límite."
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'reserva_id': reserva.id,
                        'redirect_url': reverse('mis_reservas') # O una vista de exito
                    })
                else:
                    messages.success(request, msg)
                    return redirect('mis_reservas')

            else:
                # Flujo normal de Turista
                # Calcular total a pagar (adulto/niño)
                precio_adulto = tour.precio_adulto_final()
                precio_nino = tour.precio_nino_final()
                total_pagar = (adultos * precio_adulto) + (ninos * precio_nino)

                # Crear la reserva con estado PENDIENTE (hasta que pague)
                reserva = Reserva.objects.create(
                    usuario=request.user if request.user.is_authenticated else None,
                    salida=salida,
                    adultos=adultos,
                    ninos=ninos,
                    total_pagar=total_pagar,
                    nombre=nombre if nombre else (request.user.first_name if request.user.is_authenticated else ""),
                    apellidos="",  # Puedes agregar este campo al formulario si quieres
                    correo=request.user.email if request.user.is_authenticated else "",
                    telefono=telefono,
                    identificacion=identificacion,
                    estado="pendiente"  # IMPORTANTE: Pendiente hasta que pague
                )

                # NO descontamos cupos aquí, se descontarán después del pago

                # Responder con la URL del checkout
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'reserva_id': reserva.id,
                        'redirect_url': reverse('checkout_reserva', args=[reserva.id])
                    })
                else:
                    messages.success(request, "Reserva iniciada. Completa el pago para confirmar.")
                    return redirect('checkout_reserva', reserva_id=reserva.id)

        except Exception as e:
            error_msg = f"Error al procesar la reserva: {str(e)}"
            if is_ajax:
                return JsonResponse({'error': error_msg}, status=500)
            messages.error(request, error_msg)
            return redirect('tour_detalle', pk=pk)

    resenas = tour.resenas.select_related("usuario").order_by("-fecha")
    fotos = tour.fotos.all().order_by('-fecha_agregada')

    currency_code, currency_rate = _currency_context(request)
    price_display = _tour_price_display(tour, currency_rate)
    precio_adulto = price_display["adulto"]
    precio_nino = price_display["nino"]

    salida_seleccionada = request.GET.get('salida')

    import json
    return render(request, "core/tour_detalle.html", {
        "tour": tour,
        "salidas": salidas,
        "salida_seleccionada": salida_seleccionada,
        "resenas": resenas,
        "fotos": fotos,
        "currency_code": currency_code,
        "currency_rate": str(currency_rate),
        "precio_adulto": precio_adulto,
        "precio_nino": precio_nino,
        "payment_currency": _currency(),
        "currency_options": list(getattr(settings, "CURRENCY_RATES", {}).keys()),
        "currency_rates_json": json.dumps(getattr(settings, "CURRENCY_RATES", {})),
        "whatsapp_message": f"Hola, quiero informacion del tour {tour.nombre}",
    })

@login_required
@require_POST
def crear_resena(request, pk):
    tour = get_object_or_404(Tour, pk=pk)
    comentario = (request.POST.get("comentario") or "").strip()
    try:
        puntuacion = int(request.POST.get("puntuacion", "0"))
    except ValueError:
        puntuacion = 0

    if puntuacion < 1 or puntuacion > 5:
        messages.error(request, "La puntuacion debe estar entre 1 y 5.")
        return redirect("tour_detalle", pk=pk)
    if not comentario:
        messages.error(request, "Escribe un comentario antes de enviar.")
        return redirect("tour_detalle", pk=pk)

    Resena.objects.create(
        usuario=request.user,
        tour=tour,
        puntuacion=puntuacion,
        comentario=comentario,
    )
    messages.success(request, "Gracias por compartir tu experiencia.")
    return redirect("tour_detalle", pk=pk)

def ticket_reserva(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    return render(request, "core/ticket.html", {"reserva": reserva})

def ver_ticket_pdf(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    buffer = generar_ticket_pdf(reserva)
    return HttpResponse(buffer.getvalue(), content_type='application/pdf')

# ============================================
# CHECKOUT Y PAGO (ACTUALIZADO)
# ============================================

def checkout(request, reserva_id=None):
    """Vista para la página de checkout/pago"""
    
    # Si se especifica una reserva, cargar sus datos
    if reserva_id:
        reserva = get_object_or_404(Reserva, id=reserva_id)
        
        context = {
            'reserva': reserva,
            'tour': reserva.salida.tour,
            'salida': reserva.salida,
            'destino': reserva.salida.tour.destino,
        }
    else:
        # Datos de ejemplo para demo (si no hay reserva_id)
        context = {
            'demo': True,
        }
    
    return render(request, 'core/checkout.html', context)

def procesar_pago(request):
    """Vista para procesar el pago y confirmar la reserva"""
    if request.method == 'POST':
        reserva_id = request.POST.get('reserva_id')
        
        if not reserva_id:
            messages.error(request, 'No se encontró la reserva')
            return redirect('tours')
        
        # Obtener los datos del formulario
        nombre_titular = request.POST.get('nombre_titular')
        email = request.POST.get('email')
        numero_tarjeta = request.POST.get('numero_tarjeta')
        cvv = request.POST.get('cvv')
        
        try:
            reserva = get_object_or_404(Reserva, id=reserva_id)
            
            # Verificar que la reserva esté pendiente
            if reserva.estado != 'pendiente':
                messages.warning(request, 'Esta reserva ya fue procesada.')
                return redirect('tours')
            
            # Aquí iría la integración con pasarela de pago real
            # Por ahora, simulamos que el pago fue exitoso
            
            # Actualizar la reserva a PAGADA
            reserva.estado = 'pagada'
            if email:
                reserva.correo = email.strip().lower()
            reserva.save()
            
            # AHORA SÍ descontamos los cupos
            salida = reserva.salida
            total_personas = reserva.adultos + reserva.ninos
            salida.cupos_disponibles -= total_personas
            salida.save()
            
            # Generar y enviar ticket por email
            try:
                pdf_buffer = generar_ticket_pdf(reserva)
                pdf_content = pdf_buffer.getvalue()
                pdf_buffer.close()
                
                asunto = f"✅ Confirmación de Reserva #{reserva.id:06d} - TortugaTur"
                mensaje_html = render_to_string("core/email_ticket.html", {"reserva": reserva})
                
                # Enviar al cliente
                email_cliente = EmailMessage(
                    subject=asunto,
                    body=mensaje_html,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[reserva.correo if reserva.correo else email],
                )
                email_cliente.content_subtype = "html"
                email_cliente.attach(f"Ticket_TortugaTur_{reserva.id}.pdf", pdf_content, "application/pdf")
                email_cliente.send(fail_silently=True)
                
            except Exception as e:
                print(f"Error enviando email: {e}")
            
            messages.success(request, '¡Pago procesado exitosamente! Tu reserva ha sido confirmada. Revisa tu email.')
            return redirect('tours')
            
        except Exception as e:
            messages.error(request, f'Error al procesar el pago: {str(e)}')
            return redirect('checkout_reserva', reserva_id=reserva_id)
    
    messages.error(request, 'Método no permitido')
    return redirect('tours')

# ============================================
# PANEL ADMINISTRATIVO
# ============================================

def es_admin(user):
    return user.is_staff or user.is_superuser

def es_admin_o_secretaria(user):
    return user.is_staff or user.is_superuser or (user.is_authenticated and user.groups.filter(name="secretaria").exists())

@login_required
@user_passes_test(es_admin_o_secretaria)
def panel_admin(request):
    context = {}
    if request.user.is_staff or request.user.is_superuser:
        from .models import Reserva, SalidaTour
        # Consultar las últimas reservas y salidas creadas por algún miembro del rol "secretaria"
        context['actividad_reservas'] = Reserva.objects.filter(creado_por__groups__name="secretaria").select_related('creado_por', 'salida__tour').order_by('-fecha_reserva')[:8]
        context['actividad_salidas'] = SalidaTour.objects.filter(creado_por__groups__name="secretaria").select_related('creado_por', 'tour').order_by('-id')[:8]
        
    return render(request, "core/panel/index.html", context)

@login_required
@user_passes_test(es_admin)
def admin_reservas(request):
    Reserva.objects.filter(pagos__estado="paid").exclude(estado="pagada").update(estado="pagada")

    reservas = (
        Reserva.objects.select_related("salida__tour")
        .prefetch_related("pagos")
        .exclude(estado="pendiente")
        .order_by("-id")
    )
    for reserva in reservas:
        reserva.tiene_pago = any(pago.estado == "paid" for pago in reserva.pagos.all())
        pago_exitoso = next((pago for pago in reserva.pagos.all() if pago.estado == "paid"), None)
        if pago_exitoso:
            reserva.proveedor_pago = pago_exitoso.get_proveedor_display()
        else:
            reserva.proveedor_pago = None
    return render(request, "core/panel/reservas.html", {"reservas": reservas})

@login_required
@user_passes_test(es_admin)
def cambiar_estado_reserva(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    if request.method == "POST":
        nuevo_estado = request.POST.get("estado")
        if nuevo_estado in ["pendiente", "confirmada", "cancelada", "pagada", "bloqueada_por_agencia"]:
            reserva.estado = nuevo_estado
            reserva.save()
            messages.success(request, f"Reserva #{reserva.id} actualizada correctamente.")
    return redirect("admin_reservas")

@login_required
@user_passes_test(es_admin)
def admin_agencias(request):
    from django.contrib.auth.models import User
    usuarios = User.objects.filter(perfil__is_agencia=True).select_related('perfil').order_by('-date_joined')
    return render(request, "core/panel/agencias.html", {"usuarios": usuarios})

@login_required
@user_passes_test(es_admin)
@require_POST
def crear_agencia(request):
    from django.contrib.auth.models import User
    from .models import UserProfile
    import string
    import random

    username = request.POST.get('username')
    email = request.POST.get('email')
    first_name = request.POST.get('nombre', '')
    
    if not username or not email:
        messages.error(request, "El nombre de usuario y el correo son obligatorios.")
        return redirect('admin_agencias')
        
    if User.objects.filter(username=username).exists():
        messages.error(request, "Ese nombre de usuario ya está en uso.")
        return redirect('admin_agencias')
        
    if User.objects.filter(email=email).exists():
        messages.error(request, "Ese correo electrónico ya está registrado.")
        return redirect('admin_agencias')

    password = request.POST.get('password')
    if not password:
        characters = string.ascii_letters + string.digits
        password = ''.join(random.choice(characters) for i in range(10))

    try:
        user = User.objects.create_user(username=username, email=email, password=password, first_name=first_name)
        perfil, _ = UserProfile.objects.get_or_create(user=user)
        perfil.is_agencia = True
        perfil.save()
        messages.success(request, f"¡Agencia creada existosamente! 💼 Usuario: {username} | Contraseña: {password}")
    except Exception as e:
        messages.error(request, f"Ocurrió un error al crear la agencia: {e}")
        
    return redirect('admin_agencias')

@login_required
@user_passes_test(es_admin)
@require_POST
def toggle_agencia(request, user_id):
    from .models import UserProfile
    from django.contrib.auth.models import User
    user = get_object_or_404(User, id=user_id)
    perfil, created = UserProfile.objects.get_or_create(user=user)
    perfil.is_agencia = not perfil.is_agencia
    perfil.save()
    if perfil.is_agencia:
        messages.success(request, f"{user.username} ha sido convertida en Agencia.")
    else:
        messages.warning(request, f"{user.username} perdió sus privilegios de Agencia.")
    return redirect('admin_agencias')

@login_required
@user_passes_test(es_admin)
def eliminar_reserva(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    if request.method == "POST":
        reserva_id = reserva.id
        nombre = f"{reserva.nombre} {reserva.apellidos}".strip() or "Cliente"
        reserva.delete()
        messages.success(request, f"Reserva #{reserva_id} de {nombre} eliminada correctamente.")
    return redirect("admin_reservas")

@login_required
@user_passes_test(es_admin_o_secretaria)
def admin_salidas(request):
    salidas = SalidaTour.objects.select_related("tour").all()
    return render(request, "core/panel/salidas.html", {"salidas": salidas})

@login_required
@user_passes_test(es_admin_o_secretaria)
def editar_salida(request, salida_id):
    salida = get_object_or_404(SalidaTour, id=salida_id)
    if request.method == "POST":
        salida.cupo_maximo = int(request.POST.get("cupo_maximo"))
        salida.cupos_disponibles = int(request.POST.get("cupos_disponibles"))
        salida.fecha = request.POST.get("fecha")
        hora = request.POST.get("hora")
        salida.hora = hora if hora else None
        salida.duracion = request.POST.get("duracion") or salida.tour.duracion
        salida.save()
        messages.success(request, f"La salida del {salida.fecha} ha sido actualizada.")
        return redirect("admin_salidas")
    return render(request, "core/panel/editar_salida.html", {"salida": salida})

@login_required
@user_passes_test(es_admin_o_secretaria)
def crear_salida(request):
    tours = Tour.objects.all()
    
    if request.method == "POST":
        tour_id = request.POST.get("tour")
        fecha = request.POST.get("fecha")
        hora_post = request.POST.get("hora")
        hora = hora_post if hora_post else None
        cupo_maximo = int(request.POST.get("cupo_maximo"))
        duracion = request.POST.get("duracion")
        
        tour = get_object_or_404(Tour, id=tour_id)
        
        SalidaTour.objects.create(
            tour=tour,
            fecha=fecha,
            hora=hora,
            duracion=duracion or tour.duracion,
            cupo_maximo=cupo_maximo,
            cupos_disponibles=cupo_maximo,
            creado_por=request.user
        )
        
        messages.success(request, "¡Salida programada correctamente!")
        return redirect("admin_salidas")

    return render(request, "core/panel/crear_salida.html", {"tours": tours})

@login_required
@user_passes_test(es_admin)
def destinos(request):
    destinos_list = Destino.objects.all().order_by('-id')
    
    if request.method == 'POST':
        form = DestinoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "¡Destino agregado con éxito!")
            return redirect('destinos')
    else:
        form = DestinoForm()
            
    return render(request, 'core/panel/destinos.html', {
        'destinos': destinos_list,
        'form': form
    })

@login_required
@user_passes_test(es_admin)
def editar_destino(request, pk):
    destino = get_object_or_404(Destino, pk=pk)
    if request.method == 'POST':
        form = DestinoForm(request.POST, instance=destino)
        if form.is_valid():
            form.save()
            messages.success(request, "Destino actualizado con éxito.")
            return redirect('destinos')
    else:
        form = DestinoForm(instance=destino)
    return render(request, 'core/panel/editar_destino.html', {'form': form, 'destino': destino})

@login_required
@user_passes_test(es_admin)
def eliminar_destino(request, pk):
    destino = get_object_or_404(Destino, pk=pk)
    if request.method == 'POST':
        destino.delete()
        messages.success(request, "Destino eliminado correctamente.")
    return redirect('destinos')

@login_required
@user_passes_test(es_admin)
def admin_tours(request):
    tours_list = Tour.objects.all().order_by('-id')
    destinos_list = Destino.objects.all()
    
    if request.method == 'POST':
        form = TourForm(request.POST)
        if form.is_valid():
            tour = form.save(commit=False)
            tour.cupos_disponibles = tour.cupo_maximo
            tour.save()
            messages.success(request, f"Tour '{tour.nombre}' creado exitosamente.")
            return redirect('admin_tours')
    else:
        form = TourForm()

    return render(request, 'core/panel/tours.html', {
        'tours': tours_list,
        'form': form,
        'destinos': destinos_list
    })


@login_required
@user_passes_test(es_admin)
def editar_tour(request, pk):
    tour = get_object_or_404(Tour, pk=pk)
    if request.method == "POST":
        form = TourForm(request.POST, instance=tour)
        if form.is_valid():
            tour_actualizado = form.save(commit=False)
            # Keep available seats within the updated max seats.
            if tour_actualizado.cupos_disponibles > tour_actualizado.cupo_maximo:
                tour_actualizado.cupos_disponibles = tour_actualizado.cupo_maximo
            tour_actualizado.save()
            messages.success(request, f"Tour '{tour_actualizado.nombre}' actualizado correctamente.")
            return redirect("admin_tours")
    else:
        form = TourForm(instance=tour)

    return render(request, "core/panel/editar_tour.html", {"form": form, "tour": tour})

# ============================================
# AUTENTICACIÓN
# ============================================

def registro(request):
    if request.method == 'POST':
        form = RegistroTuristaForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"¡Bienvenido a TortugaTur, {user.first_name}!")
            return redirect('home')
    else:
        form = RegistroTuristaForm()
    return render(request, 'registration/registro.html', {'form': form})

def vista_login(request):
    """Maneja el inicio de sesión y la redirección al tour original."""
    next_url = request.GET.get('next', 'home')
    
    if request.method == 'POST':
        form = TuristaLoginForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"¡Qué bueno verte de nuevo, {user.first_name}!")
            return redirect(request.POST.get('next', 'home'))
    else:
        form = TuristaLoginForm()
    
    return render(request, 'registration/login.html', {
        'form': form,
        'next': next_url
    })

def vista_logout(request):
    """Cierra la sesión y redirige a la página de inicio."""
    logout(request)
    messages.info(request, "Has cerrado sesión correctamente.")
    return redirect('home')

from django.contrib.auth.decorators import login_required

@login_required
def mis_reservas(request):
    """Vista para que el turista vea su historial de compras/reservas."""
    reservas = Reserva.objects.filter(usuario=request.user).exclude(estado="pendiente").order_by('-fecha_reserva')
    return render(request, 'core/mis_reservas.html', {'reservas': reservas})

# ============================================
# OTRAS PÁGINAS
# ============================================

def nosotros(request):
    return render(request, "core/nosotros.html")

def contacto(request):
    if request.method == "POST":
        form = ContactoForm(request.POST)
        if form.is_valid():
            datos = form.cleaned_data
            
            subject = f"✨ Nuevo Contacto: {datos['asunto']} - {datos['nombre']}"
            html_content = render_to_string('emails/aviso_contacto.html', {
                'nombre': datos['nombre'],
                'email_usuario': datos['email'],
                'asunto_elegido': datos['asunto'],
                'mensaje_texto': datos['mensaje'],
            })
            text_content = strip_tags(html_content)

            try:
                msg = EmailMultiAlternatives(
                    subject, 
                    text_content, 
                    settings.DEFAULT_FROM_EMAIL, 
                    ['tu-correo@gmail.com']
                )
                msg.attach_alternative(html_content, "text/html")
                msg.send()

                messages.success(request, "¡Mensaje enviado con éxito!")
                return redirect('contacto')
            except Exception as e:
                messages.error(request, "Error al enviar el correo.")
    else:
        form = ContactoForm()
    
    return render(request, "core/contacto.html", {'form': form})

def terminos(request):
    return render(request, 'core/terminos_condiciones.html')

def faq(request):
    return render(request, 'core/faq.html')


def checkout_redirect(request):
    messages.info(request, "Primero selecciona un tour para crear una reserva.")
    return redirect("tours")


def _site_url(request=None):
    if request is None:
        return getattr(settings, "SITE_URL", "").rstrip("/")
    return getattr(settings, "SITE_URL", request.build_absolute_uri("/").rstrip("/"))


def _currency():
    return getattr(settings, "PAYMENT_DEFAULT_CURRENCY", "USD").upper()

def _currency_context(request):
    rates = getattr(settings, "CURRENCY_RATES", {}) or {}
    default = _currency()
    code = (request.GET.get("currency") or default).upper()
    if code not in rates:
        code = default
    rate = Decimal(str(rates.get(code, 1)))
    return code, rate

def _tour_price_display(tour, currency_rate):
    precio_adulto = tour.precio_adulto_final()
    precio_nino = tour.precio_nino_final()
    return {
        "adulto": precio_adulto * currency_rate,
        "nino": precio_nino * currency_rate,
    }


def _amount_minor_units(amount):
    dec = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(dec * 100)


def _send_ticket_email(reserva):
    try:
        pdf_buffer = generar_ticket_pdf(reserva)
        pdf_content = pdf_buffer.getvalue()
        pdf_buffer.close()
        subject = f"Confirmacion de Reserva #{reserva.id:06d} - TortugaTur"
        html_body = render_to_string(
            "core/email_ticket.html",
            {
                "reserva": reserva,
                "site_url": _site_url(request=None),
                "whatsapp_number": getattr(settings, "WHATSAPP_NUMBER", ""),
                "agencia_email": getattr(settings, "AGENCIA_EMAIL", ""),
            },
        )
        recipient = reserva.correo or (reserva.usuario.email if reserva.usuario else "")
        agencia_email = getattr(settings, "AGENCIA_EMAIL", "")
        if not recipient and not agencia_email:
            return

        to_list = [recipient] if recipient else []
        bcc_list = [agencia_email] if agencia_email and agencia_email != recipient else []

        email_cliente = EmailMessage(
            subject=subject,
            body=html_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=to_list or [agencia_email],
            bcc=bcc_list,
        )
        email_cliente.content_subtype = "html"
        email_cliente.attach(f"Ticket_TortugaTur_{reserva.id}.pdf", pdf_content, "application/pdf")
        email_cliente.send(fail_silently=True)
    except Exception:
        logger.exception("No se pudo enviar ticket para la reserva %s", reserva.id)


def _extract_customer_email(proveedor, payload):
    if not isinstance(payload, dict):
        return ""
    if proveedor == "paypal":
        payer = payload.get("payer", {}) or {}
        return (payer.get("email_address") or "").strip().lower()
    if proveedor == "lemonsqueezy":
        data = payload.get("data", {}) or {}
        attributes = data.get("attributes", {}) or {}
        if attributes.get("user_email"):
            return (attributes.get("user_email") or "").strip().lower()
        first_order_item = (attributes.get("first_order_item") or {}) if isinstance(attributes, dict) else {}
        return (first_order_item.get("user_email") or "").strip().lower()
    return ""


def _mark_reserva_paid(reserva_id, proveedor, external_id="", payload=None):
    with transaction.atomic():
        reserva = Reserva.objects.select_for_update().select_related("salida").get(id=reserva_id)
        salida = SalidaTour.objects.select_for_update().get(id=reserva.salida_id)
        customer_email = _extract_customer_email(proveedor, payload or {})
        pago = None
        if external_id:
            pago = (
                Pago.objects.select_for_update()
                .filter(reserva=reserva, proveedor=proveedor, external_id=external_id)
                .order_by("-id")
                .first()
            )
        if pago is None:
            pago = (
                Pago.objects.select_for_update()
                .filter(reserva=reserva, proveedor=proveedor, estado__in=["created", "approved"])
                .order_by("-id")
                .first()
            )

        if reserva.estado == "pagada":
            if customer_email and reserva.correo != customer_email:
                reserva.correo = customer_email
                reserva.save(update_fields=["correo"])
            if pago and pago.estado != "paid":
                pago.estado = "paid"
                pago.payload = payload or pago.payload
                if external_id:
                    pago.external_id = external_id
                pago.save(update_fields=["estado", "payload", "external_id", "actualizado_en"])
            return reserva, False
        if reserva.estado == "cancelada":
            raise ValueError("La reserva esta cancelada.")

        estado_anterior = reserva.estado

        personas = reserva.adultos + reserva.ninos
        # IMPORTANTE: No restar cupos si ya se restaron cuando la agencia bloqueó
        if estado_anterior != "bloqueada_por_agencia":
            if salida.cupos_disponibles < personas:
                raise ValueError("No hay cupos suficientes al confirmar el pago.")

        reserva.estado = "pagada"
        if customer_email:
            reserva.correo = customer_email
            reserva.save(update_fields=["estado", "correo"])
        else:
            reserva.save(update_fields=["estado"])

        if estado_anterior != "bloqueada_por_agencia":
            salida.cupos_disponibles -= personas
            salida.save(update_fields=["cupos_disponibles"])

        if pago:
            pago.estado = "paid"
            pago.moneda = pago.moneda or _currency()
            pago.monto = reserva.total_pagar
            pago.payload = payload or pago.payload
            if external_id:
                pago.external_id = external_id
            pago.save(update_fields=["estado", "moneda", "monto", "payload", "external_id", "actualizado_en"])
        else:
            Pago.objects.create(
                reserva=reserva,
                proveedor=proveedor,
                estado="paid",
                moneda=_currency(),
                monto=reserva.total_pagar,
                external_id=external_id,
                payload=payload or {},
            )

    _send_ticket_email(reserva)
    
    # Enviar correo adicional confirmando que el valor bloqueado fue cancelado si era agencia
    if estado_anterior == "bloqueada_por_agencia" and reserva.usuario and reserva.usuario.email:
        from django.core.mail import send_mail
        from django.template.loader import render_to_string
        subject = f"Confirmación de Pago a Agencia - Reserva #{reserva.id:06d}"
        msg_plain = f"Gracias por su pago. La reserva del código {reserva.codigo_agencia} ha sido procesada."
        send_mail(
            subject=subject,
            message=msg_plain,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[reserva.usuario.email],
            fail_silently=True
        )

    return reserva, True


def _paypal_base_url():
    env = getattr(settings, "PAYPAL_ENV", "sandbox").lower()
    return "https://api-m.paypal.com" if env == "live" else "https://api-m.sandbox.paypal.com"


def _paypal_access_token():
    client_id = getattr(settings, "PAYPAL_CLIENT_ID", "")
    client_secret = getattr(settings, "PAYPAL_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise ValueError("PayPal no esta configurado.")

    response = requests.post(
        f"{_paypal_base_url()}/v1/oauth2/token",
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _paypal_verify_webhook(request, event_body):
    webhook_id = getattr(settings, "PAYPAL_WEBHOOK_ID", "")
    if not webhook_id:
        return False

    token = _paypal_access_token()
    verify_payload = {
        "transmission_id": request.headers.get("PAYPAL-TRANSMISSION-ID", ""),
        "transmission_time": request.headers.get("PAYPAL-TRANSMISSION-TIME", ""),
        "cert_url": request.headers.get("PAYPAL-CERT-URL", ""),
        "auth_algo": request.headers.get("PAYPAL-AUTH-ALGO", ""),
        "transmission_sig": request.headers.get("PAYPAL-TRANSMISSION-SIG", ""),
        "webhook_id": webhook_id,
        "webhook_event": event_body,
    }
    response = requests.post(
        f"{_paypal_base_url()}/v1/notifications/verify-webhook-signature",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=verify_payload,
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("verification_status") == "SUCCESS"


def _lemonsqueezy_api_base_url():
    return "https://api.lemonsqueezy.com/v1"


def _lemonsqueezy_headers():
    api_key = getattr(settings, "LEMONSQUEEZY_API_KEY", "")
    if not api_key:
        raise ValueError("Lemon Squeezy no esta configurado.")
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
    }


def _lemonsqueezy_verify_signature(request):
    secret = getattr(settings, "LEMONSQUEEZY_WEBHOOK_SECRET", "")
    signature = request.headers.get("X-Signature", "")
    if not secret or not signature:
        print(f"WEBHOOK DEBUG: Missing secret or signature. Secret: '{secret}', Signature: '{signature}'")
        return False
    digest = hmac.new(secret.encode("utf-8"), request.body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, signature):
        print(f"WEBHOOK DEBUG: Signature mismatch. Expected: '{digest}', Got: '{signature}'")
        return False
    return True


def checkout_pago(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    if reserva.estado == "pagada":
        messages.success(request, "Pago confirmado. Tu reserva ya esta pagada.")
        return redirect("home")

    context = {
        "reserva": reserva,
        "tour": reserva.salida.tour,
        "salida": reserva.salida,
        "destino": reserva.salida.tour.destino,
        "payment_currency": _currency(),
        "paypal_client_id": getattr(settings, "PAYPAL_CLIENT_ID", ""),
        "lemonsqueezy_enabled": bool(getattr(settings, "LEMONSQUEEZY_API_KEY", "")),
        "paypal_enabled": bool(getattr(settings, "PAYPAL_CLIENT_ID", "")),
    }
    return render(request, "core/checkout.html", context)


@require_POST
def create_lemonsqueezy_checkout(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    if reserva.estado not in ["pendiente", "bloqueada_por_agencia"]:
        messages.warning(request, "Esta reserva ya no esta pendiente de pago.")
        return redirect("tours")

    store_id = getattr(settings, "LEMONSQUEEZY_STORE_ID", "")
    variant_id = reserva.salida.tour.lemonsqueezy_variant_id or getattr(settings, "LEMONSQUEEZY_VARIANT_ID", "")
    if not store_id or not variant_id:
        messages.error(request, "Lemon Squeezy no esta configurado.")
        return redirect("checkout_reserva", reserva_id=reserva.id)

    site_url = _site_url(request)
    currency = _currency()
    custom_price = _amount_minor_units(reserva.total_pagar)
    checkout_payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "custom_price": custom_price,
                "checkout_data": {
                    "custom": {
                        "reserva_id": str(reserva.id),
                    },
                },
                "checkout_options": {
                    "embed": False,
                },
                "product_options": {
                    "redirect_url": f"{site_url}{reverse('home')}?pago=ok",
                    "receipt_button_text": "Volver a TortugaTur",
                    "receipt_link_url": f"{site_url}{reverse('home')}",
                },
            },
            "relationships": {
                "store": {"data": {"type": "stores", "id": str(store_id)}},
                "variant": {"data": {"type": "variants", "id": str(variant_id)}},
            },
        }
    }
    try:
        response = requests.post(
            f"{_lemonsqueezy_api_base_url()}/checkouts",
            headers=_lemonsqueezy_headers(),
            json=checkout_payload,
            timeout=20,
        )
    except requests.RequestException:
        logger.exception("Error de red al crear checkout Lemon Squeezy para reserva %s", reserva.id)
        messages.error(request, "No se pudo conectar con Lemon Squeezy.")
        return redirect("checkout_reserva", reserva_id=reserva.id)

    try:
        data = response.json()
    except ValueError:
        data = {"raw": response.text}

    if response.status_code >= 400:
        logger.error("Lemon Squeezy error %s: %s", response.status_code, data)
        error_detail = ""
        if isinstance(data, dict):
            errors = data.get("errors", [])
            if errors and isinstance(errors, list):
                first = errors[0]
                error_detail = first.get("detail") or first.get("title") or ""
        msg = "No se pudo crear el checkout en Lemon Squeezy."
        if error_detail:
            msg = f"{msg} {error_detail}"
        messages.error(request, msg)
        return redirect("checkout_reserva", reserva_id=reserva.id)

    checkout_data = data.get("data", {})
    attributes = checkout_data.get("attributes", {})
    checkout_url = attributes.get("url", "")
    checkout_id = checkout_data.get("id", "")
    if not checkout_url:
        messages.error(request, "Lemon Squeezy no devolvio URL de pago.")
        return redirect("checkout_reserva", reserva_id=reserva.id)

    Pago.objects.create(
        reserva=reserva,
        proveedor="lemonsqueezy",
        estado="created",
        moneda=currency,
        monto=reserva.total_pagar,
        external_id=checkout_id,
        checkout_url=checkout_url,
        payload=data,
    )
    if getattr(settings, "FORCE_EMAIL_ON_CREATED", False):
        _send_ticket_email(reserva)
    return redirect(checkout_url, permanent=False)


@require_POST
def create_paypal_order(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    if reserva.estado not in ["pendiente", "bloqueada_por_agencia"]:
        return JsonResponse({"error": "La reserva ya no esta pendiente de pago."}, status=400)

    currency = _currency()
    token = _paypal_access_token()
    amount_str = Decimal(reserva.total_pagar).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "custom_id": str(reserva.id),
                "reference_id": str(reserva.id),
                "amount": {"currency_code": currency, "value": f"{amount_str}"},
                "description": f"Reserva TortugaTur #{reserva.id}",
            }
        ],
        "application_context": {
            "brand_name": "TortugaTur",
            "shipping_preference": "NO_SHIPPING",
            "user_action": "PAY_NOW",
        },
    }
    response = requests.post(
        f"{_paypal_base_url()}/v2/checkout/orders",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=20,
    )
    body = response.json()
    if response.status_code >= 400:
        return JsonResponse({"error": "No se pudo crear la orden de PayPal.", "details": body}, status=400)

    order_id = body.get("id", "")
    Pago.objects.create(
        reserva=reserva,
        proveedor="paypal",
        estado="created",
        moneda=currency,
        monto=reserva.total_pagar,
        external_id=order_id,
        payload=body,
    )
    if getattr(settings, "FORCE_EMAIL_ON_CREATED", False):
        _send_ticket_email(reserva)
    return JsonResponse({"orderID": order_id})


@require_POST
def capture_paypal_order(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    try:
        body = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON invalido."}, status=400)

    order_id = body.get("orderID")
    if not order_id:
        return JsonResponse({"error": "orderID es requerido."}, status=400)

    token = _paypal_access_token()
    response = requests.post(
        f"{_paypal_base_url()}/v2/checkout/orders/{order_id}/capture",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=20,
    )
    data = response.json()
    if response.status_code >= 400:
        return JsonResponse({"error": "No se pudo capturar la orden.", "details": data}, status=400)

    if data.get("status") != "COMPLETED":
        return JsonResponse({"error": f"Estado inesperado: {data.get('status')}", "details": data}, status=400)

    try:
        _mark_reserva_paid(reserva.id, "paypal", external_id=order_id, payload=data)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse({"ok": True, "redirect_url": reverse("home")})


@csrf_exempt
def lemonsqueezy_webhook(request):
    if request.method != "POST":
        return HttpResponse(status=405)
    if not _lemonsqueezy_verify_signature(request):
        return HttpResponse(status=400)

    try:
        event = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    event_name = event.get("meta", {}).get("event_name", "")
    if event_name in ("order_created", "order_refunded"):
        data = event.get("data", {})
        attributes = data.get("attributes", {})
        custom = event.get("meta", {}).get("custom_data", {}) or {}
        reserva_id = custom.get("reserva_id")
        order_id = str(data.get("id", ""))

        if reserva_id and event_name == "order_created":
            try:
                _mark_reserva_paid(
                    int(reserva_id),
                    "lemonsqueezy",
                    external_id=order_id,
                    payload=event,
                )
            except Exception:
                logger.exception("Fallo confirmando pago Lemon Squeezy para reserva %s", reserva_id)
                return HttpResponse(status=500)
        elif reserva_id and event_name == "order_refunded":
            Pago.objects.filter(
                reserva_id=int(reserva_id),
                proveedor="lemonsqueezy",
            ).update(estado="failed", payload=event)
    return HttpResponse(status=200)


@csrf_exempt
def paypal_webhook(request):
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        body = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    try:
        if not _paypal_verify_webhook(request, body):
            return HttpResponse(status=400)
    except Exception:
        logger.exception("Error verificando webhook PayPal")
        return HttpResponse(status=400)

    if body.get("event_type") == "PAYMENT.CAPTURE.COMPLETED":
        resource = body.get("resource", {})
        order_id = resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id", "")
        reserva_id = resource.get("custom_id", "")

        if not reserva_id and order_id:
            try:
                token = _paypal_access_token()
                order_response = requests.get(
                    f"{_paypal_base_url()}/v2/checkout/orders/{order_id}",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    timeout=20,
                )
                order_response.raise_for_status()
                order_data = order_response.json()
                purchase_units = order_data.get("purchase_units", [])
                if purchase_units:
                    reserva_id = purchase_units[0].get("custom_id", "")
            except Exception:
                logger.exception("No se pudo resolver custom_id desde orden %s", order_id)

        if reserva_id:
            try:
                _mark_reserva_paid(int(reserva_id), "paypal", external_id=order_id or resource.get("id", ""), payload=body)
            except Exception:
                logger.exception("Fallo confirmando webhook PayPal para reserva %s", reserva_id)
                return HttpResponse(status=500)
    return HttpResponse(status=200)

def galeria_view(request):
    from .models import Galeria
    fotos = Galeria.objects.all().order_by('-fecha_agregada')
    return render(request, 'core/galeria.html', {'fotos': fotos})

@login_required
@user_passes_test(es_admin)
def panel_galeria(request):
    from .models import Galeria
    from .forms import GaleriaForm
    fotos_list = Galeria.objects.all().order_by('-id')
    
    if request.method == 'POST':
        form = GaleriaForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "¡Imagen agregada a la galería con éxito!")
            return redirect('panel_galeria')
        else:
            messages.error(request, "Error al subir la imagen. Verifica los datos.")
    else:
        form = GaleriaForm()
            
    return render(request, 'core/panel/galeria.html', {
        'fotos': fotos_list,
        'form': form
    })

@login_required
@user_passes_test(es_admin)
def eliminar_galeria(request, pk):
    from .models import Galeria
    foto = get_object_or_404(Galeria, pk=pk)
    if request.method == 'POST':
        foto.delete()
        messages.success(request, "Imagen eliminada correctamente.")
    return redirect('panel_galeria')

def eliminar_galeria(request, pk):
    from .models import Galeria
    foto = get_object_or_404(Galeria, pk=pk)
    if request.method == 'POST':
        foto.delete()
        messages.success(request, "Foto eliminada de la galería.")
    return redirect('panel_galeria')

@login_required
@login_required
def perfil_admin(request):
    from .models import UserProfile
    from django.contrib.auth import update_session_auth_hash
    
    # Verificar si el usuario es secretaria
    is_secretaria = request.user.groups.filter(name="secretaria").exists()
    
    # Si es secretaria y está inactivo, mostrar mensaje
    if is_secretaria and not request.user.is_active:
        messages.error(request, "Tu cuenta de secretaria ha sido desactivada. Por favor, contacta al administrador.")
        return redirect('home')
    
    # Aseguramos que el usuario tiene un perfil asociado
    perfil, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        # Info Basica
        request.user.first_name = request.POST.get('first_name', request.user.first_name)
        request.user.last_name = request.POST.get('last_name', request.user.last_name)
        request.user.email = request.POST.get('email', request.user.email)
        
        # Validacion del nombre de usuario para no chocar (naive)
        new_username = request.POST.get('username')
        if new_username and new_username != request.user.username:
            from django.contrib.auth.models import User
            if not User.objects.filter(username=new_username).exists():
                request.user.username = new_username
            else:
                messages.error(request, "Ese nombre de usuario ya está ocupado.")
                return redirect('perfil_admin')
        
        request.user.save()
        
        # Opciones extra (Foto, Teléfono, Biografía)
        if 'foto' in request.FILES:
            perfil.foto = request.FILES['foto']
        perfil.telefono = request.POST.get('telefono', perfil.telefono)
        perfil.biografia = request.POST.get('biografia', perfil.biografia)
        perfil.save()
        
        # Cambio de contraseña si se proporcionó una
        new_password = request.POST.get('new_password')
        if new_password:
            request.user.set_password(new_password)
            request.user.save()
            update_session_auth_hash(request, request.user) # Evita que se cierre sesión
            messages.success(request, "¡Contraseña actualizada!")
            
        messages.success(request, "Perfil guardado con éxito.")
        return redirect('perfil_admin')

    # Si es secretaria, obtener sus reservas
    reservas_creadas = []
    total_ventas = Decimal('0.00')
    total_personas = 0
    
    if is_secretaria:
        reservas_creadas = Reserva.objects.filter(creado_por=request.user).select_related('salida__tour').order_by('-fecha_reserva')
        total_ventas = sum(r.total_pagar for r in reservas_creadas)
        total_personas = sum(r.total_personas() for r in reservas_creadas)
    
    return render(request, 'core/perfil_admin.html', {
        'perfil': perfil,
        'is_secretaria': is_secretaria,
        'reservas_creadas': reservas_creadas,
        'total_ventas': total_ventas,
        'total_personas': total_personas,
    })

#secretaria
def _parse_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def es_secretaria(user):
    return user.is_authenticated and user.groups.filter(name="secretaria").exists()


def puede_reservar_asistida(user):
    return user.is_staff or es_secretaria(user)


@login_required
@user_passes_test(puede_reservar_asistida)
def secretaria_reservar(request):
    destinos = Destino.objects.all().order_by("nombre")
    destino_id = request.GET.get("destino", "")
    fecha = request.GET.get("fecha", "")
    personas = _parse_int(request.GET.get("personas"), 1)
    if personas < 1:
        personas = 1

    tours_con_salidas = {}
    destino_seleccionado = None
    if destino_id and fecha:
        destino_seleccionado = Destino.objects.filter(id=destino_id).first()
        if destino_seleccionado:
            salidas = (
                SalidaTour.objects.filter(
                    tour__destino=destino_seleccionado,
                    fecha=fecha,
                    cupos_disponibles__gte=personas,
                )
                .select_related("tour", "tour__destino")
                .order_by("tour__nombre", "hora")
            )
            for salida in salidas:
                tours_con_salidas.setdefault(salida.tour, []).append(salida)

    if request.method == "POST":
        salida_id = request.POST.get("salida_id")
        adultos = _parse_int(request.POST.get("adultos"))
        ninos = _parse_int(request.POST.get("ninos"))
        nombre = (request.POST.get("nombre") or "").strip()
        apellidos = (request.POST.get("apellidos") or "").strip()
        correo = (request.POST.get("correo") or "").strip().lower()
        telefono = (request.POST.get("telefono") or "").strip()
        identificacion = (request.POST.get("identificacion") or "").strip()

        salida = get_object_or_404(SalidaTour.objects.select_related("tour"), id=salida_id)
        total_personas = adultos + ninos
        if total_personas <= 0:
            messages.error(request, "Debes registrar al menos un pasajero.")
            return redirect("secretaria_reservar")
        if not salida.hay_cupo(adultos, ninos):
            messages.error(request, "No hay cupos disponibles para esa salida.")
            return redirect("secretaria_reservar")
        if not all([nombre, apellidos, correo, telefono, identificacion]):
            messages.error(request, "Completa todos los datos del cliente.")
            return redirect("secretaria_reservar")

        total_pagar = (adultos * salida.tour.precio_adulto_final()) + (ninos * salida.tour.precio_nino_final())
        reserva = Reserva.objects.create(
            usuario=None,
            salida=salida,
            adultos=adultos,
            ninos=ninos,
            total_pagar=total_pagar,
            nombre=nombre,
            apellidos=apellidos,
            correo=correo,
            telefono=telefono,
            identificacion=identificacion,
            estado="pendiente",
            creado_por=request.user,
        )

        messages.success(
            request,
            f"Reserva #{reserva.id:06d} creada. Ahora puedes cobrarla desde checkout o panel.",
        )
        return redirect("checkout_reserva", reserva_id=reserva.id)

    return render(
        request,
        "core/panel/secretaria_reservar.html",
        {
            "destinos": destinos,
            "tours_con_salidas": tours_con_salidas,
            "destino_id": destino_id,
            "fecha_busqueda": fecha,
            "personas": personas,
            "destino_seleccionado": destino_seleccionado,
        },
    )

@require_POST
@login_required
@user_passes_test(es_admin_o_secretaria)
def procesar_pago_efectivo(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    if reserva.estado == "pagada":
        messages.warning(request, "La reserva ya está pagada.")
        return redirect("checkout_reserva", reserva_id=reserva_id)
    
    try:
        # Generar ticket antes si no existe
        if not hasattr(reserva, 'ticket'):
            Ticket.objects.create(
                reserva=reserva,
                codigo=f"TKT-{reserva.id:06d}-{timezone.now().strftime('%Y%m%d%H%M%S')}"
            )
        _mark_reserva_paid(reserva.id, "efectivo", payload={"method": "efectivo", "user": request.user.username})
        messages.success(request, f"¡Reserva #{reserva.id:06d} cobrada en EFECTIVO exitosamente!")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("checkout_reserva", reserva_id=reserva_id)

@login_required
@user_passes_test(es_admin)
def admin_secretarias(request):
    group_secretaria, _ = Group.objects.get_or_create(name="secretaria")

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        first_name = (request.POST.get("first_name") or "").strip()
        last_name = (request.POST.get("last_name") or "").strip()
        email = (request.POST.get("email") or "").strip().lower()

        if not username or not password:
            messages.error(request, "Usuario y contraseña son obligatorios.")
            return redirect("admin_secretarias")
        if len(password) < 8:
            messages.error(request, "La contraseña debe tener mínimo 8 caracteres.")
            return redirect("admin_secretarias")
        if User.objects.filter(username__iexact=username).exists():
            messages.error(request, "Ese usuario ya existe.")
            return redirect("admin_secretarias")

        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
            email=email,
            is_staff=False,
        )
        user.groups.add(group_secretaria)
        messages.success(request, f"Secretaria '{username}' creada con éxito.")
        return redirect("admin_secretarias")

    secretarias = group_secretaria.user_set.all().order_by("username")
    return render(
        request,
        "core/panel/secretarias.html",
        {"secretarias": secretarias},
    )


@login_required
@user_passes_test(es_admin)
def toggle_secretaria_estado(request, user_id):
    if request.method != "POST":
        return redirect("admin_secretarias")

    group_secretaria = Group.objects.filter(name="secretaria").first()
    secretaria = get_object_or_404(User, id=user_id)
    if not group_secretaria or not secretaria.groups.filter(id=group_secretaria.id).exists():
        messages.error(request, "El usuario seleccionado no pertenece al rol secretaria.")
        return redirect("admin_secretarias")

    secretaria.is_active = not secretaria.is_active
    secretaria.save(update_fields=["is_active"])
    estado = "activada" if secretaria.is_active else "desactivada"
    messages.success(request, f"Cuenta de '{secretaria.username}' {estado} correctamente.")
    return redirect("admin_secretarias")


@login_required
@user_passes_test(es_admin)
def eliminar_secretaria(request, user_id):
    if request.method != "POST":
        return redirect("admin_secretarias")

    group_secretaria = Group.objects.filter(name="secretaria").first()
    secretaria = get_object_or_404(User, id=user_id)
    if not group_secretaria or not secretaria.groups.filter(id=group_secretaria.id).exists():
        messages.error(request, "El usuario seleccionado no pertenece al rol secretaria.")
        return redirect("admin_secretarias")

    secretaria.delete()
    messages.success(request, f"Secretaria '{secretaria.username}' eliminada definitivamente.")
    return redirect("admin_secretarias")