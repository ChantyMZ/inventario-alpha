import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from flask import (Flask, render_template, request, redirect, url_for, flash, session,
                   jsonify, send_from_directory)
from repositories import (ProductoRepository, CategoriaRepository, UsuarioRepository,
                          MovimientoRepository, SincronizacionRepository)
from observers import Inventario, AlertaStockObserver
from importador import importar_inventario
from database import asegurar_esquema
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from authlib.integrations.flask_client import OAuth

try:  # Permite guardar la configuración en un archivo .env (opcional)
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def obtener_secret_key():
    """La clave que firma las sesiones. Sale de SECRET_KEY; si no existe, se crea una
    sola vez y se guarda en .secret_key para que todos los procesos usen la misma."""
    clave = os.environ.get('SECRET_KEY')
    if clave:
        return clave
    ruta = os.path.join(BASE_DIR, '.secret_key')
    if not os.path.exists(ruta):
        try:
            fd = os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'w') as f:
                f.write(secrets.token_hex(32))
        except FileExistsError:
            pass
    with open(ruta) as f:
        return f.read().strip()


def activo(nombre):
    return os.environ.get(nombre, '').strip().lower() in ('1', 'true', 'si', 'yes')


app = Flask(__name__)
app.secret_key = obtener_secret_key()
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
# La sesión dura 30 días: así el equipo sigue con la sesión abierta aunque se quede sin internet
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = activo('COOKIE_SECURE')

if activo('BEHIND_PROXY'):
    # Detrás de un proxy HTTPS (Render, Railway, Caddy, Nginx...) para que los enlaces salgan con https
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Hora local que se muestra en pantalla (en la base todo se guarda en UTC)
try:
    ZONA = ZoneInfo(os.environ.get('APP_TZ', 'America/Bogota'))
except Exception:
    ZONA = timezone(timedelta(hours=-5))

app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID', '')
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET', '')
GOOGLE_HABILITADO = bool(app.config['GOOGLE_CLIENT_ID'] and app.config['GOOGLE_CLIENT_SECRET'])

oauth = OAuth(app)
google = None
if GOOGLE_HABILITADO:
    google = oauth.register(
        name='google',
        client_id=app.config['GOOGLE_CLIENT_ID'],
        client_secret=app.config['GOOGLE_CLIENT_SECRET'],
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )


@app.context_processor
def variables_globales():
    return {'google_habilitado': GOOGLE_HABILITADO}


producto_repo = ProductoRepository()
categoria_repo = CategoriaRepository()
usuario_repo = UsuarioRepository()
movimiento_repo = MovimientoRepository()
sync_repo = SincronizacionRepository()

try:
    asegurar_esquema()
except Exception as e:  # la app abre igual; la tabla se creará en la próxima conexión
    print(f"No se pudo preparar la base: {e}")


def login_requerido():
    return 'usuario_id' not in session


def es_admin():
    return session.get('usuario_rol') == 'admin'


# ---- AYUDAS PARA LAS PLANTILLAS ----

@app.template_filter('cop')
def formato_cop(valor):
    try:
        return '$' + '{:,.0f}'.format(float(valor)).replace(',', '.')
    except (TypeError, ValueError):
        return '-'


@app.template_filter('fecha')
def formato_fecha(valor):
    if not valor:
        return '-'
    if valor.tzinfo is None:  # la base entrega la fecha en UTC
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(ZONA).strftime('%d/%m/%Y %H:%M')


def estado_stock(producto):
    if producto['stock'] == 0:
        return 'agotado'
    if producto['stock'] <= producto['stock_minimo']:
        return 'reponer'
    return 'ok'


def nivel_stock(producto):
    """Porcentaje para la barra: el mínimo queda a un tercio del recorrido."""
    minimo = producto['stock_minimo']
    if minimo <= 0:
        return 100 if producto['stock'] > 0 else 0
    return min(100, round(producto['stock'] / (minimo * 3) * 100))


app.jinja_env.globals['estado_stock'] = estado_stock
app.jinja_env.globals['nivel_stock'] = nivel_stock


def alertas_stock(producto):
    """Patrón Observer: el inventario notifica y el observador decide si hay que avisar."""
    inventario = Inventario()
    alerta_stock = AlertaStockObserver()
    inventario.agregar_observer(alerta_stock)
    inventario.notificar_observers(producto)
    return alerta_stock.get_alertas()


def avisar_stock(producto):
    for alerta in alertas_stock(producto):
        flash(alerta, 'alerta')


# ---- AUTENTICACION ----

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        usuario = usuario_repo.obtener_por_email(email)

        if usuario is None:
            flash('El correo no esta registrado', 'error')
            return render_template('login.html')

        if not check_password_hash(usuario['password'], password):
            flash('Contrasena incorrecta', 'error')
            return render_template('login.html')

        session.permanent = True
        session['usuario_id'] = usuario['id']
        session['usuario_nombre'] = usuario['nombre']
        session['usuario_rol'] = usuario['rol']

        flash(f'Bienvenido, {usuario["nombre"]}', 'exito')
        return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form['nombre']
        email = request.form['email']
        password = request.form['password']
        confirmar = request.form['confirmar']

        if nombre == '' or email == '' or password == '':
            flash('Todos los campos son obligatorios', 'aviso')
            return render_template('registro.html')

        if len(password) < 6:
            flash('La contraseña debe tener al menos 6 caracteres.', 'aviso')
            return render_template('registro.html')

        if password != confirmar:
            flash('Las contrasenas no coinciden', 'aviso')
            return render_template('registro.html')

        if usuario_repo.email_existe(email):
            flash('El correo ya esta registrado', 'aviso')
            return render_template('registro.html')

        password_hash = generate_password_hash(password)
        rol = 'admin' if usuario_repo.contar() == 0 else 'empleado'
        usuario_repo.crear(nombre, email, password_hash, rol)

        flash('Cuenta creada exitosamente. Inicia sesion.', 'exito')
        return redirect(url_for('login'))

    return render_template('registro.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Sesion cerrada', 'info')
    return redirect(url_for('login'))


@app.route('/login/google')
def login_google():
    if google is None:
        flash('El acceso con Google no está configurado.', 'aviso')
        return redirect(url_for('login'))
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route('/login/google/callback')
def google_callback():
    if google is None:
        return redirect(url_for('login'))
    token = google.authorize_access_token()
    info = token.get('userinfo')

    if info is None or not info.get('email') or info.get('email_verified') is False:
        flash('No se pudo obtener informacion de Google', 'error')
        return redirect(url_for('login'))

    email = info['email']
    nombre = info.get('name') or email
    usuario = usuario_repo.obtener_por_email(email)

    if usuario is None:
        # Contraseña aleatoria: la cuenta de Google entra solo por Google
        password_hash = generate_password_hash(secrets.token_urlsafe(32))
        usuario_repo.crear(nombre, email, password_hash, 'empleado')
        usuario = usuario_repo.obtener_por_email(email)

    session.permanent = True
    session['usuario_id'] = usuario['id']
    session['usuario_nombre'] = usuario['nombre']
    session['usuario_rol'] = usuario['rol']

    flash(f'Bienvenido, {nombre}', 'exito')
    return redirect(url_for('index'))


# ---- INVENTARIO ----

def leer_formulario():
    return normalizar_datos(request.form)


def normalizar_datos(f):
    """Limpia los datos de un repuesto, vengan del formulario o de la cola offline."""
    def texto(campo):
        valor = f.get(campo, '')
        return '' if valor is None else str(valor)

    def opcional(campo):
        return texto(campo).strip() or None

    return {
        'codigo': opcional('codigo'),
        'nombre': texto('nombre').strip(),
        'descripcion': opcional('descripcion'),
        'marca': opcional('marca'),
        'compatibilidad': opcional('compatibilidad'),
        'ubicacion': opcional('ubicacion'),
        'precio_compra': texto('precio_compra').strip(),
        'precio_venta': texto('precio_venta').strip(),
        'stock': texto('stock').strip(),
        'stock_minimo': texto('stock_minimo').strip() or '0',
        'categoria_id': f.get('categoria_id') or None,
    }


def numero_valido(valor, entero=False):
    try:
        n = int(valor) if entero else float(valor)
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def validar(datos, producto_id=None, pedir_stock=True):
    errores = {}
    if not datos['nombre']:
        errores['nombre'] = 'Escribe el nombre del repuesto.'

    compra = numero_valido(datos['precio_compra'])
    venta = numero_valido(datos['precio_venta'])
    if compra is None:
        errores['precio_compra'] = 'Escribe un precio de compra de 0 o más.'
    if venta is None:
        errores['precio_venta'] = 'Escribe un precio de venta de 0 o más.'
    if compra is not None and venta is not None and venta < compra:
        errores['precio_venta'] = 'El precio de venta no puede ser menor al de compra.'

    if pedir_stock and numero_valido(datos['stock'], entero=True) is None:
        errores['stock'] = 'Escribe las unidades que hay, con un número entero de 0 o más.'
    if numero_valido(datos['stock_minimo'], entero=True) is None:
        errores['stock_minimo'] = 'Escribe un mínimo entero de 0 o más.'

    if datos['codigo']:
        existente = producto_repo.obtener_por_codigo(datos['codigo'])
        if existente and existente['id'] != producto_id:
            errores['codigo'] = 'Ya hay un repuesto con este código.'
    return errores


@app.route('/')
def index():
    if login_requerido():
        return redirect(url_for('login'))

    texto = request.args.get('q', '').strip()
    filtro = request.args.get('filtro', '')
    if filtro not in ('reponer', 'agotado'):
        filtro = ''

    productos = producto_repo.listar(texto, filtro)
    resumen = producto_repo.resumen()
    return render_template('index.html', productos=productos, resumen=resumen,
                           texto=texto, filtro=filtro)


@app.route('/agregar', methods=['GET', 'POST'])
def agregar_producto():
    if login_requerido():
        return redirect(url_for('login'))

    categorias = categoria_repo.obtener_todas()
    if request.method == 'POST':
        datos = leer_formulario()
        errores = validar(datos)
        if errores:
            return render_template('agregar_producto.html', categorias=categorias,
                                   datos=datos, errores=errores)

        nuevo_id = producto_repo.crear(datos)
        if int(datos['stock']) > 0:
            movimiento_repo.registrar(nuevo_id, session['usuario_id'], 'entrada',
                                      int(datos['stock']), 'Stock inicial')

        avisar_stock(producto_repo.obtener_por_id(nuevo_id))
        flash(f'Se agregó {datos["nombre"]}.', 'exito')
        return redirect(url_for('index'))

    return render_template('agregar_producto.html', categorias=categorias,
                           datos={'stock_minimo': 5}, errores={})


@app.route('/editar/<int:producto_id>', methods=['GET', 'POST'])
def editar_producto(producto_id):
    if login_requerido():
        return redirect(url_for('login'))

    producto = producto_repo.obtener_por_id(producto_id)
    categorias = categoria_repo.obtener_todas()

    if producto is None:
        flash('Ese repuesto no existe.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        datos = leer_formulario()
        datos['stock'] = producto['stock']
        errores = validar(datos, producto_id, pedir_stock=False)
        if errores:
            return render_template('editar_producto.html', producto=producto, categorias=categorias,
                                   datos=datos, errores=errores)

        producto_repo.actualizar(producto_id, datos)
        avisar_stock(producto_repo.obtener_por_id(producto_id))
        flash('Cambios guardados.', 'exito')
        return redirect(url_for('index'))

    return render_template('editar_producto.html', producto=producto, categorias=categorias,
                           datos=producto, errores={})


@app.route('/eliminar/<int:producto_id>', methods=['POST'])
def eliminar_producto(producto_id):
    if login_requerido():
        return redirect(url_for('login'))
    if not es_admin():
        flash('Solo el administrador puede eliminar repuestos.', 'aviso')
        return redirect(url_for('index'))

    if producto_repo.eliminar(producto_id):
        flash('Repuesto eliminado.', 'info')
    else:
        flash('No se pudo eliminar porque ya tiene movimientos registrados. '
              'Si ya no lo vendes, déjalo con stock 0.', 'aviso')
    return redirect(url_for('index'))


# ---- MOVIMIENTOS ----

@app.route('/movimiento/<int:producto_id>', methods=['GET', 'POST'])
def registrar_movimiento(producto_id):
    if login_requerido():
        return redirect(url_for('login'))

    producto = producto_repo.obtener_por_id(producto_id)

    if producto is None:
        flash('Ese repuesto no existe.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        tipo = request.form.get('tipo', '')
        motivo = request.form.get('motivo', '').strip()
        stock_actual = producto['stock']

        try:
            cantidad = int(request.form.get('cantidad', ''))
        except ValueError:
            cantidad = 0

        if tipo not in ('entrada', 'salida') or cantidad <= 0:
            flash('Elige entrada o salida y escribe una cantidad mayor a 0.', 'error')
            return render_template('movimiento.html', producto=producto)

        if tipo == 'salida' and cantidad > stock_actual:
            flash(f'No alcanza: hay {stock_actual} unidades y quieres sacar {cantidad}.', 'error')
            return render_template('movimiento.html', producto=producto)

        # Una sola transacción: si otro equipo vendió lo mismo a la vez, no se pasa de lo que hay
        nuevo_stock = movimiento_repo.aplicar(producto_id, session['usuario_id'], tipo, cantidad, motivo)
        if nuevo_stock is None:
            actual = producto_repo.obtener_por_id(producto_id)['stock']
            flash(f'No alcanza: ahora hay {actual} unidades y quieres sacar {cantidad}.', 'error')
            return render_template('movimiento.html', producto=producto_repo.obtener_por_id(producto_id))

        avisar_stock(producto_repo.obtener_por_id(producto_id))
        flash(f'{"Entrada" if tipo == "entrada" else "Salida"} registrada. Ahora hay {nuevo_stock} unidades.', 'exito')
        return redirect(url_for('index'))

    return render_template('movimiento.html', producto=producto)


@app.route('/movimientos')
def ver_movimientos():
    if login_requerido():
        return redirect(url_for('login'))

    movimientos = movimiento_repo.obtener_todos()
    return render_template('movimientos.html', movimientos=movimientos)


# ---- REPORTES ----

@app.route('/reportes')
def reportes():
    if login_requerido():
        return redirect(url_for('login'))

    mas_vendidos = movimiento_repo.reporte_productos_mas_vendidos()
    entradas_salidas = movimiento_repo.reporte_entradas_salidas()
    stock_bajo = producto_repo.listar('', 'reponer')

    return render_template('reportes.html',
                           mas_vendidos=mas_vendidos,
                           entradas_salidas=entradas_salidas,
                           stock_bajo=stock_bajo)


# ---- IMPORTAR DESDE EXCEL ----

@app.route('/importar', methods=['GET', 'POST'])
def importar():
    if login_requerido():
        return redirect(url_for('login'))
    if not es_admin():
        flash('Solo el administrador puede importar el inventario.', 'aviso')
        return redirect(url_for('index'))

    resultado = None
    if request.method == 'POST':
        archivo = request.files.get('archivo')
        if archivo is None or archivo.filename == '':
            flash('Elige el archivo de Excel que quieres importar.', 'aviso')
        elif not archivo.filename.lower().endswith('.xlsx'):
            flash('El archivo tiene que ser de Excel (.xlsx).', 'aviso')
        else:
            try:
                resultado = importar_inventario(archivo.stream, producto_repo, categoria_repo,
                                                movimiento_repo, session['usuario_id'])
            except ValueError as e:
                flash(str(e), 'error')
            except Exception:
                flash('No pude leer el archivo. Revisa que sea un Excel válido.', 'error')

    return render_template('importar.html', resultado=resultado)


# ---- SINCRONIZACIÓN (trabajo sin internet) ----
# El navegador guarda en el equipo lo que se registra sin conexión y lo manda aquí
# cuando vuelve el internet. Cada operación trae un identificador único (uuid): si el
# envío se corta y se repite, el servidor reconoce la operación y no la duplica.

UUID_RE = re.compile(r'^[0-9a-fA-F-]{36}$')


def fecha_de_operacion(milisegundos):
    """Fecha real en que se hizo la operación (UTC, sin zona), con límites razonables."""
    ahora = datetime.now(timezone.utc)
    try:
        fecha = datetime.fromtimestamp(float(milisegundos) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    if fecha > ahora:
        fecha = ahora
    if fecha < ahora - timedelta(days=365):
        return None
    return fecha.replace(tzinfo=None)


def resumen_errores(errores):
    return ' '.join(errores.values())


def aplicar_operacion(tipo, datos, usuario_id, fecha):
    """Ejecuta una operación. Devuelve (estado, mensaje, alertas, errores)."""
    if tipo == 'movimiento':
        mov = str(datos.get('tipo', ''))
        motivo = str(datos.get('motivo', '') or '').strip()[:200]
        try:
            cantidad = int(datos.get('cantidad'))
            producto_id = int(datos.get('producto_id'))
        except (TypeError, ValueError):
            return 'rechazada', 'La cantidad o el repuesto no son válidos.', [], {}
        if mov not in ('entrada', 'salida') or cantidad <= 0:
            return 'rechazada', 'Hay que elegir entrada o salida y una cantidad mayor a 0.', [], {}

        producto = producto_repo.obtener_por_id(producto_id)
        if producto is None:
            return 'rechazada', 'Ese repuesto ya no existe.', [], {}

        nuevo_stock = movimiento_repo.aplicar(producto_id, usuario_id, mov, cantidad, motivo, fecha)
        if nuevo_stock is None:
            hay = producto_repo.obtener_por_id(producto_id)['stock']
            return ('rechazada',
                    f'No alcanzó: de {producto["nombre"]} hay {hay} unidades y se querían sacar {cantidad}.',
                    [], {})
        mensaje = f'{"Entrada" if mov == "entrada" else "Salida"} registrada. Ahora hay {nuevo_stock} unidades.'
        return 'ok', mensaje, alertas_stock(producto_repo.obtener_por_id(producto_id)), {}

    if tipo == 'producto_nuevo':
        d = normalizar_datos(datos)
        errores = validar(d)
        if errores:
            return 'rechazada', resumen_errores(errores), [], errores
        nuevo_id = producto_repo.crear(d)
        if int(d['stock']) > 0:
            movimiento_repo.registrar(nuevo_id, usuario_id, 'entrada', int(d['stock']), 'Stock inicial', fecha)
        return 'ok', f'Se agregó {d["nombre"]}.', alertas_stock(producto_repo.obtener_por_id(nuevo_id)), {}

    if tipo == 'producto_editar':
        try:
            producto_id = int(datos.get('producto_id'))
        except (TypeError, ValueError):
            return 'rechazada', 'El repuesto no es válido.', [], {}
        producto = producto_repo.obtener_por_id(producto_id)
        if producto is None:
            return 'rechazada', 'Ese repuesto ya no existe.', [], {}
        d = normalizar_datos(datos)
        d['stock'] = producto['stock']
        errores = validar(d, producto_id, pedir_stock=False)
        if errores:
            return 'rechazada', resumen_errores(errores), [], errores
        producto_repo.actualizar(producto_id, d)
        return 'ok', 'Cambios guardados.', alertas_stock(producto_repo.obtener_por_id(producto_id)), {}

    return 'rechazada', 'Tipo de operación desconocido.', [], {}


def ejecutar_operacion(op):
    uuid = str(op.get('uuid', ''))
    tipo = str(op.get('tipo', ''))
    usuario_id = session['usuario_id']
    resultado = {'uuid': uuid}

    if not UUID_RE.match(uuid):
        return {**resultado, 'estado': 'rechazada', 'mensaje': 'Operación sin identificador válido.'}
    if op.get('usuario_id') != usuario_id:
        # La hizo otra persona en este equipo: se queda guardada hasta que ella inicie sesión
        return {**resultado, 'estado': 'otro_usuario'}
    if not isinstance(op.get('datos'), dict):
        return {**resultado, 'estado': 'rechazada', 'mensaje': 'Operación sin datos.'}

    try:
        previa = sync_repo.reclamar(uuid, usuario_id, tipo)
        if previa is not None:
            if previa['estado'] == 'procesando':
                return {**resultado, 'estado': 'reintentar'}
            # Ya se había subido antes: se responde lo mismo, sin repetirla
            return {**resultado, 'estado': previa['estado'], 'mensaje': previa['mensaje'], 'repetida': True}

        try:
            estado, mensaje, alertas, errores = aplicar_operacion(
                tipo, op['datos'], usuario_id, fecha_de_operacion(op.get('fecha')))
        except Exception:
            sync_repo.liberar(uuid)
            raise
        sync_repo.terminar(uuid, estado, mensaje)
    except Exception as e:
        app.logger.exception('Falló la operación %s', uuid)
        return {**resultado, 'estado': 'reintentar', 'mensaje': 'El servidor no pudo procesarla ahora.'}

    if op.get('flash') and estado == 'ok':
        flash(mensaje, 'exito')
        for alerta in alertas:
            flash(alerta, 'alerta')
    return {**resultado, 'estado': estado, 'mensaje': mensaje, 'errores': errores, 'alertas': alertas}


@app.route('/api/sincronizar', methods=['POST'])
def api_sincronizar():
    if login_requerido():
        return jsonify(error='sesion'), 401
    carga = request.get_json(silent=True) or {}
    operaciones = carga.get('operaciones')
    if not isinstance(operaciones, list) or len(operaciones) > 50:
        return jsonify(error='peticion'), 400
    try:
        resultados = [ejecutar_operacion(op) for op in operaciones if isinstance(op, dict)]
    except Exception:
        app.logger.exception('Falló la sincronización')
        return jsonify(error='servidor'), 503
    return jsonify(resultados=resultados)


@app.route('/api/ping')
def api_ping():
    return jsonify(ok=True), 200, {'Cache-Control': 'no-store'}


# ---- APP INSTALABLE Y MODO SIN CONEXIÓN ----

@app.route('/sw.js')
def service_worker():
    # Va en la raíz para que controle toda la página
    respuesta = send_from_directory(app.static_folder, 'js/sw.js', mimetype='application/javascript')
    respuesta.headers['Service-Worker-Allowed'] = '/'
    respuesta.headers['Cache-Control'] = 'no-cache'
    return respuesta


@app.route('/manifest.webmanifest')
def manifest():
    respuesta = send_from_directory(app.static_folder, 'manifest.webmanifest',
                                    mimetype='application/manifest+json')
    respuesta.headers['Cache-Control'] = 'no-cache'
    return respuesta


@app.route('/offline')
def pagina_offline():
    return render_template('offline.html')


@app.route('/salud')
def salud():
    """Para que el servicio de hosting compruebe que la app y la base responden."""
    try:
        asegurar_esquema()
        return jsonify(ok=True)
    except Exception:
        return jsonify(ok=False), 503


if __name__ == '__main__':
    # Para publicarlo se usa gunicorn (ver GUIA_DESPLIEGUE.md); esto es solo para probar en tu PC
    app.run(debug=activo('FLASK_DEBUG'), host=os.environ.get('HOST', '127.0.0.1'),
            port=int(os.environ.get('PORT', '5000')))
