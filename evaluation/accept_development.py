"""Odbiór publicznego CLI z użyciem wyłącznie dokumentów rozwojowych UZP."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from prepare_input import prepare
from score import load_object

DEVELOPMENT = Path(__file__).with_name("development-40.json")
PAYMENT = "case_01/doc_02.pdf"


def run_cli(folder):
    subprocess.run([sys.executable, "-m", "odwolania2json"], cwd=folder, check=True)
    raw = folder / "diagnostics/last-run.json"
    return {item["output"]: item for item in load_object(raw)["documents"]}


def first_payment(dataset, work):
    first = work / "first"
    prepare(dataset, DEVELOPMENT, first / "input", PAYMENT)
    run_cli(first)

    other = work / "renamed"
    new_name = other / "input/inna_sprawa/losowy.pdf"
    new_name.parent.mkdir(parents=True)
    shutil.copyfile(first / "input" / PAYMENT, new_name)
    run_cli(other)

    entry = next(row for row in load_object(DEVELOPMENT)["documents"] if row["input"] == PAYMENT)
    expected = load_object(dataset / entry["reference"])
    result = first / "output" / Path(PAYMENT).with_suffix(".json")
    actual = load_object(result)
    renamed = other / "output/inna_sprawa/losowy.json"
    for key, value in expected["przelew_bankowy"].items():
        obtained = actual["przelew_bankowy"][key]
        matched = value == obtained and type(value) is type(obtained)
        print(f"{key}: {'zgodne' if matched else 'rozbieżne'}")
        assert matched, f"Rozbieżne pole {key}"
    assert actual == expected
    assert result.read_bytes() == renamed.read_bytes()
    assert actual["przelew_bankowy"]["z_rachunku"] != actual["przelew_bankowy"]["na_rachunek"]


def full_tree(dataset, work):
    run = work / "tree"
    source = run / "input"
    wanted = {"case_01/doc_01.pdf", PAYMENT, "case_01/doc_03.pdf",
              "case_41/doc_03.pdf", "case_66/doc_01.pdf"}
    rows = load_object(DEVELOPMENT)["documents"]
    selected = {row["input"]: row["class"] for row in rows if row["input"] in wanted}
    assert set(selected) == wanted
    # Oddzielne etapy przygotowania i ekstrakcji, każdy przygotowany plik pochodzi z manifestu.
    for index, name in enumerate(sorted(wanted)):
        stage = work / f"staging-{index}"
        prepare(dataset, DEVELOPMENT, stage, name)
        (source / name).parent.mkdir(parents=True, exist_ok=True)
        (stage / name).replace(source / name)
    duplicate = "case_01/doc_91.pdf"
    shutil.copyfile(source / PAYMENT, source / duplicate)
    selected[duplicate] = "przelew"

    expected_paths = {Path(name).with_suffix(".json").as_posix(): kind for name, kind in selected.items()}
    diagnostics = run_cli(run)
    assert {name: item["class"] for name, item in diagnostics.items()} == expected_paths

    def outputs():
        return {path.relative_to(run / "output").as_posix(): path.read_bytes()
                for path in (run / "output").rglob("*.json")}

    before = outputs()
    assert set(before) == set(expected_paths)
    assert before["case_66/doc_01.json"] == b""
    assert before["case_01/doc_02.json"] == before["case_01/doc_91.json"]
    multiple = json.loads(before["case_41/doc_03.json"])
    assert len(multiple["mocodawca"]) == 2
    assert [len(owner["podpisujacy"]) for owner in multiple["mocodawca"]] == [1, 2]
    assert all(person["pesel"] is None for person in multiple["pelnomocnicy"])
    assert run_cli(run) == diagnostics and outputs() == before

    (source / PAYMENT).unlink()
    moved = source / "inna" / "nowa_nazwa.pdf"
    moved.parent.mkdir()
    (source / duplicate).rename(moved)
    run_cli(run)
    expected_after = {name: contents for name, contents in before.items()
                      if name not in {"case_01/doc_02.json", "case_01/doc_91.json"}}
    expected_after["inna/nowa_nazwa.json"] = before["case_01/doc_02.json"]
    assert outputs() == expected_after
    blank = work / "blank"
    blank.mkdir()
    assert run_cli(blank) == {}
    assert not list((blank / "output").iterdir())
    print("Drzewo, trzy klasy, podobny dokument obcy, powtórzenie, przemianowanie i sprzątanie: zgodne.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("work", type=Path, help="nowy katalog wyników odbioru")
    args = parser.parse_args()
    project = str(Path(__file__).resolve().parents[1])
    os.environ["PYTHONPATH"] = project
    args.work.mkdir(parents=True)
    first_payment(args.dataset.resolve(), args.work.resolve())
    full_tree(args.dataset.resolve(), args.work.resolve())
