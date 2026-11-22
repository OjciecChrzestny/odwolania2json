# Pokaz dodania klasy zawiadomienie

Próba używa publicznego CLI i osobnego profilu. Do kopii trzech klas konkursowych juror dodaje jeden plik, [zawiadomienie.json](zawiadomienie.json). Plik opisuje sygnały rozpoznania, schemat JSON i reguły odczytu dwóch pól. Po usunięciu tego pliku kopia profilu znowu zawiera dokładnie trzy klasy konkursowe.

## Próba jurora

Uruchom z katalogu głównego czystej kopii projektu. Potrzebujesz Pythona 3.13+ i zależności z `requirements.txt`. Przed uruchomieniem zapisz stan kodu według sekcji „Kontrola kodu podczas próby”.

```sh
python -m pip install -r requirements.txt
DEMO=demo/rozszerzalnosc
WORK="$(mktemp -d)/pokaz"
python "$DEMO/pokaz.py" przygotuj "$WORK"
python "$DEMO/pokaz.py" nowy "$WORK/input/wejscie-04.pdf"
```

`przygotuj` tworzy dwa wcześniejsze fikcyjne zawiadomienia, podobne pismo obce i kopię profilu. `nowy` zapisuje osobny PDF w innym układzie. Strona 1 to karta obiegu. Nagłówek zawiadomienia i sygnatura są na stronie 2, a termin posiedzenia na stronie 3. Otwórz `$WORK/input/wejscie-04.pdf`, aby odczytać oba pola.

**Profil konkursowy.** Wszystkie cztery pliki wynikowe mają po 0 B.

```sh
python -m odwolania2json --input "$WORK/input" --output "$WORK/konkurs" \
  --diagnostics "$WORK/diagnostics/konkurs.json"
wc -c "$WORK/konkurs/"*.json
```

**Dodanie klasy.** `diff` wskazuje wyłącznie dodany plik. Po przetworzeniu wejścia pismo `doc_03` nadal ma 0 B.

```sh
cp "$DEMO/zawiadomienie.json" "$WORK/klasy/"
diff -ru odwolania2json/classes "$WORK/klasy" || test "$?" -eq 1
python -m odwolania2json --input "$WORK/input" --output "$WORK/demo" \
  --config "$WORK/klasy" --diagnostics "$WORK/diagnostics/demo.json"
cat "$WORK/demo/wejscie-04.json"
wc -c "$WORK/demo/doc_03.json"
python "$DEMO/pokaz.py" zrodlo "$WORK/input/wejscie-04.pdf" "$WORK/diagnostics/demo.json"
```

```json
{
  "sygnatura": "KIO-DEMO/806/27",
  "termin": "2027-02-09"
}
```

Pole `sygnatura` pochodzi z wiersza „Sygnatura akt: KIO-DEMO/806/27” na stronie 2 i reguły `wiersz_sygnatury`. Pole `termin` pochodzi z wiersza „Termin posiedzenia: 9 lutego 2027 r.” na stronie 3 i reguły `wiersz_terminu`. Kontrprzykład `doc_03.pdf` ma obie etykiety i zawiera słowo „Zawiadomienie” w zdaniu. Nagłówek „KOMUNIKAT ORGANIZACYJNY” pozostawia tylko 2 z wymaganych 6 punktów.

**Powrót do konkursu.** Usuń dodany plik z kopii i porównaj oba profile oraz wyniki.

```sh
rm "$WORK/klasy/zawiadomienie.json"
diff -r odwolania2json/classes "$WORK/klasy"
python -m odwolania2json --input "$WORK/input" --output "$WORK/przywrocony" \
  --config "$WORK/klasy" --diagnostics "$WORK/diagnostics/przywrocony.json"
diff -r "$WORK/konkurs" "$WORK/przywrocony"
wc -c "$WORK/przywrocony/wejscie-04.json"
```

Możesz użyć własnego pliku PDF z warstwą tekstową. Umieść nagłówek „ZAWIADOMIENIE” w osobnym wierszu i etykietę „Sygnatura:” lub „Sygnatura akt:” na jednej z dwóch pierwszych stron. Użyj etykiety „Termin:” albo „Termin posiedzenia:”. Włóż PDF do osobnego katalogu wejściowego i powtórz kroki przed dodaniem pliku, po dodaniu i po usunięciu. Jeżeli nazwy pól lub rozkład tekstu są inne, dostosuj wzorce w kopii `zawiadomienie.json`.

## Od klasy do źródła pola

1. `--config` wskazuje katalog profilu. `model.load_classes` wczytuje wszystkie jego pliki JSON i sprawdza unikatowość nazw klas.
2. Klasyfikator dobiera klasę po najwyższym wyniku. Dla zawiadomienia liczy nagłówek (4 pkt) i etykietę sygnatury (2 pkt) na pierwszych dwóch stronach. Próg klasy wynosi 6. Remis kończy się dokumentem obcym.
3. Reguły odczytu biorą pierwszą grupę przechwytującą. `text` porządkuje odstępy sygnatury, a `date` zamienia datę na ISO. Schemat zachowuje oba klucze i dopuszcza `null`.
4. Diagnostyka zapisuje `fields.<pole>.page` i `fields.<pole>.rule`. Strony są liczone od 1. Komenda `zrodlo` wypisuje tekst z tych stron wejściowego PDF-u.

Czytnik odczytuje warstwę tekstową na wszystkich stronach. Domyślny budżet OCR wynosi sześć różnych stron na PDF. Szczegóły pokazu opierają się na warstwie tekstowej. Obsługę skanów opisuje [README projektu](../../README.md).

## Odbiór z czystej kopii

Wykonaj z katalogu repozytorium na wybranej rewizji. W istniejącym środowisku VPS pomiń ponowną instalację zależności.

```sh
CHECK="$(mktemp -d)"
REV="$(git rev-parse HEAD)"
git clone --no-local . "$CHECK/czysta"
git -C "$CHECK/czysta" checkout --detach "$REV"
cd "$CHECK/czysta"
python -m unittest discover -s evaluation -p 'test_*.py'
time python demo/rozszerzalnosc/accept.py --work "$CHECK/syntetyki"
```

Pełny odbiór na VPS używa przypiętych danych UZP `de135d20811caf630f3e94dc655ba5eebd9a6710` i opcjonalnego OCR. Ustaw `UZP_DATA` na katalog kopii organizatora i `OCR_DATA` na katalog z `pol.traineddata`. Polecenie poniżej używa współdzielonej blokady OCR i izolatora Landlock, który blokuje ekstraktorowi połączenia TCP oraz dostęp do etykiet. Dla każdego przebiegu użyj nowego katalogu `--work`.

```sh
cc -std=c11 -O2 -Wall -Wextra -Werror evaluation/restrict_linux.c -o "$CHECK/restrict-linux"
OCR_LOCK=/home/dev-viralpay/uzp-parallel/koordynacja/runda-ae0bae4/blokady/ocr-1.lock
OMP_THREAD_LIMIT=1 flock "$OCR_LOCK" /usr/bin/time -f 'real=%e s maxrss=%M KiB' \
  python demo/rozszerzalnosc/accept.py --work "$CHECK/odbior" \
  --dataset "$UZP_DATA" --ocr-data "$OCR_DATA" --restrict-linux "$CHECK/restrict-linux"
```

Test używa tej samej kopii kodu we wszystkich trzech przebiegach. Sprawdza dokładne wyniki, sygnały, strony i wiersze źródłowe trzech zawiadomień oraz negatyw. Na podzbiorze DEV sprawdza odwołanie, pełnomocnictwo, przelew i osiem negatywów po 0 B. Porównuje ścieżki i SHA-256 11 wyników w trzech przebiegach. Miernik korzysta z etykiet DEV po zakończeniu ekstrakcji. Oczekuje 35 trafionych pól, 0 FP i 0 FN.

Katalog `--work` zawiera wejściowe PDF-y, wszystkie wyniki i diagnostykę, `roznica-konfiguracji.diff`, `development-sha256.json` i `development-score.json`.

## Kontrola kodu podczas próby

**Kopia Git.** W katalogu głównym projektu zapisz pełny SHA aktualnie wybranej rewizji i sprawdź stan katalogu produktu przed uruchomieniem pokazu.

```sh
REV="$(git rev-parse --verify HEAD)"
printf 'Rewizja próby: %s\n' "$REV"
sprawdz_kod() {
  test "$(git rev-parse --verify HEAD)" = "$REV" &&
    stan="$(git status --porcelain=v1 --untracked-files=all -- odwolania2json)" &&
    test -z "$stan"
}
sprawdz_kod
```

Po pokazie uruchom ponownie `sprawdz_kod` w tej samej sesji. Kod 0 oznacza, że nadal pracujesz na zapisanym SHA i Git nie wykrywa zmian ani nowych plików w katalogu produktu. W razie błędu porównaj `git rev-parse --verify HEAD` z `$REV` i sprawdź pliki przez `git status --short --untracked-files=all -- odwolania2json`.

**Rozpakowane archiwum.** Jeżeli wydanie podaje sumę SHA-256 archiwum dla wybranej rewizji, sprawdź ją przed rozpakowaniem. Następnie w katalogu głównym rozpakowanego projektu zapisz listę plików produktu wraz z ich sumami SHA-256. Uruchom w Bashu z narzędziami GNU.

```bash
export PYTHONDONTWRITEBYTECODE=1
STAN_KODU="$(mktemp -d)"
sumy_kodu() (
  set -o pipefail
  find odwolania2json \( -type f -o -type l \) -print0 |
    LC_ALL=C sort -z | xargs -0 -r sha256sum
)
sumy_kodu > "$STAN_KODU/przed.sha256"
```

Po pokazie, w tej samej sesji, porównaj listę i sumy. Kod 0 potwierdza zgodność rozpakowanego katalogu produktu ze stanem zapisanym przed próbą.

```bash
sumy_kodu > "$STAN_KODU/po.sha256" &&
  diff -u "$STAN_KODU/przed.sha256" "$STAN_KODU/po.sha256"
```

## Ostatnie 50 sekund prezentacji

- **1:10–1:20** Dodaj jeden plik konfiguracji, pokaż `diff` i uruchom CLI.
- **1:20–1:40** Pokaż JSON nowego PDF-u, stronę 3 z terminem i kontrprzykład o długości 0 B.
- **1:40–2:00** Usuń plik konfiguracji i pokaż powrót do 0 B dla nowej klasy. Otwórz zapisany odbiór DEV z 11/11 zgodnych plików, 8/8 pustych negatywów i porównaniem 35 pól.
