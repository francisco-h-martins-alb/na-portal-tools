"use strict";

const $ = (id) => document.getElementById(id);
const pages = {
  "api-explorer": ["API Explorer", "Run the documented NA-PORTAL REST operations against the selected backend."],
  "health-check": ["Health check", "Check the selected backend's HTTP health endpoint or test TCP connectivity separately."],
  entities: ["List entities", "Browse your catalogs and choose an entity to work with."],
  entries: ["List entries", "Explore the entries belonging to a discovered entity."],
  "insert-entity": ["Insert entity", "Create a catalog entity from a JSON definition."],
  "delete-entity": ["Delete entity", "Remove a selected catalog entity from the portal."],
  "insert-entry": ["Insert entry", "Create entries in the selected catalog."],
  "delete-entries": ["Delete all entries", "Clear every entry in the selected catalog."],
  "coming-soon": ["", "Dedicated workflows for this API group are coming soon."],
};
const state = {
  page: "api-explorer", entities: [], selected: null, entries: [], entriesLoaded: false,
  apiOperations: [], token: null, busy: false,
  callCount: 0,
};

function status(message, kind = "") {
  $("status").hidden = false;
  $("status").className = kind;
  $("status").textContent = message;
}

function bindCopyButton(button, source) {
  const label = button.getAttribute("aria-label");
  button.title = label;
  button.classList.add("copy-button");
  button.append($("copy-icon").content.cloneNode(true));
  let reset;
  button.onclick = async () => {
    const text = source.value ?? source.textContent;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      if (source instanceof HTMLTextAreaElement) {
        source.focus();
        source.select();
      } else {
        const range = document.createRange();
        range.selectNodeContents(source);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
      }
      status("Clipboard unavailable. Copy the selected text with Ctrl+C or Cmd+C.", "error");
      return;
    }
    clearTimeout(reset);
    button.classList.add("copied");
    reset = setTimeout(() => { button.classList.remove("copied"); }, 1500);
  };
}

function endpoint() {
  return { host: $("host").value.trim(), port: $("port").value };
}

function requireEntity() {
  if (!state.selected) throw new Error("Discover entities and select an entity first.");
  return state.selected.name;
}

async function api(action, extra = {}) {
  if (!state.token) {
    const response = await fetch("/api/session", { cache: "no-store" });
    if (!response.ok) throw new Error("Could not initialize the session. Reload the page.");
    state.token = (await response.json()).token;
  }
  const response = await fetch("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Portal-Token": state.token },
    body: JSON.stringify({ ...endpoint(), action, ...extra }),
  });
  let result;
  try {
    result = await response.json();
  } catch {
    throw new Error("The UI server returned an invalid response. Check its terminal.");
  }
  recordOperation(action, result, response.ok);
  if (!response.ok) throw new Error(result.error || `Request failed (HTTP ${response.status}).`);
  return result;
}

function recordOperation(action, result, ok) {
  const { calls = [], ...output } = result;
  const title = `[${new Date().toLocaleTimeString()}] ${action.replaceAll("_", " ")}`;
  let text;
  if (!ok) text = `ERROR: ${output.error}`;
  else if (action === "entities") {
    text = output.entities.map((entity) => `${entity.id} : ${entity.name}`).join("\n") || "No entities found.";
  } else if (action === "entries") {
    text = JSON.stringify({ nacatalogs: output.entries }, null, 2);
  } else {
    text = output.message || JSON.stringify(output, null, 2);
    if (output.response !== undefined && output.response !== null) {
      const response = output.response;
      text += response && response._download
        ? `\nBinary response (${response._download.content_type}); downloaded by the browser.`
        : "\n" + (typeof response === "string" ? response : JSON.stringify(response, null, 2));
    }
  }
  if (!calls.length) text += "\n(No HTTP call: local operation or validation.)";
  $("terminal-output").value += `${title}\n${text}\n\n`;
  $("terminal-output").scrollTop = $("terminal-output").scrollHeight;
  if (calls.length && state.callCount === 0) $("api-calls").replaceChildren();
  for (const call of calls) {
    state.callCount += 1;
    const details = document.createElement("details");
    details.className = "api-call";
    details.open = true;
    const summary = document.createElement("summary");
    summary.textContent = `#${state.callCount} ${call.method} ${call.url} / ${call.status ?? "NETWORK ERROR"} / ${call.duration_ms} ms`;
    details.append(summary);
    const curlLabel = document.createElement("label");
    curlLabel.textContent = "Editable curl command";
    const curl = document.createElement("textarea");
    curl.className = "curl-command";
    curl.rows = 4;
    curl.spellcheck = false;
    curl.value = call.curl;
    curlLabel.append(curl);
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "secondary";
    copy.setAttribute("aria-label", "Copy curl command");
    bindCopyButton(copy, curl);
    details.append(copy, curlLabel);
    const responseLabel = document.createElement("label");
    responseLabel.textContent = "Response body (text preview)";
    const responseText = document.createElement("textarea");
    responseText.className = "raw-response terminal";
    responseText.rows = 8;
    responseText.readOnly = true;
    responseText.spellcheck = false;
    const headers = call.headers.map(([key, value]) => `${key}: ${value}`).join("\n");
    responseText.value = [
      call.status === null ? "No HTTP response" : `HTTP ${call.status}`,
      headers, "", call.response,
      call.error ? `\nERROR: ${call.error}` : "",
    ].join("\n");
    responseLabel.append(responseText);
    details.append(responseLabel);
    $("api-calls").append(details);
  }
}

async function task(label, work) {
  if (state.busy) return;
  state.busy = true;
  const controls = [...document.querySelectorAll("button, input, textarea, select, summary")];
  const disabled = controls.map((element) => element.disabled);
  controls.forEach((element) => { element.disabled = true; });
  document.body.setAttribute("aria-busy", "true");
  status(label, "busy");
  try {
    await work();
  } catch (error) {
    status(error.message, "error");
  } finally {
    state.busy = false;
    controls.forEach((element, index) => { element.disabled = disabled[index]; });
    document.querySelectorAll(".entity-button").forEach((button) => {
      button.disabled = false;
    });
    document.body.removeAttribute("aria-busy");
    updateButtons();
  }
}

function updateButtons() {
  $("download-entries").disabled = !state.entriesLoaded;
}

function clearEntries() {
  state.entries = [];
  state.entriesLoaded = false;
  renderEntries();
  updateButtons();
}

function selectEntity(entity) {
  if (state.busy) return;
  if (!state.selected || String(state.selected.id) !== String(entity.id)
      || state.selected.name !== entity.name) {
    clearEntries();
    $("entry-json").value = "";
    $("entry-file").value = "";
  }
  state.selected = entity;
  $("result-panel").hidden = true;
  renderEntities();
  if (state.page === "entries") loadEntries();
}

function renderEntities() {
  const list = $("entity-list");
  list.replaceChildren();
  const search = $("entity-search").value.toLowerCase();
  const filtered = state.entities.filter((entity) =>
    `${entity.name} ${entity.id}`.toLowerCase().includes(search));
  for (const entity of filtered) {
    const button = document.createElement("button");
    const selected = state.selected && state.selected.name === entity.name;
    button.className = "entity-button" + (selected ? " selected" : "");
    button.setAttribute("aria-pressed", String(Boolean(selected)));
    button.textContent = entity.name;
    const subtitle = document.createElement("small");
    subtitle.textContent = `ID ${entity.id}${selected ? " / SELECTED" : ""}`;
    button.append(subtitle);
    button.addEventListener("click", () => selectEntity(entity));
    button.disabled = state.busy;
    list.append(button);
  }
  if (!filtered.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = state.entities.length ? "No entities match your filter."
      : "No entities loaded. Click Discover entities to get started.";
    list.append(empty);
  }
  $("entity-count").textContent = `${state.entities.length} discovered`;
  $("selection").hidden = !state.selected;
  $("selection-empty").hidden = Boolean(state.selected);
  $("selected-entity-name").textContent = state.selected?.name ?? "";
  $("selected-entity-id").textContent = state.selected?.id ?? "";
  $("refresh-entities").textContent = state.entities.length ? "Refresh entities" : "Discover entities";
}

function renderEntries() {
  const output = $("entries-output");
  output.replaceChildren();
  const search = $("entry-search").value.toLowerCase();
  const entries = state.entries.filter((entry) => JSON.stringify(entry).toLowerCase().includes(search));
  $("entry-count").textContent = `${entries.length} / ${state.entries.length} entries`;
  if (!entries.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = state.entriesLoaded ? "No entries found." : "Entries will appear here.";
    output.append(empty);
    return;
  }
  const columns = [...new Set(entries.flatMap(Object.keys))];
  const table = document.createElement("table");
  const head = table.createTHead().insertRow();
  for (const column of columns) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = column;
    head.append(cell);
  }
  const body = table.createTBody();
  for (const entry of entries) {
    const row = body.insertRow();
    for (const column of columns) {
      const value = entry[column];
      row.insertCell().textContent = value === undefined ? ""
        : typeof value === "object" ? JSON.stringify(value) : String(value);
    }
  }
  output.append(table);
}

function selectedOperation() {
  const [method, ...pathParts] = $("api-operation").value.split(" ");
  const path = pathParts.join(" ");
  return state.apiOperations.find((operation) =>
    operation.method === method && operation.path === path);
}

function renderApiOperations() {
  const group = $("api-group");
  const operationSelect = $("api-operation");
  const previousGroup = group.value;
  const previousOperation = operationSelect.value;
  const groups = [...new Set(state.apiOperations.map((operation) => operation.tag))];
  group.replaceChildren();
  for (const tag of groups) {
    const option = document.createElement("option");
    option.value = tag;
    option.textContent = tag;
    group.append(option);
  }
  if (groups.includes(previousGroup)) group.value = previousGroup;
  const operations = state.apiOperations.filter((operation) => operation.tag === group.value);
  operationSelect.replaceChildren();
  for (const operation of operations) {
    const option = document.createElement("option");
    option.value = `${operation.method} ${operation.path}`;
    option.textContent = `${operation.method} ${operation.path} — ${operation.summary}`;
    operationSelect.append(option);
  }
  if (operations.some((operation) => `${operation.method} ${operation.path}` === previousOperation)) {
    operationSelect.value = previousOperation;
  }
  renderPathParameters();
}

function renderPathParameters() {
  const operation = selectedOperation();
  const container = $("api-path-params");
  container.replaceChildren();
  $("api-query").value = "{}";
  $("api-body").value = "";
  $("api-query-hint").textContent = "";
  $("api-body-label").textContent = "Request body (JSON)";
  $("load-api-example").disabled = true;
  $("api-example-note").textContent = "";
  if (!operation) {
    $("api-operation-summary").textContent = "No documented operations are available.";
    return;
  }
  $("api-operation-summary").textContent =
    `${operation.method} ${operation.path} — ${operation.summary}`;
  const hasExample = Boolean(operation.body) || operation.parameters.some((p) => "example" in p);
  $("load-api-example").disabled = !hasExample;
  $("api-example-note").textContent = !hasExample ? "No request example is defined for this operation."
    : operation.body?.schemaDerived ? "The body example is built from the schema and may contain placeholders."
      : "Loading an example fills the editors but does not send a request.";
  const query = operation.parameters.filter((p) => p.in === "query");
  $("api-query-hint").textContent = query.length
    ? `Documented: ${query.map((p) => `${p.name} (${p.type}${p.required ? ", required" : ""})`).join(", ")}`
    : "No query parameters documented.";
  $("api-body-label").textContent = operation.body
    ? `Request body (${operation.body.required ? "required" : "optional"} JSON)`
    : "Request body (none documented)";
  const parameters = [...operation.path.matchAll(/\{([^{}]+)\}/g)].map((match) => match[1]);
  for (const parameter of parameters) {
    const metadata = operation.parameters.find((p) => p.in === "path" && p.name === parameter);
    const label = document.createElement("label");
    label.textContent = `Path parameter: ${parameter} (${metadata?.type || "string"}, required)`;
    const input = document.createElement("input");
    input.dataset.pathParameter = parameter;
    input.autocomplete = "off";
    input.required = true;
    if (metadata && "example" in metadata) input.placeholder = `Example: ${metadata.example}`;
    label.append(input);
    container.append(label);
  }
}

function loadApiExample() {
  const operation = selectedOperation();
  if (!operation) return;
  const examples = operation.parameters.filter((parameter) => "example" in parameter);
  for (const input of $("api-path-params").querySelectorAll("[data-path-parameter]")) {
    const parameter = examples.find((p) => p.in === "path" && p.name === input.dataset.pathParameter);
    if (parameter) input.value = String(parameter.example);
  }
  const query = Object.fromEntries(examples.filter((p) => p.in === "query").map((p) => [p.name, p.example]));
  if (Object.keys(query).length) $("api-query").value = JSON.stringify(query, null, 2);
  if (operation.body) $("api-body").value = JSON.stringify(operation.body.example, null, 2);
}

async function loadApiOperations() {
  try {
    const response = await fetch("/api/operations", { cache: "no-store" });
    if (!response.ok) throw new Error("Could not load the documented API operations.");
    state.apiOperations = await response.json();
    renderApiOperations();
  } catch (error) {
    status(error.message, "error");
  }
}

function downloadResponse(download) {
  const binary = atob(download.data);
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  const blob = new Blob([bytes], { type: download.content_type || "application/octet-stream" });
  const link = document.createElement("a");
  const url = URL.createObjectURL(blob);
  link.href = url;
  link.download = "na-portal-response.bin";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function executeApiOperation() {
  const operation = selectedOperation();
  if (!operation) { status("Choose a documented operation first.", "error"); return; }
  let query, payload;
  try {
    query = JSON.parse($("api-query").value || "{}");
    if (!query || Array.isArray(query) || typeof query !== "object") {
      throw new Error("Query parameters must be a JSON object.");
    }
    if ($("api-body").value.trim()) payload = JSON.parse($("api-body").value);
  } catch (error) {
    status(error.message === "Unexpected end of JSON input"
      ? "Provide valid JSON for the query parameters or request body." : error.message, "error");
    return;
  }
  if (operation.body?.required && (payload === undefined || payload === null)) {
    status("This operation requires a JSON request body.", "error");
    return;
  }
  const pathParams = Object.fromEntries([...$("api-path-params").querySelectorAll("[data-path-parameter]")]
    .map((input) => [input.dataset.pathParameter, input.value]));
  const operationId = `${operation.method} ${operation.path}`;
  const request = { operation: operationId, path_params: pathParams, query };
  if (payload !== undefined) request.payload = payload;
  if (operation.method !== "GET") {
    const preview = { operation: operationId, path_params: pathParams, query, payload };
    if (!await confirmOperation(
      `Send ${operation.method} ${operation.path} to ${endpoint().host}:${endpoint().port}?`,
      "", preview,
    )) return;
    request.confirm = true;
  }
  await task("Calling documented API operation...", async () => {
    const result = await api("api_request", request);
    if (result.response && result.response._download) downloadResponse(result.response._download);
    showResult(result);
  });
}

function showPage(page) {
  if (state.busy) return;
  state.page = page;
  const [title, description] = pages[page];
  $("page-title").textContent = page === "coming-soon" ? $("workflow-group").value : title;
  $("page-description").textContent = description;
  document.querySelectorAll("nav button").forEach((button) => {
    button.classList.toggle("active", button.dataset.page === page);
    if (button.dataset.page === page) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  for (const id of ["api-explorer", "health-check", "entries", "insert-entity", "insert-entry", "delete"]) {
    $(id + "-panel").hidden = id !== page;
  }
  $("result-panel").hidden = true;
  $("entity-picker").hidden = !["entities", "entries", "insert-entry", "delete-entity", "delete-entries"].includes(page);
  $("entity-count").hidden = $("entity-picker").hidden;
  if (page.startsWith("delete-")) {
    $("delete-panel").hidden = false;
    $("delete-title").textContent = page === "delete-entity" ? "Delete selected entity" : "Delete all catalog entries";
    $("delete-description").textContent = page === "delete-entity"
      ? "This permanently deletes the selected entity definition. This operation cannot be undone here."
      : "This permanently deletes every entry in the selected entity. Download a JSON backup from List entries first. The entity definition is kept.";
  }
  if (page === "entries" && state.selected && !state.entriesLoaded) loadEntries();
}

async function discoverEntities() {
  await task("Discovering entities...", async () => {
    const result = await api("entities");
    state.entities = result.entities;
    if (state.selected) {
      state.selected = state.entities.find((e) => e.name === state.selected.name
        && String(e.id) === String(state.selected.id)) || null;
    }
    clearEntries();
    renderEntities();
    status(`${state.entities.length} entities discovered. Click an entity to select it.`);
  });
}

function loadEntries() {
  return task("Loading entries...", async () => {
    const entity = requireEntity();
    clearEntries();
    const result = await api("entries", { entity });
    state.entries = result.entries;
    state.entriesLoaded = true;
    renderEntries();
    status(`Loaded ${state.entries.length} entries for ${entity}.`);
  });
}

function confirmOperation(message, expectedName = "", preview = null) {
  $("confirm-text").textContent = message;
  $("confirm-name").value = "";
  $("confirm-name-label").hidden = !expectedName;
  $("confirm-preview").hidden = preview === null;
  $("confirm-preview").textContent = preview === null ? "" : JSON.stringify(preview, null, 2);
  $("accept-confirm").disabled = Boolean(expectedName);
  $("confirm-name").oninput = () => {
    $("accept-confirm").disabled = $("confirm-name").value !== expectedName;
  };
  return new Promise((resolve) => {
    const dialog = $("confirm-dialog");
    dialog.returnValue = "";
    $("cancel-confirm").onclick = () => dialog.close("cancel");
    $("accept-confirm").onclick = () => dialog.close("confirm");
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), { once: true });
    dialog.showModal();
  });
}

function showResult(result, kind = "") {
  const { calls, ...output } = result;
  if (output.response && output.response._download) {
    output.response = {
      content_type: output.response._download.content_type,
      downloaded: true,
    };
  }
  $("result-panel").hidden = false;
  $("result").textContent = JSON.stringify(output, null, 2);
  status(result.message || "Operation completed.", kind);
}

function parseEditor(id) {
  try {
    return JSON.parse($(id).value);
  } catch {
    throw new Error("Provide valid JSON in the editor before continuing.");
  }
}

async function insertEntries() {
  let entity, payload;
  try {
    entity = requireEntity();
    payload = parseEditor("entry-json");
    if (payload && !Array.isArray(payload) && Array.isArray(payload.nacatalogs)) {
      payload = payload.nacatalogs;
    }
    const items = Array.isArray(payload) ? payload : [payload];
    if (!items.length || items.some((item) => !item || typeof item !== "object"
        || Array.isArray(item) || !Object.keys(item).length)) {
      throw new Error("Provide an entry object or a non-empty array of entry objects.");
    }
  } catch (error) { status(error.message, "error"); return; }
  const count = Array.isArray(payload) ? payload.length : 1;
  if (!await confirmOperation(`Insert ${count} entries into ${entity} on ${endpoint().host}:${endpoint().port}? Existing entries will remain.`, "", payload)) return;
  await task("Inserting entries...", async () => {
    clearEntries();
    showResult(await api("insert_entries", { entity, payload, confirm: true }));
    $("entry-json").value = "";
    $("entry-file").value = "";
  });
}

document.querySelectorAll("nav button").forEach((button) => {
  button.addEventListener("click", () => showPage(button.dataset.page));
});
$("workflow-group").onchange = () => {
  const supported = $("workflow-group").value === "Data Management";
  $("data-management-nav").hidden = !supported;
  $("workflow-coming-soon").hidden = supported;
  $("status").hidden = true;
  showPage(supported ? "entities" : "coming-soon");
};
$("refresh-entities").onclick = discoverEntities;
$("entity-search").oninput = renderEntities;
bindCopyButton($("copy-entity-name"), $("selected-entity-name"));
bindCopyButton($("copy-entity-id"), $("selected-entity-id"));
$("entry-search").oninput = renderEntries;
$("api-group").onchange = renderApiOperations;
$("api-operation").onchange = renderPathParameters;
$("load-api-example").onclick = loadApiExample;
$("execute-api-operation").onclick = executeApiOperation;
$("run-health-check").onclick = () => task("Checking backend health...", async () => {
  $("result-panel").hidden = true;
  showResult(await api("health_check"));
});
$("run-connectivity-check").onclick = () => task("Checking TCP connectivity...", async () => {
  $("result-panel").hidden = true;
  const result = await api("connectivity_check");
  showResult(result, result.response?.reachable === false ? "error" : "");
});
$("load-entries").onclick = loadEntries;
$("insert-entries").onclick = insertEntries;

for (const id of ["host", "port"]) {
  $(id).addEventListener("input", () => {
    state.entities = [];
    state.selected = null;
    clearEntries();
    $("entry-json").value = "";
    $("entry-file").value = "";
    $("result-panel").hidden = true;
    $("status").hidden = true;
    renderEntities();
  });
}

for (const [fileId, editorId] of [["entity-file", "entity-json"], ["entry-file", "entry-json"]]) {
  $(fileId).onchange = () => task("Reading JSON file...", async () => {
    const file = $(fileId).files[0];
    if (!file) { status("No file selected."); return; }
    if (file.size > 3 * 1024 * 1024) throw new Error("Choose a JSON file smaller than 3 MB.");
    const text = await file.text();
    try { JSON.parse(text); } catch { throw new Error("The selected file is not valid JSON."); }
    $(editorId).value = text;
    status(`Loaded ${file.name}. Review the JSON before inserting.`);
  });
}

$("insert-entity").onclick = async () => {
  let payload;
  try {
    payload = parseEditor("entity-json");
    if (!payload || Array.isArray(payload) || typeof payload !== "object" || !Object.keys(payload).length) {
      throw new Error("Entity definition must be a non-empty JSON object.");
    }
  } catch (error) { status(error.message, "error"); return; }
  if (!await confirmOperation(`Insert this entity definition on ${endpoint().host}:${endpoint().port}?`, "", payload)) return;
  await task("Inserting entity definition...", async () => {
    showResult(await api("insert_entity", { payload, confirm: true }));
    state.entities = [];
    state.selected = null;
    clearEntries();
    renderEntities();
    $("entity-json").value = "";
    $("entity-file").value = "";
  });
};

$("delete-action").onclick = async () => {
  let entity;
  try { entity = requireEntity(); } catch (error) { status(error.message, "error"); return; }
  const action = state.page === "delete-entity" ? "delete_entity" : "delete_entries";
  const operation = action === "delete_entity" ? "Permanently delete entity" : "Permanently delete ALL entries in";
  if (!await confirmOperation(`${operation} ${entity} on ${endpoint().host}:${endpoint().port}? This cannot be undone.`, entity)) return;
  await task("Deleting...", async () => {
    clearEntries();
    showResult(await api(action, { entity, confirm: true }));
    if (action === "delete_entity") {
      state.entities = state.entities.filter((e) => e.name !== entity);
      state.selected = null;
      renderEntities();
    }
  });
};

$("download-entries").onclick = () => {
  if (!state.entriesLoaded) return;
  const blob = new Blob([JSON.stringify({ nacatalogs: state.entries }, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  const url = URL.createObjectURL(blob);
  link.href = url;
  link.download = `${state.selected.name.replace(/[^a-zA-Z0-9._-]/g, "_")}-entries.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

loadApiOperations();
showPage("api-explorer");

$("clear-console").onclick = () => {
  $("terminal-output").value = "";
  state.callCount = 0;
  $("api-calls").replaceChildren();
  const empty = document.createElement("p");
  empty.className = "empty";
  empty.textContent = "No API calls yet.";
  $("api-calls").append(empty);
};
