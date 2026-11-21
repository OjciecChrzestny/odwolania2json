"""Ręcznie policzone kontrole trzech mierników i PDF-y do próby porównawczej."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


CASES = {
    # TP, FP, FN, poprawność przebiegu, kontraktu i diagnostyki, błędne auto, wykryte strony.
    "canonical": (8, 0, 0, True, True, True, 0, 1),
    "swapped_accounts": (6, 2, 2, True, True, True, 1, 1),
    "opposite_account": (7, 1, 1, True, True, True, 1, 1),
    "reordered_list": (6, 2, 2, True, True, True, 1, 1),
    "null_value": (7, 0, 1, True, True, True, 1, 1),
    "missing_null_key": (8, 0, 0, True, False, False, 1, 1),
    "missing_positive": (2, 0, 6, False, False, False, 1, 1),
    "empty_positive": (2, 0, 6, False, True, False, 1, 1),
    "missing_empty_negative": (8, 0, 0, False, False, False, 1, 1),
    "nonempty_negative": (8, 0, 0, True, False, False, 1, 1),
    "zero_auto": (8, 0, 0, True, True, True, 0, 1),
    "swapped_pages": (8, 0, 0, True, True, True, 0, 0),
}
ACCOUNTS = ("00123456789012345678901234", "00987654321098765432109876")
TRANSFER = {"przelew_bankowy": {"data_operacji": "2026-01-02", "kwota": 12.5,
                                "tytul": "Wpis za odwolanie", "numer_transakcji": "0000123",
                                "z_rachunku": ACCOUNTS[0], "na_rachunek": ACCOUNTS[1]}}
POWER = {"mocodawca": [], "pelnomocnicy": [{"imie_nazwisko": "Anna Nowak", "pesel": None},
                                          {"imie_nazwisko": "Jan Testowy", "pesel": None}]}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    path.write_bytes(data)
    return digest(data)


def pages(*states):
    return [{"page": number, "status": state, "reason": "synthetic"}
            for number, state in enumerate(states, 1)]


def fixture(folder, case):
    folder.mkdir()
    output = folder / "output"
    dataset = folder / "dataset"
    output.mkdir()
    dataset.mkdir()
    cases = [("transfer", "przelew", TRANSFER, pages("readable", "unreadable")),
             ("power", "pelnomocnictwo", POWER, pages("readable")),
             ("other", "negative", None, pages("readable"))]
    manifest, report = [], []
    for name, klass, value, truth in cases:
        predicted = json.loads(json.dumps(value))
        source = f"{name}.pdf"
        target = f"{name}.json"
        src = f"%PDF synthetic for {name}\n".encode()
        (dataset / source).write_bytes(src)
        row = {"input": source, "pdf": source, "sha256": digest(src),
               "reference": None, "class": klass, "pages": truth}
        if value is not None:
            row["reference"] = f"gold-{name}.json"
            row["reference_sha256"] = write_json(dataset / row["reference"], value)
        observed = json.loads(json.dumps(truth))
        decision = "review_required" if case == "zero_auto" else "auto_accepted"
        predicted_class = klass
        omit = (name, case) in {("transfer", "missing_positive"), ("other", "missing_empty_negative")}
        if name == "transfer":
            transfer = predicted["przelew_bankowy"]
            if case in {"swapped_accounts", "opposite_account"}:
                transfer["z_rachunku"] = ACCOUNTS[1]
            if case == "swapped_accounts":
                transfer["na_rachunek"] = ACCOUNTS[0]
            if case == "null_value":
                transfer["numer_transakcji"] = None
            if case == "empty_positive":
                predicted, predicted_class = None, "negative"
            if case == "swapped_pages":
                observed[0]["status"], observed[1]["status"] = "unreadable", "readable"
        if name == "power" and case == "reordered_list":
            predicted["pelnomocnicy"].reverse()
        if name == "power" and case == "missing_null_key":
            del predicted["pelnomocnicy"][0]["pesel"]
        if name == "other" and case == "nonempty_negative":
            predicted = {}
        digest_out = None
        if not omit:
            if predicted is None:
                (output / target).touch()
                digest_out = digest(b"")
            else:
                digest_out = write_json(output / target, predicted)
        manifest.append(row)
        report.append({"input": source, "output": target, "report_version": 1,
                       "pdf_sha256": row["sha256"], "output_sha256": digest_out,
                       "extractor_revision": "synthetic", "class": predicted_class,
                       "status": "negative" if predicted_class == "negative" else "ok",
                       "pages": observed, "review": {"status": decision}})
    write_json(folder / "manifest.json", {"documents": manifest})
    write_json(folder / "diagnostics.json", {"documents": report})


def run_controls(root):
    root.mkdir(parents=True, exist_ok=False)
    summary = {}
    for case, expected in CASES.items():
        folder = root / case
        fixture(folder, case)
        output = str(folder / "output")
        args = ["--manifest", str(folder / "manifest.json")]
        diag = ["--diagnostics", str(folder / "diagnostics.json")]
        commands = {
            "fields": ["evaluation/score.py", str(folder / "dataset"), output, *args],
            "contract": ["-m", "evaluation.check_outputs", output, *args, *diag],
            "review": ["-m", "evaluation.score_review", str(folder / "dataset"), output, *args, *diag],
        }
        summaries, returncodes = {}, {}
        for name, command in commands.items():
            proc = subprocess.run([sys.executable, "-B", *command], capture_output=True, check=False)
            (folder / f"{name}.stderr").write_bytes(proc.stderr)
            (folder / f"{name}.json").write_bytes(proc.stdout)
            summaries[name] = json.loads(proc.stdout)
            returncodes[name] = proc.returncode
        field, contract, review = (summaries[name] for name in commands)
        actual = (field["tp"], field["fp"], field["fn"], field["valid_run"], contract["valid_contract"],
                  review["valid_run"], review["overall"]["decision_matrix"]["incorrect"]["auto_accepted"],
                  review["overall"]["pages"]["detected"])
        if actual != expected or tuple(returncodes.values()) != tuple(int(not ok) for ok in expected[3:6]):
            raise AssertionError(f"{case}: {actual=} {returncodes=} {expected=}")
        if case == "empty_positive" and contract["confusion_matrix"]["przelew"]["negative"] != 1:
            raise AssertionError("Brakuje FN klasy przelewu.")
        if case == "zero_auto" and review["overall"]["acceptance_accuracy"] != {
            "numerator": 0, "denominator": 0, "rate": None
        }:
            raise AssertionError("Przy zerze akceptacji mianownik powinien wynosić 0.")
        summary[case] = dict(zip(("tp", "fp", "fn", "valid_run", "valid_contract", "valid_review",
                                  "incorrect_auto", "unreadable_detected"), actual))
        summary[case].update(returncodes=returncodes, commands=commands)
    write_json(root / "summary.json", summary)
    print(f"{len(summary)}/{len(CASES)} ręcznych kontroli przeszło.")


def synthetic_spec(root):
    # Helper used by the existing CLI regression suite. Keep it scoped to fixture generation.
    sys.path.insert(0, str(Path(__file__).parent))
    from test_baseline_a import write_pdf

    root.mkdir(parents=True, exist_ok=False)
    dataset = root / "dataset"
    names = {
        "a.pdf": ("przelew", "\n".join([
            "POTWIERDZENIE PRZELEWU", "Data operacji: 2026-01-02", "Kwota: 12,50 PLN",
            "Na rachunek: " + ACCOUNTS[1], "Z rachunku: " + ACCOUNTS[0],
            "Opis: Wpis za odwolanie", "Numer transakcji: 0000123",
        ])),
        "b.pdf": ("negative", "Protokol omawia odwolanie oraz przelew i pelnomocnictwo."),
    }
    rows = []
    for name, (kind, text) in names.items():
        write_pdf(dataset / name, text)
        row = {"pdf": name, "input": name, "sha256": digest((dataset / name).read_bytes()),
               "class": kind, "reference": None, "pages": pages("readable")}
        if kind == "przelew":
            row["reference"] = "labels-a.json"
            row["reference_sha256"] = write_json(dataset / row["reference"], TRANSFER)
        rows.append(row)
    manifest = root / "manifest.json"
    manifest_hash = write_json(manifest, {"documents": rows})
    write_json(root / "spec.json", {"mode": "synthetic", "cohorts": {
        "page_review": {"dataset": str(dataset), "manifest": str(manifest),
                        "manifest_sha256": manifest_hash, "labels": "synthetic"}
    }})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("controls", "synthetic-spec"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    if args.action == "controls":
        run_controls(args.root.resolve())
    else:
        synthetic_spec(args.root.resolve())
