const API_BASE = "https://147-251-255-246.sslip.io";

const el = (id) => document.getElementById(id);
let map = null;

async function loadTables() {
  const res = await fetch(`${API_BASE}/api/tables`);
  const { tables } = await res.json();
  const select = el("table_name");
  select.innerHTML = "";
  for (const label of tables) {
    const opt = document.createElement("option");
    opt.value = label;
    opt.textContent = label;
    select.appendChild(opt);
  }
}

function buildRowsURL() {
  const params = new URLSearchParams({
    table: el("table_name").value,
    locationID: el("filter_locationID").value,
    continent: el("filter_continent").value,
    country: el("filter_country").value,
    stateProvince: el("filter_stateProvince").value,
    county: el("filter_county").value,
    locality: el("filter_locality").value,
    limit: el("row_limit").value,
  });
  return `${API_BASE}/api/rows?${params.toString()}`;
}

function renderTable(rows) {
  const container = el("result_table");
  container.innerHTML = "";
  if (rows.length === 0) return;

  const table = document.createElement("table");
  const headerRow = document.createElement("tr");
  for (const col of Object.keys(rows[0])) {
    const th = document.createElement("th");
    th.textContent = col;
    headerRow.appendChild(th);
  }
  table.appendChild(headerRow);

  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const val of Object.values(row)) {
      const td = document.createElement("td");
      td.textContent = val ?? "";
      tr.appendChild(td);
    }
    table.appendChild(tr);
  }
  container.appendChild(table);
}

function clearMap() {
  const panel = el("map_panel");
  panel.innerHTML = "";
  map = null;
}

async function renderMap(tableLabel, idCol, row) {
  const panel = el("map_panel");
  panel.innerHTML = "<h4>Polygon</h4><div class=\"leaflet-map\" id=\"leaflet-map\"></div>";

  const params = new URLSearchParams({ table: tableLabel, id: row[idCol] });
  const res = await fetch(`${API_BASE}/api/geometry?${params.toString()}`);
  if (!res.ok) {
    panel.innerHTML += "<p>No geometry found for this row.</p>";
    return;
  }
  const { geojson } = await res.json();

  map = L.map("leaflet-map");
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
  }).addTo(map);

  const label = row.locality || row.country || String(row[idCol]);
  const layer = L.geoJSON(geojson, {
    style: { fillColor: "#3388ff", color: "#1a66cc", weight: 2, fillOpacity: 0.3 },
  }).bindTooltip(label).addTo(map);

  map.fitBounds(layer.getBounds());
}

async function runQuery() {
  const tableLabel = el("table_name").value;
  const res = await fetch(buildRowsURL());
  if (!res.ok) {
    el("row_count").textContent = `Error: ${res.status} ${res.statusText}`;
    renderTable([]);
    clearMap();
    return;
  }
  const { count, id_column, rows } = await res.json();

  const hint = count === 1 ? " — polygon shown below ▼" : " — filter to 1 row to show polygon";
  el("row_count").textContent = `${count} row(s) returned${hint}`;
  renderTable(rows);
  clearMap();

  if (count === 1) {
    await renderMap(tableLabel, id_column, rows[0]);
  }
}

el("query_btn").addEventListener("click", runQuery);
loadTables();
