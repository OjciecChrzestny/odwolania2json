# Odwołania2JSON dla jurora UZP

## Ocena na VM

Wgraj PDF-y do `/opt/solution/input/` i wykonaj w `/opt/solution` polecenie `./run-jury.sh`. Wyniki będą w `output/`. Ten sam przebieg obsługuje dokumenty tekstowe i skany. Polski OCR ma do 6 różnych stron na każdy PDF, a automatyczny odczyt brakującej kwoty przez Scaleway współdzieli z panelem limit 1 EUR na VM. [Instrukcja uruchomienia](../../RUN.md)

## Czysta kopia i własny PDF

Pobierz kod i obraz z [wydania jurorskiego](https://github.com/OjciecChrzestny/odwolania2json/releases). Po wczytaniu obrazu utwórz `input/` i `output/`, umieść swój PDF w `input/` i wykonaj `./run-jury.sh`. Możesz użyć [syntetycznego skanu](../compose/skan-syntetyczny.pdf). Jego kwota wynosi 123,45 zł i ma dowód na stronie 1.

## Wynik i źródło pola

Dla `input/sprawa/pismo.pdf` otwórz `output/sprawa/pismo.json`. W `diagnostics/last-run.json` znajdziesz numer fizycznej strony i regułę pola. W panelu można wgrać PDF, obejrzeć stronę, sprawdzić czytelność i zapisać własną decyzję. [Instrukcja panelu](../../docs/operator.md)

## Skąd bierze się wynik

1. `extract.py` odczytuje przez pypdf warstwę tekstową ze wszystkich stron. Automatyczny OCR próbuje rozpoznać tekst na najwyżej sześciu różnych stronach każdego PDF-u. `ocr.py` renderuje wybrane strony przez PDFium i rozpoznaje polski tekst przez Tesseract.
2. `model.py` wczytuje definicje klas. `odwolanie.json` odpowiada odwołaniom KIO, `pelnomocnictwo.json` pełnomocnictwom, a `przelew.json` potwierdzeniom przelewu. Punktowane sygnały z treści i progi wyłaniają jedną klasę. Brak rozpoznania lub remis daje dokument obcy. Nazwy PDF-ów służą do wyznaczenia ścieżki wynikowej.
3. Reguły pól i operacje w `operations.py` normalizują wartości, a schemat określa klucze, typy i pola dopuszczające `null`. Logika dokumentów prawnych jest w `legal.py`. Dane przelewów korzystają też z `transfer.py` i reguł dla skanów i rachunków.
4. `python -m odwolania2json` zapisuje wyniki zgodnie z drzewem wejścia. Osobny plik diagnostyczny wskazuje status, klasę oraz podstawę wydobycia pola na poziomie strony i reguły.

Aby zmienić konfigurację ekstrakcji lub dodać klasę, skopiuj standardowe konfiguracje do osobnego katalogu wskazanego przez `--config KATALOG`. Każda definicja ma unikatową nazwę, sygnały, próg i schemat. Dla klasy `zawiadomienie` wystarcza jeden dodatkowy plik JSON z regułami pól `sygnatura` i `termin`. Próba podaje dokładne polecenia, dwa przykłady oraz podobne pismo obce. [Konfiguracja klas](../../README.md#reguły-i-rozszerzanie) · [Próba rozszerzenia](../../demo/rozszerzalnosc/README.md)

## Zgłoszenie, finał i przekazanie

| Etap | Materiały i warunki |
| --- | --- |
| Zgłoszenie w HackTribe | Tytuł „Odwołania2JSON” i link GitHub do działającego prototypu. Instrukcja HackTribe przewiduje prezentację w PDF do 10 MB przy końcowym zgłoszeniu. Dokumentacja techniczna i własne wyniki są materiałami dodatkowymi według README UZP. |
| Preselekcja UZP | F1 na nieujawnionym zbiorze co najmniej 10 spraw. |
| Finał UZP | Maksymalnie trzy zespoły. F1 stanowi 50%, elastyczność i łatwość dodawania klas stanowią 50%. Dowody to kod, opis architektury i prezentacja. W prezentacji wskaż komponenty zewnętrzne. |
| Przekazanie przez zwycięzcę | Kod źródłowy, instrukcja startu, konfiguracja Docker Compose i dokumentacja architektury, konfiguracji ekstrakcji danej klasy i dodawania klasy. § 3 i § 4 regulaminu określają też warunki umowy przeniesienia praw. |

Według instrukcji HackTribe projekt i wybór zadania należało zapisać do 20:00 w sobotę 21 listopada. Termin końcowy to 11:00 w niedzielę 22 listopada 2026 r., czasu warszawskiego. Szczegółowy opis PDF podaje podział finału 50/30/20. Do finału UZP stosujemy § 2 regulaminu zadania. [README UZP, rewizja z 21 listopada](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/0b360a9da4b482a6a280696df6714404e0953505/README.md#4-wymagania-formalne) · [Regulamin UZP, § 2–4](https://mudnibfuppwadjkynscc.supabase.co/storage/v1/object/public/task-files/057d36b5-cb92-4062-9393-983cb8a96088/files/aa36e74b-f96c-46cf-9970-5937ed203222.pdf#page=2) · [Szczegółowy opis UZP](https://mudnibfuppwadjkynscc.supabase.co/storage/v1/object/public/task-files/057d36b5-cb92-4062-9393-983cb8a96088/files/aeabc57d-7420-4069-946e-2c4de71d87ed.pdf#page=4) · [Przewodnik HackNation](https://hacknation.pl/przewodnik-uczestnika) · [Instrukcja HackTribe, s. 6–7](https://hacknation.pl/api/public/przewodnik/1f73a661-0852-4e9e-b3ed-58c93bce6456?asset=aa346c52-8bd9-44ac-9499-364e44c4b6b4#page=6)

Repozytorium jest publiczne. Materiały do zgłoszenia udostępnia strona wydań GitHub.

## Warunki użycia API

Automatyczny odczyt kwoty korzysta z europejskiej usługi Scaleway i wspólnego limitu wydatków. [Reguły użycia i budżet](../../RUN.md#automatyczny-ocr-i-budżet-api)

## Komponenty zewnętrzne

| Zakres | Komponent i źródło licencji |
| --- | --- |
| Uruchomienie | Python 3.13+, [PSF License](https://docs.python.org/3.13/license.html). |
| Odczyt PDF | pypdf 6.21.4, [BSD-3-Clause](https://pypi.org/project/pypdf/6.21.4/). |
| OCR | pypdfium2 5.15.2 i PDFium, [licencje pakietu i PDFium](https://github.com/pypdfium2-team/pypdfium2/blob/5.15.2/README.md#licensing). tesserocr 2.13.0, [MIT](https://github.com/sirfz/tesserocr/blob/master/LICENSE), Tesseract i polskie dane `tessdata_fast` 4.1.0, [Apache-2.0 dla silnika](https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE) i [danych](https://github.com/tesseract-ocr/tessdata_fast/blob/4.1.0/LICENSE). |
| Kontener | [Oficjalny obraz Python](https://hub.docker.com/_/python) przypięty przez digest w `Dockerfile`. [Licencja silnika Moby](https://github.com/moby/moby/blob/master/LICENSE) i [licencja Compose](https://github.com/docker/compose/blob/main/LICENSE). |
| Budowa pokazu | [ReportLab](https://pypi.org/project/reportlab/4.4.10/), [Pillow](https://pypi.org/project/pillow/13.0.0/), [charset-normalizer](https://pypi.org/project/charset-normalizer/3.5.2/), [Lato](https://github.com/latofonts/lato-source) i [DejaVu Sans Mono](https://dejavu-fonts.github.io/License.html). Wersje bibliotek w `requirements-pokaz.txt`. |
| Dane porównawcze | Publiczne przykłady i schematy organizatora w [przypiętej rewizji UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/de135d20811caf630f3e94dc655ba5eebd9a6710). Skan próbny w repozytorium jest syntetyczny. |

## Dowody do finału

- Czysty start na własnym wejściu, plik wynikowy i przejście do wskazanej strony źródłowej według instrukcji powyżej.
- Dodanie klasy z jednym plikiem JSON, dwa rozpoznane przykłady oraz pismo obce dające 0 B. [Próba rozszerzenia](../../demo/rozszerzalnosc/README.md)
- [Scenariusz i polecenia do wygenerowania aktualnej prezentacji oraz ekranów rezerwowych](SCENARIUSZ.md#uruchomienie-na-vps).

Metryki zgłoszenia wymagają potwierdzenia na jednym kandydacie wydania. Dotychczasowe raporty opisują własne próby na wskazanych w nich rewizjach i zbiorach. [Rozwój A3](../../docs/historia/RAPORT_A3.md) · [Historyczna próba A3 na skanach](../../docs/historia/RAPORT_KONCOWY_A3.md) · [Historyczna zgodność Compose](../compose/RAPORT.md)
