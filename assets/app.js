// Registry of enabled feeds. Add a new feed by adding an entry here plus
// a matching overview card / detail page — see CLAUDE.md.
const FEEDS = {
  weather: {
    dataUrl: 'data/current/weather.json',
    renderSummary(data, container) {
      const c = data.current;
      const p = document.createElement('p');
      p.textContent = `Currently ${Math.round(c.temperature_c)}°C, ${c.condition}`;
      container.replaceChildren(p);
    },
    renderDetail(data, container) {
      const c = data.current;
      const elements = [];

      pushHeading(elements, 'Current conditions');

      const current = document.createElement('p');
      current.innerHTML = `
        As of <time datetime="${c.time}">${formatDateTime(c.time)}</time>:
        ${Math.round(c.temperature_c)}°C, feels like ${Math.round(c.feels_like_c)}°C, ${c.condition}.
        Wind ${Math.round(c.wind_speed_mph)} mph ${c.wind_direction}, humidity ${c.humidity_percent}%, precipitation ${c.precipitation_mm} mm.
      `;
      elements.push(current);

      for (const [dateKey, hours] of groupByLocalDate(data.hourly)) {
        const dayLabel = formatDayHeading(dateKey);

        pushHeading(elements, dayLabel);

        const table = document.createElement('table');
        table.innerHTML = `
          <caption>Hourly forecast — ${dayLabel}</caption>
          <thead>
            <tr>
              <th scope="col">Time</th>
              <th scope="col">Temperature</th>
              <th scope="col">Conditions</th>
              <th scope="col">Chance of rain</th>
              <th scope="col">Wind</th>
              <th scope="col">Humidity</th>
            </tr>
          </thead>
          <tbody>
            ${hours.map((h) => `
              <tr>
                <th scope="row">${formatTime(h.time)}</th>
                <td>${Math.round(h.temperature_c)}°C</td>
                <td>${h.condition}</td>
                <td>${h.precipitation_probability}%</td>
                <td>${Math.round(h.wind_speed_mph)} mph ${h.wind_direction}</td>
                <td>${h.humidity_percent}%</td>
              </tr>
            `).join('')}
          </tbody>
        `;
        elements.push(table);
      }

      pushHeading(elements, 'Last 5 days');

      const recentTable = document.createElement('table');
      recentTable.innerHTML = `
        <caption>Recent daily summary</caption>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Daylight</th>
            <th scope="col">Sunshine</th>
            <th scope="col">Rain</th>
            <th scope="col">Average wind</th>
          </tr>
        </thead>
        <tbody>
          ${data.recent_days.map((d) => `
            <tr>
              <th scope="row">${formatDayHeading(d.date)}</th>
              <td>${formatHoursMinutes(d.daylight)}</td>
              <td>${formatHoursMinutes(d.sunshine)}</td>
              <td>${d.precipitation_mm} mm</td>
              <td>${d.wind_speed_mph_avg} mph</td>
            </tr>
          `).join('')}
        </tbody>
      `;
      elements.push(recentTable);

      pushFetchedAt(elements, data, 'Open-Meteo');

      container.replaceChildren(...elements);
    },
  },

  tides: {
    dataUrl: 'data/current/tides.json',
    renderSummary(data, container) {
      const todaysEvents = groupByLocalDate(data.events).get(localDateKey(new Date())) || [];
      const highs = todaysEvents.filter((e) => e.event_type === 'High tide').map((e) => formatTime(e.time));
      const lows = todaysEvents.filter((e) => e.event_type === 'Low tide').map((e) => formatTime(e.time));

      const cycleP = document.createElement('p');
      cycleP.textContent = formatTidalCycle(data.tidal_cycle);

      const highP = document.createElement('p');
      highP.textContent = highs.length ? `Today's high tides: ${highs.join(', ')}` : "No high tide data for today.";

      const lowP = document.createElement('p');
      lowP.textContent = lows.length ? `Today's low tides: ${lows.join(', ')}` : 'No low tide data for today.';

      container.replaceChildren(cycleP, highP, lowP);
    },
    renderDetail(data, container) {
      const elements = [];

      pushHeading(elements, 'Tidal cycle');

      const cycleP = document.createElement('p');
      cycleP.textContent = formatTidalCycle(data.tidal_cycle);
      elements.push(cycleP);

      for (const [dateKey, events] of groupByLocalDate(data.events)) {
        const dayLabel = formatDayHeading(dateKey);

        pushHeading(elements, dayLabel);

        const table = document.createElement('table');
        table.innerHTML = `
          <caption>Tide times — ${dayLabel}</caption>
          <thead>
            <tr>
              <th scope="col">Time</th>
              <th scope="col">Tide</th>
              <th scope="col">Height</th>
            </tr>
          </thead>
          <tbody>
            ${events.map((e) => `
              <tr>
                <th scope="row">${formatTime(e.time)}</th>
                <td>${e.event_type}</td>
                <td>${e.height_m}m</td>
              </tr>
            `).join('')}
          </tbody>
        `;
        elements.push(table);
      }

      pushFetchedAt(elements, data, 'the ADMIRALTY UK Tidal API');

      container.replaceChildren(...elements);
    },
  },

  cruise_ships: {
    dataUrl: 'data/current/cruise_ships.json',
    renderSummary(data, container) {
      const todayKey = localDateKey(new Date());
      const arrivals = data.visits.filter((v) => v.arrival && v.arrival.date === todayKey);
      const departures = data.visits.filter((v) => v.departure && v.departure.date === todayKey);

      const arrivalP = document.createElement('p');
      arrivalP.textContent = arrivals.length
        ? `Arriving today: ${arrivals.map((v) => `${v.ship_name} (${formatShipTime(v.arrival)})`).join(', ')}`
        : 'No cruise ships arriving today.';

      const departureP = document.createElement('p');
      departureP.textContent = departures.length
        ? `Departing today: ${departures.map((v) => `${v.ship_name} (${formatShipTime(v.departure)})`).join(', ')}`
        : 'No cruise ships departing today.';

      container.replaceChildren(arrivalP, departureP);
    },
    renderDetail(data, container) {
      const elements = [];

      const groups = new Map();
      for (const visit of data.visits) {
        const dateKey = (visit.arrival || visit.departure).date;
        if (!groups.has(dateKey)) groups.set(dateKey, []);
        groups.get(dateKey).push(visit);
      }

      for (const [dateKey, visits] of groups) {
        const dayLabel = formatDayHeading(dateKey);

        pushHeading(elements, dayLabel);

        const table = document.createElement('table');
        table.innerHTML = `
          <caption>Cruise ships — ${dayLabel}</caption>
          <thead>
            <tr>
              <th scope="col">Ship</th>
              <th scope="col">Berth</th>
              <th scope="col">Arrival</th>
              <th scope="col">Departure</th>
            </tr>
          </thead>
          <tbody>
            ${visits.map((v) => `
              <tr>
                <th scope="row">${formatShipNameLink(v.links, v.ship_name)}</th>
                <td>${v.berth}</td>
                <td>${formatShipTime(v.arrival)}</td>
                <td>${formatShipTime(v.departure)}</td>
              </tr>
            `).join('')}
          </tbody>
        `;
        elements.push(table);
      }

      pushFetchedAt(elements, data, 'Southampton VTS');

      container.replaceChildren(...elements);
    },
  },

  city_events: {
    dataUrl: 'data/current/city_events.json',
    renderSummary(data, container) {
      const p = document.createElement('p');
      if (!data.events.length) {
        p.textContent = 'No upcoming events listed.';
      } else {
        const next = data.events[0];
        p.textContent = `${data.events.length} upcoming events. Next: ${next.title} (${formatDayHeading(localDateKey(new Date(next.time)))}).`;
      }
      container.replaceChildren(p);
    },
    renderDetail(data, container) {
      const elements = [];

      for (const [dateKey, events] of groupByLocalDate(data.events)) {
        const dayLabel = formatDayHeading(dateKey);

        pushHeading(elements, dayLabel);

        const table = document.createElement('table');
        table.innerHTML = `
          <caption>City events — ${dayLabel}</caption>
          <thead>
            <tr>
              <th scope="col">Event</th>
              <th scope="col">Venue</th>
              <th scope="col">Time</th>
            </tr>
          </thead>
          <tbody>
            ${events.map((e) => `
              <tr>
                <th scope="row"><a href="${e.url}" target="_blank" rel="noopener noreferrer">${e.title}</a></th>
                <td>${e.venue || '—'}</td>
                <td>${formatTime(e.time)}</td>
              </tr>
            `).join('')}
          </tbody>
        `;
        elements.push(table);
      }

      pushFetchedAt(elements, data, 'hellosouthampton.co.uk');

      container.replaceChildren(...elements);
    },
  },
};

function pushHeading(elements, text) {
  const heading = document.createElement('h2');
  heading.textContent = text;
  elements.push(heading);
}

function pushFetchedAt(elements, data, sourceName) {
  const fetchedAt = document.createElement('p');
  fetchedAt.className = 'fetched-at';
  fetchedAt.textContent = `Data fetched ${new Date(data.fetched_at).toLocaleString('en-GB')} from ${sourceName}.`;
  elements.push(fetchedAt);
}

// The ship name (row header) links straight to its details page —
// CruiseMapper (specs, deck plans, itinerary) when we found an exact name
// match in its ships sitemap, otherwise a Wikipedia search as a safe
// fallback. Opens in a new tab since it navigates away from the dashboard;
// rel="noopener noreferrer" is standard practice alongside target="_blank".
function formatShipNameLink(links, shipName) {
  const url = links.cruisemapper_url || links.wikipedia_search_url;
  if (!url) return shipName;
  return `<a href="${url}" target="_blank" rel="noopener noreferrer">${shipName}</a>`;
}

function formatShipTime(event) {
  if (!event) return '—';
  if (!event.time) return event.time_label || 'TBA';
  return formatTime(event.time);
}

// {hours: 12, minutes: 14} -> "12 hours 14 minutes". Words spelled out in
// full (not "hrs"/"mins") so a screen reader reads them naturally.
function formatHoursMinutes({ hours, minutes }) {
  const parts = [];
  if (hours > 0) parts.push(`${hours} ${hours === 1 ? 'hour' : 'hours'}`);
  if (minutes > 0 || hours === 0) parts.push(`${minutes} ${minutes === 1 ? 'minute' : 'minutes'}`);
  return parts.join(' ');
}

function formatDateTime(isoLike) {
  return new Date(isoLike).toLocaleString('en-GB', {
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// data.tidal_cycle is {type: "spring"|"neap", direction: "after"|"until"|"today", days: N},
// computed from lunar phase in scripts/fetch_tides.py (an approximation —
// actual spring/neap tides can lag the astronomical moon phase by a day
// or two).
function formatTidalCycle(cycle) {
  if (cycle.direction === 'today') {
    return `${cycle.type === 'spring' ? 'Spring' : 'Neap'} tide today`;
  }
  const dayWord = cycle.days === 1 ? 'day' : 'days';
  return `${cycle.days} ${dayWord} ${cycle.direction} ${cycle.type} tide`;
}

function localDateKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

// Groups entries (already in chronological order) by the LOCAL calendar
// date they fall on, so the detail page can render one table per day —
// far fewer rows to page through with a screen reader than one long
// table. Reads the date via Date getters (not string-slicing the "time"
// field) so it's correct regardless of whether "time" is a naive local
// string (weather) or a UTC "Z" string (tides) — string-slicing a UTC
// timestamp would occasionally put a late-evening/early-morning event
// under the wrong day once converted to local time.
function groupByLocalDate(items) {
  const groups = new Map();
  for (const item of items) {
    const dateKey = localDateKey(new Date(item.time));
    if (!groups.has(dateKey)) groups.set(dateKey, []);
    groups.get(dateKey).push(item);
  }
  return groups;
}

function formatDayHeading(dateKey) {
  return new Date(`${dateKey}T00:00`).toLocaleDateString('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
}

// e.g. "07:05" -> "7:05am", "20:00" -> "8pm", "00:00" -> "12am". Exact
// minute, not rounded to the nearest hour — but skips a redundant ":00"
// when a time happens to land exactly on the hour.
function formatTime(isoLike) {
  const d = new Date(isoLike);
  const hour = d.getHours();
  const period = hour < 12 ? 'am' : 'pm';
  const hour12 = hour % 12 || 12;
  const minute = d.getMinutes();
  if (minute === 0) return `${hour12}${period}`;
  return `${hour12}:${String(minute).padStart(2, '0')}${period}`;
}

async function loadFeedData(feedName) {
  const res = await fetch(FEEDS[feedName].dataUrl, { cache: 'no-store' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function initOverviewCards() {
  const cards = document.querySelectorAll('[data-feed]');
  for (const card of cards) {
    const feedName = card.dataset.feed;
    const feed = FEEDS[feedName];
    const summaryEl = card.querySelector('.card-summary');
    if (!feed || !summaryEl) continue;
    try {
      const data = await loadFeedData(feedName);
      feed.renderSummary(data, summaryEl);
    } catch (err) {
      summaryEl.textContent = 'Unable to load right now.';
    }
  }
}

async function initDetailPage() {
  const container = document.querySelector('[data-feed-detail]');
  if (!container) return;
  const feedName = container.dataset.feedDetail;
  const feed = FEEDS[feedName];
  if (!feed) return;
  try {
    const data = await loadFeedData(feedName);
    feed.renderDetail(data, container);
  } catch (err) {
    container.textContent = 'Unable to load this data right now.';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initOverviewCards();
  initDetailPage();
});
