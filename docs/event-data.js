// Pure event transformations shared by the list, card, and calendar views.

// Allow one missed weekly update before warning. Compare calendar days so DST
// and the viewer's timezone cannot shift a date-only publication timestamp.
const MAX_DATA_AGE_DAYS = 14;

function calendarDay(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return NaN;
  const timestamp = Date.parse(`${value}T00:00:00Z`);
  if (!Number.isFinite(timestamp)
      || new Date(timestamp).toISOString().slice(0, 10) !== value) return NaN;
  return timestamp / 86400000;
}

export function dataFreshness(generated, today = regionToday()) {
  const age = calendarDay(today) - calendarDay(generated);
  if (!Number.isFinite(age) || age < 0) return 'unknown';
  return age > MAX_DATA_AGE_DAYS ? 'stale' : 'current';
}

// Chronological minutes for a "H:MM AM/PM" time; all-day (no time) sorts first.
// Keep this parser permissive: hour-only and lowercase inputs are valid.
export function timeMinutes(time) {
  if (!time) return -1;
  const match = String(time).match(/^(\d{1,2})(?::(\d{2}))?\s*(AM|PM)$/i);
  if (!match) return -1;

  let hour = parseInt(match[1], 10) % 12;
  if (match[3].toUpperCase() === 'PM') hour += 12;
  return hour * 60 + (match[2] ? parseInt(match[2], 10) : 0);
}

export function regionToday(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(now);
  const part = type => parts.find(item => item.type === type).value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}

// Date-only arithmetic stays in UTC: elapsed hours around DST are irrelevant.
export function quickDateRange(choice, today = regionToday()) {
  const day = calendarDay(today);
  const dateAt = offset => new Date((day + offset) * 86400000).toISOString().slice(0, 10);
  if (choice === 'all') return { dateFrom: '', dateTo: '' };
  if (choice === 'today') return { dateFrom: today, dateTo: today };
  if (choice === 'week') return { dateFrom: today, dateTo: dateAt(6) };
  if (choice === 'weekend') {
    const weekday = new Date(day * 86400000).getUTCDay();
    const start = weekday === 0 ? 0 : 6 - weekday;
    return { dateFrom: dateAt(start), dateTo: dateAt(start + (weekday === 0 ? 0 : 1)) };
  }
  return { dateFrom: today, dateTo: '' };
}

const DATE_CHOICES = ['upcoming', 'today', 'week', 'weekend', 'all', 'custom'];
const VIEW_CHOICES = ['list', 'cards', 'calendar'];
const URL_FILTERS = { q: 'q', from: 'dateFrom', to: 'dateTo', category: 'category', town: 'town', source: 'source' };

export function readBrowserState(search, available = {}, today = regionToday()) {
  const params = new URLSearchParams(search);
  const dateChoice = DATE_CHOICES.includes(params.get('dates')) ? params.get('dates') : 'upcoming';
  const filters = { q: params.get('q') || '', ...quickDateRange(dateChoice, today), category: '', town: '', source: '' };
  if (dateChoice === 'custom') {
    for (const [param, key] of [['from', 'dateFrom'], ['to', 'dateTo']]) {
      filters[key] = Number.isFinite(calendarDay(params.get(param))) ? params.get(param) : '';
    }
  }
  for (const key of ['category', 'town', 'source']) {
    const value = params.get(key);
    if ((available[key] || []).includes(value)) filters[key] = value;
  }
  const view = VIEW_CHOICES.includes(params.get('view')) ? params.get('view') : 'list';
  const month = params.get('month');
  const calendarMonth = /^\d{4}-\d{2}$/.test(month || '') && Number.isFinite(calendarDay(`${month}-01`))
    ? `${month}-01` : `${filters.dateFrom || today}`.slice(0, 7) + '-01';
  const day = params.get('day');
  const calendarSelectedDay = Number.isFinite(calendarDay(day)) && day.startsWith(calendarMonth.slice(0, 7))
    ? day : null;
  return { filters, dateChoice, view, calendarMonth, calendarSelectedDay };
}

export function browserStateParams(state, search = '') {
  const params = new URLSearchParams(search);
  for (const key of [...Object.keys(URL_FILTERS), 'dates', 'view', 'month', 'day']) params.delete(key);
  if (state.dateChoice !== 'upcoming') params.set('dates', state.dateChoice);
  for (const [param, key] of Object.entries(URL_FILTERS)) {
    if ((key === 'dateFrom' || key === 'dateTo') && state.dateChoice !== 'custom') continue;
    if (state.filters[key]) params.set(param, state.filters[key]);
  }
  if (state.view !== 'list') params.set('view', state.view);
  if (state.view === 'calendar') {
    params.set('month', state.calendarMonth.slice(0, 7));
    if (state.calendarSelectedDay) params.set('day', state.calendarSelectedDay);
  }
  return params.toString();
}

export function filterEvents(events, filters) {
  const { q, dateFrom, dateTo, category, town, source } = filters;
  const query = String(q || '').trim().toLowerCase();

  return events
    .map((event, index) => ({ event, index }))
    .filter(({ event }) => {
      if (query && !['title', 'description', 'venue', 'town'].some(key =>
        String(event[key] || '').toLowerCase().includes(query))) return false;
      if (dateFrom && event.date < dateFrom) return false;
      if (dateTo && event.date > dateTo) return false;
      if (category && event.category !== category) return false;
      if (town && event.town !== town) return false;
      if (source && event.source !== source) return false;
      return true;
    })
    .sort((left, right) => (
      left.event.date.localeCompare(right.event.date)
      || timeMinutes(left.event.time) - timeMinutes(right.event.time)
      || left.index - right.index
    ))
    .map(({ event }) => event);
}

export function groupEventsByDate(events) {
  const groups = {};
  events.forEach(event => {
    if (!groups[event.date]) groups[event.date] = [];
    groups[event.date].push(event);
  });
  return groups;
}

function dateString(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

export function buildCalendarCells(year, monthIndex) {
  const firstDay = new Date(year, monthIndex, 1).getDay();
  const daysInMonth = new Date(year, monthIndex + 1, 0).getDate();
  const cellCount = Math.ceil((firstDay + daysInMonth) / 7) * 7;

  return Array.from({ length: cellCount }, (_, index) => {
    const date = new Date(year, monthIndex, index - firstDay + 1);
    return {
      date: dateString(date),
      day: date.getDate(),
      inCurrentMonth: date.getFullYear() === year && date.getMonth() === monthIndex,
    };
  });
}
