import re
import pytz
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash

from app import db
from app.models import VisitaGrupal
from app.utils import enviar_correo, GMAIL_USER, NOMBRE_MUSEO

visitas_bp = Blueprint('visitas', __name__)


@visitas_bp.route('/solicitar-visita-grupal', methods=['GET', 'POST'])
def solicitar_visita_grupal():
    if request.method == 'POST':
        encargado = request.form.get('nombre_encargado').strip()
        correo = request.form.get('correo_encargado')
        confirmar_correo = request.form.get('confirmar_correo_encargado')
        telefono = request.form.get('telefono_encargado')
        institucion = request.form.get('institucion')
        nivel = request.form.get('nivel_educativo')
        bachillerato = request.form.get('bachillerato', '').strip()
        bachillerato_otro = request.form.get('bachillerato_otro', '').strip()
        numero_alumnos = request.form.get('numero_alumnos')
        fechas = request.form.get('fechas_preferidas')
        comentarios = request.form.get('comentarios')
        ciudad = request.form.get('ciudad', '').strip()
        estado_republica = request.form.get('estado_republica', '').strip()

        # Si bachillerato es "Otro", usar el campo de texto
        if bachillerato == 'Otro' and bachillerato_otro:
            bachillerato = f"Otro: {bachillerato_otro}"

        if correo != confirmar_correo:
            flash('❌ Los correos no coinciden.', 'danger')
            return render_template('solicitar_visita_grupal.html')
        if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', correo):
            flash('❌ El correo no tiene un formato válido.', 'danger')
            return render_template('solicitar_visita_grupal.html')
        if not telefono.isdigit() or len(telefono) != 10:
            flash('❌ El teléfono debe contener exactamente 10 dígitos numéricos.', 'danger')
            return render_template('solicitar_visita_grupal.html')

        try:
            numero_alumnos = int(numero_alumnos)
            if numero_alumnos <= 0:
                raise ValueError
        except Exception:
            flash('❌ El número de alumnos debe ser mayor a 0.', 'danger')
            return render_template('solicitar_visita_grupal.html')

        nueva_visita = VisitaGrupal(
            encargado=encargado, correo=correo, telefono=telefono,
            institucion=institucion, nivel=nivel,
            bachillerato=bachillerato if nivel == 'Bachillerato' else None,
            numero_alumnos=numero_alumnos, fechas_preferidas=fechas,
            comentarios=comentarios, ciudad=ciudad, estado_republica=estado_republica
        )
        db.session.add(nueva_visita)
        db.session.commit()

        enviar_correo(GMAIL_USER, f'Solicitud de visita grupal externa – {institucion}', f"""
<html><body style="font-family:Arial,sans-serif;color:#333;">
  <div style="max-width:600px;margin:auto;padding:20px;border:1px solid #eee;border-radius:10px;">
    <h3>🧬 Nueva solicitud de visita grupal</h3>
    <ul style="line-height:1.8;">
      <li><strong>Encargado:</strong> {encargado}</li>
      <li><strong>Correo:</strong> {correo}</li>
      <li><strong>Teléfono:</strong> {telefono}</li>
      <li><strong>Institución:</strong> {institucion}</li>
      <li><strong>Nivel académico:</strong> {nivel}{(' – ' + bachillerato) if bachillerato else ''}</li>
      <li><strong>Alumnos estimados:</strong> {numero_alumnos}</li>
      <li><strong>Ciudad:</strong> {ciudad}</li>
      <li><strong>Estado:</strong> {estado_republica}</li>
      <li><strong>Fechas propuestas:</strong> {fechas}</li>
      <li><strong>Comentarios:</strong> {comentarios or '—'}</li>
    </ul>
  </div>
</body></html>""")

        enviar_correo(correo, f'Solicitud recibida – {NOMBRE_MUSEO}', f"""
<html><body style="font-family:Arial,sans-serif;color:#333;">
  <div style="max-width:600px;margin:auto;padding:20px;border:1px solid #eee;border-radius:10px;">
    <h2 style="color:#4a90e2;">Solicitud recibida – {NOMBRE_MUSEO}</h2>
    <p>Hola <strong>{encargado}</strong>,</p>
    <p>Hemos recibido tu solicitud de visita grupal al {NOMBRE_MUSEO}. Nos pondremos en contacto pronto para coordinar la visita.</p>
    <ul style="line-height:1.8;">
      <li><strong>Institución:</strong> {institucion}</li>
      <li><strong>Nivel académico:</strong> {nivel}{(' – ' + bachillerato) if bachillerato else ''}</li>
      <li><strong>Alumnos estimados:</strong> {numero_alumnos}</li>
      <li><strong>Fechas propuestas:</strong> {fechas}</li>
    </ul>
    <p>Gracias por tu interés en el {NOMBRE_MUSEO}.</p>
  </div>
</body></html>""")

        flash('✅ Solicitud enviada correctamente. Revisa tu correo.', 'success')
        return redirect(url_for('visitas.solicitar_visita_grupal'))

    return render_template('solicitar_visita_grupal.html')
