/* Pagina "Tijden individuele atleet": keuze van 1-5 atleten, evolutiegrafiek en
   histogram (klassen van 5 seconden). Pure SVG, geen externe bibliotheken.
   Enkel eindtijden. Kleur + vorm volgen de PLEK (1-5) van de atleet, niet de tijd. */
(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';
  var KLEUR = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4'];   // = --serie-1..5 in stijl.css
  var VORM = ['cirkel', 'vierkant', 'ruit', 'driehoek', 'plus'];            // extra onderscheid naast kleur
  var MAX = 5, KLASSE = 5;                                                  // max atleten, klassebreedte (sec)
  var MAANDEN = ['jan', 'feb', 'mrt', 'apr', 'mei', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec'];

  var keuzes = JSON.parse(document.getElementById('gr-keuzes').textContent);
  var DATA_URL = document.currentScript.dataset.url;
  var $ = function (id) { return document.getElementById(id); };
  var slots = [null, null, null, null, null];     // atleet-id per kleurplek
  var cache = {};                                 // id -> reeks van de server
  var waarde = 'aantal', weergave = null;         // weergave null = automatisch

  /* ---------- hulpfuncties ---------- */
  function el(tag, attrs, ouder, tekst) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (tekst != null) e.textContent = tekst;
    if (ouder) ouder.appendChild(e);
    return e;
  }
  function html(tag, klasse, tekst, ouder) {
    var e = document.createElement(tag);
    if (klasse) e.className = klasse;
    if (tekst != null) e.textContent = tekst;
    if (ouder) ouder.appendChild(e);
    return e;
  }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function mmss(s) { s = Math.round(s); return pad(Math.floor(s / 60)) + ':' + pad(s % 60); }
  function dagMs(iso) { var d = iso.split('-'); return Date.UTC(+d[0], +d[1] - 1, +d[2]); }
  function datumNl(iso) { var d = iso.split('-'); return d[2] + '/' + d[1] + '/' + d[0]; }
  function naamVan(a) { return a.voornaam + ' ' + a.naam; }
  function keuzeVan(id) { return keuzes.filter(function (k) { return k.id === id; })[0]; }
  function actieve() {                            // [{slot, reeks}] van gekozen atleten met data
    var uit = [];
    slots.forEach(function (id, i) { if (id && cache[id]) uit.push({ slot: i, reeks: cache[id] }); });
    return uit;
  }

  /* Marker in een van 5 vormen, gecentreerd op (x,y), met 2px lichte rand tegen het vlak */
  function marker(ouder, slot, x, y, r) {
    var a = { fill: KLEUR[slot], stroke: '#fff', 'stroke-width': 2 }, e;
    switch (VORM[slot]) {
      case 'vierkant': a.x = x - r; a.y = y - r; a.width = 2 * r; a.height = 2 * r; a.rx = 1; e = el('rect', a, ouder); break;
      case 'ruit': a.d = 'M' + x + ' ' + (y - r * 1.3) + 'L' + (x + r * 1.3) + ' ' + y + 'L' + x + ' ' + (y + r * 1.3) + 'L' + (x - r * 1.3) + ' ' + y + 'Z'; e = el('path', a, ouder); break;
      case 'driehoek': a.d = 'M' + x + ' ' + (y - r * 1.25) + 'L' + (x + r * 1.2) + ' ' + (y + r) + 'L' + (x - r * 1.2) + ' ' + (y + r) + 'Z'; e = el('path', a, ouder); break;
      case 'plus': var t = r * 0.5; a.d = 'M' + (x - t) + ' ' + (y - r) + 'h' + 2 * t + 'v' + (r - t) + 'h' + (r - t) + 'v' + 2 * t + 'h' + (t - r) + 'v' + (r - t) + 'h' + (-2 * t) + 'v' + (t - r) + 'h' + (t - r) + 'v' + (-2 * t) + 'h' + (r - t) + 'Z'; e = el('path', a, ouder); break;
      default: a.cx = x; a.cy = y; a.r = r; e = el('circle', a, ouder);
    }
    return e;
  }

  /* "Mooie" assen */
  function mooieStap(bereik, doelAantal, stappen) {
    for (var i = 0; i < stappen.length; i++) if (bereik / stappen[i] <= doelAantal) return stappen[i];
    return stappen[stappen.length - 1];
  }
  var TIJD_STAPPEN = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800];
  var TEL_STAPPEN = [1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000];

  /* ---------- tooltip ---------- */
  function maakTip(wrap) {
    var tip = html('div', 'gr-tip', null, wrap);
    tip.hidden = true; tip.setAttribute('role', 'status');
    return tip;
  }
  function zetTip(tip, wrap, x, y, kop, rijen) {
    tip.textContent = '';
    html('div', 'tip-kop', kop, tip);
    rijen.forEach(function (r) {
      var d = html('div', 'tip-rij', null, tip);
      var s = html('span', 'tip-stip', null, d); s.style.background = KLEUR[r.slot];
      html('span', '', r.tekst, d);
    });
    tip.hidden = false;
    var b = wrap.clientWidth, w = tip.offsetWidth;
    tip.style.left = Math.max(w / 2, Math.min(b - w / 2, x)) + 'px';
    tip.style.top = Math.max(tip.offsetHeight + 14, y) + 'px';
  }

  /* ======================================================================
     EVOLUTIE
     ====================================================================== */
  var evo = { sel: null };
  function tekenEvolutie() {
    var wrap = $('gr-evolutie'), act = actieve();
    wrap.textContent = '';
    var punten = [];
    act.forEach(function (a) { a.reeks.punten.forEach(function (p) { punten.push({ slot: a.slot, reeks: a.reeks, p: p, ms: dagMs(p.d) }); }); });
    if (!punten.length) { html('p', 'gr-leeg', 'Geen eindtijden beschikbaar voor deze keuze.', wrap); return; }
    var B = Math.max(300, wrap.clientWidth), H = B < 520 ? 320 : 400;
    var m = { l: 62, r: 16, t: 12, b: 46 }, pw = B - m.l - m.r, ph = H - m.t - m.b;

    var minMs = Math.min.apply(null, punten.map(function (p) { return p.ms; }));
    var maxMs = Math.max.apply(null, punten.map(function (p) { return p.ms; }));
    var dag = 86400000;
    if (maxMs - minMs < 60 * dag) { minMs -= 30 * dag; maxMs += 30 * dag; }
    else { var pd = (maxMs - minMs) * 0.03; minMs -= pd; maxMs += pd; }
    var minS = Math.min.apply(null, punten.map(function (p) { return p.p.s; }));
    var maxS = Math.max.apply(null, punten.map(function (p) { return p.p.s; }));
    var pad_ = Math.max(5, (maxS - minS) * 0.08);
    var stapS = mooieStap(maxS - minS + 2 * pad_, 7, TIJD_STAPPEN);
    var y0 = Math.floor((minS - pad_) / stapS) * stapS, y1 = Math.ceil((maxS + pad_) / stapS) * stapS;
    var X = function (ms) { return m.l + (ms - minMs) / (maxMs - minMs) * pw; };
    var Y = function (s) { return m.t + (1 - (s - y0) / (y1 - y0)) * ph; };

    var svg = el('svg', { viewBox: '0 0 ' + B + ' ' + H, width: B, height: H, role: 'img',
      'aria-label': 'Lijngrafiek van de eindtijden van ' + act.map(function (a) { return naamVan(a.reeks); }).join(', ') + '. Een tabel met dezelfde gegevens staat onder de grafiek.' }, wrap);

    // horizontale rasterlijnen + y-labels
    for (var v = y0; v <= y1 + 0.001; v += stapS) {
      el('line', { x1: m.l, x2: B - m.r, y1: Y(v), y2: Y(v), 'class': 'raster' }, svg);
      el('text', { x: m.l - 8, y: Y(v) + 4, 'text-anchor': 'end' }, svg, mmss(v));
    }
    el('line', { x1: m.l, x2: B - m.r, y1: m.t + ph, y2: m.t + ph, 'class': 'as-lijn' }, svg);
    el('text', { x: 14, y: m.t + ph / 2, 'text-anchor': 'middle', 'class': 'as-titel', transform: 'rotate(-90 14 ' + (m.t + ph / 2) + ')' }, svg, 'Oefencross Tijd');

    // x-ticks: jaren, of maanden bij een korte periode
    var d0 = new Date(minMs), d1 = new Date(maxMs), ticks = [];
    var spanJaar = (maxMs - minMs) / (365.25 * dag);
    if (spanJaar >= 3) {
      var stapJ = mooieStap(spanJaar, Math.max(2, Math.floor(pw / 70)), [1, 2, 5, 10, 20]);
      for (var j = Math.ceil(d0.getUTCFullYear() / stapJ) * stapJ; j <= d1.getUTCFullYear(); j += stapJ)
        ticks.push({ ms: Date.UTC(j, 0, 1), t: String(j) });
    } else {
      var stapM = mooieStap(spanJaar * 12, Math.max(2, Math.floor(pw / 70)), [1, 2, 3, 6, 12]);
      var mi = d0.getUTCFullYear() * 12 + d0.getUTCMonth() + 1;
      mi = Math.ceil(mi / stapM) * stapM;
      for (; ; mi += stapM) {
        var ms = Date.UTC(Math.floor(mi / 12), mi % 12, 1);
        if (ms > maxMs) break;
        ticks.push({ ms: ms, t: MAANDEN[mi % 12] + ' ' + Math.floor(mi / 12) });
      }
    }
    ticks.forEach(function (t) {
      if (t.ms < minMs || t.ms > maxMs) return;
      el('line', { x1: X(t.ms), x2: X(t.ms), y1: m.t + ph, y2: m.t + ph + 4, 'class': 'as-lijn' }, svg);
      el('text', { x: X(t.ms), y: m.t + ph + 18, 'text-anchor': 'middle' }, svg, t.t);
    });
    el('text', { x: m.l + pw / 2, y: H - 6, 'text-anchor': 'middle', 'class': 'as-titel' }, svg, 'Datum');

    // lijnen
    act.forEach(function (a) {
      var ps = a.reeks.punten;
      if (ps.length > 1)
        el('path', { d: ps.map(function (p, i) { return (i ? 'L' : 'M') + X(dagMs(p.d)).toFixed(1) + ' ' + Y(p.s).toFixed(1); }).join(''),
          fill: 'none', stroke: KLEUR[a.slot], 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, svg);
    });
    // markers (bij heel veel punten enkel bij hover, om de lijn leesbaar te houden)
    var teveel = punten.length / act.length > 60;
    if (!teveel) punten.forEach(function (q) { marker(svg, q.slot, X(q.ms), Y(q.p.s), 4); });
    // enkel 1 punt per atleet => marker altijd tonen
    else act.forEach(function (a) { if (a.reeks.punten.length === 1) marker(svg, a.slot, X(dagMs(a.reeks.punten[0].d)), Y(a.reeks.punten[0].s), 4); });

    // interactie
    var tip = maakTip(wrap), hover = el('g', { 'pointer-events': 'none' }, svg);
    var vlak = el('rect', { x: m.l, y: m.t, width: pw, height: ph, fill: 'transparent' }, svg);
    var flat = punten.slice().sort(function (a, b) { return a.ms - b.ms || a.slot - b.slot; });
    var cur = -1;
    function toon(i) {
      hover.textContent = '';
      if (i < 0) { tip.hidden = true; return; }
      cur = i; var q = flat[i], x = X(q.ms), y = Y(q.p.s);
      el('line', { x1: x, x2: x, y1: m.t, y2: m.t + ph, stroke: '#8a918b', 'stroke-width': 1, 'stroke-dasharray': '3 3' }, hover);
      marker(hover, q.slot, x, y, 6);
      zetTip(tip, wrap, x, y, datumNl(q.p.d), [{ slot: q.slot, tekst: naamVan(q.reeks) + ': ' + q.p.t }]);
    }
    function dichtste(ev) {
      var r = svg.getBoundingClientRect(), px = (ev.clientX - r.left) * B / r.width, py = (ev.clientY - r.top) * H / r.height;
      var best = -1, bd = 1e9;
      flat.forEach(function (q, i) { var d = Math.hypot(X(q.ms) - px, Y(q.p.s) - py); if (d < bd) { bd = d; best = i; } });
      return bd <= 40 ? best : -1;
    }
    vlak.addEventListener('pointermove', function (ev) { toon(dichtste(ev)); });
    vlak.addEventListener('pointerdown', function (ev) { toon(dichtste(ev)); });
    vlak.addEventListener('pointerleave', function () { if (document.activeElement !== wrap) toon(-1); });
    wrap.onkeydown = function (ev) {
      var n = flat.length, i = cur;
      if (ev.key === 'ArrowRight') i = i < 0 ? 0 : Math.min(n - 1, i + 1);
      else if (ev.key === 'ArrowLeft') i = i < 0 ? n - 1 : Math.max(0, i - 1);
      else if (ev.key === 'Home') i = 0; else if (ev.key === 'End') i = n - 1;
      else if (ev.key === 'Escape') { toon(-1); return; } else return;
      ev.preventDefault(); toon(i);
    };
    wrap.onblur = function () { toon(-1); };
    tabelEvolutie(act);
  }
  function tabelEvolutie(act) {
    var d = $('gr-tabel-evo'); d.textContent = '';
    var datums = {};
    act.forEach(function (a) { a.reeks.punten.forEach(function (p) { (datums[p.d] = datums[p.d] || {})[a.slot] = p.t; }); });
    var t = html('table', '', null, d), kop = html('tr', '', null, html('thead', '', null, t));
    html('th', '', 'Datum', kop);
    act.forEach(function (a) { html('th', '', naamVan(a.reeks), kop); });
    var body = html('tbody', '', null, t);
    Object.keys(datums).sort().reverse().forEach(function (dt) {
      var r = html('tr', '', null, body); html('td', '', datumNl(dt), r);
      act.forEach(function (a) { html('td', '', datums[dt][a.slot] || '–', r); });
    });
  }

  /* ======================================================================
     HISTOGRAM
     ====================================================================== */
  function tekenHistogram() {
    var wrap = $('gr-histogram'), act = actieve();
    wrap.textContent = '';
    var alle = [];
    act.forEach(function (a) { a.reeks.punten.forEach(function (p) { alle.push(p.s); }); });
    if (!alle.length) { html('p', 'gr-leeg', 'Geen eindtijden beschikbaar voor deze keuze.', wrap); $('gr-tabel-hist').textContent = ''; return; }
    var lo = Math.floor(Math.min.apply(null, alle) / KLASSE) * KLASSE;
    var hi = Math.floor(Math.max.apply(null, alle) / KLASSE) * KLASSE + KLASSE;
    var nb = (hi - lo) / KLASSE;
    var tel = act.map(function (a) {
      var c = []; for (var i = 0; i < nb; i++) c.push(0);
      a.reeks.punten.forEach(function (p) { c[Math.floor((p.s - lo) / KLASSE)]++; });
      var totaal = a.reeks.punten.length;
      return { slot: a.slot, reeks: a.reeks, c: c, totaal: totaal,
        w: c.map(function (n) { return waarde === 'pct' ? n / totaal * 100 : n; }) };
    });
    var B = Math.max(300, wrap.clientWidth), H = B < 520 ? 300 : 360;
    var m = { l: 52, r: 16, t: 12, b: 50 }, pw = B - m.l - m.r, ph = H - m.t - m.b;
    var bw = pw / nb, n = tel.length;

    var modus = weergave || ((bw - 2) / n >= 8 ? 'naast' : 'over');
    if (n === 1) modus = 'naast';
    $('gr-weergave').hidden = n < 2;
    $('gr-m-naast').setAttribute('aria-pressed', String(modus === 'naast'));
    $('gr-m-over').setAttribute('aria-pressed', String(modus === 'over'));

    var maxW = Math.max.apply(null, tel.map(function (t) { return Math.max.apply(null, t.w); }));
    var stapY = mooieStap(maxW * 1.05, 6, waarde === 'pct' ? [1, 2, 5, 10, 20, 25, 50] : TEL_STAPPEN);
    var yMax = Math.max(stapY, Math.ceil(maxW / stapY - 1e-9) * stapY);
    var Y = function (v) { return m.t + (1 - v / yMax) * ph; };

    var svg = el('svg', { viewBox: '0 0 ' + B + ' ' + H, width: B, height: H, role: 'img',
      'aria-label': 'Histogram van de eindtijden van ' + act.map(function (a) { return naamVan(a.reeks); }).join(', ') + ' in klassen van 5 seconden. Een tabel met dezelfde gegevens staat onder de grafiek.' }, wrap);

    for (var v = 0; v <= yMax + 1e-9; v += stapY) {
      el('line', { x1: m.l, x2: B - m.r, y1: Y(v), y2: Y(v), 'class': v === 0 ? 'as-lijn' : 'raster' }, svg);
      el('text', { x: m.l - 8, y: Y(v) + 4, 'text-anchor': 'end' }, svg, String(v) + (waarde === 'pct' ? '%' : ''));
    }
    el('text', { x: 12, y: m.t + ph / 2, 'text-anchor': 'middle', 'class': 'as-titel', transform: 'rotate(-90 12 ' + (m.t + ph / 2) + ')' },
      svg, waarde === 'pct' ? 'Aandeel van de oefencrossen' : 'Aantal oefencrossen');

    // x-labels: begin van de klasse, met genoeg tussenruimte
    var nodig = Math.ceil(64 / bw), stapL = [1, 2, 3, 6, 12, 24, 36, 60, 120, 240].filter(function (s) { return s >= nodig; })[0] || nodig;   // hele minuten waar mogelijk
    for (var i = 0; i <= nb; i += stapL) {
      var x = m.l + i * bw;
      el('line', { x1: x, x2: x, y1: m.t + ph, y2: m.t + ph + 4, 'class': 'as-lijn' }, svg);
      el('text', { x: x, y: m.t + ph + 18, 'text-anchor': 'middle' }, svg, mmss(lo + i * KLASSE));
    }
    el('text', { x: m.l + pw / 2, y: H - 6, 'text-anchor': 'middle', 'class': 'as-titel' }, svg, 'Oefencross Tijd (klassen van 5 seconden)');

    var markeer = el('rect', { y: m.t, height: ph, fill: '#e6e9e5', opacity: 0.7, visibility: 'hidden', 'pointer-events': 'none' }, svg);
    var staven = el('g', {}, svg);

    function staaf(x, w, v, kleur, overlay) {
      if (v <= 0) return;
      var y = Y(v), h = m.t + ph - y, r = Math.min(4, w / 2, h);
      var d = 'M' + x + ' ' + (m.t + ph) + 'V' + (y + r) + 'Q' + x + ' ' + y + ' ' + (x + r) + ' ' + y + 'H' + (x + w - r) +
        'Q' + (x + w) + ' ' + y + ' ' + (x + w) + ' ' + (y + r) + 'V' + (m.t + ph) + 'Z';
      el('path', overlay ? { d: d, fill: kleur, 'fill-opacity': 0.45, stroke: kleur, 'stroke-width': 1.5 } : { d: d, fill: kleur }, staven);
    }
    if (modus === 'naast') {
      var gap = bw > 6 ? 2 : 0, breedte = Math.min(24, (bw - gap * 2 - (n - 1) * (bw > 12 ? 2 : 0)) / n);
      breedte = Math.max(1, breedte);
      var los = n > 1 && bw > 12 ? 2 : 0, groep = n * breedte + (n - 1) * los;
      tel.forEach(function (t, k) {
        for (var b = 0; b < nb; b++) staaf(m.l + b * bw + (bw - groep) / 2 + k * (breedte + los), breedte, t.w[b], KLEUR[t.slot], false);
      });
    } else {
      tel.slice().sort(function (a, b) { return Math.max.apply(null, b.w) - Math.max.apply(null, a.w); }).forEach(function (t) {
        for (var b = 0; b < nb; b++) staaf(m.l + b * bw + Math.min(1, bw / 4), Math.max(1, bw - Math.min(2, bw / 2)), t.w[b], KLEUR[t.slot], true);
      });
    }

    var tip = maakTip(wrap), cur = -1;
    var vlak = el('rect', { x: m.l, y: m.t, width: pw, height: ph, fill: 'transparent' }, svg);
    function toon(b) {
      if (b < 0 || b >= nb) { cur = -1; markeer.setAttribute('visibility', 'hidden'); tip.hidden = true; return; }
      cur = b;
      markeer.setAttribute('x', m.l + b * bw); markeer.setAttribute('width', bw); markeer.setAttribute('visibility', 'visible');
      var hoogste = Math.max.apply(null, tel.map(function (t) { return t.w[b]; }));
      zetTip(tip, wrap, m.l + (b + 0.5) * bw, Y(hoogste),
        mmss(lo + b * KLASSE) + ' tot ' + mmss(lo + (b + 1) * KLASSE),
        tel.map(function (t) {
          return { slot: t.slot, tekst: naamVan(t.reeks) + ': ' + t.c[b] + (t.c[b] === 1 ? ' keer' : ' keer') +
            (waarde === 'pct' ? ' (' + t.w[b].toFixed(1).replace('.', ',') + '%)' : '') };
        }));
    }
    function binVan(ev) {
      var r = svg.getBoundingClientRect(), px = (ev.clientX - r.left) * B / r.width;
      return Math.max(0, Math.min(nb - 1, Math.floor((px - m.l) / bw)));
    }
    vlak.addEventListener('pointermove', function (ev) { toon(binVan(ev)); });
    vlak.addEventListener('pointerdown', function (ev) { toon(binVan(ev)); });
    vlak.addEventListener('pointerleave', function () { if (document.activeElement !== wrap) toon(-1); });
    wrap.onkeydown = function (ev) {
      var i = cur;
      if (ev.key === 'ArrowRight') i = i < 0 ? 0 : Math.min(nb - 1, i + 1);
      else if (ev.key === 'ArrowLeft') i = i < 0 ? nb - 1 : Math.max(0, i - 1);
      else if (ev.key === 'Home') i = 0; else if (ev.key === 'End') i = nb - 1;
      else if (ev.key === 'Escape') { toon(-1); return; } else return;
      ev.preventDefault(); toon(i);
    };
    wrap.onblur = function () { toon(-1); };

    // tabel
    var d = $('gr-tabel-hist'); d.textContent = '';
    var t = html('table', '', null, d), kop = html('tr', '', null, html('thead', '', null, t));
    html('th', '', 'Klasse', kop);
    tel.forEach(function (x) { html('th', '', naamVan(x.reeks), kop); });
    var body = html('tbody', '', null, t);
    for (var b = 0; b < nb; b++) {
      if (!tel.some(function (x) { return x.c[b]; })) continue;
      var r = html('tr', '', null, body);
      html('td', '', mmss(lo + b * KLASSE) + ' – ' + mmss(lo + (b + 1) * KLASSE), r);
      tel.forEach(function (x) {
        html('td', '', x.c[b] + (waarde === 'pct' ? ' (' + x.w[b].toFixed(1).replace('.', ',') + '%)' : ''), r);
      });
    }
  }

  /* ======================================================================
     KEUZE VAN ATLETEN
     ====================================================================== */
  function chipVorm(slot) {
    var s = el('svg', { width: 14, height: 14, viewBox: '0 0 14 14', 'aria-hidden': 'true' });
    marker(s, slot, 7, 7, 4.5);
    return s;
  }
  function tekenChips() {
    var ul = $('gr-chips'); ul.textContent = '';
    slots.forEach(function (id, slot) {
      if (!id) return;
      var k = keuzeVan(id); if (!k) return;
      var li = html('li', 'gr-chip', null, ul);
      li.appendChild(chipVorm(slot));
      html('span', '', naamVan(k) + (k.n ? ' (' + k.n + ')' : ' (geen eindtijden)'), li);
      var kn = html('button', '', '×', li); kn.type = 'button';
      kn.setAttribute('aria-label', naamVan(k) + ' verwijderen');
      kn.addEventListener('click', function () { slots[slot] = null; bijwerken(); $('gr-invoer').focus(); });
    });
    var aantal = slots.filter(Boolean).length;
    $('gr-teller').textContent = aantal;
    $('gr-invoer').disabled = aantal >= MAX;
    $('gr-invoer').placeholder = aantal >= MAX ? 'Maximum bereikt: verwijder eerst een atleet' : 'Typ een naam of voornaam';
  }

  var lijst = $('gr-lijst'), invoer = $('gr-invoer'), opties = [], actief = -1;
  function sluitLijst() { lijst.hidden = true; invoer.setAttribute('aria-expanded', 'false'); actief = -1; }
  function norm(s) { return s.toLowerCase().replace(/\s+/g, ' ').trim(); }
  function toonLijst() {
    var q = norm(invoer.value);
    opties = keuzes.filter(function (k) {
      if (slots.indexOf(k.id) >= 0) return false;
      var s = norm(k.naam + ' ' + k.voornaam) + ' ' + norm(k.voornaam + ' ' + k.naam);
      return !q || q.split(' ').every(function (w) { return s.indexOf(w) >= 0; });
    }).slice(0, 12);
    lijst.textContent = '';
    if (!opties.length) {
      if (q) { html('div', 'sugg-item', 'Geen atleet gevonden', lijst).style.color = '#888'; lijst.hidden = false; }
      else sluitLijst();
      return;
    }
    opties.forEach(function (k, i) {
      var d = html('div', 'sugg-item', naamVan(k) + (k.n ? '' : ' (geen eindtijden)'), lijst);
      d.setAttribute('role', 'option'); d.id = 'gr-opt-' + i;
      d.addEventListener('mousedown', function (e) { e.preventDefault(); voegToe(k.id); });
    });
    lijst.hidden = false; invoer.setAttribute('aria-expanded', 'true');
  }
  function markeerActief() {
    Array.prototype.forEach.call(lijst.children, function (c, i) { c.classList.toggle('actief', i === actief); });
    if (actief >= 0) invoer.setAttribute('aria-activedescendant', 'gr-opt-' + actief); else invoer.removeAttribute('aria-activedescendant');
  }
  invoer.addEventListener('input', toonLijst);
  invoer.addEventListener('focus', toonLijst);
  invoer.addEventListener('blur', function () { setTimeout(sluitLijst, 120); });
  invoer.addEventListener('keydown', function (e) {
    if (lijst.hidden) { if (e.key === 'ArrowDown') toonLijst(); return; }
    if (e.key === 'ArrowDown') { actief = (actief + 1) % Math.max(1, opties.length); markeerActief(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { actief = (actief - 1 + opties.length) % Math.max(1, opties.length); markeerActief(); e.preventDefault(); }
    else if (e.key === 'Enter') { var k = opties[actief >= 0 ? actief : (opties.length === 1 ? 0 : -1)]; if (k) voegToe(k.id); e.preventDefault(); }
    else if (e.key === 'Escape') sluitLijst();
  });

  function voegToe(id) {
    var vrij = slots.indexOf(null);           // nieuwe atleet krijgt de laagste vrije kleurplek
    if (vrij < 0 || slots.indexOf(id) >= 0) return;
    slots[vrij] = id; invoer.value = ''; sluitLijst(); bijwerken();
  }

  function laad(id) {
    if (cache[id]) return Promise.resolve();
    return fetch(DATA_URL + '?a=' + encodeURIComponent(id), { credentials: 'same-origin' })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (j) { if (j.reeksen && j.reeksen[0]) cache[id] = j.reeksen[0]; });
  }
  function bijwerken() {
    var fout = $('gr-fout'); fout.hidden = true;
    try { history.replaceState(null, '', slots.some(Boolean) ? '?a=' + slots.map(function (s) { return s || ''; }).join(',').replace(/,+$/, '') : location.pathname); } catch (e) {}
    tekenChips();
    Promise.all(slots.filter(Boolean).map(laad)).then(tekenAlles, function () {
      fout.textContent = 'De tijden konden niet opgehaald worden. Probeer het later opnieuw.'; fout.hidden = false;
    });
  }
  function tekenAlles() {
    var heeft = slots.some(Boolean);
    $('gr-leeg').hidden = heeft;
    $('gr-kaart-evolutie').hidden = !heeft;
    $('gr-kaart-histogram').hidden = !heeft;
    if (!heeft) return;
    tekenEvolutie(); tekenHistogram();
  }

  /* knoppen */
  function zetWaarde(w) {
    waarde = w;
    $('gr-w-aantal').setAttribute('aria-pressed', String(w === 'aantal'));
    $('gr-w-pct').setAttribute('aria-pressed', String(w === 'pct'));
    tekenHistogram();
  }
  $('gr-w-aantal').addEventListener('click', function () { zetWaarde('aantal'); });
  $('gr-w-pct').addEventListener('click', function () { zetWaarde('pct'); });
  $('gr-m-naast').addEventListener('click', function () { weergave = 'naast'; tekenHistogram(); });
  $('gr-m-over').addEventListener('click', function () { weergave = 'over'; tekenHistogram(); });
  [['gr-tabel-evo-knop', 'gr-tabel-evo'], ['gr-tabel-hist-knop', 'gr-tabel-hist']].forEach(function (p) {
    $(p[0]).addEventListener('click', function () {
      var d = $(p[1]), open = d.hidden;
      d.hidden = !open; this.textContent = open ? 'Tabel verbergen' : 'Tabel tonen'; this.setAttribute('aria-expanded', String(open));
    });
  });
  var laatsteBreedte = 0;
  if (window.ResizeObserver) {
    new ResizeObserver(function () {
      var b = $('gr-evolutie').clientWidth;
      if (b && b !== laatsteBreedte) { laatsteBreedte = b; if (slots.some(Boolean)) tekenAlles(); }
    }).observe($('gr-evolutie'));
  }

  /* start: atleten uit de URL (?a=id1,,id3) */
  var q = new URLSearchParams(location.search).get('a');
  if (q) q.split(',').slice(0, MAX).forEach(function (id, i) { if (id && keuzeVan(id)) slots[i] = id; });
  bijwerken();
})();
