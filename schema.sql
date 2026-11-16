-- Base de datos de Repuestos Alfa (instalación nueva)
-- Uso:  mysql -u root -p < schema.sql

CREATE DATABASE IF NOT EXISTS repuestos_alfa
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE repuestos_alfa;

CREATE TABLE IF NOT EXISTS usuarios (
    id        INT AUTO_INCREMENT PRIMARY KEY,
    nombre    VARCHAR(100) NOT NULL,
    email     VARCHAR(120) NOT NULL UNIQUE,
    password  VARCHAR(255) NOT NULL,
    rol       VARCHAR(20)  NOT NULL DEFAULT 'empleado'
);

CREATE TABLE IF NOT EXISTS categorias (
    id      INT AUTO_INCREMENT PRIMARY KEY,
    nombre  VARCHAR(60) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS productos (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    codigo          VARCHAR(40)  NULL UNIQUE,
    nombre          VARCHAR(150) NOT NULL,
    descripcion     TEXT NULL,
    marca           VARCHAR(60)  NULL,
    compatibilidad  VARCHAR(255) NULL,
    ubicacion       VARCHAR(40)  NULL,
    precio_compra   DECIMAL(12,2) NOT NULL DEFAULT 0,
    precio_venta    DECIMAL(12,2) NOT NULL DEFAULT 0,
    stock           INT NOT NULL DEFAULT 0,
    stock_minimo    INT NOT NULL DEFAULT 5,
    categoria_id    INT NULL,
    INDEX idx_nombre (nombre),
    FOREIGN KEY (categoria_id) REFERENCES categorias(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS movimientos (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    producto_id  INT NOT NULL,
    usuario_id   INT NOT NULL,
    tipo         ENUM('entrada','salida') NOT NULL,
    cantidad     INT NOT NULL,
    motivo       VARCHAR(200) NULL,
    fecha        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (producto_id) REFERENCES productos(id),
    FOREIGN KEY (usuario_id)  REFERENCES usuarios(id)
);

INSERT IGNORE INTO categorias (nombre) VALUES
    ('Frenos'), ('Motor'), ('Suspensión y dirección'), ('Sistema eléctrico'),
    ('Filtros'), ('Lubricantes'), ('Transmisión y embrague'),
    ('Refrigeración'), ('Encendido'), ('Carrocería y luces');

-- El primer usuario que se registre en la página queda como administrador.
-- Para hacer administrador a otro:  UPDATE usuarios SET rol='admin' WHERE email='correo@ejemplo.com';

-- Operaciones hechas sin internet que ya se subieron (evita duplicarlas si el envío se repite).
-- La app también la crea sola al arrancar si no existe.
CREATE TABLE IF NOT EXISTS sync_operaciones (
    uuid        CHAR(36) NOT NULL PRIMARY KEY,
    usuario_id  INT NOT NULL,
    tipo        VARCHAR(30) NOT NULL,
    estado      VARCHAR(20) NOT NULL,
    mensaje     VARCHAR(255) NULL,
    creado      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
