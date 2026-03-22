/* ============================================================
   Pioneer Valley Events — App
   ============================================================ */

const state = {
  events: [],
  view: 'list',
  filters: { q: '', dateFrom: '', dateTo: '', category: '', town: '' },
  calendarMonth: null, // Date object for calendar display
  calendarSelectedDay: null, // 'YYYY-MM-DD'
};

/* ---- Boot ---- */
document.addEventListener('DOMContentLoaded', async () => {
  state.calendarMonth = new Date();
  state.calendarMonth.setDate(1);

  await loadEvents();
  setupFilters();
  setupViewSwitcher();
  setupModal();
  render();
});

/* ---- Data ---- */
async function loadEvents() {
  try {
    const res = await fetch('data/events.json');
    const data = await res.json();
    state.events = data.events || [];
    const gen = document.getElementById('last-updated');
    if (gen && data.generated) {
      gen.textContent = `Updated ${formatDateShort(data.generated)}`;
    }
  } catch (e) {
    console.error('Failed to load events.json:', e);
    state.events = [];
  }
}

/* ---- Filters ---- */
function setupFilters() {
  const search = document.getElementById('search');
  const dateFrom = document.getElementById('date-from');
  const dateTo = document.getElementById('date-to');
  const catFilter = document.getElementById('category-filter');
  const townFilter = document.getElementById('town-filter');
  const clearBtn = document.getElementById('clear-filters');

  search.addEventListener('input', () => { state.filters.q = search.value.trim(); render(); });
  dateFrom.addEventListener('change', () => { state.filters.dateFrom = dateFrom.value; render(); });
  dateTo.addEventListener('change', () => { state.filters.dateTo = dateTo.value; render(); });
  catFilter.addEventListener('change', () => { state.filters.category = catFilter.value; render(); });
  townFilter.addEventListener('change', () => { state.filters.town = townFilter.value; render(); });

  clearBtn.addEventListener('click', () => {
    search.value = '';
    dateFrom.value = '';
    dateTo.value = '';
    catFilter.value = '';
    townFilter.value = '';
    state.filters = { q: '', dateFrom: '', dateTo: '', category: '', town: '' };
    render();
  });
}

function applyFilters() {
  const { q, dateFrom, dateTo, category, town } = state.filters;
  const ql = q.toLowerCase();

  return state.events
    .filter(e => {
      if (q && !e.title.toLowerCase().includes(ql) &&
                !((e.description || '').toLowerCase().includes(ql)) &&
                !((e.venue || '').toLowerCase().includes(ql))) return false;
      if (dateFrom && e.date < dateFrom) return false;
      if (dateTo && e.date > dateTo) return false;
      if (category && e.category !== category) return false;
      if (town && e.town !== town) return false;
      return true;
    })
    .sort((a, b) => a.date.localeCompare(b.date) || (a.time || '').localeCompare(b.time || ''));
}

/* ---- View Switcher ---- */
function setupViewSwitcher() {
  document.querySelectorAll('.view-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      state.view = btn.dataset.view;
      document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.calendarSelectedDay = null;
      render();
    });
  });
}

/* ---- Render ---- */
function render() {
  const events = applyFilters();
  const count = document.getElementById('result-count');
  count.textContent = `${events.length} event${events.length !== 1 ? 's' : ''}`;

  const container = document.getElementById('events-container');
  if (state.view === 'list')     renderList(container, events);
  else if (state.view === 'cards')    renderCards(container, events);
  else if (state.view === 'calendar') renderCalendar(container, events);
}

/* ============================================================
   LIST VIEW
   ============================================================ */
function renderList(container, events) {
  if (!events.length) { container.innerHTML = emptyState(); return; }

  // Group by date
  const byDate = {};
  events.forEach(e => {
    if (!byDate[e.date]) byDate[e.date] = [];
    byDate[e.date].push(e);
  });

  let html = '<div class="list-view">';
  for (const date of Object.keys(byDate).sort()) {
    html += `
      <div class="date-group">
        <div class="date-group-header">${formatDateLong(date)}</div>
        <div class="date-events">
          ${byDate[date].map(e => listItem(e)).join('')}
        </div>
      </div>`;
  }
  html += '</div>';
  container.innerHTML = html;
  attachEventListeners(container);
}

function listItem(e) {
  return `
    <div class="list-item" data-id="${e.id}" role="button" tabindex="0">
      <div class="list-item-time">${e.time || 'TBD'}</div>
      <div class="list-item-body">
        <div class="list-item-title">${esc(e.title)}</div>
        <div class="list-item-meta">
          <span>${esc(e.venue)}</span>
          <span class="dot">${esc(e.town)}</span>
          <span class="dot"><span class="badge badge-${e.category}">${labelFor(e.category)}</span></span>
        </div>
      </div>
    </div>`;
}

/* ============================================================
   CARDS VIEW
   ============================================================ */
function renderCards(container, events) {
  if (!events.length) { container.innerHTML = emptyState(); return; }

  let html = '<div class="cards-grid">';
  html += events.map(e => card(e)).join('');
  html += '</div>';
  container.innerHTML = html;
  attachEventListeners(container);
}

function card(e) {
  const imgHtml = e.image_url
    ? `<div class="card-img"><img src="${esc(e.image_url)}" alt="${esc(e.title)}" loading="lazy"></div>`
    : `<div class="card-placeholder">${placeholderIcon(e.category)}</div>`;

  return `
    <div class="card" data-id="${e.id}" role="button" tabindex="0">
      ${imgHtml}
      <div class="card-body">
        <span class="badge badge-${e.category}">${labelFor(e.category)}</span>
        <div class="card-title">${esc(e.title)}</div>
        <div class="card-datetime">${formatDateShort(e.date)} &middot; ${e.time || 'TBD'}</div>
        <div class="card-venue">${esc(e.venue)} &middot; ${esc(e.town)}</div>
        ${e.description ? `<div class="card-desc">${esc(truncate(e.description, 110))}</div>` : ''}
      </div>
    </div>`;
}

/* ============================================================
   CALENDAR VIEW
   ============================================================ */
function renderCalendar(container, events) {
  const month = state.calendarMonth;
  const year = month.getFullYear();
  const mo = month.getMonth();

  // Build index: date string -> events[]
  const byDate = {};
  events.forEach(e => {
    if (!byDate[e.date]) byDate[e.date] = [];
    byDate[e.date].push(e);
  });

  const monthLabel = month.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  const todayStr = toDateStr(new Date());

  // First day of month and how many days
  const firstDay = new Date(year, mo, 1).getDay(); // 0=Sun
  const daysInMonth = new Date(year, mo + 1, 0).getDate();
  const daysInPrev = new Date(year, mo, 0).getDate();

  const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  let html = `
    <div class="calendar-view">
      <div class="calendar-nav">
        <button class="cal-nav-btn" id="cal-prev" aria-label="Previous month">&#8249;</button>
        <div class="cal-month-label">${monthLabel}</div>
        <button class="cal-today-btn" id="cal-today">Today</button>
        <button class="cal-nav-btn" id="cal-next" aria-label="Next month">&#8250;</button>
      </div>
      <div class="calendar-grid">
        <div class="cal-day-names">
          ${DAY_NAMES.map(d => `<div class="cal-day-name">${d}</div>`).join('')}
        </div>
        <div class="cal-days">`;

  // Leading days from previous month
  for (let i = firstDay - 1; i >= 0; i--) {
    html += `<div class="cal-day other-month"><div class="cal-day-num">${daysInPrev - i}</div></div>`;
  }

  // Days of this month
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${year}-${String(mo + 1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    const dayEvents = byDate[dateStr] || [];
    const isToday = dateStr === todayStr;
    const isSelected = dateStr === state.calendarSelectedDay;
    const hasEvents = dayEvents.length > 0;

    const classes = [
      'cal-day',
      isToday ? 'today' : '',
      isSelected ? 'selected' : '',
      hasEvents ? 'has-events' : '',
    ].filter(Boolean).join(' ');

    const MAX_PILLS = 3;
    const pillsHtml = dayEvents.slice(0, MAX_PILLS).map(e =>
      `<div class="cal-pill pill-${e.category}" data-id="${e.id}">${esc(e.title)}</div>`
    ).join('');
    const more = dayEvents.length > MAX_PILLS
      ? `<div class="cal-more">+${dayEvents.length - MAX_PILLS} more</div>` : '';

    html += `
      <div class="${classes}" data-date="${dateStr}" data-id="${dayEvents.length === 1 ? dayEvents[0].id : ''}">
        <div class="cal-day-num">${d}</div>
        <div class="cal-events">${pillsHtml}${more}</div>
      </div>`;
  }

  // Trailing days to fill grid
  const totalCells = Math.ceil((firstDay + daysInMonth) / 7) * 7;
  for (let i = 1; i <= totalCells - firstDay - daysInMonth; i++) {
    html += `<div class="cal-day other-month"><div class="cal-day-num">${i}</div></div>`;
  }

  html += `</div></div>`;

  // Selected day detail panel
  if (state.calendarSelectedDay && byDate[state.calendarSelectedDay]) {
    const sel = byDate[state.calendarSelectedDay];
    html += `
      <div class="cal-day-detail">
        <h3>${formatDateLong(state.calendarSelectedDay)} &mdash; ${sel.length} event${sel.length !== 1 ? 's' : ''}</h3>
        <div class="date-events">${sel.map(e => listItem(e)).join('')}</div>
      </div>`;
  }

  html += '</div>';
  container.innerHTML = html;

  // Calendar nav buttons
  document.getElementById('cal-prev').addEventListener('click', () => {
    state.calendarMonth = new Date(year, mo - 1, 1);
    state.calendarSelectedDay = null;
    render();
  });
  document.getElementById('cal-next').addEventListener('click', () => {
    state.calendarMonth = new Date(year, mo + 1, 1);
    state.calendarSelectedDay = null;
    render();
  });
  document.getElementById('cal-today').addEventListener('click', () => {
    state.calendarMonth = new Date();
    state.calendarMonth.setDate(1);
    state.calendarSelectedDay = null;
    render();
  });

  // Day click: single event → open modal, multiple → show detail panel
  container.querySelectorAll('.cal-day:not(.other-month)').forEach(cell => {
    cell.addEventListener('click', (ev) => {
      const dateStr = cell.dataset.date;
      const dayEvts = byDate[dateStr] || [];
      if (!dayEvts.length) return;

      // If clicking a pill, open that specific event
      const pill = ev.target.closest('.cal-pill');
      if (pill && pill.dataset.id) { openModal(pill.dataset.id); return; }

      if (dayEvts.length === 1) {
        openModal(dayEvts[0].id);
      } else {
        state.calendarSelectedDay = (state.calendarSelectedDay === dateStr) ? null : dateStr;
        render();
      }
    });
  });

  attachEventListeners(container);
}

/* ---- Event listeners for clickable items ---- */
function attachEventListeners(container) {
  container.querySelectorAll('[data-id]').forEach(el => {
    if (!el.dataset.id) return;
    // Skip calendar days (handled separately)
    if (el.classList.contains('cal-day')) return;
    const handler = () => openModal(el.dataset.id);
    el.addEventListener('click', handler);
    el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') handler(); });
  });
}

/* ============================================================
   MODAL
   ============================================================ */
function setupModal() {
  const overlay = document.getElementById('modal-overlay');
  const closeBtn = document.getElementById('modal-close');

  closeBtn.addEventListener('click', closeModal);
  overlay.addEventListener('click', e => { if (e.target === overlay) closeModal(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
}

function openModal(id) {
  const e = state.events.find(ev => ev.id === id);
  if (!e) return;

  const content = document.getElementById('modal-content');
  const timeStr = e.end_time ? `${e.time} – ${e.end_time}` : (e.time || 'Time TBD');

  content.innerHTML = `
    <div class="modal-category"><span class="badge badge-${e.category}">${labelFor(e.category)}</span></div>
    <div class="modal-title">${esc(e.title)}</div>
    <div class="modal-source">via ${esc(e.source || 'unknown')}</div>
    <div class="modal-meta">
      <div class="modal-meta-row">
        ${iconCal()}
        <span><strong>${formatDateLong(e.date)}</strong> &middot; ${esc(timeStr)}</span>
      </div>
      <div class="modal-meta-row">
        ${iconPin()}
        <span><strong>${esc(e.venue)}</strong>, ${esc(e.town)}${e.address ? `<br><small>${esc(e.address)}</small>` : ''}</span>
      </div>
    </div>
    ${e.description ? `<hr class="modal-divider"><p class="modal-description">${esc(e.description)}</p>` : ''}
    ${e.url ? `<a class="modal-link" href="${esc(e.url)}" target="_blank" rel="noopener">${iconExternal()} More info</a>` : ''}`;

  document.getElementById('modal-overlay').classList.remove('hidden');
  document.getElementById('modal-close').focus();
}

function closeModal() {
  document.getElementById('modal-overlay').classList.add('hidden');
}

/* ============================================================
   HELPERS
   ============================================================ */

function formatDateLong(dateStr) {
  const [y, m, d] = dateStr.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'
  });
}

function formatDateShort(dateStr) {
  const [y, m, d] = dateStr.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric'
  });
}

function toDateStr(date) {
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
}

function truncate(str, len) {
  return str.length > len ? str.slice(0, len).trimEnd() + '…' : str;
}

function esc(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;')
    .replace(/'/g,'&#39;');
}

function emptyState() {
  return `
    <div class="empty-state">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
      </svg>
      <p>No events match your filters.</p>
    </div>`;
}

const CATEGORY_LABELS = {
  music: 'Music',
  arts: 'Arts',
  film: 'Film',
  comedy: 'Comedy',
  community: 'Community',
  academia: 'Lecture',
  family: 'Family',
  food: 'Food',
  outdoor: 'Outdoor',
  festival: 'Festival',
};
function labelFor(cat) { return CATEGORY_LABELS[cat] || cat || ''; }

function placeholderIcon(category) {
  const icons = {
    music:    '<path d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"/>',
    film:     '<path d="m15 10 4.553-2.277A1 1 0 0 1 21 8.619v6.762a1 1 0 0 1-1.447.894L15 14M3 8a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    arts:     '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    default:  '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
  };
  const path = icons[category] || icons.default;
  return `<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${path}</svg>`;
}

function iconCal() {
  return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>`;
}

function iconPin() {
  return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>`;
}

function iconExternal() {
  return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>`;
}
