# Repuestos Alfa — Sistema de Gestión de Inventario

Sistema web para administrar el inventario de una tienda de repuestos automotrices. Permite organizar productos, controlar existencias, registrar entradas y salidas, importar datos desde Excel y consultar reportes.

La aplicación también incluye funciones de **PWA (Progressive Web App)** para acceder a recursos guardados y registrar algunas operaciones sin conexión, con sincronización posterior al servidor.

## Funcionalidades

- **Usuarios:** registro, inicio y cierre de sesión; roles de administrador y empleado.
- **Productos:** creación, consulta, edición, búsqueda y eliminación por administradores.
- **Existencias:** control de stock, stock mínimo y alertas de productos por reponer.
- **Movimientos:** registro de entradas y salidas con historial.
- **Reportes:** resumen de movimientos, productos por reponer y productos con más salidas.
- **Importación:** carga de inventario desde archivos `.xlsx` (administrador).
- **PWA:** instalación desde navegadores compatibles, almacenamiento local de recursos y sincronización de operaciones pendientes.
- **Google OAuth:** opción de inicio de sesión con Google cuando se configuran las credenciales correspondientes.

> **Nota:** la sincronización incluida en este proyecto corresponde a operaciones realizadas sin conexión entre el navegador y la base de datos propia. El código no incluye integración con FakeStoreAPI ni con otra API pública de productos.

## Tecnologías utilizadas

| Capa | Tecnología |
| --- | --- |
| Backend | Python, Flask |
| Frontend | HTML, CSS, JavaScript, Jinja2 |
| Base de datos | MySQL / MariaDB |
| Acceso a datos | `mysql-connector-python` |
| Archivos Excel | `openpyxl` |
| Autenticación opcional | Authlib (Google OAuth) |
| Funciones offline | Service Worker, IndexedDB |
| Despliegue | Gunicorn (configurado en `Procfile`) |

## Requisitos previos

- Python 3.10 o superior (recomendado).
- `pip` para instalar dependencias.
- MySQL o MariaDB en ejecución. Se puede utilizar **XAMPP** para el entorno local.
- Navegador web actualizado.

## Instalación y ejecución

### 1. Obtener el proyecto

Clona el repositorio desde GitHub o descarga su archivo ZIP. Abre una terminal en la carpeta que contiene `app.py` y `requirements.txt`.

### 2. Crear un entorno virtual

**Windows (PowerShell):**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Instalar las dependencias

```bash
python -m pip install -r requirements.txt
```

### 4. Crear la base de datos

**Con XAMPP:**

1. Inicia **MySQL** en el panel de XAMPP.
2. Inicia **Apache** si vas a usar phpMyAdmin.
3. Accede a `http://localhost/phpmyadmin`.
4. Ve a **Importar**, selecciona el archivo `schema.sql` y ejecuta la importación.

El archivo `schema.sql` crea la base de datos **`repuestos_alfa`**, sus tablas y categorías iniciales.

**Alternativa con terminal MySQL:**

```bash
mysql -u root -p < schema.sql
```

Si la cuenta de MySQL no tiene contraseña, utiliza las credenciales correspondientes a tu instalación.

### 5. Configurar las variables de entorno

Crea un archivo `.env` en la raíz del proyecto y ajusta estos valores a tu instalación:

```dotenv
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=
DB_NAME=repuestos_alfa

SECRET_KEY=CAMBIAR_POR_UNA_CLAVE_SEGURA
APP_TZ=America/Bogota
COOKIE_SECURE=false
BEHIND_PROXY=false
```

Para generar una clave segura, puedes ejecutar:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copia el resultado en `SECRET_KEY`.

**Seguridad:** nunca subas tu archivo `.env`, tu entorno `.venv/` ni el archivo `.secret_key` a GitHub. Agrégalos a tu `.gitignore`.

Si deseas habilitar el acceso con Google, configura también `GOOGLE_CLIENT_ID` y `GOOGLE_CLIENT_SECRET` en `.env`.

### 6. Ejecutar la aplicación

```bash
python -m flask --app app run
```

Abre en el navegador:

**http://127.0.0.1:5000**

> Es preferible iniciar con el comando de Flask indicado: carga las variables del archivo `.env` antes de importar los módulos de conexión a MySQL.

### 7. Registrar el primer usuario

1. Abre `http://127.0.0.1:5000/registro`.
2. Crea una cuenta.
3. Inicia sesión en `/login`.

**La primera cuenta registrada en una base de datos sin usuarios recibe el rol de administrador**. Las cuentas siguientes reciben el rol de empleado.

## Estructura del repositorio

```text
inventario-alpha-main/
├── app.py                   # Rutas, autenticación y aplicación Flask
├── database.py              # Configuración y conexión a MySQL
├── repositories.py          # Consultas de datos
├── observers.py             # Alertas de stock (Observer)
├── importador.py            # Importación desde Excel
├── schema.sql               # Esquema de base de datos
├── requirements.txt         # Dependencias
├── Procfile                 # Inicio con Gunicorn
├── static/
│   ├── css/estilo.css       # Estilos
│   ├── img/                 # Iconos y recursos gráficos
│   ├── js/
│   │   ├── cola.js          # Cola local de operaciones
│   │   ├── offline.js       # Funcionamiento sin conexión
│   │   └── sw.js            # Service Worker
│   └── manifest.webmanifest # Metadatos de la PWA
└── templates/               # Plantillas HTML
```

## Uso de la aplicación

Después de iniciar sesión, podrás gestionar productos desde el inventario y registrar entradas o salidas de unidades. El sistema controla el stock para impedir que se registren salidas superiores a las existencias disponibles.

Los administradores pueden importar un archivo Excel (`.xlsx`) con la información de los productos. El archivo acepta columnas como **Nombre**, **Código**, **Marca**, **Categoría**, **Compatibilidad**, **Ubicación**, **Precio compra**, **Precio venta**, **Stock** y **Stock mínimo**. El campo **Nombre** es obligatorio. El límite de carga es de **5 MB**.

La sección de reportes permite consultar los productos que requieren reposición, los artículos con más salidas y los movimientos registrados.

## Funcionalidad sin conexión

La aplicación dispone de un Service Worker y almacenamiento local. En navegadores compatibles, algunas acciones sobre productos y movimientos pueden quedar pendientes cuando no hay conexión, y la aplicación intenta enviarlas al servidor cuando se restablece.

Para utilizar esta función, abre la aplicación e inicia sesión **antes** de desconectarte. No todas las pantallas o funciones están disponibles sin conexión. Para usar la PWA en un sitio publicado se requiere HTTPS; en desarrollo puedes utilizar `localhost`.

## Rutas principales

| Ruta | Función |
| --- | --- |
| `/` | Inventario |
| `/registro` | Crear usuario |
| `/login` | Iniciar sesión |
| `/agregar` | Registrar producto |
| `/editar/<producto_id>` | Editar producto |
| `/movimientos` | Historial |
| `/reportes` | Informes |
| `/importar` | Importar Excel |
| `/api/sincronizar` | Sincronización de operaciones pendientes |
| `/salud` | Comprobación básica del servicio |

## Consideraciones

- La base de datos debe estar iniciada y correctamente configurada para utilizar el sistema.
- El repositorio **no incluye Docker** ni una API REST completa para todas las operaciones CRUD; su interfaz principal utiliza vistas y formularios de Flask.
- Para despliegues públicos se requieren variables de entorno seguras, una base de datos accesible y HTTPS.

---

**Proyecto:** Repuestos Alfa — Sistema de Gestión de Inventario.
