from flask import Blueprint, render_template, redirect, url_for

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def home_redirect():
    return redirect(url_for('main.inicio'))


@main_bp.route('/inicio')
def inicio():
    return render_template('index.html')


@main_bp.route('/ir-a-visita-grupal')
def ir_a_visita_grupal():
    return redirect(url_for('visitas.solicitar_visita_grupal'))
