// Pure event transformations shared by the list, card, and calendar views.

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

export function filterEvents(events, filters) {
  const { q, dateFrom, dateTo, category, town, source } = filters;
  const query = q.toLowerCase();

  return events
    .map((event, index) => ({ event, index }))
    .filter(({ event }) => {
      if (q && !event.title.toLowerCase().includes(query)
            && !((event.description || '').toLowerCase().includes(query))
            && !((event.venue || '').toLowerCase().includes(query))) return false;
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
