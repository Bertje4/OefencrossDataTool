/* Suggesties voor bekende atleten tijdens het invoeren.
   Werkt op alle velden input[name="naam[]"] / input[name="voornaam[]"], ook op
   rijen die later met "+ Deelnemer toevoegen" worden toegevoegd. */
(function () {
  'use strict';
  var data = [];
  try { data = JSON.parse(document.getElementById('atleten-suggesties-data').textContent) || []; } catch (e) {}
  var norm = function (s) { return (s || '').replace(/\s+/g, ' ').trim().toLowerCase(); };
  var lijst = document.createElement('div');
  lijst.className = 'sugg-lijst';
  lijst.setAttribute('role', 'listbox');
  lijst.hidden = true;
  document.body.appendChild(lijst);
  var actiefVeld = null, items = [], actief = -1;

  function rijVelden(input) {
    var rij = input.closest('tr');
    return {
      rij: rij,
      naam: rij.querySelector('input[name="naam[]"]'),
      voornaam: rij.querySelector('input[name="voornaam[]"]')
    };
  }
  function sluit() { lijst.hidden = true; actief = -1; items = []; }
  function kies(a) {
    var v = rijVelden(actiefVeld);
    v.naam.value = a.naam; v.voornaam.value = a.voornaam;
    sluit(); toonHint(v);
    var volgende = v.rij.querySelector('input[name^="ronde1"], input[name^="tussen_"]');
    if (volgende) volgende.focus();
  }
  function zoek(veld) {
    var v = rijVelden(veld);
    var n = norm(v.naam.value), vn = norm(v.voornaam.value);
    if (!n && !vn) return [];
    var treffers = data.filter(function (a) {
      var an = norm(a.naam), av = norm(a.voornaam);
      var okN = !n || an.indexOf(n) === 0 || an.indexOf(' ' + n) >= 0;
      var okV = !vn || av.indexOf(vn) === 0 || av.indexOf(' ' + vn) >= 0;
      return okN && okV;
    });
    return treffers.slice(0, 8);
  }
  function toon(veld) {
    actiefVeld = veld;
    items = zoek(veld); actief = -1;
    if (!items.length) { sluit(); return; }
    lijst.textContent = '';
    items.forEach(function (a, i) {
      var el = document.createElement('div');
      el.className = 'sugg-item'; el.setAttribute('role', 'option');
      el.textContent = a.naam + ' ' + a.voornaam;
      el.addEventListener('mousedown', function (e) { e.preventDefault(); kies(a); });
      el.dataset.i = i; lijst.appendChild(el);
    });
    var r = veld.getBoundingClientRect();
    lijst.style.left = (r.left + window.scrollX) + 'px';
    lijst.style.top = (r.bottom + window.scrollY + 2) + 'px';
    lijst.style.minWidth = Math.max(r.width, 180) + 'px';
    lijst.hidden = false;
  }
  function markeer() {
    Array.prototype.forEach.call(lijst.children, function (el, i) {
      el.classList.toggle('actief', i === actief);
    });
  }

  // Levenshtein-afstand, voor "Bedoelde u ...?" bij kleine tikfouten
  function afstand(a, b) {
    var m = [], i, j;
    for (i = 0; i <= a.length; i++) { m[i] = [i]; }
    for (j = 1; j <= b.length; j++) { m[0][j] = j; }
    for (i = 1; i <= a.length; i++) for (j = 1; j <= b.length; j++)
      m[i][j] = Math.min(m[i - 1][j] + 1, m[i][j - 1] + 1, m[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    return m[a.length][b.length];
  }
  function toonHint(v) {
    var cel = v.voornaam.parentNode;
    var oud = cel.querySelector('.sugg-hint'); if (oud) oud.remove();
    var n = norm(v.naam.value), vn = norm(v.voornaam.value);
    if (!n || !vn) return;
    var exact = data.some(function (a) { return norm(a.naam) === n && norm(a.voornaam) === vn; });
    var hint = document.createElement('div'); hint.className = 'sugg-hint';
    if (exact) {
      hint.classList.add('bekend'); hint.textContent = '✓ bekende atleet';
    } else {
      var doel = n + ' ' + vn, beste = null, bd = 99;
      data.forEach(function (a) {
        var d = afstand(doel, norm(a.naam) + ' ' + norm(a.voornaam));
        if (d < bd) { bd = d; beste = a; }
      });
      if (beste && bd <= Math.max(2, Math.floor(doel.length / 6))) {
        hint.appendChild(document.createTextNode('Bedoelde u '));
        var knop = document.createElement('button');
        knop.type = 'button'; knop.className = 'sugg-knop';
        knop.textContent = beste.naam + ' ' + beste.voornaam;
        knop.addEventListener('click', function () {
          v.naam.value = beste.naam; v.voornaam.value = beste.voornaam; toonHint(v);
        });
        hint.appendChild(knop); hint.appendChild(document.createTextNode('? Anders wordt dit een nieuwe atleet.'));
      } else {
        hint.classList.add('nieuw'); hint.textContent = 'Nieuwe atleet (nog niet in de database)';
      }
    }
    cel.appendChild(hint);
  }

  function isVeld(t) {
    return t && t.matches && t.matches('input[name="naam[]"], input[name="voornaam[]"]');
  }
  document.addEventListener('input', function (e) {
    if (!isVeld(e.target)) return;
    toon(e.target);
    var h = e.target.closest('tr').querySelector('.sugg-hint'); if (h) h.remove();
  });
  document.addEventListener('focusin', function (e) { if (isVeld(e.target) && e.target.value) toon(e.target); });
  document.addEventListener('focusout', function (e) {
    if (!isVeld(e.target)) return;
    setTimeout(function () {
      sluit();
      var rij = e.target.closest('tr');
      if (rij && !rij.contains(document.activeElement)) toonHint(rijVelden(e.target));
    }, 120);
  });
  document.addEventListener('keydown', function (e) {
    if (!isVeld(e.target) || lijst.hidden) return;
    if (e.key === 'ArrowDown') { actief = (actief + 1) % items.length; markeer(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { actief = (actief - 1 + items.length) % items.length; markeer(); e.preventDefault(); }
    else if (e.key === 'Enter' && actief >= 0) { kies(items[actief]); e.preventDefault(); }
    else if (e.key === 'Escape') { sluit(); }
  });
  window.addEventListener('scroll', sluit, true);

  // Bestaande rijen (bv. bij "Oefencross wijzigen") meteen van een hint voorzien
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('input[name="naam[]"]').forEach(function (i) {
      if (i.value) toonHint(rijVelden(i));
    });
  });
})();
