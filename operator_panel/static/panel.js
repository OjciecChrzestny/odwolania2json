"use strict";

const el = (id) => document.getElementById(id);
const statuses = {
  review_required: "Do kontroli", auto_accepted: "Akceptacja automatyczna",
  resolved: "Rozpatrzony", unavailable: "Wynik niedostępny", stale: "Wynik nieaktualny",
};
const classes = {
  przelew: "Potwierdzenie przelewu", odwolanie: "Odwołanie", pelnomocnictwo: "Pełnomocnictwo",
  negative: "Dokument spoza klas", read_error: "Błąd odczytu",
};
const pageStates = {
  readable: "Czytelna", partial: "Częściowo czytelna", unreadable: "Nieczytelna", unassessed: "Niezbadana",
};
const pageReasons = {
  ocr_page_budget: "Wyczerpano limit stron lokalnego OCR. Stronę można otworzyć do ręcznej kontroli.",
  native_read_failed: "Nie udało się odczytać warstwy tekstowej strony PDF-u.",
  ocr_interrupted: "Przerwano lokalny OCR tej strony.",
};
const reasons = {
  account_role_conflict: "Sprzeczna rola rachunku",
  account_role_unconfirmed: "Rola rachunku wymaga potwierdzenia",
  classification_conflict: "Sprzeczne przesłanki klasyfikacji",
  field_evidence_conflict: "Sprzeczne dowody dla pola",
  field_evidence_insufficient: "Niewystarczający dowód pola",
  invalid_account_checksum: "Nieprawidłowa suma kontrolna rachunku",
  missing_required_value: "Brak wymaganej wartości",
  native_fragment: "Warstwa tekstowa zawiera fragment",
  native_replacement_character: "Znaki zastępcze w warstwie tekstowej",
  native_text: "Warstwa tekstowa PDF-u",
  ocr_fragment: "OCR zwrócił fragment tekstu",
  ocr_no_page_result: "OCR nie zwrócił strony",
  ocr_no_text: "OCR nie zwrócił tekstu",
  ocr_not_configured: "OCR nie został włączony",
  ocr_not_selected: "Strona nie została skierowana do OCR",
  ocr_sparse_text: "OCR zwrócił niewiele słów",
  ocr_text: "Tekst z OCR",
  optional_absence_unconfirmed: "Brak pola opcjonalnego wymaga potwierdzenia",
  page_limit: "Strona poza limitem analizy",
  page_observations_incomplete: "Brak oceny części stron",
  page_observations_invalid: "Niespójna ocena stron",
  page_partial: "Strona częściowo czytelna",
  page_unassessed: "Strona niezbadana",
  page_unreadable: "Strona nieczytelna",
  profile_not_verified: "Profil wymaga kontroli operatora",
  read_error: "Ekstraktor zgłosił błąd odczytu",
  review_policy_unavailable: "Brak automatycznej oceny wyniku",
  uncertain_negative: "Brak pewnego dowodu wykluczającego klasy docelowe",
  unexpected_negative_value: "Niespójny pusty wynik",
  unknown_profile: "Brak profilu automatycznej kontroli",
};
let queue = [];
let current = null;
let fields = [];
let docRequest = 0;
let pageRequest = 0;
let pageNumber = 0;
let saving = false;
let uploadMode = null;
let runId = null;
let uploading = false;

function text(id, value) {
  el(id).textContent = value;
}

function message(value, isError = false) {
  text("notice", value);
  el("notice").hidden = !value;
  el("notice").dataset.error = isError;
}

function element(tag, value) {
  const node = document.createElement(tag);
  node.textContent = value;
  return node;
}

function reasonLabel(reason) {
  return [reasons[reason.code] || reason.code, reason.field, reason.page && "strona " + reason.page]
    .filter(Boolean).join(" · ");
}

async function api(path, query = {}, options) {
  const url = new URL("/api/" + path, window.location.origin);
  url.search = new URLSearchParams(query);
  if (runId && !["mode", "upload"].includes(path)) url.searchParams.set("run", runId);
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    throw Object.assign(new Error(data.error || "Nie udało się wczytać danych panelu."), { status: response.status });
  }
  return data;
}

function renderQueue() {
  const waiting = queue.filter((item) => !["resolved", "auto_accepted"].includes(item.status));
  text("queue-count", waiting.length + " do kontroli / " + queue.length + " w raporcie");
  const items = el("pending").checked ? waiting : queue;
  text("queue-empty", queue.length ? "Kolejka kontroli jest pusta." : "Brak dokumentów w raporcie.");
  el("queue-empty").hidden = items.length > 0;
  el("queue").replaceChildren(...items.map((item) => {
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "queue-item";
    button.setAttribute("aria-current", String(item.input === current?.input));
    button.append(element("strong", item.input));
    button.append(element("small", statuses[item.status] || item.status));
    if (item.reasons.length && item.status === "review_required") {
      button.append(element("small", reasonLabel(item.reasons[0])));
    }
    button.addEventListener("click", () => openDocument(item.input, { focus: true }).catch(showError));
    li.append(button);
    return li;
  }));
}

function flatten(value, schema, prefix = []) {
  if (Array.isArray(value)) {
    return value.flatMap((child, index) => typeof child === "object" && child !== null
      ? flatten(child, schema?.[0], [...prefix, index]) : []);
  }
  if (value !== null && typeof value === "object") {
    return Object.entries(value).flatMap(([key, child]) => flatten(child, schema?.[key], [...prefix, key]));
  }
  return [{ path: prefix.join("."), value, type: schema }];
}

function selectedField() {
  return fields.find((field) => field.path === el("field").value);
}

function proofFor(path) {
  const evidence = current?.fields[path];
  return Array.isArray(evidence) ? evidence.find((item) => item.page) || evidence[0] : evidence;
}

function fieldOptionLabel(path) {
  const source = current.eligible_fields?.[path];
  if (source === "text") {
    return path + (current.text_evidence_measurement?.strong ? " · mocny dowód tekstowy" : " · dowód tekstowy");
  }
  return source === "ocr" ? path + " · cytat OCR" : path;
}

function renderEvidenceQuality(field) {
  const quality = el("field-evidence-quality");
  quality.hidden = !field && current?.review_status !== "stale";
  if (quality.hidden) return;
  const source = field && current.eligible_fields?.[field.path];
  if (source === "text") {
    const measurement = current.text_evidence_measurement;
    const label = measurement?.strong
      ? "Mocne powiązanie z tekstem PDF-u."
      : "Dowód z tekstu PDF-u — do weryfikacji.";
    let observation = "";
    if (measurement?.total > 0) {
      observation = " Zgodnych oznaczeń w próbie kontrolnej: " + measurement.correct + "/" + measurement.total + ".";
    } else if (measurement?.total === 0 && measurement.sample_pdfs > 0 && measurement.marked_pdfs === 0) {
      observation = " W niezależnej próbie " + measurement.sample_pdfs +
        " syntetycznych PDF-ów reguła nie oznaczyła pól. Trafność na nowych dokumentach pozostaje nieznana.";
    }
    quality.textContent = label + " Cytat ze strony " + proofFor(field.path).page +
      " odpowiada zapisowi w JSON-ie." + observation;
  } else if (source === "ocr") {
    quality.textContent = "Cytat z OCR — do weryfikacji. Strona " + proofFor(field.path).page + ".";
  } else {
    quality.textContent = "Brak mocnego powiązania z dowodem — pole do weryfikacji.";
  }
}

function invalidateEvidenceQuality() {
  if (!current) return;
  current.eligible_fields = {};
  for (const option of el("field").options) option.textContent = fieldOptionLabel(option.value);
  renderEvidenceQuality(selectedField());
}

function renderField() {
  const field = selectedField();
  if (!field) return;
  renderEvidenceQuality(field);
  const proof = proofFor(field.path);
  text("value", JSON.stringify(field.value));
  const source = { text: "Tekst PDF-u", ocr: "OCR" }[proof?.source];
  text("evidence-meta", [proof?.page && "Strona " + proof.page, source, proof?.rule].filter(Boolean).join(" · "));
  const exact = proof?.precision === "snippet" && typeof proof.snippet === "string" && proof.snippet.length > 0;
  text("snippet", exact ? proof.snippet : "");
  el("snippet").hidden = !exact;
  text("evidence-note", exact ? "Fragment tekstu odczytanego ze strony." :
    proof?.page ? "Brak cytatu dla tego pola. Sprawdź wskazaną stronę." :
      "Brak cytatu i przypisanej strony dla tego pola.");
  el("go-evidence").hidden = !proof?.page || !current.review_id;
  const hasSchema = typeof field.type === "string";
  const numeric = hasSchema && /^(number|integer|reason|flag)\??$/.test(field.type);
  el("correct-wrap").hidden = !hasSchema;
  el("new-value").value = field.value ?? "";
  el("new-value").inputMode = numeric ? "decimal" : "text";
  el("new-value").disabled = false;
  el("set-null").checked = false;
  el("null-wrap").hidden = !hasSchema || !field.type.endsWith("?");
  text("correction-hint", numeric ? "Wpisz liczbę, np. 12,50." : "Wpisz tekst zgodny z dokumentem.");
}

function setPages(count, number) {
  el("page").replaceChildren(...Array.from({ length: count }, (_, index) =>
    new Option(String(index + 1), String(index + 1))));
  el("page").disabled = count < 2;
  el("page").value = String(number);
}

function zoomPage(zoomed) {
  const viewer = el("page-wrap");
  viewer.classList.toggle("zoomed", zoomed);
  el("zoom").setAttribute("aria-pressed", String(zoomed));
  text("zoom", zoomed ? "Dopasuj stronę" : "Powiększ stronę");
  if (zoomed) viewer.tabIndex = 0;
  else viewer.removeAttribute("tabindex");
}

async function openPage(number) {
  const request = ++pageRequest;
  pageNumber = number;
  el("page").value = String(number);
  const observation = current?.pages.find((page) => page.page === number);
  const status = observation ? pageStates[observation.status] || observation.status : "Niezbadana";
  const reason = observation ? pageReasons[observation.reason] || reasons[observation.reason] || observation.reason : "";
  text("page-state", [status, reason].filter(Boolean).join(" · "));
  const image = el("page-image");
  image.hidden = true;
  image.removeAttribute("src");
  el("zoom").hidden = true;
  zoomPage(false);
  el("page-text-wrap").open = false;
  el("page-text-wrap").hidden = true;
  text("page-text", "");
  el("page-message").hidden = false;
  if (!current?.review_id) {
    text("page-message", current?.review_status === "stale"
      ? "PDF lub wynik uległ zmianie. Uruchom ekstrakcję ponownie i odśwież panel."
      : "Brak podglądu dla bieżącego wyniku.");
    el("page-wrap").setAttribute("aria-busy", "false");
    return;
  }
  text("page-message", "Wczytywanie strony…");
  el("page-wrap").setAttribute("aria-busy", "true");
  try {
    const data = await api("page", { name: current.input, number, review_id: current.review_id });
    if (request !== pageRequest) return;
    setPages(data.page_count, data.page);
    image.alt = "Fizyczna strona " + data.page + " z " + data.page_count + " pliku PDF";
    image.src = data.image;
    image.hidden = false;
    el("zoom").hidden = false;
    text("page-text", data.text.trim() || "Ta strona nie zawiera dostępnej natywnej warstwy tekstowej.");
    el("page-text-wrap").hidden = false;
    el("page-message").hidden = true;
  } catch (error) {
    if (request === pageRequest) {
      if (error.status === 409) invalidateEvidenceQuality();
      text("page-message", error.message);
    }
  } finally {
    if (request === pageRequest) el("page-wrap").setAttribute("aria-busy", "false");
  }
}

function renderAudit(decision) {
  el("audit").hidden = !decision;
  if (!decision) return;
  text("audit-title", decision.action === "accepted" ? "Zapisano akceptację" : "Zapisano korektę");
  text("audit-change", decision.field ?
    decision.field + " · " + JSON.stringify(decision.original_value) + " → " +
    JSON.stringify(decision.corrected_value) : "Akceptacja surowego wyniku.");
  el("audit-time").dateTime = decision.decided_at;
  text("audit-time", new Date(decision.decided_at).toLocaleString("pl-PL", {
    dateStyle: "medium", timeStyle: "medium", timeZone: "Europe/Warsaw",
  }) + " · czas Warszawy");
  const identifiers = {
    "Identyfikator decyzji": decision.review_id, "SHA-256 PDF-u": decision.pdf_sha256,
    "SHA-256 wyniku": decision.output_sha256, "Rewizja ekstraktora": decision.extractor_revision,
  };
  el("audit-ids").replaceChildren(...Object.entries(identifiers)
    .flatMap(([key, value]) => [element("dt", key), element("dd", value)]));
}

function renderDocument(preferredField) {
  text("case-class", classes[current.class] || current.class);
  text("doc-title", current.input);
  text("case-status", statuses[current.review_status] || current.review_status);
  el("case-status").dataset.status = current.review_status;
  const list = current.review.reasons || [];
  text("reasons-title", "Powody kontroli (" + list.length + ")");
  el("reasons-wrap").hidden = !list.length;
  el("reasons-wrap").open = Boolean(list.length);
  el("reasons").replaceChildren(...list.map((reason) => element("li", reasonLabel(reason))));
  fields = current.result === null ? [] : flatten(current.result, current.schema);
  const initialField = fields.find((field) => field.path === preferredField) ||
    fields.find((field) => proofFor(field.path)?.precision === "snippet") || fields[0];
  el("field").replaceChildren(...fields.map(({ path }) => new Option(fieldOptionLabel(path), path)));
  el("field-wrap").hidden = !initialField;
  el("correct-wrap").hidden = !initialField;
  if (initialField) {
    el("field").value = initialField.path;
    renderField();
  } else {
    renderEvidenceQuality(null);
  }
  renderAudit(current.decision);
  el("actions").hidden = current.review_status !== "review_required" || !current.review_id;
  el("correct-wrap").open = false;
  const error = current.path_error || (current.status === "read_error" ? current.error || "Błąd odczytu PDF-u." : "");
  text("read-error", error);
  el("read-error").hidden = !error;
  text("raw", current.result !== null ? current.raw_json :
    current.class === "negative" && current.review_id ? "Pusty plik (0 B)." : "Brak bieżącego wyniku.");
  const number = proofFor(initialField?.path)?.page || list.find((reason) => reason.page)?.page || 1;
  setPages(current.pages.length || (current.review_id ? 1 : 0), number);
  el("case").hidden = false;
  el("empty").hidden = true;
  void openPage(number);
}

function showError(error) {
  message(error.message, true);
  el("notice").focus();
}

async function openDocument(name, { focus = false, preferredField = null } = {}) {
  const request = ++docRequest;
  ++pageRequest;
  current = null;
  el("case").hidden = true;
  el("empty").hidden = false;
  text("empty", "Wczytywanie dokumentu…");
  try {
    const documentView = await api("document", { name });
    if (request !== docRequest) return;
    current = documentView;
    renderQueue();
    renderDocument(preferredField);
    if (focus) el("doc-title").focus();
  } catch (error) {
    if (request !== docRequest) return;
    text("empty", "Nie udało się otworzyć dokumentu.");
    throw error;
  }
}

async function refresh() {
  message("");
  invalidateEvidenceQuality();
  queue = await api("documents");
  const previous = current?.input;
  const name = queue.find((item) => item.input === previous)?.input ||
    queue.find((item) => !["resolved", "auto_accepted"].includes(item.status))?.input || queue[0]?.input;
  renderQueue();
  if (name) {
    await openDocument(name, { preferredField: selectedField()?.path });
  } else {
    ++docRequest;
    ++pageRequest;
    current = null;
    el("case").hidden = true;
    el("empty").hidden = false;
    text("empty", uploadMode?.upload_enabled ? "Wybierz PDF, aby zobaczyć wynik." :
      "Przetwórz PDF-y w CLI, a następnie odśwież panel.");
  }
}

function correctionValue(field) {
  if (el("set-null").checked) return null;
  const value = el("new-value").value;
  if (!/^(number|integer|reason|flag)\??$/.test(field.type)) return value;
  const numeric = Number(value.trim().replace(",", "."));
  if (!value.trim() || !Number.isFinite(numeric)) throw new Error("Podaj poprawną liczbę.");
  return numeric;
}

async function decide(action) {
  if (!current?.review_id || saving || uploading) return;
  const { input: name, review_id } = current;
  const field = selectedField();
  const payload = { name, review_id, action };
  try {
    if (action === "correct") Object.assign(payload, { field: field.path, value: correctionValue(field) });
  } catch (error) {
    showError(error);
    return;
  }
  saving = true;
  el("accept").disabled = el("correct").disabled = true;
  try {
    await api("decision", {}, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload) });
    queue = await api("documents");
    if (current?.input === name) {
      await openDocument(name, { preferredField: field?.path });
      el("audit-title").focus();
    } else {
      renderQueue();
    }
    message("Zapisano decyzję w dzienniku.");
  } catch (error) {
    if (error.status === 409 && current?.input === name) invalidateEvidenceQuality();
    showError(error);
  } finally {
    saving = false;
    el("accept").disabled = el("correct").disabled = false;
  }
}

el("refresh").addEventListener("click", () => refresh().catch(showError));
el("pending").addEventListener("change", renderQueue);
el("zoom").addEventListener("click", () => zoomPage(el("zoom").getAttribute("aria-pressed") !== "true"));
el("page").addEventListener("change", (event) => void openPage(Number(event.target.value)));
el("field").addEventListener("change", () => {
  renderField();
  const page = proofFor(selectedField()?.path)?.page;
  if (page && page !== pageNumber) void openPage(page);
});
el("go-evidence").addEventListener("click", () => void openPage(proofFor(selectedField().path).page));
el("set-null").addEventListener("change", (event) => { el("new-value").disabled = event.target.checked; });
el("accept").addEventListener("click", () => void decide("accept"));
el("correction").addEventListener("submit", (event) => {
  event.preventDefault();
  void decide("correct");
});
function uploadStatus(value) {
  text("upload-status", value);
  el("upload-status").hidden = !value;
}

async function uploadPdf(event) {
  event.preventDefault();
  const file = el("upload-file").files[0];
  if (!file || uploading || saving) return;
  if (!file.size || file.size > uploadMode.max_upload_bytes) {
    showError(new Error("Wybierz niepusty PDF o rozmiarze do " + uploadMode.max_upload_bytes / 1048576 + " MiB."));
    return;
  }
  uploading = true;
  el("upload-file").disabled = el("upload-submit").disabled = true;
  el("accept").disabled = el("correct").disabled = true;
  message("");
  uploadStatus("Trwa lokalna ekstrakcja PDF-u…");
  try {
    const result = await api("upload", {}, { method: "POST", headers: { "Content-Type": "application/pdf" },
      body: file });
    runId = result.run;
    const url = new URL(window.location.href);
    url.searchParams.set("run", runId);
    window.history.replaceState(null, "", url);
    ++docRequest;
    ++pageRequest;
    current = null;
    await refresh();
    el("upload-form").reset();
    el("raw-wrap").open = true;
    message(result.read_error ? "Ekstraktor zgłosił błąd odczytu PDF-u." : "Wynik jest gotowy.", result.read_error);
    el("doc-title").focus();
  } catch (error) {
    showError(error);
  } finally {
    uploading = false;
    el("upload-file").disabled = el("upload-submit").disabled = false;
    el("accept").disabled = el("correct").disabled = false;
    uploadStatus("");
  }
}

async function initialize() {
  uploadMode = await api("mode");
  if (uploadMode.upload_enabled) {
    runId = new URLSearchParams(window.location.search).get("run");
    const limit = uploadMode.max_upload_bytes / 1048576;
    text("upload-hint", "Jeden PDF do " + limit + " MiB. " +
      (uploadMode.ocr_enabled ? "Polski OCR jest włączony." : "Odczyt warstwy tekstowej PDF-u."));
    el("upload-panel").hidden = false;
    el("upload-form").addEventListener("submit", (event) => void uploadPdf(event));
  }
  await refresh();
}

initialize().catch((error) => {
  text("empty", uploadMode?.upload_enabled ? "Wybierz PDF lub sprawdź adres przebiegu." :
    "Panel oczekuje na dostępny raport.");
  showError(error);
});
