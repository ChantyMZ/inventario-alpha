import unicodedata
from openpyxl import load_workbook

# Nombres de columna que se reconocen en el Excel (sin tildes ni mayúsculas)
ALIAS = {
    'codigo': ['codigo', 'cod', 'referencia', 'ref', 'sku'],
    'nombre': ['nombre', 'producto', 'repuesto', 'articulo', 'item', 'descripcion'],
    'marca': ['marca'],
    'categoria': ['categoria', 'tipo', 'linea'],
    'compatibilidad': ['compatibilidad', 'vehiculo', 'vehiculos', 'modelo', 'aplicacion'],
    'ubicacion': ['ubicacion', 'estante', 'bodega'],
    'precio_compra': ['precio compra', 'precio de compra', 'costo', 'compra'],
    'precio_venta': ['precio venta', 'precio de venta', 'precio', 'venta', 'valor'],
    'stock': ['stock', 'cantidad', 'existencias', 'unidades', 'inventario'],
    'stock_minimo': ['stock minimo', 'stock min', 'minimo'],
}

MAX_FILAS = 5000


def normalizar(texto):
    texto = unicodedata.normalize('NFD', str(texto or '')).encode('ascii', 'ignore').decode()
    return texto.lower().replace('_', ' ').strip()


def numero(valor, entero=False):
    """Convierte celdas como 12500, '$12.500' o '12.500,50' en número. Devuelve None si no se puede."""
    if valor is None or valor == '':
        return None
    if isinstance(valor, (int, float)):
        n = float(valor)
    else:
        t = str(valor).replace('$', '').replace(' ', '')
        if ',' in t and '.' in t:
            t = t.replace('.', '').replace(',', '.')
        elif ',' in t:
            t = t.replace(',', '.')
        elif t.count('.') > 1 or ('.' in t and len(t.split('.')[-1]) == 3):
            t = t.replace('.', '')
        try:
            n = float(t)
        except ValueError:
            return None
    if n < 0:
        return None
    return int(round(n)) if entero else n


def texto(valor):
    t = str(valor).strip() if valor is not None else ''
    return t or None


def importar_inventario(archivo, producto_repo, categoria_repo, movimiento_repo, usuario_id):
    hoja = load_workbook(archivo, read_only=True, data_only=True).active
    filas = list(hoja.iter_rows(values_only=True, max_row=MAX_FILAS + 10))

    # Buscar la fila de encabezados: la primera que tenga una columna de nombre
    columnas = {}
    inicio = None
    for i, fila in enumerate(filas[:15]):
        encontrado = {}
        for j, celda in enumerate(fila):
            nombre_col = normalizar(celda)
            for campo, alias in ALIAS.items():
                if nombre_col in alias and campo not in encontrado:
                    encontrado[campo] = j
                    break
        if 'nombre' in encontrado:
            columnas, inicio = encontrado, i + 1
            break
    if inicio is None:
        raise ValueError('No encontré una columna con el nombre del repuesto. '
                         'La primera fila debe tener encabezados como Código, Nombre, Stock y Precio venta.')

    def celda(fila, campo):
        j = columnas.get(campo)
        return fila[j] if j is not None and j < len(fila) else None

    resumen = {'nuevos': 0, 'actualizados': 0, 'errores': []}
    for n, fila in enumerate(filas[inicio:], start=inicio + 1):
        nombre = texto(celda(fila, 'nombre'))
        if not nombre:
            if any(c is not None for c in fila):
                resumen['errores'].append((n, 'Falta el nombre del repuesto.'))
            continue

        compra = numero(celda(fila, 'precio_compra'))
        venta = numero(celda(fila, 'precio_venta'))
        stock = numero(celda(fila, 'stock'), entero=True)
        minimo = numero(celda(fila, 'stock_minimo'), entero=True)
        if celda(fila, 'stock') not in (None, '') and stock is None:
            resumen['errores'].append((n, 'El stock no es un número válido.'))
            continue

        categoria = texto(celda(fila, 'categoria'))
        datos = {
            'codigo': texto(celda(fila, 'codigo')),
            'nombre': nombre,
            'descripcion': None,
            'marca': texto(celda(fila, 'marca')),
            'compatibilidad': texto(celda(fila, 'compatibilidad')),
            'ubicacion': texto(celda(fila, 'ubicacion')),
            'precio_compra': compra if compra is not None else 0,
            'precio_venta': venta if venta is not None else (compra or 0),
            'stock': stock or 0,
            'stock_minimo': minimo if minimo is not None else 5,
            'categoria_id': categoria_repo.obtener_o_crear(categoria) if categoria else None,
        }

        existente = None
        if datos['codigo']:
            existente = producto_repo.obtener_por_codigo(datos['codigo'])
        if existente is None:
            existente = producto_repo.obtener_por_nombre(nombre)

        if existente is None:
            nuevo_id = producto_repo.crear(datos)
            if datos['stock'] > 0:
                movimiento_repo.registrar(nuevo_id, usuario_id, 'entrada', datos['stock'],
                                          'Stock inicial (importación de Excel)')
            resumen['nuevos'] += 1
        else:
            # Lo que venga vacío en el Excel no pisa lo que ya estaba guardado
            for campo in ('codigo', 'marca', 'compatibilidad', 'ubicacion', 'categoria_id', 'descripcion'):
                if datos[campo] is None:
                    datos[campo] = existente[campo]
            producto_repo.actualizar(existente['id'], datos)
            if stock is not None and stock != existente['stock']:
                diferencia = stock - existente['stock']
                producto_repo.actualizar_stock(existente['id'], stock)
                movimiento_repo.registrar(existente['id'], usuario_id,
                                          'entrada' if diferencia > 0 else 'salida',
                                          abs(diferencia), 'Ajuste por importación de Excel')
            resumen['actualizados'] += 1
    return resumen
