from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
import smtplib
import uuid
import pytz
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import os

# Configuración base
app = Flask(__name__)
app.secret_key = 'secreto123'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

with app.app_context():
    db.create_all()

# Configuración de correo
GMAIL_USER = 'museoembriologia@gmail.com'
GMAIL_PASSWORD = 'qukljqwqdnfjdzgm'

# MODELOS
class Horario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha_hora = db.Column(db.String(100), nullable=False)
    disponibles = db.Column(db.Integer, nullable=False)

class Cita(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    correo = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(20), nullable=False)
    fecha_hora = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.String(20), default='activa')
    asistio = db.Column(db.String(10), nullable=True)
    token_cancelacion = db.Column(db.String(100), nullable=False)

# Función para enviar correos
def enviar_correo(destinatario, asunto, cuerpo_html):
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

# Rutas
@app.route('/', methods=['GET', 'POST'])
def agendar():
    zona = pytz.timezone('America/Chihuahua')
    ahora = datetime.now(zona)

    horarios_db = Horario.query.filter(Horario.disponibles > 0).all()
    horarios = []

    for h in horarios_db:
        try:
            fecha = datetime.strptime(h.fecha_hora, "%d/%m/%Y %I:%M %p")
        except ValueError:
            fecha = datetime.strptime(h.fecha_hora, "%Y-%m-%d %H:%M")
        fecha = zona.localize(fecha)

        if fecha >= ahora:
            horarios.append((h.id, fecha.strftime("%d/%m/%Y %I:%M %p"), h.disponibles))

    if request.method == 'POST':
        nombre = request.form['nombre']
        correo = request.form['correo']
        telefono = request.form['telefono']
        horario_id = request.form['horario']
        horario = Horario.query.get(horario_id)

        if not horario or horario.disponibles <= 0:
            flash('❌ El horario ya está lleno.', 'danger')
            return redirect(url_for('agendar'))

        token = str(uuid.uuid4())
        nueva_cita = Cita(nombre=nombre, correo=correo, telefono=telefono,
                          fecha_hora=horario.fecha_hora, token_cancelacion=token)
        horario.disponibles -= 1
        db.session.add(nueva_cita)
        db.session.commit()

        cuerpo = f"""
<html>
  <body style="font-family: Arial, sans-serif; color: #333;">
    <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
      <h2 style="color: #4a90e2;">Confirmación de Cita - Museo de Embriología Dra. Dora Virginia Chávez Corral </h2>
      <p>Hola <strong>{nombre}</strong>,</p>
      <p>Tu cita ha sido agendada exitosamente. Aquí tienes los detalles:</p>
      <ul style="line-height: 1.6;">
        <li><strong>Nombre:</strong> {nombre}</li>
        <li><strong>Correo:</strong> {correo}</li>
        <li><strong>Teléfono:</strong> {telefono}</li>
        <li><strong>Fecha y hora:</strong> {horario.fecha_hora}</li>
      </ul>
      <p>Si necesitas cancelar tu cita, puedes hacerlo aquí:</p>
      <p>
        <a href="https://embryopass.onrender.com/cancelar_usuario/{nueva_cita.id}/{token}"
           style="background-color: #d9534f; color: white; padding: 10px 15px; text-decoration: none; border-radius: 5px;">
           Cancelar mi cita
        </a>
      </p>
      <p style="margin-top: 20px;">Gracias por tu interés en el <strong>Museo de Embriología Dra. Dora Virginia Chávez Corral</strong>.</p>
    </div>
  </body>
</html>
        """
        enviar_correo(correo, 'Confirmación de Cita - Museo de Embriología', cuerpo)
        flash('✅ Cita agendada correctamente. Revisa tu correo.', 'success')
        return redirect(url_for('agendar'))

    return render_template('agendar.html', horarios=horarios)


ENCARGADO_USER = 'admin'
ENCARGADO_PASS = '1234'

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['usuario']
        password = request.form['password']
        if usuario == ENCARGADO_USER and password == ENCARGADO_PASS:
            session['usuario'] = usuario
            return redirect(url_for('dashboard'))
        flash('❌ Usuario o contraseña incorrectos.', 'danger')
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'usuario' not in session:
        flash('⚠️ Debes iniciar sesión primero.', 'warning')
        return redirect(url_for('login'))

    zona = pytz.timezone('America/Chihuahua')
    ahora = datetime.now(zona)
    rango = request.args.get('rango', default='30')

    if rango == '7':
        inicio_rango = ahora - timedelta(days=7)
    elif rango == '30':
        inicio_rango = ahora - timedelta(days=30)
    elif rango == 'mes':
        inicio_rango = ahora.replace(day=1)
    elif rango == 'todo':
        inicio_rango = datetime.min.replace(tzinfo=zona)
    else:
        inicio_rango = ahora - timedelta(days=30)

    citas_crudas = Cita.query.all()
    citas_futuras = []
    citas_pasadas = []

    for c in citas_crudas:
        try:
            fecha = datetime.strptime(c.fecha_hora, "%d/%m/%Y %I:%M %p")
        except ValueError:
            fecha = datetime.strptime(c.fecha_hora, "%Y-%m-%d %H:%M")
        fecha = zona.localize(fecha)
        tupla = (c.id, c.nombre, c.correo, c.telefono, c.fecha_hora, c.estado, c.asistio)

        if fecha >= ahora:
            citas_futuras.append(tupla)
        elif fecha >= inicio_rango:
            citas_pasadas.append(tupla)

    horarios = []
    for h in Horario.query.all():
        try:
            fecha = datetime.strptime(h.fecha_hora, "%d/%m/%Y %I:%M %p")
        except ValueError:
            fecha = datetime.strptime(h.fecha_hora, "%Y-%m-%d %H:%M")
        fecha = zona.localize(fecha)
        total = h.disponibles + Cita.query.filter_by(fecha_hora=h.fecha_hora, estado='activa').count()
        horarios.append((h.id, fecha.strftime("%d/%m/%Y %I:%M %p"), h.disponibles, total))

    return render_template('dashboard.html', citas=citas_futuras, historial=citas_pasadas, horarios=horarios, rango=rango)

@app.route('/marcar_asistencia/<int:id_cita>/<estado>')
def marcar_asistencia(id_cita, estado):
    if 'usuario' not in session:
        flash('⚠️ Debes iniciar sesión primero.', 'warning')
        return redirect(url_for('login'))

    cita = Cita.query.get(id_cita)
    if cita and estado in ['sí', 'no']:
        cita.asistio = estado
        db.session.commit()
        flash('✅ Asistencia registrada.', 'success')
    else:
        flash('❌ Error al actualizar asistencia.', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/cancelar_cita/<int:id_cita>')
def cancelar_cita(id_cita):
    if 'usuario' not in session:
        flash('⚠️ Debes iniciar sesión primero.', 'warning')
        return redirect(url_for('login'))

    cita = Cita.query.get(id_cita)
    if cita:
        horario = Horario.query.filter_by(fecha_hora=cita.fecha_hora).first()
        cita.estado = "cancelada"
        if horario:
            horario.disponibles += 1
        db.session.commit()
        flash('✅ Cita cancelada y espacio liberado.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/cancelar_usuario/<int:id_cita>/<token>')
def cancelar_usuario(id_cita, token):
    cita = Cita.query.filter_by(id=id_cita, token_cancelacion=token, estado='activa').first()
    if cita:
        cita.estado = 'cancelada'
        horario = Horario.query.filter_by(fecha_hora=cita.fecha_hora).first()
        if horario:
            horario.disponibles += 1
        db.session.commit()
        flash('✅ Tu cita fue cancelada correctamente.', 'success')
    else:
        flash('❌ Enlace inválido o cita ya cancelada.', 'danger')
    return redirect(url_for('agendar'))

@app.route('/cancelar_cita/<int:id_cita>')
def cancelar_cita(id_cita):
    if 'usuario' not in session:
        flash('⚠️ Debes iniciar sesión primero.', 'warning')
        return redirect(url_for('login'))

    cita = Cita.query.get(id_cita)
    if cita:
        horario = Horario.query.filter_by(fecha_hora=cita.fecha_hora).first()
        cita.estado = "cancelada"
        if horario:
            horario.disponibles += 1
        db.session.commit()

        # ✉️ Enviar correo estilizado al usuario
        cuerpo = f"""
        <html>
          <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #f5c6cb; border-radius: 10px;">
              <h2 style="color: #d9534f;">Cancelación de Cita</h2>
              <p>Hola <strong>{cita.nombre}</strong>,</p>
              <p>Tu cita al <strong>Museo de Embriología Dra. Dora Virginia Chávez Corral</strong> programada para el <strong>{cita.fecha_hora}</strong> ha sido cancelada por el administrador.</p>
              <p>Te invitamos a agendar una nueva cita.</p>
              <p style="margin-top: 20px;">Gracias por tu comprensión.</p>
            </div>
          </body>
        </html>
        """
        enviar_correo(cita.correo, 'Cancelación de Cita - Museo de Embriología Dra. Dora Virginia Chávez Corral', cuerpo)

        flash('✅ Cita cancelada, correo enviado y espacio liberado.', 'success')

    return redirect(url_for('dashboard'))


@app.route('/eliminar_horario/<int:id_horario>')
def eliminar_horario(id_horario):
    if 'usuario' not in session:
        flash('⚠️ Debes iniciar sesión primero.', 'warning')
        return redirect(url_for('login'))

    horario = Horario.query.get(id_horario)
    if horario:
        citas = Cita.query.filter_by(fecha_hora=horario.fecha_hora, estado='activa').all()
        for c in citas:
            c.estado = "cancelada"
            cuerpo = f"""
            <html>
              <body style="font-family: Arial, sans-serif; color: #333;">
                <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #f5c6cb; border-radius: 10px;">
                  <h2 style="color: #d9534f;">Cancelación de Cita</h2>
                  <p>Hola <strong>{c.nombre}</strong>,</p>
                  <p>Tu cita programada para el <strong>{c.fecha_hora}</strong> ha sido cancelada debido a cambios en la disponibilidad del <strong>Museo de Embriología Dra. Dora Virginia Chávez Corral</strong>.</p>
                  <p>Te invitamos a agendar una nueva cita en nuestro sitio web.</p>
                  <p style="margin-top: 20px;">Gracias por tu comprensión.</p>
                </div>
              </body>
            </html>
            """
            enviar_correo(c.correo, 'Cancelación de Cita - Museo de Embriología Dra. Dora Virginia Chávez Corral', cuerpo)

        db.session.delete(horario)
        db.session.commit()
        flash('✅ Horario eliminado y notificaciones enviadas.', 'success')

    return redirect(url_for('dashboard'))


@app.route('/agregar_horario', methods=['POST'])
def agregar_horario():
    if 'usuario' not in session:
        flash('⚠️ Debes iniciar sesión primero.', 'warning')
        return redirect(url_for('login'))

    fecha_hora = request.form['fecha_hora']
    disponibles = int(request.form['disponibles'])
    db.session.add(Horario(fecha_hora=fecha_hora, disponibles=disponibles))
    db.session.commit()
    flash('✅ Horario agregado.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.pop('usuario', None)
    flash('✅ Sesión cerrada.', 'success')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
