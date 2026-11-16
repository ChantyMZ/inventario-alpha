from mysql.connector import Error
from database import DatabaseConnection

# Campos de un repuesto tal como los llena el formulario
CAMPOS = ['codigo', 'nombre', 'descripcion', 'marca', 'compatibilidad', 'ubicacion',
          'precio_compra', 'precio_venta', 'stock', 'stock_minimo', 'categoria_id']

# El stock no se edita a mano: cambia con entradas y salidas, para que quede quién y cuándo
CAMPOS_EDITABLES = [c for c in CAMPOS if c != 'stock']

SELECT_PRODUCTOS = """
    SELECT p.id, p.codigo, p.nombre, p.descripcion, p.marca, p.compatibilidad, p.ubicacion,
           p.precio_compra, p.precio_venta, p.stock, p.stock_minimo, c.nombre AS categoria
    FROM productos p
    LEFT JOIN categorias c ON p.categoria_id = c.id
"""


class ProductoRepository:

    def __init__(self):
        self.db = DatabaseConnection.get_instancia()

    def listar(self, texto='', filtro=''):
        """Lista repuestos. El texto se busca en código, nombre, marca, vehículo y categoría;
        si trae varias palabras, el repuesto debe coincidir con todas."""
        condiciones = []
        parametros = []
        for palabra in texto.split():
            condiciones.append("""(p.codigo LIKE %s OR p.nombre LIKE %s OR p.marca LIKE %s
                                   OR p.compatibilidad LIKE %s OR c.nombre LIKE %s)""")
            parametros.extend(['%' + palabra + '%'] * 5)

        if filtro == 'reponer':
            condiciones.append("p.stock <= p.stock_minimo")
        elif filtro == 'agotado':
            condiciones.append("p.stock = 0")

        sql = SELECT_PRODUCTOS
        if condiciones:
            sql += " WHERE " + " AND ".join(condiciones)
        sql += " ORDER BY p.nombre"

        cursor = self.db.get_conexion().cursor(dictionary=True)
        cursor.execute(sql, parametros)
        productos = cursor.fetchall()
        cursor.close()
        return productos

    def resumen(self):
        cursor = self.db.get_conexion().cursor(dictionary=True)
        cursor.execute("""
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(stock <= stock_minimo), 0) AS reponer,
                   COALESCE(SUM(stock = 0), 0) AS agotados
            FROM productos
        """)
        fila = cursor.fetchone()
        cursor.close()
        return {k: int(v) for k, v in fila.items()}

    def obtener_por_id(self, producto_id):
        cursor = self.db.get_conexion().cursor(dictionary=True)
        cursor.execute("SELECT * FROM productos WHERE id = %s", (producto_id,))
        producto = cursor.fetchone()
        cursor.close()
        return producto

    def obtener_por_codigo(self, codigo):
        cursor = self.db.get_conexion().cursor(dictionary=True)
        cursor.execute("SELECT * FROM productos WHERE codigo = %s", (codigo,))
        producto = cursor.fetchone()
        cursor.close()
        return producto

    def obtener_por_nombre(self, nombre):
        cursor = self.db.get_conexion().cursor(dictionary=True)
        cursor.execute("SELECT * FROM productos WHERE nombre = %s LIMIT 1", (nombre,))
        producto = cursor.fetchone()
        cursor.close()
        return producto

    def crear(self, datos):
        conexion = self.db.get_conexion()
        cursor = conexion.cursor()
        cursor.execute(
            "INSERT INTO productos (" + ", ".join(CAMPOS) + ") VALUES (" + ", ".join(["%s"] * len(CAMPOS)) + ")",
            [datos[c] for c in CAMPOS])
        conexion.commit()
        nuevo_id = cursor.lastrowid
        cursor.close()
        return nuevo_id

    def actualizar(self, producto_id, datos):
        conexion = self.db.get_conexion()
        cursor = conexion.cursor()
        asignaciones = ", ".join(c + " = %s" for c in CAMPOS_EDITABLES)
        cursor.execute("UPDATE productos SET " + asignaciones + " WHERE id = %s",
                       [datos[c] for c in CAMPOS_EDITABLES] + [producto_id])
        conexion.commit()
        cursor.close()

    def actualizar_stock(self, producto_id, nuevo_stock):
        conexion = self.db.get_conexion()
        cursor = conexion.cursor()
        cursor.execute("UPDATE productos SET stock = %s WHERE id = %s", (nuevo_stock, producto_id))
        conexion.commit()
        cursor.close()

    def eliminar(self, producto_id):
        """Devuelve False si no se pudo, por ejemplo porque ya tiene movimientos."""
        conexion = self.db.get_conexion()
        cursor = conexion.cursor()
        try:
            cursor.execute("DELETE FROM productos WHERE id = %s", (producto_id,))
            conexion.commit()
            return True
        except Error:
            conexion.rollback()
            return False
        finally:
            cursor.close()


class CategoriaRepository:

    def __init__(self):
        self.db = DatabaseConnection.get_instancia()

    def obtener_todas(self):
        cursor = self.db.get_conexion().cursor(dictionary=True)
        cursor.execute("SELECT id, nombre FROM categorias ORDER BY nombre")
        categorias = cursor.fetchall()
        cursor.close()
        return categorias

    def obtener_o_crear(self, nombre):
        """Devuelve el id de la categoría; si no existe, la crea (lo usa la importación)."""
        conexion = self.db.get_conexion()
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT id FROM categorias WHERE nombre = %s", (nombre,))
        fila = cursor.fetchone()
        if fila:
            cursor.close()
            return fila['id']
        cursor.execute("INSERT INTO categorias (nombre) VALUES (%s)", (nombre,))
        conexion.commit()
        nuevo_id = cursor.lastrowid
        cursor.close()
        return nuevo_id


class UsuarioRepository:

    def __init__(self):
        self.db = DatabaseConnection.get_instancia()

    def obtener_por_email(self, email):
        cursor = self.db.get_conexion().cursor(dictionary=True)
        cursor.execute("SELECT * FROM usuarios WHERE email = %s", (email,))
        usuario = cursor.fetchone()
        cursor.close()
        return usuario

    def obtener_por_id(self, usuario_id):
        cursor = self.db.get_conexion().cursor(dictionary=True)
        cursor.execute("SELECT * FROM usuarios WHERE id = %s", (usuario_id,))
        usuario = cursor.fetchone()
        cursor.close()
        return usuario

    def crear(self, nombre, email, password, rol='empleado'):
        conexion = self.db.get_conexion()
        cursor = conexion.cursor()
        cursor.execute("""
            INSERT INTO usuarios (nombre, email, password, rol)
            VALUES (%s, %s, %s, %s)
        """, (nombre, email, password, rol))
        conexion.commit()
        nuevo_id = cursor.lastrowid
        cursor.close()
        return nuevo_id

    def email_existe(self, email):
        cursor = self.db.get_conexion().cursor(dictionary=True)
        cursor.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
        resultado = cursor.fetchone()
        cursor.close()
        return resultado is not None

    def contar(self):
        cursor = self.db.get_conexion().cursor()
        cursor.execute("SELECT COUNT(*) FROM usuarios")
        total = cursor.fetchone()[0]
        cursor.close()
        return total


class MovimientoRepository:

    def __init__(self):
        self.db = DatabaseConnection.get_instancia()

    def registrar(self, producto_id, usuario_id, tipo, cantidad, motivo, fecha=None):
        conexion = self.db.get_conexion()
        cursor = conexion.cursor()
        if fecha is None:
            cursor.execute("""
                INSERT INTO movimientos (producto_id, usuario_id, tipo, cantidad, motivo)
                VALUES (%s, %s, %s, %s, %s)
            """, (producto_id, usuario_id, tipo, cantidad, motivo))
        else:
            cursor.execute("""
                INSERT INTO movimientos (producto_id, usuario_id, tipo, cantidad, motivo, fecha)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (producto_id, usuario_id, tipo, cantidad, motivo, fecha))
        conexion.commit()
        cursor.close()

    def aplicar(self, producto_id, usuario_id, tipo, cantidad, motivo, fecha=None):
        """Cambia el stock y guarda el movimiento en una sola transacción.

        La resta solo se hace si alcanza (WHERE stock >= cantidad), así dos equipos
        que venden lo mismo a la vez no dejan el stock en negativo.
        Devuelve el stock nuevo, o None si no había suficientes unidades.
        """
        conexion = self.db.get_conexion()
        cursor = conexion.cursor()
        try:
            conexion.start_transaction()
            if tipo == 'entrada':
                cursor.execute("UPDATE productos SET stock = stock + %s WHERE id = %s",
                               (cantidad, producto_id))
            else:
                cursor.execute("UPDATE productos SET stock = stock - %s WHERE id = %s AND stock >= %s",
                               (cantidad, producto_id, cantidad))
            if cursor.rowcount == 0:
                conexion.rollback()
                return None

            if fecha is None:
                cursor.execute("""
                    INSERT INTO movimientos (producto_id, usuario_id, tipo, cantidad, motivo)
                    VALUES (%s, %s, %s, %s, %s)
                """, (producto_id, usuario_id, tipo, cantidad, motivo))
            else:
                cursor.execute("""
                    INSERT INTO movimientos (producto_id, usuario_id, tipo, cantidad, motivo, fecha)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (producto_id, usuario_id, tipo, cantidad, motivo, fecha))

            cursor.execute("SELECT stock FROM productos WHERE id = %s", (producto_id,))
            nuevo_stock = cursor.fetchone()[0]
            conexion.commit()
            return nuevo_stock
        except Exception:
            conexion.rollback()
            raise
        finally:
            cursor.close()

    def obtener_todos(self, limite=300):
        cursor = self.db.get_conexion().cursor(dictionary=True)
        cursor.execute("""
            SELECT m.id, p.codigo, p.nombre AS producto, u.nombre AS usuario,
                   m.tipo, m.cantidad, m.motivo, m.fecha
            FROM movimientos m
            JOIN productos p ON m.producto_id = p.id
            JOIN usuarios u ON m.usuario_id = u.id
            ORDER BY m.fecha DESC, m.id DESC
            LIMIT %s
        """, (limite,))
        movimientos = cursor.fetchall()
        cursor.close()
        return movimientos

    def reporte_productos_mas_vendidos(self):
        cursor = self.db.get_conexion().cursor(dictionary=True)
        cursor.execute("""
            SELECT p.nombre AS producto, p.codigo, SUM(m.cantidad) AS total_vendido
            FROM movimientos m
            JOIN productos p ON m.producto_id = p.id
            WHERE m.tipo = 'salida'
            GROUP BY m.producto_id, p.nombre, p.codigo
            ORDER BY total_vendido DESC
            LIMIT 15
        """)
        resultado = cursor.fetchall()
        cursor.close()
        return resultado

    def reporte_entradas_salidas(self):
        cursor = self.db.get_conexion().cursor(dictionary=True)
        cursor.execute("""
            SELECT p.nombre AS producto, p.codigo,
                   SUM(CASE WHEN m.tipo = 'entrada' THEN m.cantidad ELSE 0 END) AS total_entradas,
                   SUM(CASE WHEN m.tipo = 'salida' THEN m.cantidad ELSE 0 END) AS total_salidas
            FROM movimientos m
            JOIN productos p ON m.producto_id = p.id
            GROUP BY m.producto_id, p.nombre, p.codigo
            ORDER BY p.nombre
        """)
        resultado = cursor.fetchall()
        cursor.close()
        return resultado


class SincronizacionRepository:
    """Lleva la cuenta de las operaciones hechas sin internet que ya se subieron,
    para que reenviarlas (por un corte a mitad de camino) nunca las duplique."""

    def __init__(self):
        self.db = DatabaseConnection.get_instancia()

    def reclamar(self, uuid, usuario_id, tipo):
        """Intenta apartar la operación. Devuelve None si es nueva (ya es nuestra)
        o la fila existente si otro envío ya la había tomado."""
        conexion = self.db.get_conexion()
        cursor = conexion.cursor(dictionary=True)
        try:
            cursor.execute("""
                INSERT INTO sync_operaciones (uuid, usuario_id, tipo, estado)
                VALUES (%s, %s, %s, 'procesando')
            """, (uuid, usuario_id, tipo))
            return None
        except Error:
            cursor.execute("SELECT estado, mensaje FROM sync_operaciones WHERE uuid = %s", (uuid,))
            return cursor.fetchone()
        finally:
            cursor.close()

    def terminar(self, uuid, estado, mensaje=None):
        conexion = self.db.get_conexion()
        cursor = conexion.cursor()
        cursor.execute("UPDATE sync_operaciones SET estado = %s, mensaje = %s WHERE uuid = %s",
                       (estado, (mensaje or '')[:255] or None, uuid))
        cursor.close()

    def liberar(self, uuid):
        """Si algo falló del lado del servidor, se libera para poder reintentar."""
        conexion = self.db.get_conexion()
        cursor = conexion.cursor()
        cursor.execute("DELETE FROM sync_operaciones WHERE uuid = %s AND estado = 'procesando'", (uuid,))
        cursor.close()
