import pytz
import pandas as pd
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, make_response

from app import db
from app.models import Cita, Horario, VisitaGrupal, AdminSecret
from app.utils import enviar_correo, enviar_correo_con_excel, generar_password_segura, GMAIL_USER, NOMBRE_MUSEO

admin_bp = Blueprint('admin', __name__)

ENCARGADO_USER = 'admin'
ENCARGADO_PASS = '1234'


def login_required(f):
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

        if (fecha < ahora and fecha >= inicio_rango) or c.estado == 'cancelada':
            historial_completo.append({
                'tipo': 'Individual', 'id': c.id, 'nombre': c.nombre,
                'edad': c.edad, 'sexo': c.sexo, 'correo': c.correo,
                'telefono': c.telefono, 'fecha_hora': c.fecha_hora,
                'estado': c.estado, 'asistio': c.asistio if c.asistio in ['sí', 'no'] else None,
                'institucion': c.institucion, 'nivel': c.nivel_educativo
            })

    # ── Horarios futuros con sus citas activas embebidas ─────────────────────
    # Se incluyen TODOS los horarios (incluso llenos) para que el admin
    # siempre vea las citas reservadas dentro de cada uno.
    horarios = []
    for h in Horario.query.all():
        try:
            fecha = datetime.strptime(h.fecha_hora, "%d/%m/%Y %I:%M %p")
        except ValueError:
            fecha = datetime.strptime(h.fecha_hora, "%Y-%m-%d %H:%M")
        fecha = zona.localize(fecha)

        if fecha >= ahora:
            citas_activas = Cita.query.filter_by(fecha_hora=h.fecha_hora, estado='activa').all()
            total = h.disponibles + len(citas_activas)
            horarios.append({
                'id':          h.id,
                'fecha_hora':  fecha.strftime("%d/%m/%Y %I:%M %p"),
                'disponibles': h.disponibles,
                'total':       total,
                'citas':       citas_activas,
            })

    horarios.sort(key=lambda x: datetime.strptime(x['fecha_hora'], "%d/%m/%Y %I:%M %p"))

    if tipo == 'individual':
        historial_completo = [r for r in historial_completo if r['tipo'] == 'Individual']
    elif tipo == 'grupal':
        historial_completo = [r for r in historial_completo if r['tipo'] == 'Grupal']

    visitas_grupales = VisitaGrupal.query.order_by(VisitaGrupal.id.desc()).all()

    secret = AdminSecret.query.get(1)
    admin_password = secret.password if secret else None
    admin_password_at = None
    if secret and secret.created_at:
        chih = pytz.timezone('America/Chihuahua')
        admin_password_at = secret.created_at.replace(tzinfo=pytz.utc).astimezone(chih).strftime("%d/%m/%Y %I:%M %p")

    return render_template(
        'dashboard.html',
        historial_completo=historial_completo,
        horarios=horarios,
        rango=rango,
        admin_password=admin_password,
        admin_password_at=admin_password_at,
        tipo=tipo,
        tipo_filtro=tipo,
        visitas_grupales=visitas_grupales
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
        enviar_correo(cita.correo, f'Cancelación de Cita – {NOMBRE_MUSEO}', f"""
<html><body style="font-family:Arial,sans-serif;color:#333;">
  <div style="max-width:600px;margin:auto;padding:20px;border:1px solid #f5c6cb;border-radius:10px;">
    <h2 style="color:#d9534f;">Cancelación de Cita</h2>
    <p>Hola <strong>{cita.nombre}</strong>,</p>
    <p>Tu cita al {NOMBRE_MUSEO} del <strong>{cita.fecha_hora}</strong> ha sido cancelada debido a un imprevisto.</p>
    <p>Te invitamos a agendar una nueva cita cuando lo desees.</p>
    <p>Gracias por tu comprensión.</p>
  </div>
</body></html>""")
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
    if disponibles > 10:
        disponibles = 10
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
            enviar_correo(c.correo, f'Cancelación de Cita – {NOMBRE_MUSEO}', f"""
<html><body style="font-family:Arial,sans-serif;color:#333;">
  <div style="max-width:600px;margin:auto;padding:20px;border:1px solid #f5c6cb;border-radius:10px;">
    <h2 style="color:#d9534f;">Cancelación de Cita</h2>
    <p>Hola <strong>{c.nombre}</strong>,</p>
    <p>Tu cita del <strong>{c.fecha_hora}</strong> ha sido cancelada por cambios de disponibilidad en el {NOMBRE_MUSEO}.</p>
    <p>Te invitamos a agendar una nueva cita.</p>
  </div>
</body></html>""")
        db.session.delete(horario)
        db.session.commit()
        flash('✅ Horario eliminado y notificaciones enviadas.', 'success')
    return redirect(url_for('admin.dashboard'))


# ── Helper: nivel con plantel ────────────────────────────────────────────────
def _nivel_str(visita):
    if visita.nivel == 'Bachillerato' and visita.bachillerato:
        return f"{visita.nivel} – {visita.bachillerato}"
    return visita.nivel or '—'


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
            enviar_correo(visita.correo, f'Solicitud de visita grupal aceptada — {NOMBRE_MUSEO}', f"""
<html><body style="font-family:Arial,sans-serif;color:#333;">
  <div style="max-width:600px;margin:auto;padding:20px;border:1px solid #eee;border-radius:10px;">
    <h2 style="color:#4a90e2;">Solicitud aceptada</h2>
    <p>Hola <strong>{visita.encargado}</strong>,</p>
    <p>Tu solicitud de visita grupal al {NOMBRE_MUSEO} ha sido <strong>aceptada</strong>. En breve recibirás un correo con la fecha y hora confirmadas.</p>
    <ul style="line-height:1.6;">
      <li><strong>Institución / Plantel:</strong> {visita.institucion}</li>
      <li><strong>Nivel académico:</strong> {_nivel_str(visita)}</li>
      <li><strong>Alumnos estimados:</strong> {visita.numero_alumnos}</li>
    </ul>
    <p>Gracias por tu interés en el {NOMBRE_MUSEO}.</p>
  </div>
</body></html>""")
            flash('✅ Visita aceptada y correo enviado.', 'success')
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
        enviar_correo(visita.correo, f'Solicitud de visita grupal rechazada — {NOMBRE_MUSEO}', f"""
<html><body style="font-family:Arial,sans-serif;color:#333;">
  <div style="max-width:600px;margin:auto;padding:20px;border:1px solid #eee;border-radius:10px;">
    <h2 style="color:#d9534f;">Solicitud rechazada</h2>
    <p>Hola <strong>{visita.encargado}</strong>,</p>
    <p>Lamentamos informarte que tu solicitud de visita grupal al {NOMBRE_MUSEO} ha sido <strong>rechazada</strong>.</p>
    <p>Si lo deseas, puedes presentar una nueva solicitud con otras fechas.</p>
    <p>Gracias por tu interés en el {NOMBRE_MUSEO}.</p>
  </div>
</body></html>""")
        flash('✅ Visita rechazada y correo enviado.', 'success')
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
        nombre_excel = f"Lista_estudiantes_{visita.institucion.replace(' ','_')}_{fecha.replace('/','-').replace(' ','_')}.xlsx"

        if not fecha_anterior:
            cuerpo = f"""
<html><body style="font-family:Arial,sans-serif;color:#333;">
  <div style="max-width:600px;margin:auto;padding:20px;border:1px solid #eee;border-radius:10px;">
    <h2 style="color:#4a90e2;">Confirmación de visita grupal – {NOMBRE_MUSEO}</h2>
    <p>Hola <strong>{visita.encargado}</strong>,</p>
    <p>Tu solicitud de visita grupal al {NOMBRE_MUSEO} ha sido <strong>confirmada</strong> para:</p>
    <p style="font-size:18px;font-weight:bold;margin:12px 0;">{fecha}</p>
    <ul style="line-height:1.6;">
      <li><strong>Institución / Plantel:</strong> {visita.institucion}</li>
      <li><strong>Nivel académico:</strong> {_nivel_str(visita)}</li>
      <li><strong>Alumnos estimados:</strong> {visita.numero_alumnos}</li>
    </ul>
    <p><strong>Duración estimada de la visita:</strong> 10 a 15 minutos.</p>
    <p><strong>Indicaciones durante la visita:</strong></p>
    <ul style="line-height:1.6;">
      <li>No tocar las exhibiciones.</li>
      <li>No comer ni beber dentro del museo.</li>
      <li>No hablar en voz alta.</li>
      <li>No tomar fotos ni videos.</li>
      <li>No correr ni empujar dentro del museo.</li>
      <li>No manipular etiquetas, carteles o información sobre las piezas.</li>
    </ul>
    <p>📎 Se adjunta una lista en Excel para que registres los datos de los estudiantes que asistirán. Por favor, envíala de vuelta llena antes de la visita.</p>
    <p>Le recomendamos llegar 15 minutos antes del horario programado.</p>
    <p>Gracias por tu interés en el {NOMBRE_MUSEO}.</p>
  </div>
</body></html>"""
            enviar_correo_con_excel(visita.correo, f'Confirmación de visita grupal — {NOMBRE_MUSEO}', cuerpo, nombre_excel)
            flash('📅 Fecha confirmada y correo con Excel adjunto enviado.', 'success')

        elif fecha_anterior != fecha:

    cuerpo = f"""
<html><body style="font-family:Arial,sans-serif;color:#333;">
  <div style="max-width:600px;margin:auto;padding:20px;border:1px solid #eee;border-radius:10px;">
    <h2 style="color:#4a90e2;">Visita grupal reprogramada – {NOMBRE_MUSEO}</h2>
    <p>Hola <strong>{visita.encargado}</strong>,</p>
    <p>La fecha de tu visita ha sido <strong>actualizada</strong>:</p>
    <ul style="line-height:1.6;">
      <li><strong>Fecha anterior:</strong> {fecha_anterior}</li>
      <li><strong>Nueva fecha:</strong> {fecha}</li>
    </ul>
    <p>📎 Se adjunta nuevamente la lista en Excel para registrar a los estudiantes.</p>
    <p>Le recomendamos llegar 15 minutos antes del horario programado.</p>
    <p>Gracias por tu interés en el {NOMBRE_MUSEO}.</p>
  </div>
</body></html>"""

    enviar_correo_con_excel(
        visita.correo,
        f'Visita grupal reprogramada — {NOMBRE_MUSEO}',
        cuerpo,
        nombre_excel
    )

    flash('📅 Fecha actualizada y correo de reprogramación enviado.', 'success')
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
        enviar_correo(visita.correo, f'Cancelación de visita grupal – {NOMBRE_MUSEO}', f"""
<html><body style="font-family:Arial,sans-serif;color:#333;">
  <div style="max-width:600px;margin:auto;padding:20px;border:1px solid #eee;border-radius:10px;">
    <h2 style="color:#d9534f;">Cancelación de visita grupal</h2>
    <p>Hola <strong>{visita.encargado}</strong>,</p>
    <p>Tu solicitud de visita grupal al {NOMBRE_MUSEO} ha sido <strong>cancelada</strong>.</p>
    <p>Puedes solicitar una nueva visita cuando lo desees.</p>
    <p>Gracias por tu interés en el {NOMBRE_MUSEO}.</p>
  </div>
</body></html>""")
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
                'asistio': c.asistio, 'institucion': c.institucion,
                'nivel': c.nivel_educativo, 'ciudad': c.ciudad,
                'estado_rep': c.estado_republica
            })

    if tipo == 'individual':
        historial = [h for h in historial if h['tipo'] == 'Individual']

    data = [{
        'ID': h['id'], 'Nombre': h['nombre'], 'Correo': h['correo'],
        'Teléfono': h['telefono'], 'Edad': h['edad'], 'Sexo': h['sexo'],
        'Ciudad': h.get('ciudad'), 'Estado': h.get('estado_rep'),
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
