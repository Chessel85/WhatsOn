// Registry of enabled feeds. Add a new feed by adding an entry here plus
// a matching overview card / detail page — see CLAUDE.md.
const FEEDS = {
  weather: {
    dataUrl: 'data/current/weather.json',
    renderSummary(data, container) {
      const c = currentHourlyReading(data.hourly);
      const p = document.createElement('p');
      p.textContent = `Currently ${Math.round(c.temperature_c)}°C, ${c.condition}`;
      container.replaceChildren(p);
    },
    renderDetail(data, container) {
      const c = currentHourlyReading(data.hourly);
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

  astronomy: {
    dataUrl: 'data/current/astronomy.json',
    renderSummary(data, container) {
      const today = data.days.find((d) => d.date === localDateKey(new Date())) || data.days[0];

      const sunP = document.createElement('p');
      sunP.textContent = `Sunrise ${formatTime(today.sunrise)}, sunset ${formatTime(today.sunset)}.`;

      const moonP = document.createElement('p');
      const rise = today.moonrise ? formatTime(today.moonrise) : 'none today';
      const set = today.moonset ? formatTime(today.moonset) : 'none today';
      moonP.textContent = `Moonrise ${rise}, moonset ${set}. ${today.moon_phase}, ${Math.round(today.moon_illumination_percent)}% illuminated.`;

      container.replaceChildren(sunP, moonP);
    },
    renderDetail(data, container) {
      const elements = [];

      pushHeading(elements, 'Sun & moon — next 7 days');

      const table = document.createElement('table');
      table.innerHTML = `
        <caption>Sunrise, sunset and moon phase — Southampton</caption>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Sunrise</th>
            <th scope="col">Sunset</th>
            <th scope="col">Day length</th>
            <th scope="col">Moonrise</th>
            <th scope="col">Moonset</th>
            <th scope="col">Moon phase</th>
            <th scope="col">Illuminated</th>
          </tr>
        </thead>
        <tbody>
          ${data.days.map((d) => `
            <tr>
              <th scope="row">${formatDayHeading(d.date)}</th>
              <td>${formatTime(d.sunrise)}</td>
              <td>${formatTime(d.sunset)}</td>
              <td>${formatHoursMinutes(d.day_length)}</td>
              <td>${d.moonrise ? formatTime(d.moonrise) : '—'}</td>
              <td>${d.moonset ? formatTime(d.moonset) : '—'}</td>
              <td>${d.moon_phase}</td>
              <td>${Math.round(d.moon_illumination_percent)}%</td>
            </tr>
          `).join('')}
        </tbody>
      `;
      elements.push(table);

      pushFetchedAt(elements, data, 'sunrisesunset.io');

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
                <td>${e.all_day ? 'All day' : formatTime(e.time)}</td>
              </tr>
            `).join('')}
          </tbody>
        `;
        elements.push(table);
      }

      pushFetchedAt(elements, data, 'hellosouthampton.co.uk, University of Southampton and Visit Southampton');

      container.replaceChildren(...elements);
    },
  },
  tv_radio: {
    dataUrl: 'data/current/tv_radio.json',
    renderSummary(data, container) {
      const list = document.createElement('ul');
      const items = data.channels.map((ch) => {
        const li = document.createElement('li');
        const a = document.createElement('a');
        a.href = `tv-radio.html#${channelAnchor(ch.id)}`;
        if (ch.new_series.length) {
          const examples = ch.new_series.slice(0, 2).map((s) => s.title).join(', ');
          const more = ch.new_series.length > 2 ? ', …' : '';
          a.textContent = `${ch.name}: ${examples}${more}`;
        } else {
          a.textContent = `${ch.name}: no new series this week`;
        }
        li.appendChild(a);
        return li;
      });
      list.replaceChildren(...items);
      container.replaceChildren(list);
    },
    renderDetail(data, container) {
      const elements = [];

      for (const ch of data.channels) {
        const heading = document.createElement('h2');
        heading.id = channelAnchor(ch.id);
        heading.textContent = ch.name;
        elements.push(heading);

        if (ch.confidence === 'low') {
          const note = document.createElement('p');
          note.textContent = 'Lower-confidence detection for this channel — worth double-checking against the broadcaster.';
          elements.push(note);
        }

        if (!ch.new_series.length) {
          const p = document.createElement('p');
          p.textContent = 'No new series starting in the next 7 days.';
          elements.push(p);
          continue;
        }

        const table = document.createElement('table');
        table.innerHTML = `
          <caption>${ch.name} — new series starting soon</caption>
          <thead>
            <tr>
              <th scope="col">Programme</th>
              <th scope="col">Series</th>
              <th scope="col">Starts</th>
              <th scope="col">Synopsis</th>
            </tr>
          </thead>
          <tbody>
            ${ch.new_series.map((s) => `
              <tr>
                <th scope="row">${s.url ? `<a href="${s.url}" target="_blank" rel="noopener noreferrer">${s.title}</a>` : s.title}</th>
                <td>${s.series_number ?? '—'}</td>
                <td>${s.start_time ? `<time datetime="${s.start_time}">${formatDayHeading(localDateKey(new Date(s.start_time)))}, ${formatTime(s.start_time)}</time>` : '—'}</td>
                <td>${s.synopsis || '—'}</td>
              </tr>
            `).join('')}
          </tbody>
        `;
        elements.push(table);
      }

      pushFetchedAt(elements, data, 'BBC iPlayer, BBC Sounds and TVmaze');

      container.replaceChildren(...elements);
    },
  },

  football: {
    dataUrl: 'data/current/football.json',
    renderSummary(data, container) {
      const list = document.createElement('ul');
      const items = data.clubs.map((club) => {
        const li = document.createElement('li');
        const next = club.fixtures[0];
        li.textContent = next
          ? `${club.name}: vs ${next.opponent} (${next.home_away === 'home' ? 'H' : 'A'}), ${formatDayHeading(localDateKey(new Date(next.date)))}, ${formatTime(next.date)} kick-off, ${formatVenue(next.venue)}`
          : `${club.name}: no upcoming fixtures found.`;
        return li;
      });
      list.replaceChildren(...items);
      container.replaceChildren(list);
    },
    renderDetail(data, container) {
      const elements = [];

      for (const club of data.clubs) {
        pushHeading(elements, club.name);

        if (!club.fixtures.length) {
          const p = document.createElement('p');
          p.textContent = 'No upcoming fixtures found in the next 90 days.';
          elements.push(p);
          continue;
        }

        const table = document.createElement('table');
        table.innerHTML = `
          <caption>${club.name} — fixtures (next ${data.lookahead_days} days)</caption>
          <thead>
            <tr>
              <th scope="col">Kick-off</th>
              <th scope="col">Opponent</th>
              <th scope="col">Venue</th>
              <th scope="col">Competition</th>
            </tr>
          </thead>
          <tbody>
            ${club.fixtures.map((f) => `
              <tr>
                <th scope="row"><time datetime="${f.date}">${formatDayHeading(localDateKey(new Date(f.date)))}, ${formatTime(f.date)}</time></th>
                <td>${f.opponent} (${f.home_away === 'home' ? 'H' : 'A'})</td>
                <td>${formatVenue(f.venue)}</td>
                <td>${f.competition}</td>
              </tr>
            `).join('')}
          </tbody>
        `;
        elements.push(table);
      }

      pushFetchedAt(elements, data, 'ESPN');

      container.replaceChildren(...elements);
    },
  },
  airport: {
    dataUrl: 'data/current/airport.json',
    renderSummary(data, container) {
      const now = new Date();
      const nextArrival = data.arrivals.find((a) => new Date(a.time) >= now);
      const nextDeparture = data.departures.find((d) => new Date(d.time) >= now);

      const countsP = document.createElement('p');
      countsP.textContent = `${data.arrivals.length} arrivals and ${data.departures.length} departures today.`;

      const arrivalP = document.createElement('p');
      arrivalP.textContent = nextArrival
        ? `Next arrival: ${formatTime(nextArrival.time)} from ${nextArrival.from} (${nextArrival.flight_number}).`
        : 'No more arrivals today.';

      const departureP = document.createElement('p');
      departureP.textContent = nextDeparture
        ? `Next departure: ${formatTime(nextDeparture.time)} to ${nextDeparture.to} (${nextDeparture.flight_number}).`
        : 'No more departures today.';

      container.replaceChildren(countsP, arrivalP, departureP);
    },
    renderDetail(data, container) {
      const elements = [];

      pushHeading(elements, 'Arrivals');

      const distanceNote = document.createElement('p');
      distanceNote.textContent = "The Distance column shows how far an aircraft currently is from Southampton Airport, live-tracked for flights the board itself shows as in the air. It won't appear for every such flight — matching a flight number to its live tracking is a best-effort guess, not guaranteed for every airline.";
      elements.push(distanceNote);

      const arrivalsTable = document.createElement('table');
      arrivalsTable.innerHTML = `
        <caption>Southampton Airport — arrivals</caption>
        <thead>
          <tr>
            <th scope="col">Time</th>
            <th scope="col">Flight</th>
            <th scope="col">From</th>
            <th scope="col">Airline</th>
            <th scope="col">Status</th>
            <th scope="col">Distance</th>
          </tr>
        </thead>
        <tbody>
          ${data.arrivals.map((a) => `
            <tr>
              <th scope="row">${formatFlightTime(a.time)}</th>
              <td>${a.flight_number}</td>
              <td>${a.from}</td>
              <td>${a.airline}</td>
              <td>${a.status || '—'}</td>
              <td>${a.distance_miles != null ? `${a.distance_miles} miles away` : '—'}</td>
            </tr>
          `).join('')}
        </tbody>
      `;
      elements.push(arrivalsTable);

      pushHeading(elements, 'Departures');
      const departuresTable = document.createElement('table');
      departuresTable.innerHTML = `
        <caption>Southampton Airport — departures</caption>
        <thead>
          <tr>
            <th scope="col">Time</th>
            <th scope="col">Flight</th>
            <th scope="col">To</th>
            <th scope="col">Airline</th>
            <th scope="col">Check-in desk</th>
            <th scope="col">Status</th>
            <th scope="col">Distance</th>
          </tr>
        </thead>
        <tbody>
          ${data.departures.map((d) => `
            <tr>
              <th scope="row">${formatFlightTime(d.time)}</th>
              <td>${d.flight_number}</td>
              <td>${d.to}</td>
              <td>${d.airline}</td>
              <td>${d.check_in_desk || '—'}</td>
              <td>${d.status || '—'}</td>
              <td>${d.distance_miles != null ? `${d.distance_miles} miles away` : '—'}</td>
            </tr>
          `).join('')}
        </tbody>
      `;
      elements.push(departuresTable);

      pushHeading(elements, 'Aircraft rotations today');

      const rotationsNote = document.createElement('p');
      rotationsNote.textContent = "Southampton Airport doesn't publish which aircraft flies which flight, so these pairings are inferred from the schedule — same route, landed before it took off again — not a confirmed match to a specific airframe.";
      elements.push(rotationsNote);

      if (data.rotations.length) {
        const rotationsTable = document.createElement('table');
        rotationsTable.innerHTML = `
          <caption>Inferred aircraft rotations — same plane, arrival then departure</caption>
          <thead>
            <tr>
              <th scope="col">Arrives</th>
              <th scope="col">From</th>
              <th scope="col">Departs</th>
              <th scope="col">To</th>
              <th scope="col">Turnaround</th>
            </tr>
          </thead>
          <tbody>
            ${data.rotations.map((r) => `
              <tr>
                <th scope="row">${formatFlightTime(r.arrival_time)} ${r.arrival_flight_number}</th>
                <td>${r.arrival_from}</td>
                <td>${formatFlightTime(r.departure_time)} ${r.departure_flight_number}</td>
                <td>${r.departure_to}</td>
                <td>${formatTurnaround(r.turnaround_minutes)}</td>
              </tr>
            `).join('')}
          </tbody>
        `;
        elements.push(rotationsTable);
      } else {
        const p = document.createElement('p');
        p.textContent = 'No aircraft rotations could be inferred from today’s schedule.';
        elements.push(p);
      }

      pushFetchedAt(elements, data, 'Southampton Airport');

      container.replaceChildren(...elements);
    },
  },
};

// "bbc_one" -> "bbc-one" — used both for the overview card's per-channel
// deep links and the matching <h2 id> on the detail page.
function channelAnchor(channelId) {
  return channelId.replace(/_/g, '-');
}

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

function formatVenue(venue) {
  return venue || '—';
}

// Airport board rows are almost always "today", with an occasional stray
// next-day entry (e.g. an overnight aircraft's first flight out) — showing
// the day name alongside the time, same as the football fixtures table,
// means those rows read correctly without a separate day-grouped table.
function formatFlightTime(isoLike) {
  return `${formatDayHeading(localDateKey(new Date(isoLike)))}, ${formatTime(isoLike)}`;
}

function formatTurnaround(minutes) {
  return formatHoursMinutes({ hours: Math.floor(minutes / 60), minutes: minutes % 60 });
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

// The weather source's own "current" reading is a snapshot from whenever
// the fetch last ran (up to an hour stale, longer if a workflow run is
// late/skipped) — e.g. still showing an 8am reading at 2pm. `hourly` covers
// the same fetch out to 48h ahead on an hourly grid, so picking the entry
// for the hour we're actually in gives an always-current reading between
// fetches without needing to fetch any more often.
function currentHourlyReading(hourly) {
  const now = new Date();
  let current = hourly[0];
  for (const h of hourly) {
    if (new Date(h.time) > now) break;
    current = h;
  }
  return current;
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

async function loadAndRenderDetail(feedName, container) {
  const feed = FEEDS[feedName];
  if (!feed) return;
  try {
    const data = await loadFeedData(feedName);
    feed.renderDetail(data, container);
  } catch (err) {
    container.textContent = 'Unable to load this data right now.';
  }
}

// Opt-in per page: a page whose data changes fast enough within a day to be
// worth manually refreshing (e.g. airport gate/boarding status) adds a
// `<button data-refresh-feed>` before its data-feed-detail container; pages
// without one (most feeds, which only change a few times a day) just don't
// get a button. Returns a reload function for the page's detail container (a
// no-op if there isn't one), so initAutoRefresh can re-run just the data
// load without re-attaching the refresh button's click listener every time.
function initDetailPage() {
  const container = document.querySelector('[data-feed-detail]');
  if (!container) return async () => {};
  const feedName = container.dataset.feedDetail;
  const reload = () => loadAndRenderDetail(feedName, container);

  reload();

  const refreshButton = document.querySelector('[data-refresh-feed]');
  if (refreshButton) {
    refreshButton.addEventListener('click', async () => {
      const originalText = refreshButton.textContent;
      refreshButton.disabled = true;
      refreshButton.textContent = 'Refreshing…';
      await reload();
      refreshButton.textContent = originalText;
      refreshButton.disabled = false;
    });
  }

  return reload;
}

// A tab left open across a fetch cycle (e.g. opened on the 19th, still open
// on the 22nd) otherwise keeps showing whatever was fetched on load until
// the user manually reloads. Re-fetching whenever the tab regains
// visibility — switched back to, or restored from the back/forward cache
// after the browser was reopened — covers that without polling in the
// background while the page is out of view (which could otherwise pull the
// rug from under someone reading it, or announce unrequested changes into a
// screen reader's aria-live region).
function initAutoRefresh(reloadDetail) {
  let refreshing = false;
  async function refreshIfVisible() {
    if (document.visibilityState !== 'visible' || refreshing) return;
    refreshing = true;
    try {
      await Promise.all([initOverviewCards(), reloadDetail()]);
    } finally {
      refreshing = false;
    }
  }
  document.addEventListener('visibilitychange', refreshIfVisible);
  window.addEventListener('pageshow', (event) => {
    if (event.persisted) refreshIfVisible();
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initOverviewCards();
  const reloadDetail = initDetailPage();
  initAutoRefresh(reloadDetail);
});
