from datetime import datetime
from app import db


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
    ciudad = db.Column(db.String(100), nullable=True)
    estado_republica = db.Column(db.String(100), nullable=True)


class VisitaGrupal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    encargado = db.Column(db.String(100), nullable=False)
    correo = db.Column(db.String(120), nullable=False)
    telefono = db.Column(db.String(20), nullable=False)
    institucion = db.Column(db.String(100), nullable=False)
    nivel = db.Column(db.String(50), nullable=False)
    bachillerato = db.Column(db.String(150), nullable=True)
    numero_alumnos = db.Column(db.Integer, nullable=False)
    fechas_preferidas = db.Column(db.Text, nullable=False)
    comentarios = db.Column(db.Text)
    estado = db.Column(db.String(20), default='pendiente')
    fecha_confirmada = db.Column(db.String(100), nullable=True)
    ciudad = db.Column(db.String(100), nullable=True)
    estado_republica = db.Column(db.String(100), nullable=True)


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


class AdminSecret(db.Model):
    __tablename__ = 'admin_secret'
    id = db.Column(db.Integer, primary_key=True)
    password = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
