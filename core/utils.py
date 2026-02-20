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

    # Paleta Original Aceptada
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
    y_info = height - 255
    tarjeta_h = 110
    tarjeta_w = (width - 60 - 20) / 2

    # Cliente
    p.setFillColor(color_claro)
    p.setStrokeColor(color_borde)
    p.roundRect(20, y_info, tarjeta_w, tarjeta_h, 10, fill=1, stroke=1)

    p.setFillColor(color_primario)
    p.setFont("Helvetica-Bold", 11)
    p.drawString(30, y_info + 87, "DATOS DEL CLIENTE")
    p.setStrokeColor(color_secundario)
    p.setLineWidth(1)
    p.line(30, y_info + 82, 170, y_info + 82)

    p.setFillColor(color_texto)
    p.setFont("Helvetica", 10)
    p.drawString(30, y_info + 62, f"Nombre: {reserva.nombre} {reserva.apellidos}")
    p.drawString(30, y_info + 46, f"Identificacion: {reserva.identificacion}")
    p.drawString(30, y_info + 30, f"Email: {reserva.correo}")

    # Viaje
    x_viaje = 20 + tarjeta_w + 20
    p.setFillColor(color_claro)
    p.setStrokeColor(color_borde)
    p.roundRect(x_viaje, y_info, tarjeta_w, tarjeta_h, 10, fill=1, stroke=1)

    p.setFillColor(color_primario)
    p.setFont("Helvetica-Bold", 11)
    p.drawString(x_viaje + 10, y_info + 87, "DETALLES DEL VIAJE")
    p.setStrokeColor(color_secundario)
    p.line(x_viaje + 10, y_info + 82, x_viaje + 160, y_info + 82)

    p.setFillColor(color_texto)
    p.setFont("Helvetica", 10)
    p.drawString(x_viaje + 10, y_info + 62, f"Tour: {reserva.salida.tour.nombre}")
    p.drawString(x_viaje + 10, y_info + 46, f"Destino: {reserva.salida.tour.destino.nombre}")
    
    hora_str = reserva.salida.hora.strftime('%H:%M') if reserva.salida.hora else "Por definir"
    p.drawString(x_viaje + 10, y_info + 30, f"Salida: {reserva.salida.fecha} a las {hora_str}")

    # Tabla de conceptos
    precio_adulto = reserva.salida.tour.precio_adulto_final()
    precio_nino = reserva.salida.tour.precio_nino_final()
    
    subtotal_adultos = reserva.adultos * precio_adulto
    subtotal_ninos = reserva.ninos * precio_nino

    data = [["Descripción", "Cantidad", "Precio Unit.", "Subtotal"]]
    
    if reserva.adultos > 0:
        data.append([
            f"Adultos - {reserva.salida.tour.nombre}",
            str(reserva.adultos),
            _fmt_money(precio_adulto),
            _fmt_money(subtotal_adultos),
        ])
        
    if reserva.ninos > 0:
        data.append([
            "Niños",
            str(reserva.ninos),
            _fmt_money(precio_nino),
            _fmt_money(subtotal_ninos),
        ])

    data.append(["", "", "TOTAL PAGADO", _fmt_money(reserva.total_pagar)])

    # Alturas dinámicas
    row_heights = [28] + [24] * (len(data) - 2) + [30]
    table = Table(data, colWidths=[280, 70, 90, 90], rowHeights=row_heights)
    
    # Grid dinámico dependiendo de la cantidad de filas
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), color_primario),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 1), (0, -1), "LEFT"),
        ("ALIGN", (3, 1), (3, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, len(data) - 2), 0.5, color_borde),
        ("LINEABOVE", (0, len(data) - 1), (-1, len(data) - 1), 1, color_secundario),
        ("FONTNAME", (2, len(data) - 1), (3, len(data) - 1), "Helvetica-Bold"),
        ("FONTSIZE", (3, len(data) - 1), (3, len(data) - 1), 13),
        ("TEXTCOLOR", (2, len(data) - 1), (3, len(data) - 1), color_primario),
        ("BACKGROUND", (0, 1), (-1, len(data) - 2), colors.white),
        ("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1), color_claro),
    ]
    
    table.setStyle(TableStyle(estilo))

    # Center placement
    table_height = sum(row_heights)
    current_y = height - 280 - table_height
    table.wrapOn(p, margen_x, current_y)
    table.drawOn(p, margen_x, current_y)

    # Pie de pagina legal
    p.setStrokeColor(color_borde)
    p.line(margen_x, 70, width - margen_x, 70)
    p.setFillColor(colors.HexColor("#475569"))
    p.setFont("Helvetica-Oblique", 8)
    p.drawString(
        margen_x,
        56,
        "Este documento es un comprobante de reserva general y no constituye una factura legal fiscal.",
    )

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer
