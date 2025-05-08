
import sqlite3

conexion = sqlite3.connect('base_de_datos.db')
cursor = conexion.cursor()

# Crear tabla de horarios
cursor.execute('''
CREATE TABLE IF NOT EXISTS horarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora TEXT NOT NULL,
    disponibles INTEGER NOT NULL
)
''')

# Crear tabla de citas con campo 'token_cancelacion'
cursor.execute('''
CREATE TABLE IF NOT EXISTS citas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    correo TEXT NOT NULL,
    telefono TEXT NOT NULL,
    fecha_hora TEXT NOT NULL,
    estado TEXT DEFAULT 'activa',
    token_cancelacion TEXT
)
''')

conexion.commit()
conexion.close()

print("✅ Base de datos creada exitosamente.")
