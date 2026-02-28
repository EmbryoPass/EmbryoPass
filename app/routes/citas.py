import re
import uuid
import pytz
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from sqlalchemy import update

from app import db
from app.models import Cita, Horario
from app.utils import enviar_correo, GMAIL_USER

citas_bp = Blueprint('citas', __name__)


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

        nombre = request.form['nombre'].strip()
        correo = request.form['correo']
        confirmar_correo = request.form['confirmar_correo']
        telefono = request.form['telefono']
        horario_id = request.form['horario']
        edad = request.form['edad']
        sexo = request.form['sexo']
        institucion = request.form.get('institucion', '').strip()
        nivel_educativo = request.form.get('nivel', '').strip()

        if not institucion or not nivel_educativo:
            flash('❌ Institución y nivel académico son obligatorios.', 'danger')
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

        horario = Horario.query.get(horario_id)
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
            rows_updated = db.session.execute(
                update(Horario)
                .where(Horario.id == horario_id)
                .where(Horario.disponibles > 0)
                .values(disponibles=Horario.disponibles - 1)
            ).rowcount

            if rows_updated == 0:
                flash('❌ El horario ya está lleno.', 'danger')
                db.session.rollback()
                return redirect(url_for('citas.agendar'))

            token = str(uuid.uuid4())
            nueva_cita = Cita(
                nombre=nombre, correo=correo, telefono=telefono,
                fecha_hora=horario.fecha_hora, token_cancelacion=token,
                edad=edad, sexo=sexo, institucion=institucion, nivel_educativo=nivel_educativo
            )
            db.session.add(nueva_cita)
            db.session.commit()

            cuerpo = f"""
<html><body style="font-family: Arial, sans-serif; color: #333;">
  <div style="max-width:600px;margin:auto;padding:20px;border:1px solid #eee;border-radius:10px;">
    <h2 style="color:#4a90e2;">Confirmación de Cita - Museo de Embriología Dra. Dora Virginia Chávez Corral</h2>
    <p>Hola <strong>{nombre}</strong>, tu cita ha sido agendada exitosamente.</p>
    <ul style="line-height:1.6;">
      <li><strong>Fecha y hora:</strong> {horario.fecha_hora}</li>
      <li><strong>Institución:</strong> {institucion}</li>
      <li><strong>Nivel educativo:</strong> {nivel_educativo}</li>
    </ul>
    <p>Si necesitas cancelar tu cita:</p>
    <a href="https://embryopass.onrender.com/cancelar_usuario/{nueva_cita.id}/{token}"
       style="background:#d9534f;color:white;padding:10px 15px;text-decoration:none;border-radius:5px;">
       Cancelar mi cita
    </a>
  </div>
</body></html>"""
            enviar_correo(correo, 'Confirmación de Cita - Museo de Embriología', cuerpo)
            enviar_correo(GMAIL_USER, 'Nueva Cita Agendada',
                f'<p>Nueva cita de <strong>{nombre}</strong> para el {horario.fecha_hora}.</p>')

            flash('✅ Cita agendada correctamente. Revisa tu correo.', 'success')
            return redirect(url_for('citas.agendar'))

        except Exception as e:
            db.session.rollback()
            flash('❌ Error al agendar cita. Intenta nuevamente.', 'danger')
            print(f"Error al agendar cita: {e}")

    hay_disponibles = len(horarios) > 0
    return render_template('agendar.html', horarios=horarios, hay_disponibles=hay_disponibles)


@citas_bp.route('/cancelar_usuario/<int:id_cita>/<token>')
def cancelar_usuario(id_cita, token):
    zona = pytz.timezone('America/Chihuahua')
    ahora = datetime.now(zona)

    cita = Cita.query.filter_by(id=id_cita, token_cancelacion=token, estado='activa').first()
    if not cita:
        flash('❌ Enlace inválido o cita ya cancelada.', 'danger')
        return redirect(url_for('citas.agendar'))

    try:
        fecha = datetime.strptime(cita.fecha_hora, "%d/%m/%Y %I:%M %p")
    except ValueError:
        fecha = datetime.strptime(cita.fecha_hora, "%Y-%m-%d %H:%M")
    fecha = zona.localize(fecha)

    if ahora > fecha:
        flash('⚠️ No puedes cancelar una cita pasada.', 'warning')
        return redirect(url_for('citas.agendar'))

    cita.estado = 'cancelada'
    horario = Horario.query.filter_by(fecha_hora=cita.fecha_hora).first()
    if horario:
        horario.disponibles += 1
    db.session.commit()

    enviar_correo('museoembriologia@gmail.com', 'Cancelación de Cita - Museo de Embriología',
        f'<p>{cita.nombre} canceló su cita del {cita.fecha_hora}.</p>')

    flash('✅ Tu cita fue cancelada correctamente.', 'success')
    return redirect(url_for('citas.agendar'))
