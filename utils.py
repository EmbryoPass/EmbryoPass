import os
import smtplib
import secrets
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy import text

GMAIL_USER = os.environ.get('GMAIL_USER', 'museoembriologia@gmail.com')
GMAIL_PASSWORD = os.environ.get('GMAIL_PASSWORD')


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
    """Agrega columnas faltantes a la tabla cita si no existen."""
    with app.app_context():
        inspector = db.inspect(db.engine)
        columnas = [col['name'] for col in inspector.get_columns('cita')]
        cambios = []

        if 'institucion' not in columnas:
            cambios.append("ADD COLUMN institucion VARCHAR(100)")
        if 'nivel_educativo' not in columnas:
            cambios.append("ADD COLUMN nivel_educativo VARCHAR(50)")

        if cambios:
            alter_sql = f"ALTER TABLE cita {', '.join(cambios)};"
            db.session.execute(text(alter_sql))
            db.session.commit()
            print("✅ Columnas agregadas:", ', '.join(cambios))
        else:
            print("✅ Esquema de BD correcto. No se hicieron cambios.")
