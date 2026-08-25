const state = { readings: new Map(), history: new Map(), locations: [], location: "", lastEventId: "" };
const $ = (selector) => document.querySelector(selector);
const temperature = (value) => value == null ? "—" : `${Number(value).toFixed(1)}°C`;
const metric = (value, suffix = "") => value == null ? "—" : `${Number(value).toFixed(0)}${suffix}`;
const observed = (value) => value ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "—";
const esc = (value) => String(value ?? "").replace(/[&<>\"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;", "'":"&#39;"}[char]));

function visibleReadings() {
  return [...state.readings.values()].filter((item) => !state.location || item.location_id === state.location);
}
function selectedHistory() {
  if (state.location) return state.history.get(state.location) || [];
  const first = state.locations[0]?.id;
  return first ? state.history.get(first) || [] : [];
}
function addHistory(item) {
  if (!item.location_id) return;
  const entries = state.history.get(item.location_id) || [];
  const withoutDuplicate = entries.filter((entry) => entry.id !== item.id && entry.ingested_at !== item.ingested_at);
  state.history.set(item.location_id, [...withoutDuplicate, item].sort((a, b) => new Date(a.observed_at) - new Date(b.observed_at)).slice(-48));
}
function linePath(values, x, y) {
  return values.map((value, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(value).toFixed(1)}`).join(" ");
}
function renderChart() {
  const entries = selectedHistory().filter((item) => item.temperature_c != null || item.humidity_percent != null);
  if (entries.length < 2) {
    $("#chart").innerHTML = '<p class="empty">Waiting for enough readings to draw the trend.</p>';
    return;
  }
  const width = 920, height = 300, left = 48, right = 18, plotWidth = width - left - right;
  const rowHeight = 100, gap = 34;
  const temp = entries.map((item) => Number(item.temperature_c)).filter(Number.isFinite);
  const humidity = entries.map((item) => Number(item.humidity_percent)).filter(Number.isFinite);
  const range = (values, fallback) => {
    if (!values.length) return fallback;
    const min = Math.min(...values), max = Math.max(...values);
    const padding = Math.max((max - min) * 0.18, 1);
    return [min - padding, max + padding];
  };
  const tempRange = range(temp, [0, 40]), humidityRange = range(humidity, [0, 100]);
  const x = (index) => left + (index / Math.max(entries.length - 1, 1)) * plotWidth;
  const yFor = (value, min, max, top) => top + rowHeight - ((value - min) / (max - min || 1)) * rowHeight;
  const timeLabel = (item) => new Date(item.observed_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const tempLine = linePath(entries.map((item) => Number(item.temperature_c)), x, (value) => yFor(value, tempRange[0], tempRange[1], 18));
  const humidityLine = linePath(entries.map((item) => Number(item.humidity_percent)), x, (value) => yFor(value, humidityRange[0], humidityRange[1], 18 + rowHeight + gap));
  const labelIndexes = [...new Set([0, Math.floor((entries.length - 1) / 2), entries.length - 1])];
  $("#chart").innerHTML = `<svg viewBox="0 0 ${width} ${height + 22}" class="chart" aria-hidden="true" preserveAspectRatio="none">
    <g class="grid"><line x1="${left}" x2="${width - right}" y1="18" y2="18"/><line x1="${left}" x2="${width - right}" y1="${18 + rowHeight}" y2="${18 + rowHeight}"/><line x1="${left}" x2="${width - right}" y1="${18 + rowHeight + gap}" y2="${18 + rowHeight + gap}"/><line x1="${left}" x2="${width - right}" y1="${18 + rowHeight * 2 + gap}" y2="${18 + rowHeight * 2 + gap}"/></g>
    <text x="8" y="30" class="axis-label">°C</text><text x="8" y="${30 + rowHeight + gap}" class="axis-label">%</text>
    <path d="${tempLine}" class="series temp-line"/><path d="${humidityLine}" class="series humidity-line"/>
    ${labelIndexes.map((index) => `<text x="${x(index)}" y="${height + 12}" class="axis-label" text-anchor="middle">${timeLabel(entries[index])}</text>`).join("")}
  </svg>
  <div class="chart-note">${esc(state.location ? (state.locations.find((item) => item.id === state.location)?.name || state.location) : (state.locations[0]?.name || "Latest location"))} · last ${entries.length} processed events</div>`;
}
function render() {
  const items = visibleReadings().sort((a, b) => String(a.location_name).localeCompare(String(b.location_name)));
  $("#count").textContent = `${items.length} ${items.length === 1 ? "event" : "events"}`;
  $("#cards").innerHTML = items.length ? items.map((item) => `
    <article class="card"><div class="card-top"><span class="location">${esc(item.location_name)}</span><span class="badge">${esc(item.source || "stream")}</span></div>
      <div class="temperature">${temperature(item.temperature_c)}</div>
      <div class="metrics"><div><span class="metric-label">Feels like</span><span class="metric-value">${temperature(item.apparent_temperature_c)}</span></div>
      <div><span class="metric-label">Humidity</span><span class="metric-value">${metric(item.humidity_percent, "%")}</span></div>
      <div><span class="metric-label">Wind</span><span class="metric-value">${metric(item.wind_speed_kmh, " km/h")}</span></div></div>
    </article>`).join("") : `<p class="empty">No readings yet. Start the ingest and processor services.</p>`;
  $("#reading-table").innerHTML = items.length ? items.map((item) => `<tr><td><strong>${esc(item.location_name)}</strong></td><td>${temperature(item.temperature_c)}</td><td>${temperature(item.apparent_temperature_c)}</td><td>${metric(item.humidity_percent, "%")}</td><td>${metric(item.wind_speed_kmh, " km/h")}</td><td>${observed(item.observed_at)}</td></tr>`).join("") : `<tr><td colspan="6" class="empty">No data available.</td></tr>`;
  if (items.length) $("#updated").textContent = `Last update ${observed(items.reduce((a, b) => new Date(a.ingested_at) > new Date(b.ingested_at) ? a : b).ingested_at)}`;
  renderChart();
}
async function refresh() {
  const query = state.location ? `?location_id=${encodeURIComponent(state.location)}` : "";
  const response = await fetch(`/api/weather/latest${query}`);
  if (!response.ok) throw new Error("API unavailable");
  const readings = await response.json();
  readings.forEach((item) => { state.readings.set(item.location_id, item); addHistory(item); });
  const locations = state.location ? [state.location] : state.locations.map((item) => item.id);
  await Promise.all(locations.map(async (location) => {
    const historyResponse = await fetch(`/api/weather/history?location_id=${encodeURIComponent(location)}&limit=48`);
    if (!historyResponse.ok) return;
    const history = await historyResponse.json();
    state.history.set(location, history.reverse());
  }));
  render();
}
async function loadLocations() {
  const response = await fetch("/api/locations");
  if (!response.ok) throw new Error("Could not load locations");
  state.locations = await response.json();
  $("#location-filter").insertAdjacentHTML("beforeend", state.locations.map((item) => `<option value="${esc(item.id)}">${esc(item.name)}</option>`).join(""));
}
function connect() {
  const source = new EventSource("/api/events");
  source.onopen = () => { $("#connection").classList.add("live"); $("#connection").innerHTML = '<span class="dot"></span> Live'; };
  source.onmessage = (event) => {
    try {
      const item = JSON.parse(event.data);
      state.lastEventId = event.lastEventId;
      state.readings.set(item.location_id, item);
      addHistory(item);
      render();
    } catch (error) { console.warn("Invalid stream event", error); }
  };
  source.onerror = () => { $("#connection").classList.remove("live"); $("#connection").innerHTML = '<span class="dot"></span> Reconnecting'; };
}
$("#location-filter").addEventListener("change", (event) => { state.location = event.target.value; refresh().catch((error) => { $("#updated").textContent = error.message; }); });
$("#refresh").addEventListener("click", () => refresh().catch((error) => { $("#updated").textContent = error.message; }));
Promise.all([loadLocations(), refresh()]).then(connect).catch((error) => { $("#updated").textContent = error.message; connect(); });
