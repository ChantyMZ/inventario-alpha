import os
import threading

import mysql.connector
from mysql.connector import Error


class DatabaseConnection:
    """Singleton de acceso a MySQL.

    La instancia es única, pero cada hilo (cada petición simultánea de otro PC)
    recibe su propia conexión: una conexión compartida entre hilos se corrompe
    cuando varias personas usan el sistema al mismo tiempo.
    """
    _instancia = None
    _config = {
        'host': os.environ.get('DB_HOST', 'localhost'),
        'user': os.environ.get('DB_USER', 'root'),
        'password': os.environ.get('DB_PASSWORD', '1234'),
        'database': os.environ.get('DB_NAME', 'repuestos_alfa'),
        'port': int(os.environ.get('DB_PORT', '3306')),
        # Cada lectura ve lo último que guardaron los demás equipos
        'autocommit': True,
        # Las fechas se guardan en UTC y la página las muestra en la hora local
        'time_zone': '+00:00',
        'connection_timeout': 10,
    }

    def __init__(self):
        self._local = threading.local()

    @classmethod
    def get_instancia(cls):
        # Singleton: solo se crea una vez
        if cls._instancia is None:
            cls._instancia = DatabaseConnection()
        return cls._instancia

    def conectar(self):
        try:
            self._local.conexion = mysql.connector.connect(**self._config)
        except Error as e:
            print(f"Error al conectar: {e}")
            self._local.conexion = None

    def get_conexion(self):
        conexion = getattr(self._local, 'conexion', None)
        if conexion is None or not conexion.is_connected():
            self.conectar()
        return self._local.conexion

    def cerrar(self):
        conexion = getattr(self._local, 'conexion', None)
        if conexion is not None and conexion.is_connected():
            conexion.close()
        self._local.conexion = None


SQL_SINCRONIZACION = """
CREATE TABLE IF NOT EXISTS sync_operaciones (
    uuid        CHAR(36) NOT NULL PRIMARY KEY,
    usuario_id  INT NOT NULL,
    tipo        VARCHAR(30) NOT NULL,
    estado      VARCHAR(20) NOT NULL,
    mensaje     VARCHAR(255) NULL,
    creado      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def asegurar_esquema():
    """Crea la tabla que evita duplicar operaciones offline si todavía no existe."""
    conexion = DatabaseConnection.get_instancia().get_conexion()
    if conexion is None:
        return False
    cursor = conexion.cursor()
    cursor.execute(SQL_SINCRONIZACION)
    cursor.close()
    return True
