# Odwołania2JSON dla jurora UZP

## Własny PDF, wynik i źródło pola

Z katalogu głównego wydania, w Pythonie 3.13+:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
WORK="$(mktemp -d)"
mkdir "$WORK/input"
cp "/ścieżka/do/pisma.pdf" "$WORK/input/doc_01.pdf"
python -m odwolania2json --input "$WORK/input" --output "$WORK/output" \
  --diagnostics "$WORK/diagnostics/last-run.json"
wc -c "$WORK/output/doc_01.json"
cat "$WORK/output/doc_01.json"
python demo/rozszerzalnosc/pokaz.py zrodlo "$WORK/input/doc_01.pdf" \
  "$WORK/diagnostics/last-run.json"
```

W JSON-ie odszukaj pole, np. `przelew_bankowy.kwota`. W diagnostyce ten sam klucz zawiera `page` i `rule`. Polecenie `zrodlo` odczytuje tekst wskazanej strony z wejściowego PDF-u. Możesz otworzyć tę samą stronę w przeglądarce PDF. Plik o rozmiarze 0 B oznacza dokument sklasyfikowany jako obcy. Błąd odczytu ma osobny status `read_error`, kod wyjścia 1 i brak odpowiadającego pliku wynikowego.

A2 działa lokalnie na CPU i bez API. Czytnik analizuje do sześciu pierwszych stron. Przy braku czytelnej warstwy tekstowej na początku dokumentu można użyć opcjonalnego polskiego OCR przez `--ocr-data KATALOG` po instalacji [zależności OCR](../../README.md#opcjonalny-ocr) lub przez gotowy [profil Compose](../compose/README.md). Dla zeskanowanej strony źródłowej otwórz obraz w czytniku PDF. `zrodlo` wypisuje tekst dostępny w samym dokumencie.

## Skąd bierze się wynik

`PDF → odczyt/OCR → klasyfikacja → reguły i schemat → JSON/diagnostyka`

1. `extract.py` odczytuje tekst przez pypdf. Jeśli włączono OCR, `ocr.py` renderuje wybrane strony przez PDFium i rozpoznaje polski tekst przez Tesseract.
2. `model.py` wczytuje definicje klas. Sygnały z treści i progi wyłaniają jedną klasę. Brak kandydata lub remis daje dokument obcy.
3. `operations.py` stosuje reguły pól i normalizuje wartości. Schemat sprawdza typy i klucze, a `legal.py` obsługuje złożoną strukturę odwołań i pełnomocnictw.
4. `python -m odwolania2json` zapisuje JSON-y z zachowaniem drzewa wejścia. Osobny plik diagnostyczny wskazuje regułę i numer strony liczony od 1. Dla brakującego pola schemat może dopuszczać `null`.

Przykładowa klasa `zawiadomienie` używa jednego pliku z sygnałami, progiem, schematem i regułami pól. Do jej włączenia skopiuj standardowe konfiguracje do osobnego katalogu, dodaj do niego `demo/rozszerzalnosc/zawiadomienie.json` i podaj `--config KATALOG`. Nagłówek „ZAWIADOMIENIE” i etykieta „Sygnatura” lub „Sygnatura akt” powinny pojawić się na jednej z dwóch pierwszych stron rozpatrywanych przez klasyfikator. [Próba i konfiguracja nowej klasy](../../demo/rozszerzalnosc/README.md)

## Co przekazać na poszczególnych etapach

| Etap | Materiały |
| --- | --- |
| Zgłoszenie | Tytuł „Odwołania2JSON” i link GitHub do działającego prototypu. |
| Finał | Kod i opis architektury oraz prezentacja z dowodami działania. Regulamin liczy jakość ekstrakcji i łatwość rozbudowy po 50%. |
| Przekazanie przez zwycięzcę | Kod, instrukcja uruchomienia, konfiguracja Docker Compose oraz dokumentacja architektury, konfiguracji ekstrakcji klasy i dodawania klasy. Regulamin przewiduje umowę przeniesienia praw. |

[Wymagania UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/de135d20811caf630f3e94dc655ba5eebd9a6710/README.md) · [Regulamin, § 2–4](https://mudnibfuppwadjkynscc.supabase.co/storage/v1/object/public/task-files/057d36b5-cb92-4062-9393-983cb8a96088/files/aa36e74b-f96c-46cf-9970-5937ed203222.pdf#page=2)

Właściciel potwierdza adres i SHA zgłoszenia, dostęp do prywatnego repozytorium z konta jurora oraz możliwość pobrania PDF-u po przesłaniu w formularzu. Ustala też, kto przedstawia demo i czy sala pozwala przełączyć okno PDF na terminal. Publikację i wysyłkę wykonuje właściciel.

## Pomiary i komponenty zewnętrzne

| Zakres | Komponent i źródło licencji |
| --- | --- |
| Uruchomienie | Python 3.13.18, [PSF License](https://docs.python.org/3.13/license.html). |
| Odczyt PDF | pypdf 6.21.4, [BSD-3-Clause](https://pypi.org/project/pypdf/6.21.4/). |
| Opcjonalny OCR | pypdfium2 5.15.2 i PDFium, [licencje pakietu i PDFium](https://github.com/pypdfium2-team/pypdfium2#license). tesserocr 2.13.0, [MIT](https://github.com/sirfz/tesserocr/blob/master/LICENSE), Tesseract i polskie dane `tessdata_fast` 4.1.0, [Apache-2.0 dla silnika](https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE) i [danych](https://github.com/tesseract-ocr/tessdata_fast/blob/4.1.0/LICENSE). |
| Kontener | [Oficjalny obraz Python](https://hub.docker.com/_/python), [licencja silnika Moby](https://github.com/moby/moby/blob/master/LICENSE) i [licencja Compose](https://github.com/docker/compose/blob/main/LICENSE). Szczegóły obrazu w raporcie Compose. |
| Tylko budowa pokazu | [ReportLab](https://pypi.org/project/reportlab/4.4.10/), [Pillow](https://pypi.org/project/pillow/13.0.0/), [charset-normalizer](https://pypi.org/project/charset-normalizer/3.5.2/), [Lato](https://github.com/latofonts/lato-source) i [DejaVu Sans Mono](https://dejavu-fonts.github.io/License.html). Konkretne wersje bibliotek w `requirements-pokaz.txt`. |

- **A** ma ścisłe mikro-F1 **0,9878 na 32 walidacyjnych PDF-ach**. Zwrócił `valid_run=false`, bo potraktował jeden przelew jako dokument obcy. Kod pomiaru `19f702fc58e685f85f2fae14557d14f2c5453cfd`. Raport `0dd1ed2f37f109dc7750c1309402bfb3a2b557e9:RAPORT_A.md`.
- **A2** ma ścisłe mikro-F1 **0,9963 na 128 rozwojowych PDF-ach**, z identycznymi wyjściami jak A na tym zbiorze. Odzyskał dwa przelewy w teście syntetycznym ze złamanymi nagłówkami. Kod pomiaru `d04fe1b816df09782d9c893541fe7cd29b461068`. Raport `39805dd26c0443f5dcdcef837734897f843f4395:RAPORT_A2.md`.
- **Compose** uzyskał zgodne ścieżki, bajty i diagnostykę na sześciu wejściach ze sprawdzonej gałęzi Compose. Raport `a2f5412a89a2ccfbfd9d91f19641df88a50f05a4:delivery/compose/RAPORT.md`.
- Wynik na zbiorze jury jest nieznany. Eksperyment B/C używał atrap. Wyników atrap nie używamy do oceny wydania.
