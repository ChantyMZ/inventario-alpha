/* Cola de operaciones sin conexión.
 *
 * Lo que se registra sin internet se guarda en IndexedDB (dentro del navegador de este
 * equipo) y se manda al servidor cuando vuelve la conexión. Este archivo lo usan tanto
 * las páginas como el service worker (sw.js), por eso no toca el DOM.
 */
(function (global) {
  'use strict';

  var DB_NOMBRE = 'alfa-offline';
  var dbPromesa = null;

  function abrir() {
    if (dbPromesa) return dbPromesa;
    dbPromesa = new Promise(function (resolve, reject) {
      var req = indexedDB.open(DB_NOMBRE, 1);
      req.onupgradeneeded = function () {
        var db = req.result;
        if (!db.objectStoreNames.contains('cola')) db.createObjectStore('cola', { keyPath: 'uuid' });
        if (!db.objectStoreNames.contains('meta')) db.createObjectStore('meta', { keyPath: 'clave' });
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { dbPromesa = null; reject(req.error); };
    });
    return dbPromesa;
  }

  function pedir(tienda, modo, fn) {
    return abrir().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(tienda, modo);
        var resultado = fn(tx.objectStore(tienda));
        tx.oncomplete = function () { resolve(resultado && 'result' in resultado ? resultado.result : undefined); };
        tx.onerror = tx.onabort = function () { reject(tx.error); };
      });
    });
  }

  function nuevoUuid() {
    if (global.crypto && crypto.randomUUID) return crypto.randomUUID();
    var b = new Uint8Array(16);
    crypto.getRandomValues(b);
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    var h = Array.prototype.map.call(b, function (x) { return ('0' + x.toString(16)).slice(-2); }).join('');
    return h.slice(0, 8) + '-' + h.slice(8, 12) + '-' + h.slice(12, 16) + '-' + h.slice(16, 20) + '-' + h.slice(20);
  }

  var Cola = {
    nuevoUuid: nuevoUuid,

    guardar: function (op) { return pedir('cola', 'readwrite', function (t) { return t.put(op); }); },
    borrar: function (uuid) { return pedir('cola', 'readwrite', function (t) { return t.delete(uuid); }); },
    listar: function () {
      return pedir('cola', 'readonly', function (t) { return t.getAll(); }).then(function (ops) {
        return (ops || []).sort(function (a, b) { return a.creado - b.creado; });
      });
    },
    meta: function (clave) {
      return pedir('meta', 'readonly', function (t) { return t.get(clave); })
        .then(function (fila) { return fila ? fila.valor : undefined; });
    },
    guardarMeta: function (clave, valor) {
      return pedir('meta', 'readwrite', function (t) { return t.put({ clave: clave, valor: valor }); });
    },

    /* Sube lo pendiente al servidor.
     * opciones.interactiva: uuid de la operación que la persona acaba de enviar
     *   (el servidor deja sus avisos para la siguiente pantalla).
     * Devuelve { estado, porUuid, subidas, rechazadas }.
     *   estado: 'vacio' | 'ok' | 'red' | 'sesion' | 'servidor' | 'ocupado' */
    sincronizar: function (opciones) {
      opciones = opciones || {};
      var trabajo = function () { return Cola._sincronizar(opciones); };
      if (global.navigator && navigator.locks) {
        return navigator.locks.request('alfa-sincronizar', { ifAvailable: true }, function (lock) {
          if (!lock) return { estado: 'ocupado', porUuid: {}, subidas: 0, rechazadas: 0 };
          return trabajo();
        });
      }
      return trabajo();
    },

    _sincronizar: function (opciones) {
      var vacio = function (estado) { return { estado: estado, porUuid: {}, subidas: 0, rechazadas: 0 }; };
      return Promise.all([Cola.listar(), Cola.meta('usuarioId')]).then(function (datos) {
        var usuarioId = datos[1];
        var pendientes = datos[0].filter(function (op) {
          return op.estado === 'pendiente' && op.usuario_id === usuarioId;
        }).slice(0, 50);
        if (!pendientes.length) return vacio('vacio');

        var carga = pendientes.map(function (op) {
          return {
            uuid: op.uuid, tipo: op.tipo, datos: op.datos, fecha: op.fecha,
            usuario_id: op.usuario_id, flash: op.uuid === opciones.interactiva
          };
        });

        var control = new AbortController();
        var corte = setTimeout(function () { control.abort(); }, 20000);
        return fetch('/api/sincronizar', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ operaciones: carga }),
          credentials: 'same-origin',
          cache: 'no-store',
          signal: control.signal
        }).then(function (resp) {
          clearTimeout(corte);
          if (resp.status === 401) return Cola.guardarMeta('necesitaLogin', true).then(function () { return vacio('sesion'); });
          if (!resp.ok) return vacio('servidor');
          return resp.json().then(function (cuerpo) {
            var porUuid = {}, subidas = 0, rechazadas = 0, tareas = [];
            (cuerpo.resultados || []).forEach(function (r) {
              porUuid[r.uuid] = r;
              var op = pendientes.filter(function (o) { return o.uuid === r.uuid; })[0];
              if (!op) return;
              if (r.estado === 'ok') {
                subidas++;
                tareas.push(Cola.borrar(r.uuid));
              } else if (r.estado === 'rechazada') {
                rechazadas++;
                if (r.uuid === opciones.interactiva) {
                  tareas.push(Cola.borrar(r.uuid)); // se le muestra al instante; no queda en la cola
                } else {
                  op.estado = 'rechazada';
                  op.mensaje = r.mensaje || 'El servidor no la aceptó.';
                  tareas.push(Cola.guardar(op));
                }
              } else {
                op.intentos = (op.intentos || 0) + 1;
                tareas.push(Cola.guardar(op));
              }
            });
            tareas.push(Cola.guardarMeta('necesitaLogin', false));
            if (subidas) tareas.push(Cola.guardarMeta('ultimaSubida', Date.now()));
            return Promise.all(tareas).then(function () {
              return { estado: 'ok', porUuid: porUuid, subidas: subidas, rechazadas: rechazadas };
            });
          });
        }).catch(function () {
          clearTimeout(corte);
          return vacio('red');
        });
      });
    }
  };

  global.Cola = Cola;
})(self);
