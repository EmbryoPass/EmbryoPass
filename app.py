from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime


app = Flask(__name__)
app.secret_key = 'secreto123'

GMAIL_USER = 'museoembriologia@gmail.com'
GMAIL_PASSWORD = 'qukljqwqdnfjdzgm'

def enviar_correo(destinatario, asunto, cuerpo):
    mensaje = MIMEMultipart()
    mensaje['From'] = GMAIL_USER
    mensaje['To'] = destinatario
    mensaje['Subject'] = asunto
    mensaje.attach(MIMEText(cuerpo, 'plain'))

    servidor = smtplib.SMTP('smtp.gmail.com', 587)
    servidor.starttls()
    servidor.login(GMAIL_USER, GMAIL_PASSWORD)
    texto = mensaje.as_string()
    servidor.sendmail(GMAIL_USER, destinatario, texto)
    servidor.quit()

# Página principal para agendar citas
@app.route('/', methods=['GET', 'POST'])
def agendar():
    conexion = sqlite3.connect('base_de_datos.db')
    cursor = conexion.cursor()
    cursor.execute('SELECT id, fecha_hora, disponibles FROM horarios WHERE disponibles > 0')
    horarios_crudos = cursor.fetchall()
    horarios = []

    for id, fecha_hora, disponibles in horarios_crudos:
        try:
            fecha_objeto = datetime.strptime(fecha_hora, "%d/%m/%Y %I:%M %p")
        except ValueError:
            fecha_objeto = datetime.strptime(fecha_hora, "%Y-%m-%d %H:%M")
        fecha_formateada = fecha_objeto.strftime("%d/%m/%Y %I:%M %p")
        horarios.append((id, fecha_formateada))

    conexion.close()

    if request.method == 'POST':
        nombre = request.form['nombre']
        correo = request.form['correo']
        telefono = request.form['telefono']
        horario_id = request.form['horario']

        # Verificar si ya existe una cita con los mismos datos
        conexion = sqlite3.connect('base_de_datos.db')
        cursor = conexion.cursor()
        cursor.execute('''
            SELECT * FROM citas WHERE correo = ? AND fecha_hora = ?
        ''', (correo, horario_id))
        cita_existente = cursor.fetchone()

        if cita_existente:
            flash('❌ Ya tienes una cita agendada para este horario.', 'danger')
            return redirect(url_for('agendar'))

        # Obtener fecha y hora seleccionada
        cursor.execute('SELECT fecha_hora FROM horarios WHERE id = ?', (horario_id,))
        fecha_hora = cursor.fetchone()[0]

        # Insertar nueva cita
        cursor.execute('''
            INSERT INTO citas (nombre, correo, telefono, fecha_hora)
            VALUES (?, ?, ?, ?)
        ''', (nombre, correo, telefono, fecha_hora))

        # Actualizar disponibilidad
        cursor.execute('''
            UPDATE horarios SET disponibles = disponibles - 1 WHERE id = ?
        ''', (horario_id,))

        conexion.commit()
        conexion.close()

        # Enviar correo de confirmación
        cuerpo = f'''
        Hola {nombre},

        Tu cita al Museo de Embriología ha sido agendada exitosamente.

        Datos de tu cita:
        - Nombre: {nombre}
        - Correo: {correo}
        - Teléfono: {telefono}
        - Fecha y hora: {fecha_hora}

        Gracias por visitarnos.
        '''
        enviar_correo(correo, 'Confirmación de Cita - Museo de Embriología', cuerpo)

        # También enviar notificación al museo
        cuerpo_museo = f'''
        Se ha agendado una nueva cita:

        - Nombre: {nombre}
        - Correo: {correo}
        - Teléfono: {telefono}
        - Fecha y hora: {fecha_hora}

        Por favor verificar el registro en el sistema.
        '''
        enviar_correo('museoembriologia@gmail.com', 'Nueva Cita Agendada - Museo de Embriología', cuerpo_museo)

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
        else:
            flash('❌ Usuario o contraseña incorrectos.', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'usuario' not in session:
        flash('⚠️ Debes iniciar sesión primero.', 'warning')
        return redirect(url_for('login'))

    conexion = sqlite3.connect('base_de_datos.db')
    cursor = conexion.cursor()

    cursor.execute('SELECT id, nombre, correo, telefono, fecha_hora, estado FROM citas')
    citas = cursor.fetchall()

    cursor.execute('SELECT id, fecha_hora, disponibles FROM horarios')
    horarios_crudos = cursor.fetchall()

    horarios = []
    for id, fecha_hora, disponibles in horarios_crudos:
        try:
            fecha_objeto = datetime.strptime(fecha_hora, "%d/%m/%Y %I:%M %p")
        except ValueError:
            fecha_objeto = datetime.strptime(fecha_hora, "%Y-%m-%d %H:%M")
        fecha_formateada = fecha_objeto.strftime("%d/%m/%Y %I:%M %p")
        horarios.append((id, fecha_formateada, disponibles))

    conexion.close()

    return render_template('dashboard.html', citas=citas, horarios=horarios)

@app.route('/logout')
def logout():
    session.pop('usuario', None)
    flash('✅ Sesión cerrada correctamente.', 'success')
    return redirect(url_for('login'))

@app.route('/cancelar_cita/<int:id_cita>')
def cancelar_cita(id_cita):
    if 'usuario' not in session:
        flash('⚠️ Debes iniciar sesión primero.', 'warning')
        return redirect(url_for('login'))

    conexion = sqlite3.connect('base_de_datos.db')
    cursor = conexion.cursor()

    # Obtener correo, nombre, fecha y hora de la cita
    cursor.execute('SELECT nombre, correo, fecha_hora FROM citas WHERE id = ?', (id_cita,))
    cita = cursor.fetchone()

    if cita:
        nombre, correo, fecha_hora = cita

        # Cambiar el estado a cancelada
        cursor.execute('UPDATE citas SET estado = "cancelada" WHERE id = ?', (id_cita,))

        # Buscar el horario correspondiente y aumentar disponibles en +1
        cursor.execute('UPDATE horarios SET disponibles = disponibles + 1 WHERE fecha_hora = ?', (fecha_hora,))

        conexion.commit()

        # Enviar correo de cancelación
        cuerpo = f'''
Hola {nombre},

Lamentamos informarte que tu cita al Museo de Embriología programada para el {fecha_hora} ha sido cancelada debido a un imprevisto.

Por favor agenda una nueva cita en nuestra página.  
Nos disculpamos por los inconvenientes.

Saludos,
Museo de Embriología Dra. Dora Virginia Chávez Corral
'''
        enviar_correo(correo, 'Cancelación de Cita - Museo de Embriología', cuerpo)

        flash('✅ Cita cancelada, correo enviado y espacio liberado.', 'success')

    conexion.close()
    return redirect(url_for('dashboard'))

@app.route('/agregar_horario', methods=['POST'])
def agregar_horario():
    if 'usuario' not in session:
        flash('⚠️ Debes iniciar sesión primero.', 'warning')
        return redirect(url_for('login'))

    fecha_hora = request.form['fecha_hora']
    disponibles = request.form['disponibles']

    conexion = sqlite3.connect('base_de_datos.db')
    cursor = conexion.cursor()
    cursor.execute('INSERT INTO horarios (fecha_hora, disponibles) VALUES (?, ?)', (fecha_hora, disponibles))
    conexion.commit()
    conexion.close()

    flash('✅ Nuevo horario agregado correctamente.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/eliminar_horario/<int:id_horario>')
def eliminar_horario(id_horario):
    if 'usuario' not in session:
        flash('⚠️ Debes iniciar sesión primero.', 'warning')
        return redirect(url_for('login'))

    conexion = sqlite3.connect('base_de_datos.db')
    cursor = conexion.cursor()

    # 1. Obtener fecha_hora del horario que queremos eliminar
    cursor.execute('SELECT fecha_hora FROM horarios WHERE id = ?', (id_horario,))
    resultado = cursor.fetchone()

    if resultado:
        fecha_hora = resultado[0]

        # 2. Buscar citas activas asociadas a esa fecha
        cursor.execute('SELECT id, nombre, correo FROM citas WHERE fecha_hora = ? AND estado = "activa"', (fecha_hora,))
        citas_afectadas = cursor.fetchall()

        for cita_id, nombre, correo in citas_afectadas:
            # 3. Cancelar la cita en la base de datos
            cursor.execute('UPDATE citas SET estado = "cancelada" WHERE id = ?', (cita_id,))

            # 4. Enviar correo de cancelación
            cuerpo = f'''
Hola {nombre},

Lamentamos informarte que tu cita programada para el {fecha_hora} ha sido cancelada debido a cambios en la disponibilidad del Museo de Embriología.

Te invitamos a agendar una nueva cita desde nuestro sitio web.
Nos disculpamos por las molestias

Museo de Embriología
'''
            enviar_correo(correo, 'Cancelación de Cita - Museo de Embriología', cuerpo)

        # 5. Eliminar el horario después de cancelar citas
        cursor.execute('DELETE FROM horarios WHERE id = ?', (id_horario,))

        conexion.commit()
        flash('✅ Horario eliminado y citas canceladas correctamente.', 'success')
    else:
        flash('❌ No se encontró el horario.', 'danger')

    conexion.close()
    return redirect(url_for('dashboard'))


@app.route('/eliminar_cita/<int:id_cita>')
def eliminar_cita(id_cita):
    if 'usuario' not in session:
        flash('⚠️ Debes iniciar sesión primero.', 'warning')
        return redirect(url_for('login'))

    conexion = sqlite3.connect('base_de_datos.db')
    cursor = conexion.cursor()

    cursor.execute('DELETE FROM citas WHERE id = ?', (id_cita,))
    conexion.commit()
    conexion.close()

    flash('✅ Cita eliminada correctamente.', 'success')
    return redirect(url_for('dashboard'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
