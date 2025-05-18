
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
import smtplib
import requests
import uuid
import pytz
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import os
from sqlalchemy import text
import pandas as pd
from flask import make_response

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
    edad = db.Column(db.Integer, nullable=True)
    sexo = db.Column(db.String(10), nullable=True)
    institucion = db.Column(db.String(100), nullable=True) 
    nivel_educativo = db.Column(db.String(50), nullable=True)

class VisitaGrupal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    encargado = db.Column(db.String(100), nullable=False)  # nombre_encargado en el formulario
    correo = db.Column(db.String(120), nullable=False)      # correo_encargado
    telefono = db.Column(db.String(20), nullable=False)     # telefono_encargado
    institucion = db.Column(db.String(100), nullable=False)
    nivel = db.Column(db.String(50), nullable=False)        # nivel_educativo
    numero_alumnos = db.Column(db.Integer, nullable=False)
    fechas_preferidas = db.Column(db.Text, nullable=False)
    comentarios = db.Column(db.Text)
    estado = db.Column(db.String(20), default='pendiente')
    fecha_confirmada = db.Column(db.String(100), nullable=True)

class EstudianteGrupal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    correo = db.Column(db.String(120), nullable=True)
    telefono = db.Column(db.String(20), nullable=True)  
    edad = db.Column(db.Integer, nullable=True)
    sexo = db.Column(db.String(10), nullable=True)
    hora_registro = db.Column(db.String(100), nullable=False)
    visita_id = db.Column(db.Integer, db.ForeignKey('visita_grupal.id'), nullable=False)
    visita = db.relationship('VisitaGrupal', backref=db.backref('estudiantes', lazy=True))


@app.route('/inicio')
def inicio():
    return render_template('index.html')

@app.route('/')
def home_redirect():
    return redirect(url_for('inicio'))

@app.route('/ir-a-visita-grupal')
def ir_a_visita_grupal():
    return redirect(url_for('solicitar_visita_grupal'))

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

@app.route('/agendar-cita', methods=['GET', 'POST'])
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
        confirmar_correo = request.form['confirmar_correo']
        telefono = request.form['telefono']
        horario_id = request.form['horario']
        edad = request.form['edad']
        sexo = request.form['sexo']
        institucion = request.form.get('institucion') or None
        nivel_educativo = request.form.get('nivel') or None


        if correo != confirmar_correo:
            flash('❌ Los correos no coinciden.', 'danger')
            return redirect(url_for('agendar'))

        # Validar formato de correo
        import re
        patron = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not re.match(patron, correo):
            flash('❌ El correo electrónico no tiene un formato válido.', 'danger')
            return redirect(url_for('agendar'))

        if not telefono.isdigit() or len(telefono) != 10:
            flash('❌ El teléfono debe tener exactamente 10 dígitos numéricos.', 'danger')
            return redirect(url_for('agendar'))

        horario = Horario.query.get(horario_id)
        if not horario:
            flash('❌ El horario seleccionado no existe.', 'danger')
            return redirect(url_for('agendar'))

        cita_existente = Cita.query.filter_by(
            correo=correo,
            fecha_hora=horario.fecha_hora,
            estado='activa'
        ).first()
        if cita_existente:
            flash('❌ Ya tienes una cita activa para este horario.', 'danger')
            return redirect(url_for('agendar'))

        try:
            rows_updated = db.session.execute(
                db.update(Horario)
                .where(Horario.id == horario_id)
                .where(Horario.disponibles > 0)
                .values(disponibles=Horario.disponibles - 1)
            ).rowcount

            if rows_updated == 0:
                flash('❌ El horario ya está lleno.', 'danger')
                db.session.rollback()
                return redirect(url_for('agendar'))

            token = str(uuid.uuid4())
            nueva_cita = Cita(
                nombre=nombre,
                correo=correo,
                telefono=telefono,
                fecha_hora=horario.fecha_hora,
                token_cancelacion=token,
                edad=edad,
                sexo=sexo,
                institucion=institucion,
                nivel_educativo=nivel_educativo
            )
            db.session.add(nueva_cita)
            db.session.commit()

            cuerpo = f"""
<html>
  <body style="font-family: Arial, sans-serif; color: #333;">
    <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
      <h2 style="color: #4a90e2;">Confirmación de Cita - Museo de Embriología Dra. Dora Virginia Chávez Corral</h2>
      <p>Hola <strong>{nombre}</strong>,</p>
      <p>Tu cita ha sido agendada exitosamente. Aquí tienes los detalles:</p>
      <ul style="line-height: 1.6;">
        <li><strong>Nombre:</strong> {nombre}</li>
        <li><strong>Correo:</strong> {correo}</li>
        <li><strong>Teléfono:</strong> {telefono}</li>
        <li><strong>Edad:</strong> {edad}</li>
        <li><strong>Sexo:</strong> {sexo}</li>
        <li><strong>Institución:</strong> {nueva_cita.institucion or '—'}</li>
        <li><strong>Nivel educativo:</strong> {nueva_cita.nivel_educativo or '—'}</li>
        <li><strong>Fecha y hora:</strong> {horario.fecha_hora}</li>
      </ul>
      <p>Si necesitas cancelar tu cita, puedes hacerlo aquí:</p>
      <p>
        <a href="https://embryopass.onrender.com/cancelar_usuario/{nueva_cita.id}/{token}"
           style="background-color: #d9534f; color: white; padding: 10px 15px; text-decoration: none; border-radius: 5px;">
           Cancelar mi cita
        </a>
      </p>
      <p style="margin-top: 20px;">Gracias por el interés en el <strong>Museo de Embriología Dra. Dora Virginia Chávez Corral</strong>.</p>
    </div>
  </body>
</html>
            """
            enviar_correo(correo, 'Confirmación de Cita - Museo de Embriología', cuerpo)

            enviar_correo(
                GMAIL_USER,
                'Nueva Cita Agendada',
                f'''
                <html>
                <body style="font-family: Arial, sans-serif;">
                  <h3>🧬 Nueva cita agendada</h3>
                  <ul>
                    <li><strong>Nombre:</strong> {nombre}</li>
                    <li><strong>Correo:</strong> {correo}</li>
                    <li><strong>Teléfono:</strong> {telefono}</li>
                    <li><strong>Edad:</strong> {edad}</li>
                    <li><strong>Sexo:</strong> {sexo}</li>
                    <li><strong>Fecha:</strong> {horario.fecha_hora}</li>
                  </ul>
                </body>
                </html>
                '''
            )

            flash('✅ Cita agendada correctamente. Revisa tu correo.', 'success')
            return redirect(url_for('agendar'))

        except Exception as e:
            db.session.rollback()
            flash('❌ Error al agendar cita. Intenta nuevamente.', 'danger')
            print(f"Error al agendar cita: {e}")

    return render_template('agendar.html', horarios=horarios)

@app.route('/solicitar-visita-grupal', methods=['GET', 'POST'])
def solicitar_visita_grupal():
    if request.method == 'POST':
        encargado = request.form.get('nombre_encargado')
        correo = request.form.get('correo_encargado')
        confirmar_correo = request.form.get('confirmar_correo_encargado')
        telefono = request.form.get('telefono_encargado')
        institucion = request.form.get('institucion')
        nivel = request.form.get('nivel_educativo')
        numero_alumnos = request.form.get('numero_alumnos')
        fechas = request.form.get('fechas_preferidas')
        comentarios = request.form.get('comentarios')

        # ✅ Validar correo
        import re
        patron_correo = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if correo != confirmar_correo:
            flash('❌ Los correos no coinciden.', 'danger')
            return render_template('solicitar_visita_grupal.html')
        if not re.match(patron_correo, correo):
            flash('❌ El correo no tiene un formato válido.', 'danger')
            return render_template('solicitar_visita_grupal.html')

        # ✅ Validar teléfono
        if not telefono.isdigit() or len(telefono) != 10:
            flash('❌ El teléfono debe contener exactamente 10 dígitos numéricos.', 'danger')
            return render_template('solicitar_visita_grupal.html')

        # ✅ Validar número de alumnos
        try:
            numero_alumnos = int(numero_alumnos)
            if numero_alumnos <= 0:
                raise ValueError
        except:
            flash('❌ El número de alumnos debe ser mayor a 0.', 'danger')
            return render_template('solicitar_visita_grupal.html')

        # ✅ Guardar en la base de datos
        nueva_visita = VisitaGrupal(
            encargado=encargado,
            correo=correo,
            telefono=telefono,
            institucion=institucion,
            nivel=nivel,
            numero_alumnos=numero_alumnos,
            fechas_preferidas=fechas,
            comentarios=comentarios
        )
        db.session.add(nueva_visita)
        db.session.commit()

        # ✅ Correo al museo
        cuerpo_museo = f"""
        <html>
          <body style="font-family: Arial, sans-serif;">
            <p>🧬 Se ha solicitado una visita grupal externa al museo por parte de <strong>{encargado}</strong>, de la institución <strong>{institucion}</strong>.</p>
            <br>
            <p><strong>Detalles de la solicitud:</strong></p>
            <ul>
              <li><strong>Encargado:</strong> {encargado}</li>
              <li><strong>Correo:</strong> {correo}</li>
              <li><strong>Teléfono:</strong> {telefono}</li>
              <li><strong>Institución:</strong> {institucion}</li>
              <li><strong>Nivel educativo:</strong> {nivel}</li>
              <li><strong>Número estimado de alumnos:</strong> {numero_alumnos}</li>
              <li><strong>Fechas y horarios propuestos:</strong> {fechas}</li>
              <li><strong>Comentarios adicionales:</strong> {comentarios or 'Ninguno'}</li>
            </ul>
          </body>
        </html>
        """
        enviar_correo('museoembriologia@gmail.com', f'Solicitud de visita grupal externa – {institucion}', cuerpo_museo)

        # ✅ Correo al encargado
        cuerpo_encargado = f"""
<html>
  <body style="font-family: Arial, sans-serif; color: #333;">
    <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
      <h2 style="color: #4a90e2;">Solicitud recibida - Museo de Embriología Dra. Dora Virginia Chávez Corral</h2>
      <p>Hola <strong>{encargado}</strong>,</p>
      <p>Hemos recibido su solicitud de visita grupal para el Museo de Embriología  Dra. Dora Virginia Chávez Corral.</p>
      <p>Nos pondremos en contacto pronto para coordinar la visita.</p>
      </p>Aquí tienes los detalles:</p>
      <ul style="line-height: 1.6;">
        <li><strong>Encargado:</strong> {encargado}</li>
        <li><strong>Correo:</strong> {correo}</li>
        <li><strong>Teléfono:</strong> {telefono}</li>
        <li><strong>Institución:</strong> {institucion}</li>
        <li><strong>Nivel académico:</strong> {nivel}</li>
        <li><strong>Alumnos estimados:</strong> {numero_alumnos}</li>
        <li><strong>Fechas propuestas:</strong> {fechas}</li>
      </ul>
      <p style="margin-top: 20px;">Gracias por el interés en el <strong>Museo de Embriología Dra. Dora Virginia Chávez Corral</strong>.</p>
    </div>
  </body>
</html>
"""

        enviar_correo(correo, 'Solicitud recibida - Museo de Embriología', cuerpo_encargado)

        flash('✅ Solicitud enviada correctamente. Revisa tu correo.', 'success')
        return redirect(url_for('inicio'))

    return render_template('solicitar_visita_grupal.html')

@app.route('/registrar-asistencia-grupal', methods=['GET', 'POST'])
def registrar_asistencia_grupal():
    zona = pytz.timezone('America/Chihuahua')
    ahora = datetime.now(zona)

    # Filtrar visitas aceptadas y con fecha confirmada válida
    visitas = []
    for v in VisitaGrupal.query.filter_by(estado='aceptada').all():
        if not v.fecha_confirmada:
            continue
        try:
            fecha = datetime.strptime(v.fecha_confirmada, "%d/%m/%Y %I:%M %p")
        except ValueError:
            continue
        fecha = zona.localize(fecha)
        if ahora >= (fecha - timedelta(hours=1)) and ahora <= (fecha + timedelta(hours=2)):
            visitas.append((v.id, v.institucion, v.fecha_confirmada))

    if request.method == 'POST':
        nombre = request.form.get('nombre')
        correo = request.form.get('correo') or None  # correo opcional
        telefono = request.form.get('telefono')
        edad = request.form.get('edad')
        sexo = request.form.get('sexo')
        visita_id = request.form.get('visita_id')

        if not nombre or not visita_id:
            flash('❌ Todos los campos obligatorios deben estar llenos.', 'danger')
            return redirect(url_for('registrar_asistencia_grupal'))

        estudiante = EstudianteGrupal(
            nombre=nombre,
            correo=correo,
            telefono=telefono,
            edad=edad,
            sexo=sexo,
            visita_id=visita_id,
            hora_registro=datetime.now(zona).strftime("%d/%m/%Y %I:%M %p")
        )
        db.session.add(estudiante)
        db.session.commit()
        flash('✅ Asistencia registrada correctamente.', 'success')
        return redirect(url_for('registrar_asistencia_grupal'))

    return render_template('registrar_asistencia_grupal.html', visitas=visitas)


# Nuevas rutas para el flujo de visitas grupales
@app.route('/aceptar_visita/<int:id>')
def aceptar_visita(id):
    if 'usuario' not in session:
        flash('⚠️ Debes iniciar sesión primero.', 'warning')
        return redirect(url_for('login'))

    visita = VisitaGrupal.query.get(id)
    if visita:
        visita.estado = 'aceptada'
        db.session.commit()
        flash('✅ Visita marcada como aceptada.', 'success')
    else:
        flash('❌ Visita no encontrada.', 'danger')
    return redirect(url_for('dashboard'))


@app.route('/rechazar_visita/<int:id>')
def rechazar_visita(id):
    if 'usuario' not in session:
        flash('⚠️ Debes iniciar sesión primero.', 'warning')
        return redirect(url_for('login'))

    visita = VisitaGrupal.query.get(id)
    if visita:
        visita.estado = 'rechazada'
        db.session.commit()
        flash('✅ Visita marcada como rechazada.', 'success')
    else:
        flash('❌ Visita no encontrada.', 'danger')
    return redirect(url_for('dashboard'))


@app.route('/asignar_fecha_visita/<int:id>', methods=['POST'])
def asignar_fecha_visita(id):
    if 'usuario' not in session:
        flash('⚠️ Debes iniciar sesión primero.', 'warning')
        return redirect(url_for('login'))

    visita = VisitaGrupal.query.get(id)
    if visita and visita.estado == 'aceptada':
        fecha = request.form.get('fecha_confirmada')
        visita.fecha_confirmada = fecha
        db.session.commit()
        flash('📅 Fecha confirmada para la visita grupal.', 'success')
    else:
        flash('❌ La visita no existe o no ha sido aceptada aún.', 'danger')
    return redirect(url_for('dashboard'))


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
    tipo = request.args.get('tipo', default='todos')  # nuevo filtro de tipo

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
    historial_completo = []

    for c in citas_crudas:
        try:
            fecha = datetime.strptime(c.fecha_hora, "%d/%m/%Y %I:%M %p")
        except ValueError:
            fecha = datetime.strptime(c.fecha_hora, "%Y-%m-%d %H:%M")
        fecha = zona.localize(fecha)

        tupla = (
            c.id, c.nombre, c.correo, c.telefono,
            c.fecha_hora, c.estado, c.asistio,
            c.edad, c.sexo, c.institucion, c.nivel_educativo
        )

        if fecha >= ahora:
            citas_futuras.append(tupla)
        elif fecha < ahora and fecha >= inicio_rango:
            historial_completo.append({
                'tipo': 'Individual',
                'id': c.id,
                'nombre': c.nombre,
                'edad': c.edad,
                'sexo': c.sexo,
                'correo': c.correo,
                'telefono': c.telefono,
                'fecha_hora': c.fecha_hora,
                'estado': c.estado,
                'asistio': c.asistio,
                'institucion': c.institucion,
                'nivel': c.nivel_educativo
            })

    for e in EstudianteGrupal.query.all():
        try:
            fecha = datetime.strptime(e.visita.fecha_confirmada, "%d/%m/%Y %I:%M %p")
        except (ValueError, TypeError):
            continue
        fecha = zona.localize(fecha)

        if fecha < ahora and fecha >= inicio_rango:
            historial_completo.append({
                'tipo': 'Grupal',
                'id': e.id,
                'nombre': e.nombre,
                'edad': e.edad,
                'sexo': e.sexo,
                'correo': e.correo,
                'telefono': e.telefono,
                'fecha_hora': e.visita.fecha_confirmada,
                'estado': 'finalizada',
                'asistio': 'sí',
                'institucion': e.visita.institucion,
                'nivel': e.visita.nivel
            })

    horarios = []
    for h in Horario.query.all():
        try:
            fecha = datetime.strptime(h.fecha_hora, "%d/%m/%Y %I:%M %p")
        except ValueError:
            fecha = datetime.strptime(h.fecha_hora, "%Y-%m-%d %H:%M")
        fecha = zona.localize(fecha)
        total = h.disponibles + Cita.query.filter_by(fecha_hora=h.fecha_hora, estado='activa').count()
        horarios.append((h.id, fecha.strftime("%d/%m/%Y %I:%M %p"), h.disponibles, total))

    if tipo == 'individual':
        historial_completo = [r for r in historial_completo if r['tipo'] == 'Individual']
    elif tipo == 'grupal':
        historial_completo = [r for r in historial_completo if r['tipo'] == 'Grupal']

    visitas_grupales = VisitaGrupal.query.order_by(VisitaGrupal.id.desc()).all()
    estudiantes_grupales = EstudianteGrupal.query.order_by(EstudianteGrupal.hora_registro.desc()).all()

    return render_template(
        'dashboard.html',
        citas=citas_futuras,
        historial_completo=historial_completo,
        horarios=horarios,
        rango=rango,
        tipo_filtro=tipo,
        visitas_grupales=visitas_grupales,
        estudiantes_grupales=estudiantes_grupales
    )


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


@app.route('/cancelar_usuario/<int:id_cita>/<token>')
def cancelar_usuario(id_cita, token):
    cita = Cita.query.filter_by(id=id_cita, token_cancelacion=token, estado='activa').first()
    if cita:
        cita.estado = 'cancelada'
        horario = Horario.query.filter_by(fecha_hora=cita.fecha_hora).first()
        if horario:
            horario.disponibles += 1
        db.session.commit()

        # ✉️ Notificación al museo incluyendo edad y sexo
        cuerpo_admin = f"""
        <html>
          <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #ccc; border-radius: 10px;">
              <h2 style="color: #d9534f;">Cancelación de Cita</h2>
              <p>Un visitante ha cancelado su cita:</p>
              <ul style="line-height: 1.6;">
                <li><strong>Nombre:</strong> {cita.nombre}</li>
                <li><strong>Correo:</strong> {cita.correo}</li>
                <li><strong>Teléfono:</strong> {cita.telefono}</li>
                <li><strong>Edad:</strong> {cita.edad}</li>
                <li><strong>Sexo:</strong> {cita.sexo}</li>        
                <li><strong>Institución:</strong> {cita.institucion or '—'}</li>
                <li><strong>Nivel educativo:</strong> {cita.nivel_educativo or '—'}</li>
                <li><strong>Fecha y hora:</strong> {cita.fecha_hora}</li>
              </ul>
            </div>
          </body>
        </html>
        """
        enviar_correo('museoembriologia@gmail.com', 'Cancelación de Cita - Museo de Embriología', cuerpo_admin)

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

        # ✉️ Correo al usuario
        cuerpo_usuario = f"""
<html>
  <body style="font-family: Arial, sans-serif; color: #333;">
    <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #f5c6cb; border-radius: 10px;">
      <h2 style="color: #d9534f;">Cancelación de Cita</h2>
      <p>Hola <strong>{cita.nombre}</strong>,</p>
      <p>Tu cita al <strong>Museo de Embriología Dra. Dora Virginia Chávez Corral</strong> programada para el <strong>{cita.fecha_hora}</strong> ha sido cancelada debido a un imprevisto.</p>
      <p>Te invitamos a agendar una nueva cita.</p>
      <p style="text-align: center; margin-top: 20px;">
        <a href="https://embryopass.onrender.com/" 
           style="display: inline-block; padding: 10px 20px; background-color: #5cb85c; color: white; text-decoration: none; border-radius: 5px;">
           Agendar nueva cita
        </a>
      </p>
      <p style="margin-top: 20px;">Gracias por la comprensión.</p>
    </div>
  </body>
</html>
"""
        enviar_correo(cita.correo, 'Cancelación de Cita - Museo de Embriología Dra. Dora Virginia Chávez Corral', cuerpo_usuario)

        # ✉️ Notificación al museo
        cuerpo_admin = f"""
<html>
  <body style="font-family: Arial, sans-serif; color: #333;">
    <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #ccc; border-radius: 10px;">
      <h2 style="color: #d9534f;">Cancelación de Cita desde el Panel</h2>
      <p>Una cita fue cancelada desde el panel de administración:</p>
      <ul style="line-height: 1.6;">
        <li><strong>Nombre:</strong> {cita.nombre}</li>
        <li><strong>Correo:</strong> {cita.correo}</li>
        <li><strong>Teléfono:</strong> {cita.telefono}</li>
        <li><strong>Edad:</strong> {cita.edad}</li>
        <li><strong>Sexo:</strong> {cita.sexo}</li>
        <li><strong>Institución:</strong> {cita.institucion or '—'}</li>
        <li><strong>Nivel educativo:</strong> {cita.nivel_educativo or '—'}</li>
        <li><strong>Fecha y hora:</strong> {cita.fecha_hora}</li>
      </ul>
    </div>
  </body>
</html>
"""
        enviar_correo('museoembriologia@gmail.com', 'Cancelación de Cita - Museo de Embriología', cuerpo_admin)

        flash('✅ Cita cancelada, correo enviado y espacio liberado.', 'success')

    return redirect(url_for('dashboard'))


@app.route('/eliminar_cita/<int:id_cita>')
def eliminar_cita(id_cita):
    if 'usuario' not in session:
        flash('⚠️ Debes iniciar sesión primero.', 'warning')
        return redirect(url_for('login'))

    cita = Cita.query.get(id_cita)
    if cita:
        db.session.delete(cita)
        db.session.commit()
        flash('✅ Cita eliminada.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/eliminar_visita_grupal/<int:id>')
def eliminar_visita_grupal(id):
    if 'usuario' not in session:
        flash('⚠️ Debes iniciar sesión primero.', 'warning')
        return redirect(url_for('login'))

    visita = VisitaGrupal.query.get(id)
    if visita:
        db.session.delete(visita)
        db.session.commit()
        flash('✅ Solicitud de visita eliminada.', 'success')
    else:
        flash('❌ Visita no encontrada.', 'danger')

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

            # ✉️ Correo al usuario
            cuerpo = f"""
<html>
  <body style="font-family: Arial, sans-serif; color: #333;">
    <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #f5c6cb; border-radius: 10px;">
      <h2 style="color: #d9534f;">Cancelación de Cita</h2>
      <p>Hola <strong>{c.nombre}</strong>,</p>
      <p>Tu cita programada para el <strong>{c.fecha_hora}</strong> ha sido cancelada debido a cambios en la disponibilidad del <strong>Museo de Embriología Dra. Dora Virginia Chávez Corral</strong>.</p>
      <p>Te invitamos a agendar una nueva cita.</p>
      <p style="text-align: center;">
        <a href="https://embryopass.onrender.com/" 
           style="display: inline-block; padding: 10px 20px; background-color: #5cb85c; color: white; text-decoration: none; border-radius: 5px;">
           Agendar nueva cita
        </a>
      </p>
      <p style="margin-top: 20px;">Gracias por tu comprensión.</p>
    </div>
  </body>
</html>
"""
            enviar_correo(c.correo, 'Cancelación de Cita - Museo de Embriología Dra. Dora Virginia Chávez Corral', cuerpo)

        # ✉️ Notificación global al museo
        cuerpo_admin = f"""
        <html>
          <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #ccc; border-radius: 10px;">
              <h2 style="color: #d9534f;">Horario Eliminado</h2>
              <p>El siguiente horario ha sido eliminado y todas sus citas activas han sido canceladas:</p>
              <ul>
                <li><strong>Fecha y hora:</strong> {horario.fecha_hora}</li>
                <li><strong>Total de citas canceladas:</strong> {len(citas)}</li>
              </ul>
            </div>
          </body>
        </html>
        """
        enviar_correo('museoembriologia@gmail.com', 'Horario eliminado - Museo de Embriología', cuerpo_admin)

        db.session.delete(horario)
        db.session.commit()
        flash('✅ Horario eliminado y notificaciones enviadas.', 'success')

    return redirect(url_for('dashboard'))

@app.route('/cancelar_visita_grupal/<int:id>')
def cancelar_visita_grupal(id):
    if 'usuario' not in session:
        flash('⚠️ Debes iniciar sesión primero.', 'warning')
        return redirect(url_for('login'))

    visita = VisitaGrupal.query.get(id)
    if visita:
        visita.estado = 'cancelada'
        db.session.commit()

        # Enviar correo al encargado notificando la cancelación
        cuerpo = f"""
        <html>
          <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
              <h2 style="color: #d9534f;">Cancelación de Solicitud de Visita Grupal - Museo de Embriología Dra. Dora Virginia Chávez Corral</h2>
              <p>Hola <strong>{visita.encargado}</strong>,</p>
              <p>Lamentamos informarte que tu solicitud de visita grupal institucional ha sido <strong>cancelada</strong>. Aquí tienes los detalles:</p>
              <ul style="line-height: 1.6;">
                <li><strong>Encargado:</strong> {visita.encargado}</li>
                <li><strong>Correo:</strong> {visita.correo}</li>
                <li><strong>Teléfono:</strong> {visita.telefono}</li>
                <li><strong>Institución:</strong> {visita.institucion}</li>
                <li><strong>Nivel académico:</strong> {visita.nivel}</li>
                <li><strong>Alumnos estimados:</strong> {visita.numero_alumnos}</li>
                <li><strong>Fechas propuestas:</strong> {visita.fechas_preferidas}</li>
                <li><strong>Comentarios:</strong> {visita.comentarios or '—'}</li>
              </ul>
              <p>Si deseas realizar una nueva solicitud, puedes hacerlo aquí:</p>
              <p>
                <a href="https://embryopass.onrender.com/ir-a-visita-grupal"
                   style="background-color: #5cb85c; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                   Solicitar nueva visita
                </a>
              </p>
              <p style="margin-top: 20px;">Gracias por tu interés en el <strong>Museo de Embriología Dra. Dora Virginia Chávez Corral</strong>.</p>
            </div>
          </body>
        </html>
        """
        enviar_correo(visita.correo, 'Cancelación de visita grupal - Museo de Embriología', cuerpo)

        flash('✅ Visita cancelada y notificación enviada.', 'success')
    else:
        flash('❌ Visita no encontrada.', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/eliminar_estudiante_grupal/<int:id>')
def eliminar_estudiante_grupal(id):
    if 'usuario' not in session:
        flash('⚠️ Debes iniciar sesión primero.', 'warning')
        return redirect(url_for('login'))

    estudiante = EstudianteGrupal.query.get(id)
    if estudiante:
        db.session.delete(estudiante)
        db.session.commit()
        flash('✅ Estudiante eliminado correctamente.', 'success')
    else:
        flash('❌ Estudiante no encontrado.', 'danger')
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
@app.route('/descargar_historial')
def descargar_historial():
    if 'usuario' not in session:
        flash('⚠️ Debes iniciar sesión primero.', 'warning')
        return redirect(url_for('login'))

    zona = pytz.timezone('America/Chihuahua')
    ahora = datetime.now(zona)
    rango = request.args.get('rango', default='30')
    tipo = request.args.get('tipo', default='todos')

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

    historial = []

    # Citas individuales
    for c in Cita.query.all():
        try:
            fecha = datetime.strptime(c.fecha_hora, "%d/%m/%Y %I:%M %p")
        except ValueError:
            fecha = datetime.strptime(c.fecha_hora, "%Y-%m-%d %H:%M")
        fecha = zona.localize(fecha)

        if fecha < ahora and fecha >= inicio_rango:
            historial.append({
                'tipo': 'Individual',
                'id': c.id,
                'nombre': c.nombre,
                'correo': c.correo,
                'telefono': c.telefono,
                'edad': c.edad,
                'sexo': c.sexo,
                'fecha': c.fecha_hora,
                'estado': c.estado,
                'asistio': c.asistio,
                'institucion': c.institucion,
                'nivel': c.nivel_educativo
            })

    # Estudiantes de visitas grupales
    for e in EstudianteGrupal.query.all():
        try:
            fecha = datetime.strptime(e.visita.fecha_confirmada, "%d/%m/%Y %I:%M %p")
        except (ValueError, TypeError):
            continue
        fecha = zona.localize(fecha)

        if fecha < ahora and fecha >= inicio_rango:
            historial.append({
                'tipo': 'Grupal',
                'id': e.id,
                'nombre': e.nombre,
                'correo': e.correo,
                'telefono': e.telefono,
                'edad': e.edad,
                'sexo': e.sexo,
                'fecha': e.visita.fecha_confirmada,
                'estado': 'finalizada',
                'asistio': 'sí',
                'institucion': e.visita.institucion,
                'nivel': e.visita.nivel
            })

    # Aplicar filtro por tipo
    if tipo == 'individual':
        historial = [h for h in historial if h['tipo'] == 'Individual']
    elif tipo == 'grupal':
        historial = [h for h in historial if h['tipo'] == 'Grupal']

    # Construir DataFrame
    data = [{
        'ID': h['id'],
        'Nombre': h['nombre'],
        'Correo': h['correo'],
        'Teléfono': h['telefono'],
        'Edad': h['edad'],
        'Sexo': h['sexo'],
        'Institución': h['institucion'],
        'Nivel Académico': h['nivel'],
        'Fecha y Hora': h['fecha'],
        'Tipo de Cita': h['tipo'],
        'Estado': h['estado'],
        'Asistió': h['asistio']
    } for h in historial]

    df = pd.DataFrame(data)

    # Crear archivo con fecha en el nombre
    fecha_str = ahora.strftime("%Y-%m-%d_%H-%M")
    nombre_archivo = f"historial_citas_{fecha_str}.xlsx"
    df.to_excel(nombre_archivo, index=False)

    with open(nombre_archivo, 'rb') as f:
        excel_data = f.read()

    response = make_response(excel_data)
    response.headers['Content-Disposition'] = f'attachment; filename={nombre_archivo}'
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

    return response


@app.route('/logout')
def logout():
    session.pop('usuario', None)
    flash('✅ Sesión cerrada.', 'success')
    return redirect(url_for('login'))

def verificar_y_agregar_columnas_postgresql():
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
            print("✅ Columnas agregadas: ", ', '.join([c.split()[2] for c in cambios]))
        else:
            print("✅ Las columnas ya existen. No se hicieron cambios.")
            
def inicializar_tablas():
    with app.app_context():
        db.create_all()

if __name__ == '__main__':
    inicializar_tablas()
    verificar_y_agregar_columnas_postgresql()  # 👈 agrega esta línea
    app.run(host='0.0.0.0', port=10000)

