const API_BASE = "https://geo-explorer.geomattr.org";

const el = (id) => document.getElementById(id);

// Placeholder hints for the per-column filter inputs.
const PLACEHOLDERS = {
  locationID: "e.g. MOBI_adm0_105",
  continent: "e.g. Europe",
  country: "e.g. France",
  countryCode: "e.g. FR",
  parentISO: "e.g. FI",
  stateProvince: "e.g. Montevideo",
  county: "e.g. Bella Unión",
  locality: "e.g. Paillaco",
  isCustomRegion: "Yes / No",
  geometrySource: "e.g. GADM",
};

let columns = [];
let idColumn = "locationID";
let map = null;
let mapLayer = null;
let queryToken = 0;
let visibleRows = [];
const DEFAULT_ROW_LIMIT = "200";

async function loadTables() {
  const res = await fetch(`${API_BASE}/api/tables`);
  const data = await res.json();
  columns = data.columns;
  idColumn = data.id_column;

  const select = el("table_name");
  select.innerHTML = "";
  for (const label of data.tables) {
    const opt = document.createElement("option");
    opt.value = label;
    opt.textContent = label;
    select.appendChild(opt);
  }
  buildHeader();
}

// Filter inputs sit directly above their column header; the first column holds the map button.
function buildHeader() {
  const filterRow = el("filter_row");
  const headerRow = el("header_row");
  filterRow.innerHTML = "<th></th>";
  headerRow.innerHTML = "<th>Map</th>";

  for (const col of columns) {
    const fth = document.createElement("th");
    const input = document.createElement("input");
    input.type = "search";
    input.id = `filter_${col}`;
    input.dataset.col = col;
    input.placeholder = PLACEHOLDERS[col] || "";
    input.title = "Whole-value match, case ignored (tick 'Allow partial matches' to match part of the value). "
      + "Combine values with upper-case OR / AND, e.g. France OR Spain";
    input.addEventListener("keydown", onEnter);
    fth.appendChild(input);
    filterRow.appendChild(fth);

    const th = document.createElement("th");
    th.textContent = col;
    headerRow.appendChild(th);
  }
}

function onEnter(e) {
  if (e.key === "Enter") runQuery();
}

function buildRowsURL() {
  const params = new URLSearchParams({
    table: el("table_name").value,
    q: el("search_all").value,
    partial: el("partial").checked,
    limit: el("row_limit").value,
  });
  for (const input of el("filter_row").querySelectorAll("input[data-col]")) {
    if (input.value.trim()) params.set(input.dataset.col, input.value);
  }
  return `${API_BASE}/api/rows?${params.toString()}`;
}

function renderRows(tableLabel, rows) {
  visibleRows = rows;
  el("copy_btn").disabled = rows.length === 0;
  const body = el("result_body");
  body.innerHTML = "";
  for (const row of rows) {
    const tr = document.createElement("tr");

    const btnTd = document.createElement("td");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "map-btn";
    btn.textContent = "Show";
    btn.addEventListener("click", () => openMap(tableLabel, row));
    btnTd.appendChild(btn);
    tr.appendChild(btnTd);

    for (const col of columns) {
      const td = document.createElement("td");
      td.textContent = row[col] ?? "";
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }
}

async function runQuery() {
  const token = ++queryToken;  // ignore responses from superseded queries
  const tableLabel = el("table_name").value;
  el("row_count").textContent = "Querying…";
  const res = await fetch(buildRowsURL());
  if (token !== queryToken) return;
  if (!res.ok) {
    el("row_count").textContent = `Error: ${res.status} ${res.statusText}`;
    renderRows(tableLabel, []);
    return;
  }
  const { count, rows } = await res.json();
  if (token !== queryToken) return;
  el("row_count").textContent = `${count} row(s) returned`;
  renderRows(tableLabel, rows);
}

// Back to the initial state: first table, empty boxes, default row limit, exact matching.
function resetForm() {
  el("table_name").selectedIndex = 0;
  el("search_all").value = "";
  el("row_limit").value = DEFAULT_ROW_LIMIT;
  el("partial").checked = false;
  for (const input of el("filter_row").querySelectorAll("input[data-col]")) input.value = "";
  runQuery();
}

// Tab-separated values with a header line; tabs and line breaks inside cells become spaces.
function rowsToTSV(rows) {
  const clean = (v) => String(v ?? "").replace(/[\t\r\n]+/g, " ");
  const lines = [columns.join("\t")];
  for (const row of rows) lines.push(columns.map((c) => clean(row[c])).join("\t"));
  return lines.join("\n") + "\n";
}

async function writeClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const ta = document.createElement("textarea");  // fallback for non-secure contexts
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  const ok = document.execCommand("copy");
  ta.remove();
  if (!ok) throw new Error("copy command failed");
}

async function copyVisibleRows() {
  const btn = el("copy_btn");
  const label = "Copy visible rows";
  try {
    await writeClipboard(rowsToTSV(visibleRows));
    btn.textContent = `Copied ${visibleRows.length} row(s)`;
  } catch {
    btn.textContent = "Copy failed";
  }
  setTimeout(() => { btn.textContent = label; }, 2000);
}

async function openMap(tableLabel, row) {
  const dialog = el("map_dialog");
  const id = row[idColumn];
  el("map_title").textContent = `${row.locality || row.county || row.stateProvince || row.country || id} (${id})`;
  el("map_status").textContent = "Loading polygon…";
  dialog.showModal();

  if (!map) {
    map = L.map("leaflet-map");
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    map.setView([0, 0], 1);
  }
  map.invalidateSize();  // the container was hidden until showModal()
  if (mapLayer) {
    mapLayer.remove();
    mapLayer = null;
  }

  const params = new URLSearchParams({ table: tableLabel, id });
  const res = await fetch(`${API_BASE}/api/geometry?${params.toString()}`);
  if (!res.ok) {
    el("map_status").textContent = "No geometry found for this row.";
    return;
  }
  const { geojson } = await res.json();
  mapLayer = L.geoJSON(geojson, {
    style: { fillColor: "#3388ff", color: "#1a66cc", weight: 2, fillOpacity: 0.3 },
  }).addTo(map);
  map.fitBounds(mapLayer.getBounds());
  el("map_status").textContent = "";
}

const dialog = el("map_dialog");
el("map_close").addEventListener("click", () => dialog.close());
dialog.addEventListener("click", (e) => {
  if (e.target === dialog) dialog.close();  // click on the backdrop
});

el("query_btn").addEventListener("click", runQuery);
el("reset_btn").addEventListener("click", resetForm);
el("copy_btn").addEventListener("click", copyVisibleRows);
el("table_name").addEventListener("change", runQuery);
el("partial").addEventListener("change", runQuery);
el("search_all").addEventListener("keydown", onEnter);
el("row_limit").addEventListener("keydown", onEnter);
loadTables().then(runQuery);
