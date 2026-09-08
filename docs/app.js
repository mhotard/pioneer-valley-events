import { buildCalendarCells, filterEvents, groupEventsByDate } from './event-data.js';

/* ============================================================
   Pioneer Valley Events — App
   ============================================================ */

const state = {
  events: [],
  view: 'list',
  filters: { q: '', dateFrom: '', dateTo: '', category: '', town: '', source: '' },
  calendarMonth: null, // Date object for calendar display
  calendarSelectedDay: null, // 'YYYY-MM-DD'
};

/* ---- Boot ---- */
document.addEventListener('DOMContentLoaded', async () => {
  state.calendarMonth = new Date();
  state.calendarMonth.setDate(1);

  await loadEvents();
  populateSourceFilter();
  populateTownFilter();
  setupFilters();
  setupViewSwitcher();
  setupModal();
  setupEventInteractions();
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

/* ---- Source dropdown (dynamic) ---- */
function populateSourceFilter() {
  const sel = document.getElementById('source-filter');
  const sources = [...new Set(state.events.map(e => e.source).filter(Boolean))].sort();
  sources.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s;
    opt.textContent = s;
    sel.appendChild(opt);
  });
}

/* ---- Town dropdown (dynamic — the data has far more towns than any
       hardcoded list; harriers races especially add small towns) ---- */
function populateTownFilter() {
  const sel = document.getElementById('town-filter');
  const towns = [...new Set(state.events.map(e => e.town).filter(Boolean))].sort();
  towns.forEach(t => {
    const opt = document.createElement('option');
    opt.value = t;
    opt.textContent = t === 'Pioneer Valley' ? 'Regionwide' : t;
    sel.appendChild(opt);
  });
}

/* ---- Filters ---- */
function setupFilters() {
  const search = document.getElementById('search');
  const dateFrom = document.getElementById('date-from');
  const dateTo = document.getElementById('date-to');
  const catFilter = document.getElementById('category-filter');
  const townFilter = document.getElementById('town-filter');
  const sourceFilter = document.getElementById('source-filter');
  const clearBtn = document.getElementById('clear-filters');

  search.addEventListener('input', () => { state.filters.q = search.value.trim(); render(); });
  dateFrom.addEventListener('change', () => { state.filters.dateFrom = dateFrom.value; render(); });
  dateTo.addEventListener('change', () => { state.filters.dateTo = dateTo.value; render(); });
  catFilter.addEventListener('change', () => { state.filters.category = catFilter.value; render(); });
  townFilter.addEventListener('change', () => { state.filters.town = townFilter.value; render(); });
  sourceFilter.addEventListener('change', () => { state.filters.source = sourceFilter.value; render(); });

  clearBtn.addEventListener('click', () => {
    search.value = '';
    dateFrom.value = '';
    dateTo.value = '';
    catFilter.value = '';
    townFilter.value = '';
    sourceFilter.value = '';
    state.filters = { q: '', dateFrom: '', dateTo: '', category: '', town: '', source: '' };
    render();
  });
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
  const events = filterEvents(state.events, state.filters);
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

  const byDate = groupEventsByDate(events);

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

  const byDate = groupEventsByDate(events);
  const cells = buildCalendarCells(year, mo);

  const monthLabel = month.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  const todayStr = toDateStr(new Date());

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

  for (const cell of cells) {
    if (!cell.inCurrentMonth) {
      html += `<div class="cal-day other-month"><div class="cal-day-num">${cell.day}</div></div>`;
      continue;
    }

    const dayEvents = byDate[cell.date] || [];
    const isToday = cell.date === todayStr;
    const isSelected = cell.date === state.calendarSelectedDay;
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
      <div class="${classes}" data-date="${cell.date}">
        <div class="cal-day-num">${cell.day}</div>
        <div class="cal-events">${pillsHtml}${more}</div>
      </div>`;
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
}

/* ---- Stable delegated interactions ---- */
function setupEventInteractions(openEvent = openModal) {
  const container = document.getElementById('events-container');

  container.addEventListener('click', event => {
    const nav = event.target.closest('#cal-prev, #cal-next, #cal-today');
    if (nav && container.contains(nav)) {
      const month = state.calendarMonth;
      if (nav.id === 'cal-prev') {
        state.calendarMonth = new Date(month.getFullYear(), month.getMonth() - 1, 1);
      } else if (nav.id === 'cal-next') {
        state.calendarMonth = new Date(month.getFullYear(), month.getMonth() + 1, 1);
      } else {
        state.calendarMonth = new Date();
        state.calendarMonth.setDate(1);
      }
      state.calendarSelectedDay = null;
      render();
      return;
    }

    const eventTarget = event.target.closest('.list-item, .card, .cal-pill');
    if (eventTarget && container.contains(eventTarget) && eventTarget.dataset.id) {
      const visibleEvents = filterEvents(state.events, state.filters);
      if (visibleEvents.some(item => item.id === eventTarget.dataset.id)) {
        openEvent(eventTarget.dataset.id);
      }
      return;
    }

    const day = event.target.closest('.cal-day:not(.other-month)');
    if (!day || !container.contains(day)) return;

    const byDate = groupEventsByDate(filterEvents(state.events, state.filters));
    const dayEvents = byDate[day.dataset.date] || [];
    if (dayEvents.length === 1) {
      openEvent(dayEvents[0].id);
    } else if (dayEvents.length > 1) {
      state.calendarSelectedDay = state.calendarSelectedDay === day.dataset.date
        ? null
        : day.dataset.date;
      render();
    }
  });

  container.addEventListener('keydown', event => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const eventTarget = event.target.closest('.list-item, .card');
    if (!eventTarget || !container.contains(eventTarget) || !eventTarget.dataset.id) return;

    event.preventDefault();
    const visibleEvents = filterEvents(state.events, state.filters);
    if (visibleEvents.some(item => item.id === eventTarget.dataset.id)) {
      openEvent(eventTarget.dataset.id);
    }
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
