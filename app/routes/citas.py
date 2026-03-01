import os
import re
import uuid
import pytz
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import update

from app import db
from app.models import Cita, Horario
from app.utils import enviar_correo, GMAIL_USER, NOMBRE_MUSEO

citas_bp = Blueprint('citas', __name__)

URL_SITIO = os.environ.get('URL_SITIO', 'http://localhost:5000')


@citas_bp.route('/agendar-cita', methods=['GET', 'POST'])
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
        if not horarios:
            flash('❌ Actualmente no hay citas disponibles.', 'danger')
            return redirect(url_for('citas.agendar'))

        nombre           = request.form['nombre'].strip()
        correo           = request.form['correo'].strip().lower()
        confirmar_correo = request.form['confirmar_correo'].strip().lower()
        telefono         = request.form['telefono'].strip()
        horario_id       = request.form['horario']
        edad_raw         = request.form.get('edad', '').strip()
        sexo             = request.form['sexo']
        institucion      = request.form.get('institucion', '').strip()
        nivel            = request.form.get('nivel', '').strip()
        nivel_otro       = request.form.get('nivel_otro', '').strip()
        ciudad           = request.form.get('ciudad', '').strip()
        estado_republica = request.form.get('estado_republica', '').strip()

        # Si nivel es "Otro", usar el campo de texto libre
        nivel_educativo = nivel_otro if nivel == 'Otro' and nivel_otro else nivel

        # ── Validaciones ─────────────────────────────────────────────────────
        if not institucion or not nivel_educativo:
            flash('❌ Institución y nivel académico son obligatorios.', 'danger')
            return redirect(url_for('citas.agendar'))

        if not ciudad or not estado_republica:
            flash('❌ Ciudad y estado son obligatorios.', 'danger')
            return redirect(url_for('citas.agendar'))

        if correo != confirmar_correo:
            flash('❌ Los correos no coinciden.', 'danger')
            return redirect(url_for('citas.agendar'))

        if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', correo):
            flash('❌ El correo electrónico no tiene un formato válido.', 'danger')
            return redirect(url_for('citas.agendar'))

        if not telefono.isdigit() or len(telefono) != 10:
            flash('❌ El teléfono debe tener exactamente 10 dígitos numéricos.', 'danger')
            return redirect(url_for('citas.agendar'))

        try:
            edad = int(edad_raw)
            if edad < 1 or edad > 120:
                raise ValueError
        except (ValueError, TypeError):
            flash('❌ La edad debe ser un número válido (1–120).', 'danger')
            return redirect(url_for('citas.agendar'))

        # Usar db.session.get() — forma correcta en SQLAlchemy 2.0
        horario = db.session.get(Horario, int(horario_id))
        if not horario:
            flash('❌ El horario seleccionado no existe.', 'danger')
            return redirect(url_for('citas.agendar'))

        cita_existente = Cita.query.filter_by(
            correo=correo, fecha_hora=horario.fecha_hora, estado='activa'
        ).first()
        if cita_existente:
            flash('❌ Ya tienes una cita activa para este horario.', 'danger')
            return redirect(url_for('citas.agendar'))

        try:
            # UPDATE atómico para evitar condiciones de carrera
            rows_updated = db.session.execute(
                update(Horario)
                .where(Horario.id == horario_id)
                .where(Horario.disponibles > 0)
                .values(disponibles=Horario.disponibles - 1)
            ).rowcount

            if rows_updated == 0:
                flash('❌ El horario ya está lleno. Por favor elige otro.', 'danger')
                db.session.rollback()
                return redirect(url_for('citas.agendar'))

            token = str(uuid.uuid4())
            nueva_cita = Cita(
                nombre=nombre, correo=correo, telefono=telefono,
                fecha_hora=horario.fecha_hora, token_cancelacion=token,
                edad=edad, sexo=sexo, institucion=institucion,
                nivel_educativo=nivel_educativo, ciudad=ciudad,
                estado_republica=estado_republica
            )
            db.session.add(nueva_cita)
            db.session.commit()

            cuerpo = f"""
<html><body style="font-family:Arial,sans-serif;color:#333;">
  <div style="max-width:600px;margin:auto;padding:20px;border:1px solid #eee;border-radius:10px;">
    <h2 style="color:#4a90e2;">Confirmacion de Cita - {NOMBRE_MUSEO}</h2>
    <p>Hola <strong>{nombre}</strong>, tu cita ha sido agendada exitosamente.</p>
    <ul style="line-height:1.6;">
      <li><strong>Fecha y hora:</strong> {horario.fecha_hora}</li>
      <li><strong>Nombre:</strong> {nombre}</li>
      <li><strong>Correo:</strong> {correo}</li>
      <li><strong>Telefono:</strong> {telefono}</li>
      <li><strong>Ciudad y estado de procedencia:</strong> {ciudad}, {estado_republica}</li>
      <li><strong>Institucion:</strong> {institucion}</li>
      <li><strong>Nivel educativo:</strong> {nivel_educativo}</li>
    </ul>
    <p><strong>Duracion estimada:</strong> 10 a 15 minutos.</p>
    <p><strong>Indicaciones durante la visita:</strong></p>
    <ul style="line-height:1.6;">
      <li>No tocar las exhibiciones.</li>
      <li>No comer ni beber dentro del museo.</li>
      <li>No hablar en voz alta.</li>
      <li>No tomar fotos ni videos.</li>
      <li>No correr ni empujar dentro del museo.</li>
      <li>No manipular etiquetas, carteles o informacion sobre las piezas.</li>
    </ul>
    <p>Si necesitas cancelar tu cita:</p>
    <a href="{URL_SITIO}/cancelar_usuario/{nueva_cita.id}/{token}"
       style="background:#d9534f;color:white;padding:10px 15px;text-decoration:none;border-radius:5px;">
       Cancelar mi cita
    </a>
    <p style="margin-top:20px;">Gracias por tu interes en el {NOMBRE_MUSEO}.</p>
  </div>
</body></html>"""
            enviar_correo(correo, f'Confirmacion de Cita - {NOMBRE_MUSEO}', cuerpo)
            enviar_correo(GMAIL_USER, 'Nueva Cita Agendada', f"""
<html><body style="font-family:Arial,sans-serif;">
  <h3>Nueva cita agendada</h3>
  <ul>
    <li><strong>Fecha y hora:</strong> {horario.fecha_hora}</li>
    <li><strong>Nombre:</strong> {nombre}</li>
    <li><strong>Correo:</strong> {correo}</li>
    <li><strong>Telefono:</strong> {telefono}</li>
    <li><strong>Ciudad y estado de procedencia:</strong> {ciudad}, {estado_republica}</li>
    <li><strong>Institucion:</strong> {institucion}</li>
    <li><strong>Nivel educativo:</strong> {nivel_educativo}</li>
  </ul>
</body></html>""")

            flash('Cita agendada correctamente. Revisa tu correo.', 'success')
            return redirect(url_for('citas.agendar'))

        except Exception as e:
            db.session.rollback()
            flash('Error al agendar cita. Intenta nuevamente.', 'danger')
            print(f"[ERROR agendar]: {type(e).__name__}: {e}")

    hay_disponibles = len(horarios) > 0
    return render_template('agendar.html', horarios=horarios, hay_disponibles=hay_disponibles)


@citas_bp.route('/cancelar_usuario/<int:id_cita>/<token>')
def cancelar_usuario(id_cita, token):
    zona = pytz.timezone('America/Chihuahua')
    ahora = datetime.now(zona)

    cita = Cita.query.filter_by(id=id_cita, token_cancelacion=token, estado='activa').first()
    if not cita:
        flash('Enlace invalido o cita ya cancelada.', 'danger')
        return redirect(url_for('citas.agendar'))

    try:
        fecha = datetime.strptime(cita.fecha_hora, "%d/%m/%Y %I:%M %p")
    except ValueError:
        fecha = datetime.strptime(cita.fecha_hora, "%Y-%m-%d %H:%M")
    fecha = zona.localize(fecha)

    if ahora > fecha:
        flash('No puedes cancelar una cita pasada.', 'warning')
        return redirect(url_for('citas.agendar'))

    try:
        cita.estado = 'cancelada'
        horario = Horario.query.filter_by(fecha_hora=cita.fecha_hora).first()
        if horario:
            citas_activas_restantes = Cita.query.filter_by(
                fecha_hora=cita.fecha_hora, estado='activa'
            ).count() - 1
            total_original = horario.disponibles + Cita.query.filter_by(
                fecha_hora=cita.fecha_hora, estado='activa'
            ).count()
            horario.disponibles = max(0, total_original - citas_activas_restantes)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash('Error al cancelar la cita. Intenta de nuevo.', 'danger')
        print(f"[ERROR cancelar_usuario]: {type(e).__name__}: {e}")
        return redirect(url_for('citas.agendar'))

    try:
        enviar_correo(GMAIL_USER, f'Cancelacion de Cita - {NOMBRE_MUSEO}',
            f'<p>{cita.nombre} cancelo su cita del {cita.fecha_hora}.</p>')
    except Exception as e:
        print(f"[EMAIL cancelar_usuario]: {e}")

    flash('Tu cita fue cancelada correctamente.', 'success')
    return redirect(url_for('citas.agendar'))
