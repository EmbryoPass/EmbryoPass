import io
import os
import smtplib
import secrets
import string
import openpyxl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from sqlalchemy import text

GMAIL_USER = os.environ.get('GMAIL_USER', 'museoembriologia@gmail.com')
GMAIL_PASSWORD = os.environ.get('GMAIL_PASSWORD')

NOMBRE_MUSEO = '"Museo de Embriología Dra. Dora Virginia Chávez Corral"'


def enviar_correo(destinatario, asunto, cuerpo_html):
    """Envía un correo HTML usando Gmail SMTP."""
    if not GMAIL_USER or not GMAIL_PASSWORD:
        print("⚠️ GMAIL_USER/GMAIL_PASSWORD no configurados; no se envía correo.")
        return

    mensaje = MIMEMultipart()
    mensaje['From'] = GMAIL_USER
    mensaje['To'] = destinatario
    mensaje['Subject'] = asunto
    mensaje.attach(MIMEText(cuerpo_html, 'html'))

    servidor = smtplib.SMTP('smtp.gmail.com', 587)
    servidor.starttls()
    servidor.login(GMAIL_USER, GMAIL_PASSWORD)
    servidor.sendmail(GMAIL_USER, destinatario, mensaje.as_string())
    servidor.quit()


def enviar_correo_con_excel(destinatario, asunto, cuerpo_html, nombre_archivo_excel):
    """Envía un correo HTML con un Excel provisional adjunto para llenar datos de estudiantes."""
    if not GMAIL_USER or not GMAIL_PASSWORD:
        print("⚠️ GMAIL_USER/GMAIL_PASSWORD no configurados; no se envía correo.")
        return

    # Crear Excel en memoria
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Estudiantes"

    # Encabezados provisionales
    encabezados = ["No.", "Nombre completo", "Edad", "Sexo (Hombre/Mujer)", "Correo electrónico", "Teléfono"]
    ws.append(encabezados)

    # Estilo de encabezados
    from openpyxl.styles import Font, PatternFill, Alignment
    for col, celda in enumerate(ws[1], start=1):
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="8B4513")
        celda.alignment = Alignment(horizontal="center")
        ws.column_dimensions[celda.column_letter].width = 25

    # Filas vacías numeradas (10 alumnos máx)
    for i in range(1, 11):
        ws.append([i, "", "", "", "", ""])

    # Guardar en buffer
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    # Armar correo
    mensaje = MIMEMultipart()
    mensaje['From'] = GMAIL_USER
    mensaje['To'] = destinatario
    mensaje['Subject'] = asunto
    mensaje.attach(MIMEText(cuerpo_html, 'html'))

    # Adjuntar Excel
    adjunto = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    adjunto.set_payload(buffer.read())
    encoders.encode_base64(adjunto)
    adjunto.add_header('Content-Disposition', f'attachment; filename="{nombre_archivo_excel}"')
    mensaje.attach(adjunto)

    servidor = smtplib.SMTP('smtp.gmail.com', 587)
    servidor.starttls()
    servidor.login(GMAIL_USER, GMAIL_PASSWORD)
    servidor.sendmail(GMAIL_USER, destinatario, mensaje.as_string())
    servidor.quit()


def generar_password_segura(longitud=14):
    """Genera una contraseña segura aleatoria."""
    alfabeto = string.ascii_letters + string.digits + "!@#$%_-"
    while True:
        pwd = ''.join(secrets.choice(alfabeto) for _ in range(longitud))
        if (any(c.islower() for c in pwd) and
                any(c.isupper() for c in pwd) and
                any(c.isdigit() for c in pwd) and
                any(c in "!@#$%_-" for c in pwd)):
            return pwd


def verificar_y_agregar_columnas(app, db):
    """Agrega columnas faltantes si no existen."""
    with app.app_context():
        inspector = db.inspect(db.engine)

        # Tabla cita
        columnas_cita = [col['name'] for col in inspector.get_columns('cita')]
        cambios_cita = []
        if 'institucion' not in columnas_cita:
            cambios_cita.append("ADD COLUMN institucion VARCHAR(100)")
        if 'nivel_educativo' not in columnas_cita:
            cambios_cita.append("ADD COLUMN nivel_educativo VARCHAR(50)")
        if 'ciudad' not in columnas_cita:
            cambios_cita.append("ADD COLUMN ciudad VARCHAR(100)")
        if 'estado_republica' not in columnas_cita:
            cambios_cita.append("ADD COLUMN estado_republica VARCHAR(100)")
        if cambios_cita:
            db.session.execute(text(f"ALTER TABLE cita {', '.join(cambios_cita)};"))
            db.session.commit()
            print("✅ Columnas agregadas a cita:", cambios_cita)

        # Tabla visita_grupal
        columnas_vg = [col['name'] for col in inspector.get_columns('visita_grupal')]
        cambios_vg = []
        if 'ciudad' not in columnas_vg:
            cambios_vg.append("ADD COLUMN ciudad VARCHAR(100)")
        if 'estado_republica' not in columnas_vg:
            cambios_vg.append("ADD COLUMN estado_republica VARCHAR(100)")
        if 'bachillerato' not in columnas_vg:
            cambios_vg.append("ADD COLUMN bachillerato VARCHAR(150)")
        if cambios_vg:
            db.session.execute(text(f"ALTER TABLE visita_grupal {', '.join(cambios_vg)};"))
            db.session.commit()
            print("✅ Columnas agregadas a visita_grupal:", cambios_vg)
