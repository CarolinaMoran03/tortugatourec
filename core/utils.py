from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

def _fmt_money(value):
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"

def generar_ticket_pdf(reserva):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Paleta (Consistente con el diseño moderno)
    color_primario = colors.HexColor("#0F172A")
    color_secundario = colors.HexColor("#0EA5A5")
    color_claro = colors.HexColor("#F8FAFC")
    color_borde = colors.HexColor("#CBD5E1")
    color_texto = colors.HexColor("#0F172A")

    margen_x = 40

    # Encabezado
    p.setFillColor(color_primario)
    p.roundRect(20, height - 120, width - 40, 90, 12, fill=1, stroke=0)

    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 22)
    p.drawString(margen_x, height - 65, "TORTUGATOUR")

    p.setFont("Helvetica", 10)
    p.drawString(margen_x, height - 83, "RUC: 1792345678001 | Agencia de Viajes")

    p.setFont("Helvetica-Bold", 13)
    p.drawRightString(width - margen_x, height - 62, "VOUCHER DE RESERVA")
    p.setFont("Helvetica", 11)
    p.drawRightString(width - margen_x, height - 82, f"No. {reserva.id:06d}")

    # Tarjetas de información
    y_info = height - 265  # Bajamos un poco para dar aire
    tarjeta_h = 120        # Aumentamos altura para el teléfono
    tarjeta_w = (width - 60 - 20) / 2

    # --- CLIENTE (Actualizado con Apellido y Teléfono) ---
    p.setFillColor(color_claro)
    p.setStrokeColor(color_borde)
    p.roundRect(20, y_info, tarjeta_w, tarjeta_h, 10, fill=1, stroke=1)

    p.setFillColor(color_primario)
    p.setFont("Helvetica-Bold", 11)
    p.drawString(30, y_info + 100, "DATOS DEL CLIENTE")
    p.setStrokeColor(color_secundario)
    p.setLineWidth(1)
    p.line(30, y_info + 95, 170, y_info + 95)

    p.setFillColor(color_texto)
    p.setFont("Helvetica", 10)
    # Mostramos Nombre y Apellidos completos
    p.drawString(30, y_info + 75, f"Nombre: {reserva.nombre} {reserva.apellidos}")
    p.drawString(30, y_info + 59, f"Identificación: {reserva.identificacion}")
    p.drawString(30, y_info + 43, f"Email: {reserva.correo}")
    p.drawString(30, y_info + 27, f"WhatsApp: {reserva.telefono}") # <-- Nuevo campo

    # --- VIAJE (Actualizado con Hora) ---
    x_viaje = 20 + tarjeta_w + 20
    p.setFillColor(color_claro)
    p.setStrokeColor(color_borde)
    p.roundRect(x_viaje, y_info, tarjeta_w, tarjeta_h, 10, fill=1, stroke=1)

    p.setFillColor(color_primario)
    p.setFont("Helvetica-Bold", 11)
    p.drawString(x_viaje + 10, y_info + 100, "DETALLES DEL VIAJE")
    p.setStrokeColor(color_secundario)
    p.line(x_viaje + 10, y_info + 95, x_viaje + 160, y_info + 95)

    p.setFillColor(color_texto)
    p.setFont("Helvetica", 10)
    p.drawString(x_viaje + 10, y_info + 75, f"Tour: {reserva.salida.tour.nombre}")
    p.drawString(x_viaje + 10, y_info + 59, f"Destino: {reserva.salida.tour.destino.nombre}")
    # Formateamos fecha y añadimos la hora
    fecha_str = reserva.salida.fecha.strftime("%d/%m/%Y")
    hora_str = reserva.salida.hora.strftime("%H:%M")
    p.drawString(x_viaje + 10, y_info + 43, f"Fecha: {fecha_str}")
    p.drawString(x_viaje + 10, y_info + 27, f"Hora Salida: {hora_str}") # <-- Nuevo campo

    # Tabla de conceptos
    precio_unit = reserva.salida.tour.precio
    subtotal_adultos = reserva.adultos * precio_unit
    subtotal_ninos = reserva.ninos * precio_unit

    data = [
        ["Descripción", "Cantidad", "Precio Unit.", "Subtotal"],
        [
            f"Reserva Adultos - {reserva.salida.tour.nombre}",
            str(reserva.adultos),
            _fmt_money(precio_unit),
            _fmt_money(subtotal_adultos),
        ],
        [
            "Reserva Niños",
            str(reserva.ninos),
            _fmt_money(precio_unit),
            _fmt_money(subtotal_ninos),
        ],
        ["", "", "TOTAL PAGADO", _fmt_money(reserva.total_pagar)],
    ]

    table = Table(data, colWidths=[280, 70, 90, 90], rowHeights=[28, 24, 24, 30])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), color_primario),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("ALIGN", (0, 1), (0, -1), "LEFT"),
                ("ALIGN", (3, 1), (3, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, 2), 0.5, color_borde),
                ("LINEABOVE", (0, 3), (-1, 3), 1, color_secundario),
                ("FONTNAME", (2, 3), (3, 3), "Helvetica-Bold"),
                ("FONTSIZE", (3, 3), (3, 3), 13),
                ("TEXTCOLOR", (2, 3), (3, 3), color_primario),
                ("BACKGROUND", (0, 1), (-1, 2), colors.white),
                ("BACKGROUND", (0, 3), (-1, 3), color_claro),
            ]
        )
    )

    table.wrapOn(p, margen_x, height - 450)
    table.drawOn(p, margen_x, height - 450)

    # Pie de página
    p.setStrokeColor(color_borde)
    p.line(margen_x, 70, width - margen_x, 70)
    p.setFillColor(colors.HexColor("#475569"))
    p.setFont("Helvetica-Oblique", 8)
    p.drawString(margen_x, 56, "Gracias por su compra. Por favor, llegue 15 minutos antes de la hora de salida.")
    p.drawRightString(width - margen_x, 56, "www.tortugatour.com")

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer