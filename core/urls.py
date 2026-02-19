from django.urls import path, include
from . import views

# URLs de TortugaTour
urlpatterns = [
    path("", views.home, name="home"),
    path("tours/", views.tours, name="tours"),  # lista general (TODOS)
    path("buscar/", views.lista_tours, name="lista_tours"),  # 🔍 RESULTADOS FILTRADOS
    path("tours/<int:pk>/", views.tour_detalle, name="tour_detalle"),
    path("tours/<int:pk>/resena/", views.crear_resena, name="crear_resena"),
    path("ticket/<int:reserva_id>/", views.ticket_reserva, name="ticket_reserva"),
    path('nosotros/', views.nosotros, name='nosotros'),
    path('contacto/', views.contacto, name='contacto'),
    path('terminos-y-condiciones/', views.terminos, name='terminos'),
    path('preguntas-frecuentes/', views.faq, name='faq'),

    path("panel/", views.panel_admin, name="panel_admin"),
    path("panel/reservas/", views.admin_reservas, name="admin_reservas"),
    path("panel/reservas/<int:reserva_id>/estado/", views.cambiar_estado_reserva, name="cambiar_estado_reserva"),
    path("panel/reservas/<int:reserva_id>/eliminar/", views.eliminar_reserva, name="eliminar_reserva"),
    path("panel/salidas/", views.admin_salidas, name="admin_salidas"),
    path("panel/salidas/<int:salida_id>/editar/", views.editar_salida, name="editar_salida"),
    path("panel/salidas/nueva/", views.crear_salida, name="crear_salida"),
    # Tu archivo core/urls.py
    path('panel/destinos/', views.destinos, name='destinos'),
    path('panel/destinos/editar/<int:pk>/', views.editar_destino, name='editar_destino'),
    path('panel/destinos/eliminar/<int:pk>/', views.eliminar_destino, name='eliminar_destino'),
    path("panel/tours/", views.admin_tours, name="admin_tours"),
    path("panel/tours/editar/<int:pk>/", views.editar_tour, name="editar_tour"),

    #logueo
    path('registro/', views.registro, name='registro'),
    path('login/', views.vista_login, name='login'),
    path('logout/', views.vista_logout, name='logout'),
    
    # Ruta para ver el ticket después de reservar
    path('ticket/<int:reserva_id>/', views.ticket_reserva, name='ticket_reserva'),
    path('ticket/<int:reserva_id>/pdf/', views.ver_ticket_pdf, name='ver_ticket_pdf'),
    
    # Checkout/Pago
    path('checkout/', views.checkout_redirect, name='checkout'),
    path('checkout/<int:reserva_id>/', views.checkout_pago, name='checkout_reserva'),
    path('procesar-pago/', views.procesar_pago, name='procesar_pago'),
    path('pagos/lemonsqueezy/<int:reserva_id>/checkout/', views.create_lemonsqueezy_checkout, name='create_lemonsqueezy_checkout'),
    path('pagos/paypal/<int:reserva_id>/order/', views.create_paypal_order, name='create_paypal_order'),
    path('pagos/paypal/<int:reserva_id>/capture/', views.capture_paypal_order, name='capture_paypal_order'),
    path('webhooks/lemonsqueezy/', views.lemonsqueezy_webhook, name='lemonsqueezy_webhook'),
    path('webhooks/paypal/', views.paypal_webhook, name='paypal_webhook'),
]
