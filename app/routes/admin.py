import pytz
import pandas as pd
import secrets
import string
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, make_response

from app import db
from app.models import Cita, Horario, VisitaGrupal, EstudianteGrupal, AdminSecret
from app.utils import enviar_correo, generar_password_segura, GMAIL_USER

admin_bp = Blueprint('admin', __name__)

ENCARGADO_USER = 'admin'
ENCARGADO_PASS = '1234'


def login_required(f):
    """Decorador simple para proteger rutas de admin."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'usuario' not in session:
            flash('⚠️ Debes iniciar sesión primero.', 'warning')
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['usuario']
        password = request.form['password']
        if usuario == ENCARGADO_USER and password == ENCARGADO_PASS:
            session['usuario'] = usuario
            return redirect(url_for('admin.dashboard'))
        flash('❌ Usuario o contraseña incorrectos.', 'danger')
    return render_template('login.html')


@admin_bp.route('/logout')
def logout():
    session.pop('usuario', None)
    flash('✅ Sesión cerrada.', 'success')
    return redirect(url_for('admin.login'))


@admin_bp.route('/dashboard')
@login_required
def dashboard():
    zona = pytz.timezone('America/Chihuahua')
    ahora = datetime.now(zona)
    rango = request.args.get('rango', default='30')
    tipo = request.args.get('tipo', default='todas')

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

    citas_futuras = []
    historial_completo = []

    for c in Cita.query.all():
        try:
            fecha = datetime.strptime(c.fecha_hora, "%d/%m/%Y %I:%M %p")
        except ValueError:
            try:
                fecha = datetime.strptime(c.fecha_hora, "%Y-%m-%d %H:%M")
            except ValueError:
                continue
        fecha = zona.localize(fecha)

        tupla = (c.id, c.nombre, c.correo, c.telefono, c.fecha_hora,
                 c.estado, c.asistio, c.edad, c.sexo, c.institucion, c.nivel_educativo)

        if fecha >= ahora and c.estado == 'activa':
            citas_futuras.append(tupla)
        elif (fecha < ahora and fecha >= inicio_rango) or c.estado == 'cancelada':
            historial_completo.append({
                'tipo': 'Individual', 'id': c.id, 'nombre': c.nombre,
                'edad': c.edad, 'sexo': c.sexo, 'correo': c.correo,
                'telefono': c.telefono, 'fecha_hora': c.fecha_hora,
                'estado': c.estado, 'asistio': c.asistio if c.asistio in ['sí', 'no'] else None,
                'institucion': c.institucion, 'nivel': c.nivel_educativo
            })

    for e in EstudianteGrupal.query.order_by(EstudianteGrupal.hora_registro.desc()).all():
        if not e.visita.fecha_confirmada:
            continue
        try:
            fecha = datetime.strptime(e.visita.fecha_confirmada, "%d/%m/%Y %I:%M %p")
        except (ValueError, TypeError):
            continue
        fecha = zona.localize(fecha)

        if fecha < ahora and fecha >= inicio_rango:
            historial_completo.append({
                'tipo': 'Grupal', 'id': e.id, 'nombre': e.nombre,
                'edad': e.edad, 'sexo': e.sexo, 'correo': e.correo,
                'telefono': e.telefono, 'fecha_hora': e.visita.fecha_confirmada,
                'estado': 'finalizada', 'asistio': 'sí',
                'institucion': e.visita.institucion, 'nivel': e.visita.nivel
            })

    horarios = []
    for h in Horario.query.filter(Horario.disponibles > 0).all():
        try:
            fecha = datetime.strptime(h.fecha_hora, "%d/%m/%Y %I:%M %p")
        except ValueError:
            fecha = datetime.strptime(h.fecha_hora, "%Y-%m-%d %H:%M")
        fecha = zona.localize(fecha)
        if fecha >= ahora:
            total = h.disponibles + Cita.query.filter_by(fecha_hora=h.fecha_hora, estado='activa').count()
            horarios.append((h.id, fecha.strftime("%d/%m/%Y %I:%M %p"), h.disponibles, total))

    if tipo == 'individual':
        historial_completo = [r for r in historial_completo if r['tipo'] == 'Individual']
    elif tipo == 'grupal':
        historial_completo = [r for r in historial_completo if r['tipo'] == 'Grupal']

    visitas_grupales = VisitaGrupal.query.order_by(VisitaGrupal.id.desc()).all()
    estudiantes_grupales = []
    for e in EstudianteGrupal.query.order_by(EstudianteGrupal.hora_registro.desc()).all():
        if not e.visita.fecha_confirmada:
            continue
        try:
            fecha = datetime.strptime(e.visita.fecha_confirmada, "%d/%m/%Y %I:%M %p")
        except (ValueError, TypeError):
            continue
        fecha = zona.localize(fecha)
        if fecha >= ahora:
            estudiantes_grupales.append(e)

    secret = AdminSecret.query.get(1)
    admin_password = secret.password if secret else None
    admin_password_at = None
    if secret and secret.created_at:
        chih = pytz.timezone('America/Chihuahua')
        admin_password_at = secret.created_at.replace(tzinfo=pytz.utc).astimezone(chih).strftime("%d/%m/%Y %I:%M %p")

    return render_template(
        'dashboard.html',
        citas=citas_futuras, historial_completo=historial_completo,
        horarios=horarios, rango=rango, admin_password=admin_password,
        admin_password_at=admin_password_at, tipo=tipo, tipo_filtro=tipo,
        visitas_grupales=visitas_grupales, estudiantes_grupales=estudiantes_grupales
    )


@admin_bp.route('/marcar_asistencia/<int:id_cita>/<estado>')
@login_required
def marcar_asistencia(id_cita, estado):
    cita = Cita.query.get(id_cita)
    if cita and estado in ['sí', 'no']:
        cita.asistio = estado
        db.session.commit()
        flash('✅ Asistencia registrada.', 'success')
    else:
        flash('❌ Error al actualizar asistencia.', 'danger')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/cancelar_cita/<int:id_cita>')
@login_required
def cancelar_cita(id_cita):
    cita = Cita.query.get(id_cita)
    if cita:
        horario = Horario.query.filter_by(fecha_hora=cita.fecha_hora).first()
        cita.estado = "cancelada"
        if horario:
            horario.disponibles += 1
        db.session.commit()
        enviar_correo(cita.correo, 'Cancelación de Cita - Museo de Embriología',
            f'<p>Hola <strong>{cita.nombre}</strong>, tu cita del {cita.fecha_hora} ha sido cancelada.</p>')
        flash('✅ Cita cancelada, correo enviado y espacio liberado.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/eliminar_cita/<int:id_cita>')
@login_required
def eliminar_cita(id_cita):
    cita = Cita.query.get(id_cita)
    if cita:
        db.session.delete(cita)
        db.session.commit()
        flash('✅ Cita eliminada.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/agregar_horario', methods=['POST'])
@login_required
def agregar_horario():
    fecha_hora = request.form['fecha_hora']
    disponibles = int(request.form['disponibles'])
    db.session.add(Horario(fecha_hora=fecha_hora, disponibles=disponibles))
    db.session.commit()
    flash('✅ Horario agregado.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/eliminar_horario/<int:id_horario>')
@login_required
def eliminar_horario(id_horario):
    horario = Horario.query.get(id_horario)
    if horario:
        citas = Cita.query.filter_by(fecha_hora=horario.fecha_hora, estado='activa').all()
        for c in citas:
            c.estado = "cancelada"
            enviar_correo(c.correo, 'Cancelación de Cita - Museo de Embriología',
                f'<p>Hola <strong>{c.nombre}</strong>, la cita del {c.fecha_hora} fue cancelada por cambios de disponibilidad.</p>')
        db.session.delete(horario)
        db.session.commit()
        flash('✅ Horario eliminado y notificaciones enviadas.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/aceptar_visita/<int:id>')
@login_required
def aceptar_visita(id):
    visita = VisitaGrupal.query.get(id)
    if not visita:
        flash('❌ Visita no encontrada.', 'danger')
        return redirect(url_for('admin.dashboard'))

    ya_aceptada = (visita.estado == 'aceptada')
    visita.estado = 'aceptada'
    db.session.commit()

    if not ya_aceptada and visita.correo:
        try:
            enviar_correo(visita.correo, 'Solicitud de visita grupal aceptada — Museo de Embriología',
                f'<p>Hola <strong>{visita.encargado}</strong>, tu solicitud de visita grupal ha sido aceptada. En breve te enviaremos la fecha confirmada.</p>')
            flash('✅ Visita marcada como aceptada y correo enviado.', 'success')
        except Exception as e:
            print(f"[EMAIL] Error: {e}")
            flash('✅ Visita aceptada, pero no se pudo enviar el correo.', 'warning')
    else:
        flash('ℹ️ La visita ya estaba aceptada.', 'info')

    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/rechazar_visita/<int:id>')
@login_required
def rechazar_visita(id):
    visita = VisitaGrupal.query.get(id)
    if not visita:
        flash('❌ Visita no encontrada.', 'danger')
        return redirect(url_for('admin.dashboard'))

    visita.estado = 'rechazada'
    db.session.commit()

    try:
        enviar_correo(visita.correo, 'Solicitud de visita grupal rechazada — Museo de Embriología',
            f'<p>Hola <strong>{visita.encargado}</strong>, lamentamos informarte que tu solicitud fue rechazada. Puedes enviar una nueva solicitud con otras fechas.</p>')
        flash('✅ Visita marcada como rechazada y correo enviado.', 'success')
    except Exception as e:
        print(f"[EMAIL] Error: {e}")
        flash('⚠️ Visita rechazada, pero no se pudo enviar el correo.', 'warning')

    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/asignar_fecha_visita/<int:id>', methods=['POST'])
@login_required
def asignar_fecha_visita(id):
    visita = VisitaGrupal.query.get(id)
    if not visita:
        flash('❌ Visita no encontrada.', 'danger')
        return redirect(url_for('admin.dashboard'))

    if visita.estado != 'aceptada':
        flash('❌ La visita aún no ha sido aceptada.', 'danger')
        return redirect(url_for('admin.dashboard'))

    fecha = (request.form.get('fecha_confirmada') or '').strip()
    if not fecha:
        flash('❌ Debes proporcionar una fecha válida.', 'danger')
        return redirect(url_for('admin.dashboard'))

    fecha_anterior = (visita.fecha_confirmada or '').strip()
    visita.fecha_confirmada = fecha
    db.session.commit()

    try:
        if not fecha_anterior:
            enviar_correo(visita.correo, 'Confirmación de visita grupal — Museo de Embriología',
                f'<p>Hola <strong>{visita.encargado}</strong>, tu visita grupal ha sido confirmada para el <strong>{fecha}</strong>.</p>')
            flash('📅 Fecha confirmada y correo enviado.', 'success')
        elif fecha_anterior != fecha:
            enviar_correo(visita.correo, 'Actualización de fecha — Visita grupal al Museo de Embriología',
                f'<p>Hola <strong>{visita.encargado}</strong>, la fecha de tu visita ha sido actualizada de {fecha_anterior} a <strong>{fecha}</strong>.</p>')
            flash('📅 Fecha actualizada y correo enviado.', 'success')
        else:
            flash('📅 Fecha confirmada.', 'success')
    except Exception as e:
        print(f"[EMAIL] Error: {e}")
        flash('📅 Fecha guardada, pero no se pudo enviar el correo.', 'warning')

    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/cancelar_visita_grupal/<int:id>')
@login_required
def cancelar_visita_grupal(id):
    visita = VisitaGrupal.query.get(id)
    if not visita:
        flash('❌ Visita no encontrada.', 'danger')
        return redirect(url_for('admin.dashboard'))

    if visita.estado in ['rechazada', 'cancelada']:
        flash('ℹ️ No es posible cancelar una solicitud rechazada o ya cancelada.', 'info')
        return redirect(url_for('admin.dashboard'))

    visita.estado = 'cancelada'
    db.session.commit()

    try:
        enviar_correo(visita.correo, 'Cancelación de visita grupal - Museo de Embriología',
            f'<p>Hola <strong>{visita.encargado}</strong>, tu visita grupal ha sido cancelada. Puedes solicitar una nueva visita cuando lo desees.</p>')
        flash('✅ Visita cancelada y notificación enviada.', 'success')
    except Exception as e:
        print(f"[EMAIL] Error: {e}")
        flash('✅ Visita cancelada, pero no se pudo enviar el correo.', 'warning')

    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/eliminar_visita_grupal/<int:id>')
@login_required
def eliminar_visita_grupal(id):
    visita = VisitaGrupal.query.get(id)
    if not visita:
        flash('❌ Visita no encontrada.', 'danger')
        return redirect(url_for('admin.dashboard'))

    if visita.estado not in ['cancelada', 'rechazada']:
        flash('❌ Solo puedes eliminar visitas canceladas o rechazadas.', 'danger')
        return redirect(url_for('admin.dashboard'))

    for estudiante in visita.estudiantes:
        db.session.delete(estudiante)
    db.session.delete(visita)
    db.session.commit()
    flash('✅ Visita eliminada correctamente.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/eliminar_estudiante_grupal/<int:id>')
@login_required
def eliminar_estudiante_grupal(id):
    estudiante = EstudianteGrupal.query.get(id)
    if estudiante:
        db.session.delete(estudiante)
        db.session.commit()
        flash('✅ Estudiante eliminado correctamente.', 'success')
    else:
        flash('❌ Estudiante no encontrado.', 'danger')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/generar_password', methods=['POST'])
@login_required
def generar_password():
    nueva = generar_password_segura(14)
    ahora_utc = datetime.utcnow()
    secret = AdminSecret.query.get(1)
    if secret:
        secret.password = nueva
        secret.created_at = ahora_utc
    else:
        secret = AdminSecret(id=1, password=nueva, created_at=ahora_utc)
        db.session.add(secret)
    db.session.commit()
    flash('🔐 Nueva contraseña generada.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/descargar_historial')
@login_required
def descargar_historial():
    zona = pytz.timezone('America/Chihuahua')
    ahora = datetime.now(zona)
    rango = request.args.get('rango', default='30')
    tipo = request.args.get('tipo', default='todas')

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

    for c in Cita.query.all():
        try:
            fecha = datetime.strptime(c.fecha_hora, "%d/%m/%Y %I:%M %p")
        except ValueError:
            fecha = datetime.strptime(c.fecha_hora, "%Y-%m-%d %H:%M")
        fecha = zona.localize(fecha)
        if fecha < ahora and fecha >= inicio_rango:
            historial.append({
                'tipo': 'Individual', 'id': c.id, 'nombre': c.nombre,
                'correo': c.correo, 'telefono': c.telefono, 'edad': c.edad,
                'sexo': c.sexo, 'fecha': c.fecha_hora, 'estado': c.estado,
                'asistio': c.asistio, 'institucion': c.institucion, 'nivel': c.nivel_educativo
            })

    for e in EstudianteGrupal.query.all():
        try:
            fecha = datetime.strptime(e.visita.fecha_confirmada, "%d/%m/%Y %I:%M %p")
        except (ValueError, TypeError):
            continue
        fecha = zona.localize(fecha)
        if fecha < ahora and fecha >= inicio_rango:
            historial.append({
                'tipo': 'Grupal', 'id': e.id, 'nombre': e.nombre,
                'correo': e.correo, 'telefono': e.telefono, 'edad': e.edad,
                'sexo': e.sexo, 'fecha': e.visita.fecha_confirmada, 'estado': 'finalizada',
                'asistio': 'sí', 'institucion': e.visita.institucion, 'nivel': e.visita.nivel
            })

    if tipo == 'individual':
        historial = [h for h in historial if h['tipo'] == 'Individual']
    elif tipo == 'grupal':
        historial = [h for h in historial if h['tipo'] == 'Grupal']

    data = [{
        'ID': h['id'], 'Nombre': h['nombre'], 'Correo': h['correo'],
        'Teléfono': h['telefono'], 'Edad': h['edad'], 'Sexo': h['sexo'],
        'Institución': h['institucion'], 'Nivel Académico': h['nivel'],
        'Fecha y Hora': h['fecha'], 'Tipo de Cita': h['tipo'],
        'Estado': h['estado'], 'Asistió': h['asistio']
    } for h in historial]

    df = pd.DataFrame(data)
    fecha_str = ahora.strftime("%Y-%m-%d_%H-%M")
    nombre_archivo = f"historial_citas_{fecha_str}.xlsx"
    df.to_excel(nombre_archivo, index=False)

    with open(nombre_archivo, 'rb') as f:
        excel_data = f.read()

    response = make_response(excel_data)
    response.headers['Content-Disposition'] = f'attachment; filename={nombre_archivo}'
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    return response


@admin_bp.route('/db-ping')
def db_ping():
    from sqlalchemy import text
    try:
        db.session.execute(text("select 1"))
        return "ok", 200
    except Exception as e:
        return f"db error: {e}", 500
