// Pure, offline single-event iCalendar export (RFC 5545).
import { regionToday } from './event-data.js';
const encoder = new TextEncoder();
const REGION = 'America/New_York';

export function validCalendarDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith('0000')) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export function safeEventURL(value) {
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

// Strict clock parser: an invalid published time becomes unknown, never midnight.
export function calendarMinutes(value) {
  if (typeof value !== 'string') return null;
  const match = value.trim().match(/^(1[0-2]|0?[1-9])(?::([0-5][0-9]))?\s*(AM|PM)$/i);
  if (!match) return null;
  return (Number(match[1]) % 12 + (match[3].toUpperCase() === 'PM' ? 12 : 0)) * 60 + Number(match[2] || 0);
}

export function calendarTiming(event) {
  if (!validCalendarDate(event.date)) return { error: 'The published event date is invalid. A calendar entry cannot be made.' };
  const start = calendarMinutes(event.time);
  const suppliedEnd = calendarMinutes(event.end_time);
  const end = start !== null && suppliedEnd !== null && suppliedEnd > start ? suppliedEnd : null;
  const note = start === null
    ? 'Time is unknown. Saved as an all-day date reminder; this does not mean the event lasts all day.'
    : end === null
      ? 'Saved in America/New_York time. A reliable same-day end time is unavailable; no duration is supplied.'
      : 'Saved with the published start and end times in America/New_York.';
  return { start, end, note };
}

function text(value) {
  return String(value ?? '').replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '')
    .replace(/\r\n?/g, '\n').replace(/\\/g, '\\\\').replace(/\n/g, '\\n')
    .replace(/;/g, '\\;').replace(/,/g, '\\,');
}

function foldLine(line) {
  const lines = [];
  let current = '';
  let bytes = 0;
  for (const character of line) {
    const size = encoder.encode(character).length;
    if (bytes + size > 75) {
      lines.push(current);
      current = ' ';
      bytes = 1;
    }
    current += character;
    bytes += size;
  }
  lines.push(current);
  return lines.join('\r\n');
}

function utcDate(year, month = 0, day = 1) {
  const date = new Date(0);
  date.setUTCFullYear(year, month, day);
  date.setUTCHours(0, 0, 0, 0);
  return date.getTime();
}

function compactDate(timestamp) {
  return new Date(timestamp).toISOString().slice(0, 10).replace(/-/g, '');
}

function localClock(minutes) {
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}${String(minutes % 60).padStart(2, '0')}00`;
}

function offsetText(seconds) {
  const absolute = Math.abs(seconds);
  const hours = String(Math.floor(absolute / 3600)).padStart(2, '0');
  const minutes = String(Math.floor(absolute % 3600 / 60)).padStart(2, '0');
  const remainder = absolute % 60;
  return `${seconds < 0 ? '-' : '+'}${hours}${minutes}${remainder ? String(remainder).padStart(2, '0') : ''}`;
}

// Use the browser's timezone database, with explicit observances for this event
// year. No hardcoded assumption about future or historical DST rules, no network.
function timezoneLines(year) {
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone: REGION, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  });
  const offsetAt = timestamp => {
    const parts = Object.fromEntries(formatter.formatToParts(new Date(timestamp)).map(part => [part.type, part.value]));
    const local = utcDate(Number(parts.year), Number(parts.month) - 1, Number(parts.day))
      + (Number(parts.hour) * 3600 + Number(parts.minute) * 60 + Number(parts.second)) * 1000;
    return (local - timestamp) / 1000;
  };
  const start = utcDate(year);
  const finish = utcDate(year + 1);
  let previous = offsetAt(start);
  const lines = ['BEGIN:VTIMEZONE', `TZID:${REGION}`];
  const observance = (kind, local, from, to) => {
    lines.push(`BEGIN:${kind}`, `DTSTART:${local}`, `TZOFFSETFROM:${offsetText(from)}`,
      `TZOFFSETTO:${offsetText(to)}`, `END:${kind}`);
  };
  // Anchor the offset in effect on January 1, even before the first transition.
  observance('STANDARD', `${String(year).padStart(4, '0')}0101T000000`, previous, previous);
  for (let day = start + 86400000; day <= finish; day += 86400000) {
    const next = offsetAt(day);
    if (next === previous) continue;
    let low = day - 86400000;
    let high = day;
    // Offset transitions occur on whole seconds; preserve historical seconds too.
    while (high - low > 1000) {
      const middle = Math.floor((low + high) / 2000) * 1000;
      if (offsetAt(middle) === previous) low = middle;
      else high = middle;
    }
    const wall = new Date(high + previous * 1000).toISOString().slice(0, 19).replace(/[-:]/g, '');
    observance(next > previous ? 'DAYLIGHT' : 'STANDARD', wall, previous, next);
    previous = next;
  }
  lines.push('END:VTIMEZONE');
  return lines;
}

function eventUID(id) {
  // Hex UTF-16 code units preserve every existing ID without collisions or ICS
  // delimiters. IDs and resulting UIDs remain stable when titles/details change.
  let encoded = '';
  for (let index = 0; index < id.length; index++) encoded += id.charCodeAt(index).toString(16).padStart(4, '0');
  return `pve-${encoded}@pioneer-valley-events`;
}

export function createCalendar(event, generated, now = new Date()) {
  if (!event || typeof event.id !== 'string' || !event.id.trim()) throw new Error('A published event ID is required.');
  const timing = calendarTiming(event);
  if (timing.error) throw new Error(timing.error);
  const stamp = new Date(now);
  if (!Number.isFinite(stamp.getTime())) throw new Error('An export timestamp is required.');
  const organizerURL = safeEventURL(event.url);
  const location = [event.venue, event.town, event.address].filter(value => typeof value === 'string' && value.trim()).join(', ');
  const description = [
    `Event: ${event.title ?? ''}`, event.description || '', `Venue: ${location || 'Unspecified'}`,
    organizerURL ? `Organizer: ${organizerURL}` : '',
    validCalendarDate(generated)
      ? generated <= regionToday(stamp) ? `Dataset updated: ${generated}.`
        : `Dataset supplied update date: ${generated} (unverified; in the future).`
      : 'Dataset update date unverified.',
    timing.note, 'Confirm details with the event organizer before attending.',
  ].filter(Boolean).join('\n');
  const lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Pioneer Valley Events//Single event export//EN', 'CALSCALE:GREGORIAN'];
  if (timing.start !== null) lines.push(...timezoneLines(Number(event.date.slice(0, 4))));
  lines.push('BEGIN:VEVENT', `UID:${eventUID(event.id)}`,
    `DTSTAMP:${stamp.toISOString().slice(0, 19).replace(/[-:]/g, '')}Z`,
    `SUMMARY:${text(event.title)}`, `LOCATION:${text(location)}`, `DESCRIPTION:${text(description)}`);
  const date = event.date.replace(/-/g, '');
  if (timing.start === null) {
    const nextDay = compactDate(Date.parse(`${event.date}T00:00:00Z`) + 86400000);
    lines.push(`DTSTART;VALUE=DATE:${date}`, `DTEND;VALUE=DATE:${nextDay}`);
  } else {
    lines.push(`DTSTART;TZID=${REGION}:${date}T${localClock(timing.start)}`);
    if (timing.end !== null) lines.push(`DTEND;TZID=${REGION}:${date}T${localClock(timing.end)}`);
  }
  if (organizerURL) lines.push(`URL:${organizerURL}`);
  lines.push('END:VEVENT', 'END:VCALENDAR');
  return lines.map(foldLine).join('\r\n') + '\r\n';
}
