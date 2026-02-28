import re
import pytz
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session

from app import db
from app.models import VisitaGrupal, EstudianteGrupal
from app.utils import enviar_correo, GMAIL_USER

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
        numero_alumnos = request.form.get('numero_alumnos')
        fechas = request.form.get('fechas_preferidas')
        comentarios = request.form.get('comentarios')

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
            institucion=institucion, nivel=nivel, numero_alumnos=numero_alumnos,
            fechas_preferidas=fechas, comentarios=comentarios
        )
        db.session.add(nueva_visita)
        db.session.commit()

        enviar_correo(GMAIL_USER, f'Solicitud de visita grupal externa – {institucion}',
            f'<p>Nueva solicitud de <strong>{encargado}</strong> de {institucion}.</p>')
        enviar_correo(correo, 'Solicitud recibida - Museo de Embriología',
            f'<p>Hola <strong>{encargado}</strong>, hemos recibido tu solicitud. Nos pondremos en contacto pronto.</p>')

        flash('✅ Solicitud enviada correctamente. Revisa tu correo.', 'success')
        return redirect(url_for('visitas.solicitar_visita_grupal'))

    return render_template('solicitar_visita_grupal.html')


@visitas_bp.route('/registrar-asistencia-grupal', methods=['GET', 'POST'])
def registrar_asistencia_grupal():
    zona = pytz.timezone('America/Chihuahua')
    ahora = datetime.now(zona)

    visitas = []
    for v in VisitaGrupal.query.filter_by(estado='aceptada').all():
        if not v.fecha_confirmada:
            continue
        try:
            fecha = datetime.strptime(v.fecha_confirmada, "%d/%m/%Y %I:%M %p")
        except ValueError:
            continue
        fecha = zona.localize(fecha)
        if fecha.date() == ahora.date():
            visitas.append((v.id, v.institucion, v.fecha_confirmada))

    if request.method == 'POST':
        nombre = (request.form.get('nombre') or '').strip()
        correo = request.form.get('correo') or ''
        telefono = request.form.get('telefono') or ''
        edad = request.form.get('edad')
        sexo = request.form.get('sexo')
        visita_id = request.form.get('visita_id')

        if not nombre or not sexo or not edad or not visita_id:
            flash('❌ Todos los campos obligatorios deben estar llenos.', 'danger')
            return render_template('registrar_asistencia_grupal.html', visitas=visitas)

        try:
            edad_int = int(edad)
            if edad_int <= 0:
                raise ValueError
        except Exception:
            flash('❌ La edad debe ser un número entero mayor que cero.', 'danger')
            return render_template('registrar_asistencia_grupal.html', visitas=visitas)

        try:
            visita_id_int = int(visita_id)
        except (TypeError, ValueError):
            flash('❌ Visita inválida.', 'danger')
            return render_template('registrar_asistencia_grupal.html', visitas=visitas)

        from sqlalchemy import func
        norm_in = ''.join(nombre.split()).lower()
        existente = (
            EstudianteGrupal.query
            .filter(EstudianteGrupal.visita_id == visita_id_int)
            .filter(func.lower(func.regexp_replace(EstudianteGrupal.nombre, r'\s+', '', 'g')) == norm_in)
            .first()
        )
        if existente:
            flash('❌ Ya hay un registro con ese nombre para esta visita.', 'danger')
            return render_template('registrar_asistencia_grupal.html', visitas=visitas)

        estudiante = EstudianteGrupal(
            nombre=nombre, correo=correo, telefono=telefono,
            edad=edad_int, sexo=sexo, visita_id=visita_id_int,
            hora_registro=ahora.strftime("%d/%m/%Y %I:%M %p")
        )
        db.session.add(estudiante)
        db.session.commit()

        if correo:
            visita = VisitaGrupal.query.get(visita_id_int)
            enviar_correo(correo, 'Confirmación de asistencia a visita grupal',
                f'<p>Hola <strong>{nombre}</strong>, tu asistencia a la visita de {visita.institucion} el {visita.fecha_confirmada} fue registrada.</p>')

        flash('✅ Asistencia registrada correctamente.', 'success')
        return redirect(url_for('visitas.registrar_asistencia_grupal'))

    return render_template('registrar_asistencia_grupal.html', visitas=visitas)
