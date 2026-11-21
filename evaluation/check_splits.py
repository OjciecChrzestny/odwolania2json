"""Verify the frozen UZP 40/10/10 split without parsing reference values."""
import argparse
import hashlib
import re
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path, PurePosixPath

from score import checked_file, load_object


REVISION = "de135d20811caf630f3e94dc655ba5eebd9a6710"
FINAL_MANIFEST_SHA256 = "f36fffc9127520e0caad2df4413a2e6769b2b4d9e2dc1de5de9c668e9efa0a8b"
SPLITS = {"development": 40, "validation": 10, "final": 10}
CLASSES = {"odwolanie.pdf": "odwolanie", "pelnomocnictwo.pdf": "pelnomocnictwo",
           "potwierdzenie_przelewu.pdf": "przelew"}


def lf_hash(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def check_splits(dataset, manifests):
    data = dataset / "dane"
    pdfs = {p.relative_to(dataset).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in data.rglob("*.pdf")}
    source_paths, references, inputs = set(), set(), set()
    pdf_sets, ref_sets, case_sets, documents = {}, {}, {}, {}
    for split, count in SPLITS.items():
        path = manifests / f"{split}-{count}.json"
        manifest = load_object(path)
        if manifest["revision"] != REVISION:
            raise ValueError(f"{path.name}: unexpected UZP revision")
        if split == "final" and lf_hash(path) != FINAL_MANIFEST_SHA256:
            raise ValueError(f"{path.name}: frozen manifest changed")
        rows = manifest["documents"]
        documents[split] = rows
        cases, hashes, ref_hashes = set(), set(), set()
        for row in rows:
            source = row["pdf"]
            pdf = PurePosixPath(source)
            neutral = row["input"]
            case = pdf.parent.name
            if not re.fullmatch(r"case_[0-9]{2}/doc_[0-9]{2}\.pdf", neutral) or neutral in inputs:
                raise ValueError(f"Invalid or repeated input: {neutral}")
            inputs.add(neutral)
            if source not in pdfs or pdfs[source] != row["sha256"]:
                raise ValueError(f"Missing PDF or hash mismatch: {source}")
            if source in source_paths or row["sha256"] in hashes:
                raise ValueError(f"Repeated PDF in {split}: {source}")
            source_paths.add(source)
            hashes.add(row["sha256"])
            if case == "negatywne":
                if split != "development" or int(neutral[5:7]) <= 60:
                    raise ValueError(f"Standalone negative outside development supplement: {source}")
            else:
                if not re.fullmatch(r"przyklad_[0-9]{2}", case) or neutral[5:7] != case[-2:]:
                    raise ValueError(f"Broken case mapping: {source} -> {neutral}")
                cases.add(case)
            kind = CLASSES.get(pdf.name, "negative")
            label = pdf.with_name(kind + ".json").as_posix() if kind != "negative" else None
            if row["class"] != kind or row["reference"] != label:
                raise ValueError(f"Incorrect class or reference mapping: {source}")
            if label is not None:
                path_to_label = checked_file(dataset, label, row["reference_sha256"], reference=True)
                references.add(label)
                ref_hashes.add(lf_hash(path_to_label))
            elif row["reference_sha256"] is not None:
                raise ValueError(f"Negative has a reference hash: {source}")
        if len(cases) != count:
            raise ValueError(f"{split}: expected {count} complete cases, got {len(cases)}")
        pdf_sets[split], ref_sets[split], case_sets[split] = hashes, ref_hashes, cases
        print(f"{split}: cases={len(cases)}, PDFs={len(rows)}, classes={dict(Counter(r['class'] for r in rows))}")

    for a, b in combinations(SPLITS, 2):
        for what, groups in (("cases", case_sets), ("PDF SHA-256", pdf_sets), ("reference SHA-256 (LF)", ref_sets)):
            overlap = groups[a] & groups[b]
            if overlap:
                raise ValueError(f"{a}/{b}: shared {what}: {sorted(overlap)}")
        print(f"{a}/{b}: shared cases=0, PDF SHA-256=0, reference SHA-256 (LF)=0")

    expected_cases = {f"przyklad_{i:02d}" for i in range(1, 61)}
    if set.union(*case_sets.values()) != expected_cases:
        raise ValueError("The manifests do not cover the 60 UZP cases")
    for case in expected_cases:
        for name in CLASSES:
            if f"dane/{case}/{name}" not in source_paths:
                raise ValueError(f"Incomplete case: {case}/{name}")
    expected_labels = {p.relative_to(dataset).as_posix() for p in data.rglob("*.json")}
    if references != expected_labels:
        raise ValueError(f"Reference coverage mismatch: {sorted(references ^ expected_labels)}")
    assigned = set.union(*pdf_sets.values())
    aliases = sorted(set(pdfs) - source_paths)
    for name in aliases:
        if not name.startswith("dane/negatywne/") or pdfs[name] not in assigned:
            raise ValueError(f"Unassigned PDF: {name}")
    print(f"Coverage: {len(pdfs)} PDF paths, {len(assigned)} unique PDFs, {len(references)} references")
    for name in aliases:
        print(f"Excluded duplicate: {name}")
    print(f"final-10.json SHA-256 (LF): {FINAL_MANIFEST_SHA256}")
    return documents


# Generic printed headings only. Used for split auditing, independently of extraction.
HEADINGS = set("""odwołanie|odwołujący|zamawiający|zarzuty|żądania|uzasadnienie|dotyczy
pełnomocnictwo|pełnomocnictwo procesowe|mocodawca|pełnomocnictwo przyjmuję|zakres pełnomocnictwa
polecenie przelewu|potwierdzenie przelewu krajowego|potwierdzenie realizacji polecenia przelewu
potwierdzenie transakcji|potwierdzenie operacji bankowej|potwierdzenie wykonania przelewu
odbiorca|nadawca|zleceniodawca|płatnik|rachunek odbiorcy|rachunek zleceniodawcy|rachunek nadawcy
dane odbiorcy|dane nadawcy|data operacji|data transakcji|kwota operacji|szczegóły operacji
z rachunku|tytułem|tytuł|tytuł przelewu|identyfikator operacji
ogłoszenie o zamówieniu|ogłoszenie o wyniku postępowania|procedura|nabywca""".replace("\n", "|").split("|"))


def page_features(page):
    runs = []

    def visit(text, cm, tm, font, size):
        if text.strip() and len(runs) < 6:
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            name = str((font or {}).get("/BaseFont", "?")).split("+")[-1]
            runs.append((round(x), round(y), round(size, 1), name))

    first_page = page.extract_text(visitor_text=visit) or ""
    layout = (page.rotation, round(page.mediabox.width), round(page.mediabox.height), tuple(runs))
    lines = (" ".join(line.casefold().split()).rstrip(":").rstrip() for line in first_page.splitlines())
    headings = tuple(line for line in lines if line in HEADINGS)
    return layout if len(runs) == 6 else None, headings if len(set(headings)) >= 2 else None


def report_templates(dataset, documents):
    from pypdf import PdfReader, __version__

    print(f"First-page layout and heading signatures (pypdf {__version__})")
    layouts, patterns = defaultdict(dict), defaultdict(dict)
    coverage = defaultdict(Counter)
    for split, rows in documents.items():
        for row in rows:
            with (dataset / row["pdf"]).open("rb") as stream:
                layout, headings = page_features(PdfReader(stream).pages[0])
            case = row["input"][5:7]
            coverage[row["class"]].update(docs=1, layout=int(layout is not None), headings=int(headings is not None))
            for groups, signature in ((layouts, layout), (patterns, headings)):
                if signature:
                    groups[row["class"], signature].setdefault(split, []).append(case)
    for kind in sorted(coverage):
        print(f"{kind}: {dict(coverage[kind])}")
        for a, b in combinations(SPLITS, 2):
            counts = [sum(k == kind and a in members and b in members for (k, _), members in groups.items())
                      for groups in (layouts, patterns)]
            print(f"{kind} {a}/{b}: shared layout={counts[0]}, shared heading sequence={counts[1]}")
        examples = [(sum(map(len, members.values())), signature, members)
                    for (k, signature), members in patterns.items() if k == kind and len(members) == len(SPLITS)]
        if examples:
            _, signature, members = max(examples, key=lambda x: (x[0], x[1]))
            print(f"Shared heading sequence: {' > '.join(signature)} | {members}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="Root of the pinned UZP data")
    parser.add_argument("--templates", action="store_true", help="Compare layouts and headings (pypdf)")
    args = parser.parse_args()
    try:
        splits = check_splits(args.dataset, Path(__file__).resolve().parent)
        if args.templates:
            report_templates(args.dataset, splits)
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(1, f"{exc}\n")
