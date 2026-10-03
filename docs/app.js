import {
  browserStateParams, buildCalendarCells, dataFreshness, filterEvents,
  groupEventsByDate, quickDateRange, readBrowserState, regionToday,
} from './event-data.js';

/* ============================================================
   Pioneer Valley Events — App
   ============================================================ */

const state = {
  events: [],
  generated: null,
  loadFailed: false,
  view: 'list',
  dateChoice: 'upcoming',
  today: regionToday(),
  filters: { q: '', dateFrom: '', dateTo: '', category: '', town: '', source: '' },
  calendarMonth: null, // Date object for calendar display
  calendarSelectedDay: null, // 'YYYY-MM-DD'
};

/* ---- Boot ---- */
document.addEventListener('DOMContentLoaded', async () => {
  await loadEvents();
  // Reassess an open tab as the data ages, including when returning to it.
  setInterval(refreshDateStatus, 60 * 60 * 1000);
  document.addEventListener('visibilitychange', refreshDateStatus);
  populateSourceFilter();
  populateTownFilter();
  restoreBrowserState();
  setupFilterDisclosure();
  setupFilters();
  setupViewSwitcher();
  setupModal();
  setupEventInteractions();
  render();
  window.addEventListener('popstate', () => {
    closeModal();
    restoreBrowserState();
    render();
  });
});

/* ---- Data ---- */
async function loadEvents() {
  try {
    const res = await fetch('data/events.json', { cache: 'no-cache' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (!data || !Array.isArray(data.events)) throw new Error('Invalid events payload');
    state.events = data.events;
    state.generated = data.generated;
  } catch (e) {
    console.error('Failed to load events.json:', e);
    state.events = [];
    state.loadFailed = true;
  }
  updateDataStatus();
}

function updateDataStatus() {
  const updated = document.getElementById('last-updated');
  const warning = document.getElementById('data-warning');
  const freshness = dataFreshness(state.generated);
  warning.hidden = !state.loadFailed && freshness === 'current';

  if (state.loadFailed) {
    updated.textContent = 'Update unavailable';
    warning.textContent = 'Event listings could not be loaded. Please try again later.';
  } else if (freshness === 'unknown') {
    updated.textContent = 'Update date unverified';
    warning.textContent = 'The last event update date could not be verified. Listings may be out of date; confirm details with the event organizer.';
  } else {
    const label = formatDateShort(state.generated);
    updated.textContent = `${freshness === 'stale' ? 'Out of date · updated' : 'Updated'} ${label}`;
    warning.textContent = freshness === 'stale'
      ? `Event listings are out of date. Last updated ${label}; updates are scheduled weekly. Events may have passed or changed, and newer events may be missing. Confirm details with the event organizer.`
      : '';
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
function monthFromDate(date) {
  const [year, month] = date.split('-').map(Number);
  return new Date(year, month - 1, 1);
}

function restoreBrowserState() {
  const available = {};
  for (const key of ['category', 'town', 'source']) {
    available[key] = [...document.querySelectorAll(`#${key}-filter option`)].map(option => option.value);
  }
  const restored = readBrowserState(location.search, available);
  Object.assign(state, restored, { calendarMonth: monthFromDate(restored.calendarMonth) });
  syncControls();
}

function syncControls() {
  const controls = { q: 'search', dateFrom: 'date-from', dateTo: 'date-to', category: 'category-filter', town: 'town-filter', source: 'source-filter' };
  for (const [key, id] of Object.entries(controls)) document.getElementById(id).value = state.filters[key];
  document.querySelectorAll('[data-dates]').forEach(button => {
    const selected = button.dataset.dates === state.dateChoice;
    button.classList.toggle('active', selected);
    button.setAttribute('aria-pressed', String(selected));
  });
  document.querySelectorAll('.view-btn').forEach(button => {
    button.classList.toggle('active', button.dataset.view === state.view);
    button.setAttribute('aria-pressed', String(button.dataset.view === state.view));
  });
}

function updateBrowserState(replace = false) {
  const query = browserStateParams({ ...state, calendarMonth: toDateStr(state.calendarMonth) }, location.search);
  const url = `${location.pathname}${query ? '?' + query : ''}${location.hash}`;
  if (url !== location.pathname + location.search + location.hash) {
    history[replace ? 'replaceState' : 'pushState'](null, '', url);
  }
}

function applyDateChoice(choice) {
  state.dateChoice = choice;
  Object.assign(state.filters, quickDateRange(choice));
  state.calendarMonth = monthFromDate(state.filters.dateFrom || regionToday());
  state.calendarSelectedDay = null;
}

function resetFilters() {
  state.filters = { q: '', category: '', town: '', source: '' };
  applyDateChoice('upcoming');
  syncControls();
  updateBrowserState();
  render();
}

function refreshDateStatus() {
  updateDataStatus();
  const today = regionToday();
  if (today === state.today) return;
  state.today = today;
  if (state.dateChoice !== 'custom') {
    applyDateChoice(state.dateChoice);
    syncControls();
    updateBrowserState(true);
    render();
  }
}

function setupFilterDisclosure() {
  const toggle = document.getElementById('filters-toggle');
  const options = document.getElementById('filter-options');
  const mobile = matchMedia('(max-width: 700px)');
  let expanded = false;
  const update = () => {
    options.hidden = mobile.matches && !expanded;
    toggle.setAttribute('aria-expanded', String(!options.hidden));
  };
  toggle.addEventListener('click', () => { expanded = !expanded; update(); });
  mobile.addEventListener('change', () => {
    if (mobile.matches && options.contains(document.activeElement)) toggle.focus();
    update();
  });
  update();
}

function updateFilterSummary() {
  const labels = { upcoming: 'Upcoming', today: 'Today', week: 'Next 7 days', weekend: 'This weekend', all: 'All published dates' };
  const parts = [labels[state.dateChoice] || `${state.filters.dateFrom || 'Any start'} to ${state.filters.dateTo || 'any end'}`];
  if (state.filters.q) parts.push(`Search: ${state.filters.q}`);
  for (const key of ['category', 'town', 'source']) {
    if (state.filters[key]) {
      const control = document.getElementById(`${key}-filter`);
      parts.push(control.selectedOptions[0]?.textContent || state.filters[key]);
    }
  }
  document.getElementById('filter-summary').textContent = parts.join(' · ');
}

function setupFilters() {
  const controls = { q: 'search', dateFrom: 'date-from', dateTo: 'date-to', category: 'category-filter', town: 'town-filter', source: 'source-filter' };
  for (const [key, id] of Object.entries(controls)) {
    const control = document.getElementById(id);
    control.addEventListener(key === 'q' ? 'input' : 'change', () => {
      state.filters[key] = control.value.trim();
      if (key === 'dateFrom' || key === 'dateTo') {
        state.dateChoice = 'custom';
        state.calendarMonth = monthFromDate(state.filters.dateFrom || regionToday());
        state.calendarSelectedDay = null;
      }
      // Typing updates the current history entry; deliberate choices add one.
      if (key !== 'q') syncControls();
      updateBrowserState(key === 'q');
      render();
    });
  }
  document.querySelectorAll('[data-dates]').forEach(button => {
    button.addEventListener('click', () => {
      applyDateChoice(button.dataset.dates);
      syncControls();
      updateBrowserState();
      render();
    });
  });
  document.getElementById('clear-filters').addEventListener('click', resetFilters);
}

/* ---- View Switcher ---- */
function setupViewSwitcher() {
  document.querySelectorAll('.view-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      state.view = btn.dataset.view;
      state.calendarSelectedDay = null;
      syncControls();
      updateBrowserState();
      render();
    });
  });
}

/* ---- Render ---- */
function render() {
  updateFilterSummary();
  const events = filterEvents(state.events, state.filters);
  const count = document.getElementById('result-count');
  count.textContent = state.loadFailed
    ? 'Events unavailable'
    : `${events.length} event${events.length !== 1 ? 's' : ''}`;

  const container = document.getElementById('events-container');
  if (state.loadFailed) {
    container.innerHTML = '<div class="empty-state"><p>Event listings could not be loaded. Please try again later.</p></div>';
    return;
  }
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
    <div class="list-item" data-id="${esc(e.id)}" role="button" tabindex="0">
      <div class="list-item-time">${esc(e.time || 'TBD')}</div>
      <div class="list-item-body">
        <div class="list-item-title">${esc(e.title)}</div>
        <div class="list-item-meta">
          <span>${esc(e.venue)}</span>
          <span class="dot">${esc(e.town)}</span>
          <span class="dot"><span class="badge badge-${categoryFor(e.category)}">${labelFor(e.category)}</span></span>
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
  const imageURL = safeEventURL(e.image_url);
  const imgHtml = imageURL
    ? `<div class="card-img"><img src="${esc(imageURL)}" alt="${esc(e.title)}" loading="lazy"></div>`
    : `<div class="card-placeholder">${placeholderIcon(e.category)}</div>`;

  return `
    <div class="card" data-id="${esc(e.id)}" role="button" tabindex="0">
      ${imgHtml}
      <div class="card-body">
        <span class="badge badge-${categoryFor(e.category)}">${labelFor(e.category)}</span>
        <div class="card-title">${esc(e.title)}</div>
        <div class="card-datetime">${formatDateShort(e.date)} &middot; ${esc(e.time || 'TBD')}</div>
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
  const todayStr = regionToday();

  const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  let html = `${events.length ? '' : emptyState()}
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
      `<button class="cal-pill pill-${categoryFor(e.category)}" data-id="${esc(e.id)}" aria-label="${esc(e.title)}">${esc(e.title)}</button>`
    ).join('');
    const more = dayEvents.length > MAX_PILLS
      ? `<div class="cal-more">+${dayEvents.length - MAX_PILLS} more</div>` : '';

    html += `
      <div class="${classes}" data-date="${cell.date}">
        <button class="cal-day-num cal-day-select" aria-label="${formatDateLong(cell.date)}: ${dayEvents.length} event${dayEvents.length === 1 ? '' : 's'}" ${hasEvents ? '' : 'disabled'} ${dayEvents.length > 1 ? `aria-expanded="${isSelected}"` : ''}>${cell.day}</button>
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
    if (event.target.closest('#reset-results')) { resetFilters(); return; }
    if (event.target.closest('#show-all-dates')) {
      applyDateChoice('all'); syncControls(); updateBrowserState(); render(); return;
    }
    const nav = event.target.closest('#cal-prev, #cal-next, #cal-today');
    if (nav && container.contains(nav)) {
      const month = state.calendarMonth;
      if (nav.id === 'cal-prev') {
        state.calendarMonth = new Date(month.getFullYear(), month.getMonth() - 1, 1);
      } else if (nav.id === 'cal-next') {
        state.calendarMonth = new Date(month.getFullYear(), month.getMonth() + 1, 1);
      } else {
        state.calendarMonth = monthFromDate(regionToday());
      }
      state.calendarSelectedDay = null;
      updateBrowserState();
      render();
      document.getElementById(nav.id).focus();
      return;
    }

    const eventTarget = event.target.closest('.list-item, .card, .cal-pill');
    if (eventTarget && container.contains(eventTarget) && eventTarget.dataset.id) {
      const visibleEvents = filterEvents(state.events, state.filters);
      if (visibleEvents.some(item => item.id === eventTarget.dataset.id)) {
        openEvent(eventTarget.dataset.id, eventTarget);
      }
      return;
    }

    const day = event.target.closest('.cal-day:not(.other-month)');
    if (!day || !container.contains(day)) return;

    const byDate = groupEventsByDate(filterEvents(state.events, state.filters));
    const dayEvents = byDate[day.dataset.date] || [];
    if (dayEvents.length === 1) {
      openEvent(dayEvents[0].id, day.querySelector('.cal-day-select'));
    } else if (dayEvents.length > 1) {
      state.calendarSelectedDay = state.calendarSelectedDay === day.dataset.date
        ? null
        : day.dataset.date;
      updateBrowserState();
      render();
      container.querySelector(`.cal-day[data-date="${day.dataset.date}"] .cal-day-select`).focus();
    }
  });

  container.addEventListener('keydown', event => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const eventTarget = event.target.closest('.list-item, .card');
    if (!eventTarget || !container.contains(eventTarget) || !eventTarget.dataset.id) return;

    event.preventDefault();
    const visibleEvents = filterEvents(state.events, state.filters);
    if (visibleEvents.some(item => item.id === eventTarget.dataset.id)) {
      openEvent(eventTarget.dataset.id, eventTarget);
    }
  });
}

/* ============================================================
   MODAL
   ============================================================ */
let modalOpener = null;
let modalBackground = [];

function setupModal() {
  const overlay = document.getElementById('modal-overlay');
  document.getElementById('modal-close').addEventListener('click', closeModal);
  overlay.addEventListener('click', event => { if (event.target === overlay) closeModal(); });
  document.addEventListener('keydown', event => {
    if (overlay.classList.contains('hidden')) return;
    if (event.key === 'Escape') { event.preventDefault(); closeModal(); return; }
    if (event.key !== 'Tab') return;
    const controls = [...overlay.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])')]
      .filter(element => element.getClientRects().length > 0);
    const first = controls[0];
    const last = controls[controls.length - 1];
    if (event.shiftKey && (document.activeElement === first || !overlay.contains(document.activeElement))) {
      event.preventDefault(); last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || !overlay.contains(document.activeElement))) {
      event.preventDefault(); first.focus();
    }
  });
  document.addEventListener('focusin', event => {
    if (!overlay.classList.contains('hidden') && !overlay.contains(event.target)) {
      document.getElementById('modal-close').focus();
    }
  });
}

function openModal(id, opener = document.activeElement) {
  const e = state.events.find(ev => ev.id === id);
  if (!e) return;

  const content = document.getElementById('modal-content');
  const eventURL = safeEventURL(e.url);
  const timeStr = e.time ? (e.end_time ? `${e.time} – ${e.end_time}` : e.time) : 'Time TBD';

  content.innerHTML = `
    <div class="modal-category"><span class="badge badge-${categoryFor(e.category)}">${labelFor(e.category)}</span></div>
    <div class="modal-title" id="modal-title">${esc(e.title)}</div>
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
    ${eventURL ? `<a class="modal-link" href="${esc(eventURL)}" target="_blank" rel="noopener">${iconExternal()} More info</a>` : ''}`;

  const overlay = document.getElementById('modal-overlay');
  if (overlay.classList.contains('hidden')) {
    modalOpener = opener;
    modalBackground = [...document.body.children].filter(element => element !== overlay && element.tagName !== 'SCRIPT')
      .map(element => ({ element, inert: element.inert }));
    modalBackground.forEach(({ element }) => { element.inert = true; });
  }
  document.body.classList.add('modal-open');
  overlay.classList.remove('hidden');
  document.getElementById('modal-close').focus();
}

function closeModal() {
  const overlay = document.getElementById('modal-overlay');
  if (overlay.classList.contains('hidden')) return;
  overlay.classList.add('hidden');
  document.body.classList.remove('modal-open');
  modalBackground.forEach(({ element, inert }) => { element.inert = inert; });
  modalBackground = [];
  if (modalOpener?.isConnected) modalOpener.focus();
  else document.querySelector(`.view-btn[data-view="${state.view}"]`).focus();
  modalOpener = null;
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

// Published historical records need the same link boundary as fresh extraction.
function safeEventURL(value) {
  if (typeof value !== 'string') return '';
  const candidate = value.trim();
  if (!/^https?:\/\//i.test(candidate) || /[\s\\\u0000-\u001f\u007f]/.test(candidate)) return '';
  const authority = candidate.match(/^https?:\/\/([^/?#]+)/i)?.[1];
  if (!authority || /[@<>"{}|^%]/.test(authority)) return '';
  try {
    const url = new URL(candidate);
    return ['http:', 'https:'].includes(url.protocol) && url.hostname.replace(/\./g, '') && !url.username && !url.password
      ? url.href : '';
  } catch { return ''; }
}

function truncate(str, len) {
  str = String(str);
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
      <p>No events match these filters and dates.</p>
      <p>Try upcoming events with fewer filters, or browse earlier published listings.</p>
      <div class="empty-actions">
        <button id="reset-results" class="clear-btn">Reset to upcoming events</button>
        <button id="show-all-dates" class="clear-btn">All published dates</button>
      </div>
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
function categoryFor(cat) { return Object.hasOwn(CATEGORY_LABELS, cat) ? cat : 'community'; }
function labelFor(cat) { return CATEGORY_LABELS[categoryFor(cat)]; }

function placeholderIcon(category) {
  const icons = {
    music:    '<path d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"/>',
    film:     '<path d="m15 10 4.553-2.277A1 1 0 0 1 21 8.619v6.762a1 1 0 0 1-1.447.894L15 14M3 8a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    arts:     '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    default:  '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
  };
  const path = icons[categoryFor(category)] || icons.default;
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
