/* Service worker de Repuestos Alfa.
 *  - Guarda las páginas que ya visitaste para poder abrirlas sin internet.
 *  - Si hay operaciones pendientes, las sube apenas el navegador recupere la conexión
 *    (aunque la página esté cerrada, en navegadores que lo permiten).
 * Cuando cambies este archivo o los de /static, sube el número de VERSION. */
importScripts('/static/js/cola.js');

var VERSION = 'v1';
var ESTATICOS = 'alfa-estaticos-' + VERSION;
var PAGINAS = 'alfa-paginas-' + VERSION;
var ESPERA_RED_MS = 6000;

var PRECARGA = [
  '/offline',
  '/manifest.webmanifest',
  '/static/css/estilo.css',
  '/static/js/cola.js',
  '/static/js/offline.js',
  '/static/img/logo.png',
  '/static/img/favicon.png',
  '/static/img/icon-192.png'
];

// Páginas que nunca se guardan (acceso y cierre de sesión)
function esPaginaDeAcceso(ruta) {
  return ruta === '/login' || ruta.indexOf('/login/') === 0 || ruta === '/registro' || ruta === '/logout' ||
         ruta === '/salud' || ruta === '/offline';
}

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(ESTATICOS).then(function (c) { return c.addAll(PRECARGA); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (nombres) {
      return Promise.all(nombres.filter(function (n) {
        return n.indexOf('alfa-') === 0 && n !== ESTATICOS && n !== PAGINAS;
      }).map(function (n) { return caches.delete(n); }));
    }).then(function () { return self.clients.claim(); })
  );
});

function conTiempo(promesa, ms) {
  return new Promise(function (resolve, reject) {
    var t = setTimeout(function () { reject(new Error('tiempo')); }, ms);
    promesa.then(function (r) { clearTimeout(t); resolve(r); }, function (err) { clearTimeout(t); reject(err); });
  });
}

// ¿La respuesta trae avisos de una sola vez ("Se agregó...")? Esas no se guardan, para que
// no reaparezcan al abrir la página sin internet.
function tieneAvisos(respuesta) {
  return respuesta.clone().text().then(function (t) { return t.indexOf('class="avisos"') !== -1; });
}

function guardarPagina(peticion, respuesta) {
  if (!respuesta || respuesta.status !== 200 || respuesta.redirected) return Promise.resolve();
  return tieneAvisos(respuesta).then(function (conAvisos) {
    if (conAvisos) return;
    return caches.open(PAGINAS).then(function (c) { return c.put(peticion, respuesta.clone()); });
  });
}

function paginaConRed(peticion) {
  return conTiempo(fetch(peticion), ESPERA_RED_MS).then(function (respuesta) {
    var url = new URL(peticion.url);
    if (!esPaginaDeAcceso(url.pathname)) guardarPagina(peticion, respuesta.clone());
    return respuesta;
  });
}

function paginaSinRed(peticion) {
  var url = new URL(peticion.url);
  return caches.open(PAGINAS).then(function (c) {
    return c.match(peticion).then(function (r) {
      if (r) return r;
      // Búsquedas como /?q=freno: se usa el inventario completo y la página filtra en pantalla
      if (url.pathname === '/') return c.match('/', { ignoreSearch: true });
    });
  }).then(function (r) { return r || caches.match('/offline'); });
}

function estaticoConActualizacion(peticion) {
  return caches.open(ESTATICOS).then(function (c) {
    return c.match(peticion).then(function (guardado) {
      var red = fetch(peticion).then(function (r) {
        if (r && (r.status === 200 || r.type === 'opaque')) c.put(peticion, r.clone());
        return r;
      }).catch(function () { return guardado; });
      return guardado || red;
    });
  });
}

self.addEventListener('fetch', function (e) {
  var peticion = e.request;
  if (peticion.method !== 'GET') return;
  var url = new URL(peticion.url);

  if (url.origin !== self.location.origin) {
    if (url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com') {
      e.respondWith(estaticoConActualizacion(peticion));
    }
    return;
  }

  if (url.pathname.indexOf('/api/') === 0 || url.pathname === '/sw.js') return;

  if (url.pathname === '/logout') {
    // Al cerrar sesión se borra lo guardado, para que el siguiente usuario del equipo no vea datos ajenos
    e.waitUntil(caches.delete(PAGINAS));
    return;
  }

  if (url.pathname.indexOf('/static/') === 0 || url.pathname === '/manifest.webmanifest') {
    e.respondWith(estaticoConActualizacion(peticion));
    return;
  }

  if (peticion.mode === 'navigate') {
    if (url.pathname.indexOf('/login/') === 0) return; // el retorno de Google va directo
    e.respondWith(paginaConRed(peticion).catch(function () { return paginaSinRed(peticion); }));
  }
});

// La página pide guardar de antemano las pantallas de movimiento y edición
// para poder usarlas sin internet.
self.addEventListener('message', function (e) {
  var d = e.data || {};
  if (d.tipo !== 'precargar' || !Array.isArray(d.urls)) return;
  var urls = d.urls.slice(0, 400);
  e.waitUntil((function () {
    var i = 0;
    function trabajador() {
      if (i >= urls.length) return Promise.resolve();
      var u = urls[i++];
      return fetch(u, { credentials: 'same-origin' }).then(function (r) {
        return guardarPagina(new Request(u), r);
      }).catch(function () {}).then(trabajador);
    }
    return Promise.all([trabajador(), trabajador(), trabajador(), trabajador()]);
  })());
});

// Subida en segundo plano (Chrome, Edge): se dispara cuando vuelve la conexión
self.addEventListener('sync', function (e) {
  if (e.tag !== 'alfa-sync') return;
  e.waitUntil(self.Cola.sincronizar().then(function (r) {
    if (r.estado === 'red' || r.estado === 'servidor') throw new Error('reintentar'); // el navegador vuelve a intentar
    return self.clients.matchAll({ includeUncontrolled: true }).then(function (clientes) {
      clientes.forEach(function (c) { c.postMessage({ tipo: 'sincronizado', subidas: r.subidas }); });
    });
  }));
});
