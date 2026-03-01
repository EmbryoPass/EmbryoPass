import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.pool import NullPool

db = SQLAlchemy()


def create_app():
    app = Flask(__name__, template_folder='../templates', static_folder='../static')

    # Configuración general
    secret_key = os.environ.get('SECRET_KEY')
    if not secret_key:
        raise RuntimeError("SECRET_KEY no está definido en las variables de entorno.")
    app.secret_key = secret_key

    # Sesión expira al cerrar el navegador; en producción las cookies son seguras
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    from datetime import timedelta
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)

    # Configuración de base de datos
    uri = os.environ.get('DATABASE_URL')
    if not uri:
        raise RuntimeError("DATABASE_URL no está definido.")

    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql+psycopg2://", 1)
    elif uri.startswith("postgresql://") and "+psycopg2" not in uri:
        uri = uri.replace("postgresql://", "postgresql+psycopg2://", 1)

    if "sslmode=" not in uri:
        uri += ("&" if "?" in uri else "?") + "sslmode=require"

    uri = uri.replace("&channel_binding=require", "").replace("?channel_binding=require", "")

    app.config['SQLALCHEMY_DATABASE_URI'] = uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "poolclass": NullPool,
        "connect_args": {
            "sslmode": "require",
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
    }

    db.init_app(app)

    # Registrar blueprints
    from app.routes.main import main_bp
    from app.routes.citas import citas_bp
    from app.routes.visitas import visitas_bp
    from app.routes.admin import admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(citas_bp)
    app.register_blueprint(visitas_bp)
    app.register_blueprint(admin_bp)

    # Inicializar tablas al arrancar
    with app.app_context():
        from app.models import Cita, Horario, VisitaGrupal, EstudianteGrupal, AdminSecret
        from app.utils import verificar_y_agregar_columnas
        db.create_all()
        verificar_y_agregar_columnas(app, db)

    return app
