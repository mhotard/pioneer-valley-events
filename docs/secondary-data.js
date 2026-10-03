// Shared status and validation for the historical podcast surfaces.
import { dataFreshness } from './event-data.js';

const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const text = value => typeof value === 'string';
const optionalText = value => value == null || text(value);
const count = value => Number.isFinite(value) && value >= 0;
const date = value => text(value) && /^\d{4}-\d{2}-\d{2}$/.test(value)
  && Number.isFinite(Date.parse(`${value}T00:00:00Z`))
  && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;
const episode = value => object(value) && text(value.date) && optionalText(value.url)
  && optionalText(value.title);
const counts = value => object(value) && Object.values(value).every(count);

export function validSeasonal(data) {
  return object(data) && object(data.months)
    && Object.entries(data.months).every(([month, events]) =>
      /^(?:[1-9]|1[0-2])$/.test(month) && Array.isArray(events)
      && events.every(event => object(event) && text(event.name)
        && optionalText(event.town) && optionalText(event.event_type)
        && Array.isArray(event.years) && event.years.every(year => /^\d{4}$/.test(String(year)))
        && Array.isArray(event.episodes) && event.episodes.every(episode)));
}

export function validDashboard(data) {
  return object(data) && counts(data.totals)
    && ['episodes', 'entities', 'unique', 'towns'].every(key => count(data.totals[key]))
    && Array.isArray(data.towns) && data.towns.every(town => object(town)
      && text(town.town) && count(town.count)
      && Number.isFinite(town.lat) && Number.isFinite(town.lng))
    && counts(data.kinds) && counts(data.months) && object(data.timeline)
    && Array.isArray(data.timeline.quarters) && data.timeline.quarters.every(text)
    && object(data.timeline.series) && Object.values(data.timeline.series).every(series =>
      Array.isArray(series) && series.length === data.timeline.quarters.length && series.every(count))
    && Array.isArray(data.index) && data.index.every(row => object(row)
      && text(row.name) && text(row.kind) && optionalText(row.town)
      && optionalText(row.note) && optionalText(row.url) && count(row.count)
      && Array.isArray(row.episodes) && row.episodes.every(episode));
}

export function regionalToday() {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(new Date());
}

export function publicationStatus(generated) {
  const freshness = dataFreshness(generated, regionalToday());
  const updated = date(generated) ? `Generated ${generated}.` : 'Generation date unavailable.';
  const warning = freshness === 'stale'
    ? ' This dataset is more than 14 days old; newer podcast coverage may be missing.'
    : freshness === 'unknown' ? ' The update date could not be verified.' : '';
  return `${updated}${warning} Podcast coverage is historical evidence, not confirmation of upcoming event dates.`;
}

export function coverageLabel(values, label = 'Podcast coverage') {
  const dates = values.filter(date).sort();
  return dates.length ? `${label}: ${dates[0]} to ${dates[dates.length - 1]}.`
    : `${label}: no dated evidence available.`;
}

export function safeURL(value) {
  if (!text(value)) return '';
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
  } catch { return ''; }
}

export async function loadPublished(url, valid) {
  const response = await fetch(url, { cache: 'no-cache' });
  if (!response.ok) throw new Error('Unavailable published dataset');
  const data = await response.json();
  if (!valid(data)) throw new Error('Invalid published dataset');
  return data;
}
