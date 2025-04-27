# -*- coding: utf-8 -*-
"""
Created on Sun Apr 27 12:15:00 2025

@author: Marce
"""

from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = 'secreto123'  # Necesario para mostrar mensajes flash

# Configura tu correo
GMAIL_USER = 'museoembriologia@gmail.com'
GMAIL_PASSWORD = 'qukljqwqdnfjdzgm'

# Función para enviar correos
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

    # Obtener horarios disponibles
    cursor.execute('SELECT id, fecha_hora FROM horarios WHERE disponibles > 0')
    horarios = cursor.fetchall()
    conexion.close()

    if request.method == 'POST':
        nombre = request.form['nombre']
        correo = request.form['correo']
        telefono = request.form['telefono']
        horario_id = request.form['horario']

        # Obtener fecha y hora seleccionada
        conexion = sqlite3.connect('base_de_datos.db')
        cursor = conexion.cursor()
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

from flask import session

# Credenciales del encargado
ENCARGADO_USER = 'admin'
ENCARGADO_PASS = '1234'

# Página de login
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

# Página de Dashboard (solo accesible si inició sesión)
@app.route('/dashboard')
def dashboard():
    if 'usuario' not in session:
        flash('⚠️ Debes iniciar sesión primero.', 'warning')
        return redirect(url_for('login'))

    conexion = sqlite3.connect('base_de_datos.db')
    cursor = conexion.cursor()

    # Traer citas
    cursor.execute('SELECT id, nombre, correo, telefono, fecha_hora, estado FROM citas')
    citas = cursor.fetchall()

    # Traer horarios disponibles
    cursor.execute('SELECT id, fecha_hora, disponibles FROM horarios')
    horarios = cursor.fetchall()

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

    # Obtener correo y datos de la cita
    cursor.execute('SELECT nombre, correo, fecha_hora FROM citas WHERE id = ?', (id_cita,))
    cita = cursor.fetchone()

    if cita:
        nombre, correo, fecha_hora = cita

        # Cambiar estado a "cancelada"
        cursor.execute('UPDATE citas SET estado = "cancelada" WHERE id = ?', (id_cita,))
        conexion.commit()

        # Enviar correo de cancelación al usuario
        cuerpo = f'''
Hola {nombre},

Lamentamos informarte que tu cita al Museo de Embriología programada para:

Fecha y hora: {fecha_hora}

ha sido cancelada debido a un imprevisto.

Por favor agenda una nueva cita en nuestra página.  
Disculpa los inconvenientes.

Saludos,
Museo de Embriología
'''
        enviar_correo(correo, 'Cancelación de Cita - Museo de Embriología', cuerpo)

        flash('✅ Cita cancelada y correo enviado al usuario.', 'success')

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

    # Insertar nuevo horario en la base de datos
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

    # Eliminar horario
    cursor.execute('DELETE FROM horarios WHERE id = ?', (id_horario,))
    conexion.commit()
    conexion.close()

    flash('✅ Horario eliminado correctamente.', 'success')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
