// POP·FIT — preview e-commerce de bracelets pour Swatch x Audemars Piguet Royal Pop.

const COLORWAYS = [
  { id: 'otto-rosso',   name: 'Otto Rosso',   a: '#E63946', b: '#F4A6B8', label: 'Rouge & rose' },
  { id: 'huit-blanc',   name: 'Huit Blanc',   a: '#F5F5F0', b: '#1976D2', label: 'Blanc arc-en-ciel', rainbow: true },
  { id: 'green-eight',  name: 'Green Eight',  a: '#2E7D32', b: '#A5D6A7', label: 'Vert & vert clair' },
  { id: 'blaue-acht',   name: 'Blaue Acht',   a: '#C6FF00', b: '#81D4FA', label: 'Lime & bleu ciel' },
  { id: 'orenji-hachi', name: 'Orenji Hachi', a: '#0D1B4C', b: '#FF8A33', label: 'Marine & orange' },
  { id: 'lan-ba',       name: 'Lan Ba',       a: '#4FC3F7', b: '#1976D2', label: 'Bleu ciel & bleu' },
  { id: 'ocho-negro',   name: 'Ocho Negro',   a: '#111111', b: '#F5F5F0', label: 'Noir & blanc' },
  { id: 'otg-roz',      name: 'Otg Roz',      a: '#FF80AB', b: '#FFD54F', c: '#26A69A', label: 'Rose, jaune & teal' },
];

const BRACELETS = [
  { id: 'nato',     name: 'NATO tissé',           price: 49 },
  { id: 'metal',    name: 'Maillons octogonaux',  price: 89 },
  { id: 'silicone', name: 'Silicone bioceramic',  price: 59 },
];

const RAINBOW = ['#E63946', '#FF8A33', '#FFD54F', '#A5D6A7', '#4FC3F7', '#1976D2', '#FF80AB'];

const STORE_KEY = 'popfit.preorders';

// State filtres
const state = {
  bracelets: new Set(),  // vide = tous
  colorways: new Set(),
};

// ───────────────────────── SVG generation ─────────────────────────

function octagonPoints(cx, cy, r) {
  const pts = [];
  for (let i = 0; i < 8; i++) {
    const angle = (Math.PI / 8) + (i * Math.PI / 4);
    pts.push(`${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`);
  }
  return pts.join(' ');
}

function watchHeadSVG(cx, cy, r, cw) {
  const inner = r * 0.78;
  const dial = cw.id === 'ocho-negro' ? '#F5F5F0' : (cw.id === 'huit-blanc' ? '#F5F5F0' : '#F5F5F0');
  const bezel = cw.a;
  const accent = cw.id === 'huit-blanc' ? '#111' : cw.b;
  const screwR = r * 0.06;
  const screws = [];
  for (let i = 0; i < 8; i++) {
    const angle = (Math.PI / 8) + (i * Math.PI / 4);
    const sx = cx + (r * 0.86) * Math.cos(angle);
    const sy = cy + (r * 0.86) * Math.sin(angle);
    const col = cw.rainbow ? RAINBOW[i % RAINBOW.length] : '#111';
    screws.push(`<circle cx="${sx}" cy="${sy}" r="${screwR}" fill="${col}"/>`);
  }
  return `
    <polygon points="${octagonPoints(cx, cy, r)}" fill="${bezel}" stroke="#111" stroke-width="1.5"/>
    <polygon points="${octagonPoints(cx, cy, inner)}" fill="${dial}" stroke="#111" stroke-width="1"/>
    ${screws.join('')}
    <line x1="${cx}" y1="${cy}" x2="${cx}" y2="${cy - inner * 0.6}" stroke="${accent}" stroke-width="2.5" stroke-linecap="round"/>
    <line x1="${cx}" y1="${cy}" x2="${cx + inner * 0.45}" y2="${cy}" stroke="#111" stroke-width="2" stroke-linecap="round"/>
    <circle cx="${cx}" cy="${cy}" r="2.5" fill="#111"/>
  `;
}

function renderBraceletSVG(bracelet, cw) {
  // viewBox 320x240, watch head au centre (160,120), bracelet horizontal
  const cx = 160, cy = 120, r = 46;
  const top = cy - r - 4, bot = cy + r + 4;
  const stripeBg = cw.id === 'huit-blanc' ? '#F5F5F0' : cw.a;
  const stripeFg = cw.id === 'huit-blanc' ? '#1976D2' : cw.b;
  const third = cw.c;

  let strap = '';
  if (bracelet.id === 'nato') {
    // bandes tissées avec 2-3 rayures
    const stripeColors = third ? [cw.a, cw.b, third, cw.a, cw.b, third] : [stripeBg, stripeFg, stripeBg, stripeFg, stripeBg];
    const segments = [];
    const stripeH = (bot - top) / stripeColors.length;
    for (let i = 0; i < stripeColors.length; i++) {
      const y = top + i * stripeH;
      // côté gauche
      segments.push(`<rect x="6" y="${y}" width="${cx - r - 6}" height="${stripeH}" fill="${stripeColors[i]}"/>`);
      segments.push(`<rect x="${cx + r}" y="${y}" width="${320 - cx - r - 6}" height="${stripeH}" fill="${stripeColors[i]}"/>`);
    }
    // texture tissée (petites lignes verticales)
    const weave = [];
    for (let x = 8; x < 320 - 8; x += 6) {
      if (x > cx - r - 2 && x < cx + r + 2) continue;
      weave.push(`<line x1="${x}" y1="${top}" x2="${x}" y2="${bot}" stroke="rgba(0,0,0,0.08)" stroke-width="1"/>`);
    }
    strap = segments.join('') + weave.join('') +
      `<rect x="4" y="${top - 2}" width="${cx - r - 4}" height="${bot - top + 4}" fill="none" stroke="#111" stroke-width="1.4" rx="4"/>` +
      `<rect x="${cx + r}" y="${top - 2}" width="${320 - cx - r - 4}" height="${bot - top + 4}" fill="none" stroke="#111" stroke-width="1.4" rx="4"/>`;
  } else if (bracelet.id === 'metal') {
    // maillons octogonaux successifs
    const links = [];
    const linkW = 28, gap = 2;
    const linkH = bot - top - 4;
    const drawLinks = (startX, endX, dir) => {
      for (let x = startX; (dir > 0 ? x < endX : x > endX); x += dir * (linkW + gap)) {
        const lx = dir > 0 ? x : x - linkW;
        const fill = (Math.round((lx - 4) / (linkW + gap)) % 2 === 0) ? cw.a : cw.b;
        // octogone allongé
        const pts = [
          `${lx + 6},${top + 2}`,
          `${lx + linkW - 6},${top + 2}`,
          `${lx + linkW},${top + 2 + 6}`,
          `${lx + linkW},${top + 2 + linkH - 6}`,
          `${lx + linkW - 6},${top + 2 + linkH}`,
          `${lx + 6},${top + 2 + linkH}`,
          `${lx},${top + 2 + linkH - 6}`,
          `${lx},${top + 2 + 6}`,
        ].join(' ');
        links.push(`<polygon points="${pts}" fill="${fill}" stroke="#111" stroke-width="1.2"/>`);
      }
    };
    drawLinks(6, cx - r, 1);
    drawLinks(320 - 6, cx + r, -1);
    strap = links.join('');
  } else {
    // silicone : bande lisse, dégradé entre a et b, avec petite côte centrale
    const gradLeft = `gradL-${cw.id}`;
    const gradRight = `gradR-${cw.id}`;
    strap = `
      <defs>
        <linearGradient id="${gradLeft}" x1="0" x2="1">
          <stop offset="0" stop-color="${cw.b}"/>
          <stop offset="1" stop-color="${cw.a}"/>
        </linearGradient>
        <linearGradient id="${gradRight}" x1="0" x2="1">
          <stop offset="0" stop-color="${cw.a}"/>
          <stop offset="1" stop-color="${cw.b}"/>
        </linearGradient>
      </defs>
      <rect x="6" y="${top}" width="${cx - r - 6}" height="${bot - top}" fill="url(#${gradLeft})" stroke="#111" stroke-width="1.4" rx="12"/>
      <rect x="${cx + r}" y="${top}" width="${320 - cx - r - 6}" height="${bot - top}" fill="url(#${gradRight})" stroke="#111" stroke-width="1.4" rx="12"/>
      <line x1="6" y1="${cy}" x2="${cx - r - 6}" y2="${cy}" stroke="rgba(0,0,0,0.18)" stroke-width="1.2"/>
      <line x1="${cx + r}" y1="${cy}" x2="${320 - 6}" y2="${cy}" stroke="rgba(0,0,0,0.18)" stroke-width="1.2"/>
    `;
    if (third) {
      strap += `<rect x="6" y="${cy - 3}" width="${cx - r - 6}" height="6" fill="${third}" opacity="0.6"/>`;
      strap += `<rect x="${cx + r}" y="${cy - 3}" width="${320 - cx - r - 6}" height="6" fill="${third}" opacity="0.6"/>`;
    }
  }

  // boucle à droite
  const buckle = `<rect x="${320 - 16}" y="${cy - 12}" width="10" height="24" fill="#cfcfcf" stroke="#111" stroke-width="1"/>`;

  return `
    <svg viewBox="0 0 320 240" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${bracelet.name} colorway ${cw.name}">
      ${strap}
      ${buckle}
      ${watchHeadSVG(cx, cy, r, cw)}
    </svg>
  `;
}

// ───────────────────────── Catalog ─────────────────────────

function buildSKUs() {
  const skus = [];
  for (const b of BRACELETS) {
    for (const cw of COLORWAYS) {
      skus.push({ id: `${b.id}-${cw.id}`, bracelet: b, colorway: cw, price: b.price });
    }
  }
  return skus;
}

const SKUS = buildSKUs();

function passesFilters(sku) {
  if (state.bracelets.size && !state.bracelets.has(sku.bracelet.id)) return false;
  if (state.colorways.size && !state.colorways.has(sku.colorway.id)) return false;
  return true;
}

function renderCatalog() {
  const grid = document.getElementById('catalogGrid');
  const empty = document.getElementById('emptyState');
  const visible = SKUS.filter(passesFilters);
  grid.innerHTML = visible.map(sku => `
    <article class="card" data-sku="${sku.id}">
      <div class="card-art">${renderBraceletSVG(sku.bracelet, sku.colorway)}</div>
      <div class="card-meta">
        <div>
          <div class="card-name">${sku.colorway.name}</div>
          <div class="card-type">${sku.bracelet.name}</div>
        </div>
        <div class="card-price">${sku.price}&nbsp;€</div>
      </div>
      <button class="card-cta" type="button" data-preorder="${sku.id}">Précommander</button>
    </article>
  `).join('');
  empty.hidden = visible.length !== 0;
}

function renderFilters() {
  const bFilters = document.getElementById('braceletFilters');
  bFilters.innerHTML = BRACELETS.map(b => `
    <button type="button" class="chip" data-bracelet="${b.id}">${b.name}</button>
  `).join('');
  const cFilters = document.getElementById('colorwayFilters');
  cFilters.innerHTML = COLORWAYS.map(cw => `
    <button type="button" class="chip" data-colorway="${cw.id}" title="${cw.label}">
      <span class="chip-dot" style="background: ${cw.rainbow ? 'linear-gradient(45deg,#E63946,#FFD54F,#4FC3F7,#FF80AB)' : `linear-gradient(135deg, ${cw.a} 0%, ${cw.a} 50%, ${cw.b} 50%, ${cw.b} 100%)`};"></span>
      ${cw.name}
    </button>
  `).join('');
}

function bindFilterEvents() {
  document.getElementById('braceletFilters').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-bracelet]');
    if (!btn) return;
    const id = btn.dataset.bracelet;
    if (state.bracelets.has(id)) state.bracelets.delete(id); else state.bracelets.add(id);
    btn.classList.toggle('is-active');
    renderCatalog();
  });
  document.getElementById('colorwayFilters').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-colorway]');
    if (!btn) return;
    const id = btn.dataset.colorway;
    if (state.colorways.has(id)) state.colorways.delete(id); else state.colorways.add(id);
    btn.classList.toggle('is-active');
    renderCatalog();
  });
  document.getElementById('resetFilters').addEventListener('click', () => {
    state.bracelets.clear();
    state.colorways.clear();
    document.querySelectorAll('.chip.is-active').forEach(c => c.classList.remove('is-active'));
    renderCatalog();
  });
}

// ───────────────────────── Preorder modal ─────────────────────────

let currentSku = null;

function openPreorderModal(skuId) {
  const sku = SKUS.find(s => s.id === skuId);
  if (!sku) return;
  currentSku = sku;
  const summary = document.getElementById('preorderSummary');
  summary.innerHTML = `
    ${renderBraceletSVG(sku.bracelet, sku.colorway)}
    <div class="sum-text">
      <span class="sum-name">${sku.colorway.name}</span>
      <span class="sum-sub">${sku.bracelet.name}</span>
    </div>
    <span class="sum-price">${sku.price}&nbsp;€</span>
  `;
  const dlg = document.getElementById('preorderModal');
  const form = document.getElementById('preorderForm');
  form.reset();
  dlg.showModal();
}

function savePreorder({ sku, size, email }) {
  const all = readPreorders();
  all.push({
    id: `${sku.id}-${Date.now()}`,
    skuId: sku.id,
    braceletId: sku.bracelet.id,
    colorwayId: sku.colorway.id,
    size, email, price: sku.price,
    at: new Date().toISOString(),
  });
  localStorage.setItem(STORE_KEY, JSON.stringify(all));
}

function readPreorders() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY) || '[]'); }
  catch { return []; }
}

function bindPreorderEvents() {
  document.getElementById('catalogGrid').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-preorder]');
    if (!btn) return;
    openPreorderModal(btn.dataset.preorder);
  });

  document.getElementById('preorderForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    if (!form.reportValidity()) return;
    const data = new FormData(form);
    if (!currentSku) return;
    savePreorder({
      sku: currentSku,
      size: data.get('size'),
      email: data.get('email'),
    });
    document.getElementById('preorderModal').close();
    showToast(`Précommande enregistrée pour ${currentSku.colorway.name} (${currentSku.bracelet.name})`);
    currentSku = null;
  });

  document.querySelectorAll('.modal [data-close]').forEach(btn => {
    btn.addEventListener('click', () => btn.closest('dialog').close());
  });

  document.getElementById('myPreordersLink').addEventListener('click', (e) => {
    e.preventDefault();
    showPreordersList();
  });
}

function showPreordersList() {
  const list = readPreorders();
  const target = document.getElementById('preordersList');
  if (!list.length) {
    target.innerHTML = `<p class="po-empty">Aucune précommande pour l'instant.</p>`;
  } else {
    target.innerHTML = list.map(item => {
      const cw = COLORWAYS.find(c => c.id === item.colorwayId);
      const b = BRACELETS.find(br => br.id === item.braceletId);
      if (!cw || !b) return '';
      return `
        <div class="po-item">
          ${renderBraceletSVG(b, cw)}
          <div class="po-text">
            <strong>${cw.name}</strong> · ${b.name}<br/>
            Taille ${item.size} · ${item.email}<br/>
            <span style="color: var(--muted)">${new Date(item.at).toLocaleString('fr-FR')} — ${item.price}&nbsp;€</span>
          </div>
        </div>
      `;
    }).join('');
  }
  document.getElementById('preordersListModal').showModal();
}

// ───────────────────────── Toast ─────────────────────────

let toastTimer;
function showToast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('is-visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('is-visible'), 3200);
}

// ───────────────────────── Hero color cycle ─────────────────────────

function cycleHeroAccent() {
  const cycleColors = COLORWAYS.map(cw => cw.id === 'huit-blanc' ? '#1976D2' : cw.a);
  let i = 0;
  const apply = () => {
    document.documentElement.style.setProperty('--accent', cycleColors[i]);
    i = (i + 1) % cycleColors.length;
  };
  apply();
  setInterval(apply, 4000);
}

// ───────────────────────── Init ─────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  renderFilters();
  renderCatalog();
  bindFilterEvents();
  bindPreorderEvents();
  cycleHeroAccent();
});
