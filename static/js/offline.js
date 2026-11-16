/* Modo sin conexión en las páginas de Repuestos Alfa.
 *  - Registra el service worker (páginas disponibles sin internet).
 *  - Los formularios de movimiento y repuestos se envían a una cola local; si hay internet
 *    se suben al instante y si no, quedan guardados y se suben solos al volver la conexión.
 *  - Muestra el estado (sin conexión / pendientes) y ajusta las existencias con lo pendiente.
 */
(function () {
  'use strict';

  var cuerpo = document.body;
  var usuarioId = Number(cuerpo.getAttribute('data-usuario-id')) || null;
  var estado = { red: navigator.onLine, ops: [], necesitaLogin: false, sincronizando: false };
  var canal = window.BroadcastChannel ? new BroadcastChannel('alfa-cola') : null;

  function $(sel, raiz) { return (raiz || document).querySelector(sel); }
  function $$(sel, raiz) { return Array.prototype.slice.call((raiz || document).querySelectorAll(sel)); }
  function plural(n, uno, varios) { return n + ' ' + (n === 1 ? uno : varios); }

  /* ---------- Avisos (mismo aspecto que los del servidor) ---------- */
  var ICONOS = {
    exito: '<path d="M5.5 12.5l4.2 4.2L18.5 8"/>',
    error: '<path d="M7 7l10 10M17 7L7 17"/>',
    aviso: '<path d="M12 7.5v5.5M12 16.5v.01"/>',
    info: '<path d="M12 11v5.5M12 7.5v.01"/>'
  };
  var TITULOS = { exito: 'Listo', error: 'Error', aviso: 'Atención', info: 'Información' };

  function aviso(tipo, texto) {
    var contenedor = $('.avisos');
    if (!contenedor) {
      contenedor = document.createElement('div');
      contenedor.className = 'avisos';
      contenedor.setAttribute('aria-live', 'polite');
      (document.querySelector('.contenedor') || document.body).appendChild(contenedor);
    }
    var el = document.createElement('div');
    el.className = 'aviso aviso-' + tipo;
    el.setAttribute('role', tipo === 'error' ? 'alert' : 'status');
    el.style.setProperty('--duracion', tipo === 'error' ? '12s' : '7s');
    el.innerHTML =
      '<span class="aviso-icono" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">' + ICONOS[tipo] + '</svg></span>' +
      '<div class="aviso-texto"><strong></strong><span></span></div>' +
      '<button type="button" class="aviso-cerrar" aria-label="Cerrar notificación">&times;</button>' +
      '<span class="aviso-tiempo" aria-hidden="true"></span>';
    $('strong', el).textContent = TITULOS[tipo];
    $('.aviso-texto span', el).textContent = texto;
    function cerrar() {
      if (el.classList.contains('saliendo')) return;
      el.classList.add('saliendo');
      setTimeout(function () { el.remove(); }, 250);
    }
    $('.aviso-cerrar', el).addEventListener('click', cerrar);
    $('.aviso-tiempo', el).addEventListener('animationend', cerrar);
    setTimeout(cerrar, (tipo === 'error' ? 13 : 8) * 1000);
    contenedor.appendChild(el);
  }

  // Un aviso que debe verse en la pantalla siguiente (después de redirigir)
  function avisoSiguiente(tipo, texto) {
    try { sessionStorage.setItem('alfa-aviso', JSON.stringify({ tipo: tipo, texto: texto })); } catch (e) { /* sin sessionStorage */ }
  }
  function mostrarAvisoPendiente() {
    try {
      var guardado = sessionStorage.getItem('alfa-aviso');
      if (!guardado) return;
      sessionStorage.removeItem('alfa-aviso');
      var a = JSON.parse(guardado);
      aviso(a.tipo, a.texto);
    } catch (e) { /* nada */ }
  }

  /* ---------- Estado y panel ---------- */
  function pendientes(soloMios) {
    return estado.ops.filter(function (o) {
      return o.estado === 'pendiente' && (!soloMios || o.usuario_id === usuarioId);
    });
  }
  function conProblema() { return estado.ops.filter(function (o) { return o.estado === 'rechazada'; }); }

  function pintarEstado() {
    var boton = $('#estadoRed');
    if (!boton) return;
    var pend = pendientes(true).length;
    var ajenas = pendientes(false).length - pend;
    var malas = conProblema().length;
    var texto = '', clase = '';

    if (estado.sincronizando) { texto = 'Subiendo cambios…'; clase = 'pendiente'; }
    else if (!estado.red) { texto = pend ? 'Sin conexión · ' + pend + ' por subir' : 'Sin conexión'; clase = 'sin-red'; }
    else if (estado.necesitaLogin && pend) { texto = 'Inicia sesión para subir ' + pend; clase = 'problema'; }
    else if (malas) { texto = plural(malas, 'cambio con problema', 'cambios con problema'); clase = 'problema'; }
    else if (pend) { texto = pend + ' por subir'; clase = 'pendiente'; }
    else if (ajenas) { texto = ajenas + ' de otro usuario'; clase = 'pendiente'; }

    boton.hidden = !texto;
    boton.className = 'estado-red' + (clase ? ' estado-red-' + clase : '');
    $('span', boton).textContent = texto;
  }

  function etiquetaOp(op) { return op.resumen || op.tipo; }

  function pintarPanel() {
    var lista = $('#listaCola');
    if (!lista) return;
    lista.innerHTML = '';
    if (!estado.ops.length) {
      var vacio = document.createElement('li');
      vacio.className = 'cola-vacia';
      vacio.textContent = 'No hay nada pendiente. Todo está al día.';
      lista.appendChild(vacio);
    }
    estado.ops.forEach(function (op) {
      var li = document.createElement('li');
      li.className = 'cola-item' + (op.estado === 'rechazada' ? ' cola-item-mala' : '');
      var info = document.createElement('div');
      var t = document.createElement('strong');
      t.textContent = etiquetaOp(op);
      var d = document.createElement('small');
      var hecho = new Date(op.creado).toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' });
      d.textContent = (op.estado === 'rechazada' ? 'No se pudo subir · ' : 'Por subir · ') + 'hecho el ' + hecho +
        (op.usuario_id !== usuarioId ? ' · de otro usuario' : '');
      info.appendChild(t);
      info.appendChild(d);
      if (op.mensaje) {
        var m = document.createElement('p');
        m.textContent = op.mensaje;
        info.appendChild(m);
      }
      var quitar = document.createElement('button');
      quitar.type = 'button';
      quitar.className = 'boton boton-sec boton-chico';
      quitar.textContent = 'Descartar';
      quitar.addEventListener('click', function () {
        var pregunta = op.estado === 'rechazada'
          ? '¿Descartar este cambio? No se aplicará al inventario.'
          : '¿Descartar este cambio sin subirlo? No se aplicará al inventario.';
        if (!confirm(pregunta)) return;
        Cola.borrar(op.uuid).then(function () { refrescar(true); });
      });
      li.appendChild(info);
      li.appendChild(quitar);
      lista.appendChild(li);
    });
    var subir = $('#subirAhora');
    if (subir) subir.disabled = pendientes(true).length === 0;
  }

  function refrescar(avisarOtros) {
    return Promise.all([Cola.listar(), Cola.meta('necesitaLogin')]).then(function (d) {
      estado.ops = d[0];
      estado.necesitaLogin = !!d[1];
      pintarEstado();
      pintarPanel();
      proyectarExistencias();
      if (avisarOtros && canal) canal.postMessage('cambio');
    }).catch(function () { /* sin IndexedDB: se trabaja como una página normal */ });
  }

  /* ---------- Existencias: lo mostrado + lo pendiente de subir ---------- */
  function cambiosPendientes() {
    var mapa = {};
    pendientes(false).forEach(function (op) {
      if (op.tipo !== 'movimiento') return;
      var id = String(op.datos.producto_id);
      var n = parseInt(op.datos.cantidad, 10) || 0;
      mapa[id] = (mapa[id] || 0) + (op.datos.tipo === 'entrada' ? n : -n);
    });
    return mapa;
  }

  function pintarFila(fila, stock, cambio) {
    var minimo = Number(fila.getAttribute('data-minimo')) || 0;
    var est = stock <= 0 ? 'agotado' : (stock <= minimo ? 'reponer' : 'ok');
    fila.setAttribute('data-estado', est);
    var celda = $('.existencia', fila);
    if (!celda) return;
    celda.className = 'existencia estado-' + est;
    var cifra = $('.existencia-cifra', celda);
    if (cifra && cifra.firstChild) cifra.firstChild.nodeValue = stock;
    var barra = $('.barra-nivel span', celda);
    if (barra) {
      var nivel = minimo <= 0 ? (stock > 0 ? 100 : 0) : Math.min(100, Math.round(stock / (minimo * 3) * 100));
      barra.style.width = Math.max(0, nivel) + '%';
    }
    $$('.etiqueta-estado, .marca-pendiente', celda).forEach(function (n) { n.remove(); });
    if (est !== 'ok') {
      var e = document.createElement('span');
      e.className = 'etiqueta-estado';
      e.textContent = est === 'agotado' ? 'Agotado' : 'Por reponer';
      celda.appendChild(e);
    }
    if (cambio) {
      var p = document.createElement('span');
      p.className = 'marca-pendiente';
      p.textContent = 'incluye cambios sin subir';
      celda.appendChild(p);
    }
  }

  function proyectarExistencias() {
    var mapa = cambiosPendientes();
    $$('tr[data-producto-id]').forEach(function (fila) {
      var base = Number(fila.getAttribute('data-stock'));
      var cambio = mapa[fila.getAttribute('data-producto-id')] || 0;
      pintarFila(fila, base + cambio, cambio);
    });
    var form = $('form[data-offline="movimiento"]');
    var cifra = $('#stockActual');
    if (form && cifra) {
      var cambioForm = mapa[form.getAttribute('data-producto-id')] || 0;
      cifra.textContent = Number(form.getAttribute('data-stock')) + cambioForm;
      var nota = $('.marca-pendiente', cifra.parentNode);
      if (nota) nota.remove();
      if (cambioForm) {
        nota = document.createElement('small');
        nota.className = 'marca-pendiente';
        nota.textContent = 'incluye cambios sin subir';
        cifra.parentNode.appendChild(nota);
      }
    }
    filtrarInventario();
  }

  /* ---------- Buscador del inventario sin internet ---------- */
  function normalizar(t) {
    return String(t || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  }
  function filtrarInventario() {
    var tabla = $('#tablaInventario');
    if (!tabla) return;
    var params = new URLSearchParams(location.search);
    var palabras = normalizar(params.get('q')).split(/\s+/).filter(Boolean);
    var filtro = params.get('filtro') || '';
    if (!palabras.length && !filtro) return;
    var visibles = 0;
    $$('tbody tr[data-producto-id]', tabla).forEach(function (fila) {
      var texto = normalizar(fila.getAttribute('data-busqueda'));
      var est = fila.getAttribute('data-estado');
      var ok = palabras.every(function (p) { return texto.indexOf(p) !== -1; });
      if (filtro === 'reponer') ok = ok && (est === 'reponer' || est === 'agotado');
      if (filtro === 'agotado') ok = ok && est === 'agotado';
      fila.style.display = ok ? '' : 'none';
      if (ok) visibles++;
    });
    var pie = $('#pieTabla');
    if (pie) pie.textContent = visibles ? 'Mostrando ' + plural(visibles, 'repuesto', 'repuestos') + '.' : 'No hay repuestos que coincidan.';
  }

  /* ---------- Formularios ---------- */
  function numero(v, entero) {
    if (v === '' || v == null) return null;
    if (entero && !/^\d+$/.test(String(v).trim())) return null;
    var n = Number(v);
    return isFinite(n) && n >= 0 ? n : null;
  }

  function validarRepuesto(d, esNuevo) {
    var e = {};
    if (!String(d.nombre || '').trim()) e.nombre = 'Escribe el nombre del repuesto.';
    var compra = numero(d.precio_compra), venta = numero(d.precio_venta);
    if (compra === null) e.precio_compra = 'Escribe un precio de compra de 0 o más.';
    if (venta === null) e.precio_venta = 'Escribe un precio de venta de 0 o más.';
    if (compra !== null && venta !== null && venta < compra) e.precio_venta = 'El precio de venta no puede ser menor al de compra.';
    if (esNuevo && numero(d.stock, true) === null) e.stock = 'Escribe las unidades que hay, con un número entero de 0 o más.';
    if (numero(d.stock_minimo || '0', true) === null) e.stock_minimo = 'Escribe un mínimo entero de 0 o más.';
    return e;
  }

  function mostrarErrores(form, errores) {
    $$('.campo.con-error', form).forEach(function (c) { c.classList.remove('con-error'); });
    $$('.campo .error', form).forEach(function (n) { n.remove(); });
    var primero = null;
    Object.keys(errores).forEach(function (nombre) {
      var entrada = form.elements[nombre];
      var campo = entrada && entrada.closest ? entrada.closest('.campo') : null;
      if (!campo) return;
      campo.classList.add('con-error');
      var msg = document.createElement('span');
      msg.className = 'error';
      msg.textContent = errores[nombre];
      entrada.insertAdjacentElement('afterend', msg);
      if (!primero) primero = entrada;
    });
    if (primero) primero.focus();
  }

  function resumenOperacion(tipo, d, form) {
    var nombre = form.getAttribute('data-nombre') || d.nombre || 'repuesto';
    if (tipo === 'movimiento') return (d.tipo === 'entrada' ? 'Entrada de ' : 'Salida de ') + d.cantidad + ' · ' + nombre;
    if (tipo === 'producto_nuevo') return 'Repuesto nuevo · ' + nombre;
    return 'Cambios en ' + nombre;
  }

  function registrarSubidaEnSegundoPlano() {
    if (!navigator.serviceWorker) return;
    navigator.serviceWorker.ready.then(function (reg) {
      if (reg.sync) return reg.sync.register('alfa-sync');
    }).catch(function () { /* el navegador no lo permite: se sube al abrir la página */ });
  }

  function enviarFormulario(form, e) {
    if (e.defaultPrevented) return; // el propio formulario ya detectó un error
    var tipo = form.getAttribute('data-offline');
    var datos = {};
    new FormData(form).forEach(function (v, k) { datos[k] = v; });
    if (form.getAttribute('data-producto-id')) datos.producto_id = form.getAttribute('data-producto-id');

    if (tipo !== 'movimiento') {
      var errores = validarRepuesto(datos, tipo === 'producto_nuevo');
      if (Object.keys(errores).length) { e.preventDefault(); mostrarErrores(form, errores); return; }
    }
    if (!usuarioId || !window.indexedDB || !window.Cola) return; // sin sesión o sin soporte: envío normal

    e.preventDefault();
    var boton = $('[type="submit"]', form);
    if (boton) boton.disabled = true;

    var op = {
      uuid: Cola.nuevoUuid(), tipo: tipo, datos: datos, usuario_id: usuarioId,
      fecha: Date.now(), creado: Date.now(), estado: 'pendiente', intentos: 0,
      resumen: resumenOperacion(tipo, datos, form)
    };

    // 1) Se guarda primero en el equipo: así no se pierde aunque se cierre la página
    Cola.guardar(op).then(function () {
      return Cola.guardarMeta('usuarioId', usuarioId);
    }).then(function () {
      // 2) Se intenta subir ya. Si no hay internet, queda guardada.
      return Cola.sincronizar({ interactiva: op.uuid });
    }).then(function (r) {
      var res = r.porUuid[op.uuid];
      if (res && res.estado === 'ok') { location.href = '/'; return; }

      if (res && res.estado === 'rechazada') {
        if (boton) boton.disabled = false;
        if (res.errores && Object.keys(res.errores).length) mostrarErrores(form, res.errores);
        else aviso('error', res.mensaje || 'El servidor no aceptó el cambio.');
        refrescar(true);
        return;
      }

      // No se pudo subir ahora: queda guardada en este equipo
      registrarSubidaEnSegundoPlano();
      var texto = r.estado === 'sesion'
        ? 'Tu sesión venció. El cambio quedó guardado; inicia sesión para subirlo.'
        : 'Sin conexión: el cambio quedó guardado en este equipo y se subirá solo cuando vuelva el internet.';
      var puedeNavegar = navigator.onLine || (navigator.serviceWorker && navigator.serviceWorker.controller);
      refrescar(true).then(function () {
        if (puedeNavegar) { avisoSiguiente('aviso', texto); location.href = '/'; }
        else { aviso('aviso', texto); form.reset(); if (boton) boton.disabled = false; }
      });
    }).catch(function () {
      form.submit(); // si el navegador no deja guardar en el equipo, se envía como siempre
    });
  }

  /* ---------- Subida automática ---------- */
  function recargarSiCorresponde() {
    var ruta = location.pathname;
    var enLista = ruta === '/' || ruta === '/movimientos' || ruta === '/reportes';
    var escribiendo = document.activeElement && /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
    if (enLista && !escribiendo) setTimeout(function () { location.reload(); }, 1500);
  }

  function intentarSubir() {
    if (estado.sincronizando || !window.Cola) return Promise.resolve();
    if (!pendientes(true).length) return Promise.resolve();
    estado.sincronizando = true;
    pintarEstado();
    return Cola.sincronizar().then(function (r) {
      estado.sincronizando = false;
      if (r.estado === 'red') estado.red = false;
      else if (r.estado !== 'ocupado' && r.estado !== 'vacio') estado.red = true;
      if (r.subidas > 0) {
        aviso('exito', 'Se subieron ' + plural(r.subidas, 'cambio hecho', 'cambios hechos') + ' sin conexión.');
        recargarSiCorresponde();
      }
      if (r.rechazadas > 0) {
        aviso('error', plural(r.rechazadas, 'cambio no se pudo aplicar', 'cambios no se pudieron aplicar') + '. Revísalos en el panel de pendientes.');
      }
      if (r.estado === 'sesion') aviso('aviso', 'Inicia sesión de nuevo para subir los cambios guardados en este equipo.');
      return refrescar(r.subidas > 0 || r.rechazadas > 0);
    });
  }

  /* ---------- Páginas guardadas de antemano ---------- */
  function precargarPantallas() {
    if (!navigator.serviceWorker || !navigator.onLine || location.pathname !== '/') return;
    if (location.search) return; // solo con el inventario completo a la vista
    var ultimo = 0;
    try { ultimo = Number(localStorage.getItem('alfa-precarga')) || 0; } catch (e) { /* nada */ }
    if (Date.now() - ultimo < 5 * 60 * 1000) return;
    var urls = ['/', '/agregar', '/movimientos', '/reportes'];
    $$('tr[data-producto-id] a[href]').forEach(function (a) { urls.push(a.getAttribute('href')); });
    navigator.serviceWorker.ready.then(function (reg) {
      if (!reg.active) return;
      reg.active.postMessage({ tipo: 'precargar', urls: urls.filter(function (u, i) { return urls.indexOf(u) === i; }) });
      try { localStorage.setItem('alfa-precarga', String(Date.now())); } catch (e) { /* nada */ }
    });
  }

  /* ---------- Arranque ---------- */
  function iniciar() {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function () {});
      navigator.serviceWorker.addEventListener('message', function (e) {
        if (e.data && e.data.tipo === 'sincronizado') { refrescar(); if (e.data.subidas) recargarSiCorresponde(); }
      });
    }

    $$('form[data-offline]').forEach(function (form) {
      form.addEventListener('submit', function (e) { enviarFormulario(form, e); });
    });

    var panel = $('#panelCola');
    var pill = $('#estadoRed');
    if (pill && panel && panel.showModal) {
      pill.addEventListener('click', function () { refrescar().then(function () { panel.showModal(); }); });
      $('#cerrarPanel').addEventListener('click', function () { panel.close(); });
      $('#subirAhora').addEventListener('click', function () { intentarSubir(); });
    }

    var salir = $('#enlaceSalir');
    if (salir) salir.addEventListener('click', function (e) {
      var n = pendientes(true).length;
      if (n && !confirm('Tienes ' + plural(n, 'cambio', 'cambios') + ' sin subir. Se quedan guardados en este equipo y se suben cuando vuelvas a entrar con tu usuario. ¿Cerrar sesión?')) e.preventDefault();
    });

    window.addEventListener('online', function () { estado.red = true; pintarEstado(); intentarSubir(); });
    window.addEventListener('offline', function () { estado.red = false; pintarEstado(); });
    document.addEventListener('visibilitychange', function () { if (!document.hidden) intentarSubir(); });
    if (canal) canal.onmessage = function () { refrescar(); };
    setInterval(function () { if (!document.hidden) intentarSubir(); }, 20000);

    mostrarAvisoPendiente();
    filtrarInventario();

    if (!window.indexedDB || !window.Cola) return;
    var listo = usuarioId ? Cola.guardarMeta('usuarioId', usuarioId) : Promise.resolve();
    listo.then(function () { return refrescar(); }).then(function () {
      if (pendientes(true).length) registrarSubidaEnSegundoPlano();
      return intentarSubir();
    }).then(precargarPantallas).catch(function () {});
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
