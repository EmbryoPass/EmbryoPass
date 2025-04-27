# -*- coding: utf-8 -*-
"""
Created on Sun Apr 27 12:11:24 2025

@author: Marce
"""

import sqlite3

# Crear o conectar a una base de datos
conexion = sqlite3.connect('base_de_datos.db')
cursor = conexion.cursor()

# Crear tabla de citas
cursor.execute('''
CREATE TABLE IF NOT EXISTS citas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    correo TEXT NOT NULL,
    telefono TEXT NOT NULL,
    fecha_hora TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'activa'
)
''')

# Crear tabla de horarios disponibles
cursor.execute('''
CREATE TABLE IF NOT EXISTS horarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora TEXT NOT NULL,
    disponibles INTEGER NOT NULL
)
''')

conexion.commit()
conexion.close()

print("✅ Base de datos creada correctamente.")
