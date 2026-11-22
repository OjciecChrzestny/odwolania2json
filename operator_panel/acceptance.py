"""Odbiór publicznego CLI i panelu w Chromium na jawnych syntetykach."""
import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from contextlib import closing, contextmanager
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright
from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation"))
from test_baseline_a import write_pdf
from test_review_cli import ACCOUNT, AMOUNT, NUMBER, RECEIPT

ACCEPTED = "sprawa/pelnomocnictwo.pdf"
CORRECTED = "sprawa/faktura.pdf"
NEGATIVE = "sprawa/potwierdzenie_przelewu.pdf"
BROKEN = "sprawa/uszkodzony.pdf"
MARKUP = "<img src=x onerror=globalThis.panelLeak=1>"
LONG = "pozycja_o_nazwie_ktora_musi_sie_zawinac_" * 3 + ".pdf"


def arguments(folder):
    return ["--input", str(folder / "input"), "--output", str(folder / "output"),
            "--diagnostics", str(folder / "diagnostics" / "run.json")]


def extract(folder, expected=1):
    run = subprocess.run([sys.executable, "-B", "-m", "odwolania2json", *arguments(folder)],
                         cwd=ROOT, text=True, capture_output=True, timeout=20)
    (folder / "cli.log").write_text(run.stdout + run.stderr)
    assert run.returncode == expected, (run.stdout, run.stderr)


def generate(folder):
    fixtures = folder / "fixtures"
    cover, receipt = fixtures / "cover.pdf", fixtures / "receipt.pdf"
    write_pdf(cover, "POTWIERDZENIE PRZELEWU\nData operacji: 2026-01-02\nSzczegoly na kolejnej stronie.")
    write_pdf(receipt, RECEIPT + "\nOpis: " + MARKUP)
    destination = folder / "input" / ACCEPTED
    destination.parent.mkdir(parents=True)
    with PdfWriter() as combined:
        combined.append(cover)
        combined.append(receipt)
        combined.write(destination)
    write_pdf(folder / "input" / CORRECTED, RECEIPT)
    write_pdf(folder / "input" / NEGATIVE, "Protokol wspomina odwolanie, przelew i pelnomocnictwo.")
    (folder / "input" / BROKEN).write_bytes(b"bad PDF")


@contextmanager
def panel(folder, *, demo=False, ocr_data=None):
    options = ["--demo-workspace", str(folder)] if demo else arguments(folder)
    if ocr_data:
        options.extend(("--ocr-data", str(ocr_data)))
    process = subprocess.Popen([sys.executable, "-B", "-m", "operator_panel", *options, "--port", "0"],
                               cwd=ROOT, text=True, stdout=subprocess.PIPE)
    try:
        startup = process.stdout.readline().strip()
        assert startup.startswith("Panel dostępny na http://127.0.0.1:"), startup
        yield startup.removeprefix("Panel dostępny na ")
    finally:
        process.terminate()
        process.wait(timeout=10)
        process.stdout.close()


def output_hashes(folder):
    root = folder / "output"
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*.json"))}


def select(page, name):
    page.get_by_role("button", name=name, exact=False).click()
    expect(page.locator("#doc-title")).to_have_text(name)


def tab_to(page, selector, max_tabs=24):
    for _ in range(max_tabs):
        if page.locator(selector).evaluate("(node) => node === document.activeElement"):
            return
        page.keyboard.press("Tab")
    raise AssertionError(f"Klawiatura nie dotarła do {selector}")


def unsafe_requests(page, url, folder):
    assert page.request.get(url + "/api/page", params={"name": "../poza.pdf", "number": 1, "review_id": "0" * 64}).status == 404
    assert page.request.get(url + "/api/document", params={"name": "/etc/passwd"}).status == 404
    assert page.request.get(url, headers={"Host": "inna-domena.invalid"}).status == 403
    assert page.request.post(url + "/api/decision", data={}, headers={"Origin": "https://inna-domena.invalid"}).status == 403
    source = folder / "input" / NEGATIVE
    backup = source.with_suffix(".bak")
    source.rename(backup)
    try:
        source.symlink_to(folder / "fixtures" / "receipt.pdf")
        blocked = page.request.get(url + "/api/document", params={"name": NEGATIVE}).json()
        assert blocked["review_id"] is None and blocked["review_status"] == "unavailable"
    finally:
        backup.replace(source)


def check_desktop(browser, folder, pngs):
    initial = output_hashes(folder)
    assert len(initial) == 3
    with panel(folder) as url:
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.set_default_timeout(6000)
        page.goto(url)
        expect(page.locator("#queue-count")).to_have_text("4 do kontroli / 4 w raporcie")
        expect(page.locator("#upload-panel")).to_be_hidden()
        assert page.request.post(url + "/api/upload", data=b"bad PDF",
                                 headers={"Origin": url, "Content-Type": "application/pdf"}).status == 404
        page.keyboard.press("Tab")
        expect(page.locator(".skip")).to_be_focused()
        assert page.locator(".skip").evaluate("(node) => getComputedStyle(node).outlineWidth") == "3px"
        tab_to(page, "#queue li:nth-child(2) button")
        page.keyboard.press("Enter")
        expect(page.locator("#doc-title")).to_have_text(ACCEPTED)
        expect(page.locator("#doc-title")).to_be_focused()
        page.select_option("#field", AMOUNT)
        expect(page.locator("#page-image")).to_have_attribute("alt", "Fizyczna strona 2 z 2 pliku PDF")
        expect(page.locator("#page-image")).to_be_visible()
        expect(page.locator("#snippet")).to_have_text("12,50")
        expect(page.locator("#page-state")).to_contain_text("Czytelna")
        page.wait_for_function("document.querySelector('#page-image').naturalWidth > 0")
        page.locator("#page-text-wrap summary").click()
        expect(page.locator("#page-text")).to_contain_text(MARKUP)
        expect(page.locator("#page-text img")).to_have_count(0)
        assert page.evaluate("!globalThis.panelLeak")
        page.locator("#page-text-wrap summary").click()
        page.select_option("#page", "1")
        expect(page.locator("#page-image")).to_have_attribute("alt", "Fizyczna strona 1 z 2 pliku PDF")
        page.get_by_role("button", name="Otwórz stronę dowodu").click()
        expect(page.locator("#page-image")).to_have_attribute("alt", "Fizyczna strona 2 z 2 pliku PDF")
        page.screenshot(path=pngs / "desktop-1440.png", full_page=True)
        old = page.request.get(url + "/api/document", params={"name": ACCEPTED}).json()
        page.locator("#doc-title").focus()
        tab_to(page, "#accept")
        page.keyboard.press("Enter")
        expect(page.locator("#audit-title")).to_have_text("Zapisano akceptację")

        select(page, CORRECTED)
        page.select_option("#field", ACCOUNT)
        expect(page.locator("#evidence-note")).to_contain_text("Brak cytatu")
        expect(page.locator("#value")).to_have_text("null")
        page.locator("#correct-wrap summary").focus()
        page.keyboard.press("Enter")
        page.keyboard.press("Tab")
        expect(page.locator("#new-value")).to_be_focused()
        page.keyboard.type(NUMBER)
        page.keyboard.press("Enter")
        expect(page.locator("#audit-title")).to_have_text("Zapisano korektę")
        expect(page.locator("#audit-change")).to_contain_text(NUMBER)
        expect(page.locator("#value")).to_have_text("null")

        select(page, NEGATIVE)
        page.locator("#raw-wrap summary").click()
        expect(page.locator("#raw")).to_have_text("Pusty plik (0 B).")
        select(page, BROKEN)
        expect(page.locator("#case-status")).to_have_text("Wynik niedostępny")
        expect(page.locator("#page-message")).to_contain_text("Brak podglądu")
        expect(page.locator("#actions")).to_be_hidden()
        expect(page.locator("#read-error")).to_be_visible()
        unsafe_requests(page, url, folder)
        page.close()
    assert output_hashes(folder) == initial
    assert (folder / "output" / Path(NEGATIVE).with_suffix(".json")).stat().st_size == 0
    return initial, old


def check_resume(browser, folder, pngs, old, initial):
    journal = folder / "diagnostics" / "run.decisions.sqlite3"
    digest = hashlib.sha256(journal.read_bytes()).hexdigest()
    with panel(folder) as url:
        page = browser.new_page(viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True)
        page.set_default_timeout(6000)
        page.goto(url)
        select(page, CORRECTED)
        expect(page.locator("#audit-title")).to_have_text("Zapisano korektę")
        page.locator(".audit-ids summary").click()
        expect(page.locator("#audit-ids")).to_contain_text("SHA-256 PDF-u")
        select(page, ACCEPTED)
        expect(page.locator("#audit-title")).to_have_text("Zapisano akceptację")
        page.select_option("#field", AMOUNT)
        expect(page.locator("#page-image")).to_have_attribute("alt", "Fizyczna strona 2 z 2 pliku PDF")
        expect(page.locator("#page-image")).to_be_visible()
        page.locator("#zoom").focus()
        page.keyboard.press("Enter")
        expect(page.locator("#zoom")).to_have_attribute("aria-pressed", "true")
        assert page.locator("#page-wrap").evaluate("(node) => node.scrollWidth > node.clientWidth")
        page.keyboard.press("Enter")
        expect(page.locator("#zoom")).to_have_attribute("aria-pressed", "false")
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
        page.screenshot(path=pngs / "phone-375.png", full_page=True)
        assert output_hashes(folder) == initial
        source = folder / "input" / ACCEPTED
        with source.open("ab") as stream:
            stream.write(b"\n% dodatkowa stopka\n")
        stale = page.request.post(url + "/api/decision",
                                  data={"name": ACCEPTED, "review_id": old["review_id"], "action": "accept"},
                                  headers={"Origin": url})
        assert stale.status == 409, stale.text()
        page.get_by_role("button", name="Odśwież").click()
        expect(page.locator("#case-status")).to_have_text("Wynik nieaktualny")
        expect(page.locator("#audit")).to_be_hidden()
        expect(page.locator("#actions")).to_be_hidden()
        extract(folder)
        page.get_by_role("button", name="Odśwież").click()
        expect(page.locator("#case-status")).to_have_text("Do kontroli")
        expect(page.locator("#actions")).to_be_visible()
        fresh = page.request.get(url + "/api/document", params={"name": ACCEPTED}).json()
        assert fresh["review_id"] != old["review_id"] and fresh["decision"] is None
        assert fresh["pdf_sha256"] != old["pdf_sha256"] and fresh["output_sha256"] == old["output_sha256"]
        stale_preview = page.request.get(url + "/api/page", params={"name": ACCEPTED, "number": 2,
                                                                   "review_id": old["review_id"]})
        assert stale_preview.status == 409
        page.close()
    assert output_hashes(folder) == initial
    assert hashlib.sha256(journal.read_bytes()).hexdigest() == digest
    with closing(sqlite3.connect(journal.as_uri() + "?mode=ro", uri=True)) as store:
        assert store.execute("SELECT count(*) FROM decisions").fetchone()[0] == 2
    return digest


def check_empty_and_long(browser, folder):
    folder.mkdir()
    with panel(folder) as url:
        page = browser.new_page(viewport={"width": 375, "height": 812})
        page.set_default_timeout(6000)
        page.goto(url)
        expect(page.locator("#notice")).to_contain_text("Brak raportu")
        extract(folder, expected=0)
        page.get_by_role("button", name="Odśwież").click()
        expect(page.locator("#queue-empty")).to_have_text("Brak dokumentów w raporcie.")
        write_pdf(folder / "input" / LONG, RECEIPT)
        extract(folder, expected=0)
        page.get_by_role("button", name="Odśwież").click()
        expect(page.locator("#doc-title")).to_have_text(LONG)
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
        page.close()


def upload(page, workspace, source):
    previous = page.url
    page.get_by_role("button", name="Wgraj własny PDF", exact=True).set_input_files(source)
    with page.expect_response(lambda response: response.url.endswith("/api/upload"), timeout=200_000) as pending:
        page.get_by_role("button", name="Przetwórz PDF").click()
    response = pending.value
    assert response.status == 201, response.text()
    page.wait_for_url(lambda url: url != previous and "run" in parse_qs(urlsplit(url).query))
    run_id, = parse_qs(urlsplit(page.url).query)["run"]
    assert re.fullmatch(r"[0-9a-f]{32}", run_id)
    expect(page.locator("#doc-title")).to_have_text("dokument.pdf")
    expect(page.locator("#upload-submit")).to_be_enabled()
    directory = workspace / run_id
    assert [path.name for path in (directory / "input").iterdir()] == ["dokument.pdf"]
    assert (directory / "input" / "dokument.pdf").read_bytes() == source.read_bytes()
    assert page.locator("#raw-wrap").evaluate("(details) => details.open")
    record, = json.loads((directory / "diagnostics" / "run.json").read_bytes())["documents"]
    return directory, record["status"] == "read_error"


def check_upload(browser, evidence, ocr_data):
    fixtures = evidence / "upload-fixtures"
    receipt = fixtures / "faktura-wlasny-dokument.pdf"
    negative = fixtures / "potwierdzenie-jedynie-protokol.pdf"
    broken = fixtures / "blad-odczytu.pdf"
    write_pdf(receipt, RECEIPT.replace("12,50", "137,29") + "\nOpis: Wplata pokazowa")
    write_pdf(negative, "Protokol z otwarcia ofert. Wspomniano tylko planowany przelew.")
    broken.write_bytes(b"niepoprawny PDF")
    foreign = evidence / "existing-report"
    foreign.mkdir()
    sentinel = foreign / "raport.json"
    sentinel.write_bytes(b"existing data")
    rejected = subprocess.run([sys.executable, "-B", "-m", "operator_panel", "--demo-workspace", str(foreign)],
                              cwd=ROOT, capture_output=True, timeout=10)
    assert rejected.returncode == 2 and sentinel.read_bytes() == b"existing data"
    assert sorted(path.name for path in foreign.iterdir()) == ["raport.json"]

    workspace = evidence / "upload-workspace"
    with panel(workspace, demo=True, ocr_data=ocr_data) as url:
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(url)
        expect(page.locator("#empty")).to_have_text("Wybierz PDF, aby zobaczyć wynik.")
        expect(page.locator("#upload-panel")).to_be_visible()
        assert page.request.get(url + "/api/documents", params={"run": ".."}).status == 404
        assert page.request.post(url + "/api/upload", data=b"bad PDF", headers={
            "Origin": "https://inna-domena.invalid", "Content-Type": "application/pdf",
        }).status == 403
        with closing(HTTPConnection(urlsplit(url).netloc, timeout=10)) as connection:
            connection.request("POST", "/api/upload", headers={
                "Content-Type": "application/pdf", "Origin": url, "Content-Length": str(32 * 1024 * 1024 + 1),
            })
            assert connection.getresponse().status == 413
        positive_run, read_error = upload(page, workspace, receipt)
        assert not read_error
        expect(page.locator("#raw")).to_contain_text("137.29")
        raw = positive_run / "output" / "dokument.json"
        original_sha = hashlib.sha256(raw.read_bytes()).hexdigest()
        assert page.locator("#raw").text_content().encode("utf-8") == raw.read_bytes()
        page.select_option("#field", AMOUNT)
        expect(page.locator("#value")).to_have_text("137.29")
        expect(page.locator("#snippet")).to_have_text("137,29")
        expect(page.locator("#page-image")).to_have_attribute("alt", "Fizyczna strona 1 z 1 pliku PDF")
        expect(page.locator("#page-image")).to_be_visible()
        page.screenshot(path=evidence / "upload-result.png", full_page=True)
        page.get_by_role("button", name="Akceptuj wynik").click()
        expect(page.locator("#audit-title")).to_have_text("Zapisano akceptację")
        assert hashlib.sha256(raw.read_bytes()).hexdigest() == original_sha

        page.set_viewport_size({"width": 375, "height": 812})
        negative_run, read_error = upload(page, workspace, negative)
        assert not read_error
        expect(page.locator("#raw")).to_have_text("Pusty plik (0 B).")
        assert (negative_run / "output" / "dokument.json").stat().st_size == 0
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth")

        failed_run, read_error = upload(page, workspace, broken)
        assert read_error
        expect(page.locator("#notice")).to_have_text("Ekstraktor zgłosił błąd odczytu PDF-u.")
        expect(page.locator("#case-status")).to_have_text("Wynik niedostępny")
        expect(page.locator("#actions")).to_be_hidden()
        assert not list((failed_run / "output").glob("*.json"))

        ocr = None
        if ocr_data:
            scan, read_error = upload(page, workspace, ROOT / "delivery/compose/skan-syntetyczny.pdf")
            assert not read_error
            expect(page.locator("#raw")).to_contain_text("123.45")
            page.select_option("#field", AMOUNT)
            expect(page.locator("#value")).to_have_text("123.45")
            expect(page.locator("#evidence-meta")).to_contain_text("OCR")
            document = json.loads((scan / "diagnostics" / "run.json").read_bytes())["documents"][0]
            assert document["fields"][AMOUNT]["page"] == 1 and document["fields"][AMOUNT]["source"] == "ocr"
            ocr = {"amount": 123.45, "page": 1, "source": "ocr"}
        page.close()
    with panel(workspace, demo=True, ocr_data=ocr_data) as url:
        page = browser.new_page()
        page.goto(url + "/?run=" + positive_run.name)
        expect(page.locator("#audit-title")).to_have_text("Zapisano akceptację")
        assert hashlib.sha256(raw.read_bytes()).hexdigest() == original_sha
        page.close()
    return {"positive": {"amount": 137.29, "page": 1, "unchanged_output_sha256": original_sha},
            "negative_bytes": 0, "broken_pdf_output_count": 0, "saved_decision_after_restart": True,
            "separate_runs": len(list(workspace.glob("*/input/dokument.pdf"))), "ocr": ocr}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--ocr-data", type=Path, help="dodatkowa próba faktycznego OCR po wgraniu PDF-u")
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    evidence.mkdir()
    folder = evidence / "run"
    generate(folder)
    extract(folder)
    with sync_playwright() as playwright, playwright.chromium.launch() as browser:
        initial, old = check_desktop(browser, folder, evidence)
        digest = check_resume(browser, folder, evidence, old, initial)
        check_empty_and_long(browser, evidence / "empty-and-long")
        upload_result = check_upload(browser, evidence, args.ocr_data)
        result = {"chromium": browser.version, "viewports": ["1440x900", "375x812"], "output_sha256": initial,
                  "negative_bytes": 0, "decisions_after_restart": 2, "stale_write_status": 409,
                  "journal_sha256_after_both_extractions": digest, "upload": upload_result,
                  "checked": ["keyboard", "no_quote", "read_error", "empty", "long_label", "safe_text",
                              "traversal", "symlink", "origin", "host", "physical_page_2", "zoom", "stale_preview"]}
        text = json.dumps(result, indent=2) + "\n"
        (evidence / "result.json").write_text(text)
        print(text, end="")


if __name__ == "__main__":
    main()
