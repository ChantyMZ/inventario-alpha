# Repuestos Alfa — Sistema de inventario

Aplicación web para gestionar el inventario de una tienda de repuestos: registro de productos, entradas y salidas de stock, alertas de stock mínimo y reportes. Funciona también **sin conexión a internet**: guarda las operaciones en el navegador y las envía a la base de datos cuando vuelve la conexión.

## Características

- Inicio de sesión y registro de usuarios (el primer usuario registrado queda como **administrador**).
- Gestión de repuestos: agregar, editar, buscar y eliminar (eliminar solo el administrador).
- Movimientos de **entrada** y **salida** de stock con motivo, fecha y usuario.
- Alertas cuando un producto queda en su stock mínimo o por debajo.
- Historial de movimientos y reportes.
- Importación de productos desde Excel (solo administrador).
- **Modo sin conexión (PWA):** instalable como app; las operaciones hechas sin internet se guardan en una cola local y se sincronizan al volver la conexión, sin duplicarse.
- Acceso con Google opcional (si no se configura, el botón no aparece).

## Tecnologías

| Capa | Tecnología |
|---|---|
| Backend | Python, Flask, Gunicorn |
| Base de datos | MySQL (local) / TiDB Cloud, compatible con MySQL (nube) |
| Frontend | HTML, CSS, JavaScript |
| Modo sin conexión | Service Worker, cola de operaciones en el navegador, `manifest.webmanifest` |
| Otros | openpyxl (Excel), Authlib (Google), python-dotenv |

## Estructura del proyecto

```
├── app.py              # Rutas y lógica principal de Flask
├── database.py         # Conexión a la base de datos
├── repositories.py     # Acceso a datos (productos, movimientos, usuarios)
├── observers.py        # Patrón Observer: alertas de stock bajo
├── importador.py       # Importación desde Excel
├── schema.sql          # Estructura de la base de datos
├── requirements.txt    # Dependencias de Python
├── Procfile            # Comando de arranque para el despliegue
├── templates/          # Vistas HTML
└── static/
    ├── css/            # Estilos
    ├── img/            # Logo e íconos de la app
    ├── js/             # sw.js, cola.js, offline.js (modo sin conexión)
    └── manifest.webmanifest
```

## Ejecutar en local

1. Crear la base de datos:
   ```bash
   mysql -u root -p < schema.sql
   ```
2. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```
3. Configurar variables: copiar `.env.example` como `.env` y completar los valores (ver tabla abajo). **Nunca subas el archivo `.env` a internet.**
4. Iniciar:
   ```bash
   python app.py
   ```
   La app queda en `http://127.0.0.1:5000`.

## Variables de entorno

| Variable | Descripción |
|---|---|
| `DB_HOST`, `DB_PORT` | Servidor y puerto de la base de datos |
| `DB_USER`, `DB_PASSWORD` | Credenciales de la base de datos |
| `DB_NAME` | Nombre de la base de datos |
| `SECRET_KEY` | Clave larga y aleatoria para firmar las sesiones |
| `BEHIND_PROXY` | `1` cuando está publicado detrás de un proxy HTTPS |
| `COOKIE_SECURE` | `1` cuando se usa HTTPS |
| `APP_TZ` | Zona horaria que se muestra (ej. `America/Bogota`) |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Opcionales, para acceso con Google |

Para generar una `SECRET_KEY`:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Despliegue gratuito (Render + TiDB Cloud)

1. **Base de datos:** crear una instancia gratuita en TiDB Cloud (Starter, compatible con MySQL) y ejecutar el contenido de `schema.sql` sin las líneas `CREATE DATABASE` y `USE`.
2. **Aplicación:** crear un *Web Service* en Render conectado a este repositorio.
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn app:app --workers 2 --threads 4 --timeout 60 --bind 0.0.0.0:$PORT`
3. Agregar en Render las variables de entorno de la tabla anterior (con los datos de conexión de TiDB, `DB_PORT=4000`).

Notas:
- El servicio gratuito de Render se duerme tras 15 minutos sin visitas; la primera carga posterior puede tardar cerca de un minuto.
- El modo sin conexión requiere **HTTPS** (Render lo incluye) y haber abierto la app al menos una vez con internet.

## Modo sin conexión

1. Con internet, el navegador guarda las pantallas y los productos (Service Worker).
2. Sin internet, los movimientos se guardan en una cola local del navegador.
3. Al volver la conexión, la cola se envía a `/api/sincronizar`. La tabla `sync_operaciones` registra lo ya procesado para evitar duplicados si el envío se repite.

## Rutas principales

| Ruta | Función |
|---|---|
| `/login`, `/registro`, `/logout` | Autenticación |
| `/` | Inventario |
| `/agregar`, `/editar/<id>`, `/eliminar/<id>` | Gestión de repuestos |
| `/movimiento/<id>` | Registrar entrada o salida |
| `/movimientos` | Historial de movimientos |
| `/reportes` | Reportes |
| `/importar` | Importar desde Excel (administrador) |
| `/api/sincronizar` | Recibe la cola del modo sin conexión |
| `/salud` | Verificación de estado del servicio |

## Seguridad

- Las contraseñas de los usuarios se guardan con *hash*, no en texto plano.
- Las credenciales y claves van en variables de entorno, nunca en el código ni en el repositorio.
- Usar `COOKIE_SECURE=1` y HTTPS en producción.

## Datos de ejemplo

Hay un archivo opcional con 49 repuestos y casi dos meses de movimientos para probar los reportes. Requiere haber registrado antes al menos un usuario.
