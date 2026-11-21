# Dwuminutowa próba finałowa Odwołania2JSON

Dwie minuty to cel próby. Przewodnik HackNation zaleca demo do dwóch minut w zgłoszeniu. W publicznym przewodniku i regulaminie UZP nie znaleziono limitu wystąpienia przed jury. Osoba prowadząca potwierdza aktualny czas ze swoim koordynatorem przed finałem. [Przewodnik HackNation](https://hacknation.pl/przewodnik-uczestnika) · [Regulamin UZP](https://mudnibfuppwadjkynscc.supabase.co/storage/v1/object/public/task-files/057d36b5-cb92-4062-9393-983cb8a96088/files/aa36e74b-f96c-46cf-9970-5937ed203222.pdf#page=2)

## 0:00–0:35 · PDF, CLI i wynik

Otwórz slajd 1 i syntetyczny plik `input/doc_01.pdf`. Uruchom etap `przelew`. Pokaż kwotę i dwa rachunki w `domyslne/output/doc_01.json`, a potem rozmiar wyniku dla `doc_02.pdf`.

> Wkładam fikcyjne potwierdzenie do katalogu wejściowego. Program zwraca sześć pól, w tym kwotę i rachunki z przypisanymi rolami. Wezwanie do zapłaty ma tę samą kwotę. Program zwraca dla niego pusty plik.

## 0:35–1:20 · Źródło, ręczna kontrola i jakość

Na slajdzie 2 lub w terminalu wskaż wiersz „Kwota: 123,45 PLN”, stronę 1 i regułę `kwota_operacji`. Na slajdzie 3 pokaż `doc_05.pdf` i `numer_transakcji: null`. Otwórz pełną stronę PDF-u i potwierdź, że numeru brakuje. W próbie kontrolę inicjuje prezenter i pozostawia pole puste. Kolejka, akceptacja i zapis decyzji operatora czekają na wspólny odbiór z modułami 02–05.

> Diagnostyka wskazuje stronę i regułę kwoty. W drugim przelewie brakuje numeru. Sprawdzam PDF i zostawiam puste pole. Slajd jakości podaje wynik wyłącznie dla rewizji pokazanej w stopce. [Odczytaj wynik, liczebność zbioru i status pomiaru ze slajdu 4. Przy braku wyniku powiedz, że ta rewizja czeka na pomiar.]

## 1:20–2:00 · Dodanie klasy

Uruchom etap `klasa`. Na slajdzie 5 pokaż dopisany plik `zawiadomienie.json`, termin na stronie 2, zapis ISO i pusty wynik pisma obcego. Zakończ wynikiem regresji z terminala.

> Na tych samych trzech dokumentach włączam jeden nowy plik konfiguracji. Dwa zawiadomienia zwracają sygnaturę i termin, a komunikat organizacyjny pozostaje pusty. Ten termin pochodzi ze strony drugiej. Wszystkie pięć wyników z pierwszego przebiegu zachowało identyczne sumy po dodaniu klasy.

## Uruchomienie na VPS

Ustaw `KOD` na czysty checkout sprawdzanej rewizji, `PY` na absolutną ścieżkę do interpretera z zależnościami z `delivery/final/requirements-pokaz.txt` i `RUN` na własny, istniejący katalog odbioru. Skrypty i repozytorium pochodzą z tego samego checkoutu. Przed próbą zainstaluj zależności, przygotuj Docker rootless oraz fonty Lato i DejaVu Sans Mono. Przebieg korzysta wyłącznie z wygenerowanych PDF-ów z warstwą tekstową.

```sh
export PATH="$HOME/.local/bin:$PATH" DOCKER_CONTEXT=rootless
ROUND=/home/dev-viralpay/uzp-parallel/koordynacja/runda-ae0bae4
RC_SHA=$(git -C "$KOD" rev-parse HEAD)
IMAGE="uzp-17-pokaz:$RC_SHA"
LOCK="$ROUND/blokady/ocr-1.lock"
WORK="$RUN/proba"
MATERIALY="$RUN/materialy"

# Tylko przed próbą, jeśli brakuje obrazu tej rewizji.
OMP_THREAD_LIMIT=1 flock "$LOCK" docker build \
  --label "org.opencontainers.image.revision=$RC_SHA" --tag "$IMAGE" "$KOD"

# Pełna próba techniczna na gotowym obrazie, bez sieci w kontenerach.
time "$PY" -B "$KOD/delivery/final/proba.py" "$KOD" "$WORK" calosc \
  --sha "$RC_SHA" --image "$IMAGE"
"$PY" -B "$KOD/delivery/final/buduj.py" "$WORK" "$MATERIALY"
cat "$WORK/potwierdzenie.json" "$MATERIALY/materialy.json"
```

W pokazie na żywo wybierz nowy katalog i wywołaj kolejno te same polecenia z etapami `przygotuj`, `przelew` i `klasa` zamiast `calosc`. Pierwszy etap wykonaj przed wejściem na scenę. Przy lokalnym Pythonie uruchom wszystkie etapy bez `--image`. Każdy etap sprawdza SHA kodu oraz zapis i pliki etapów, z których korzysta. W Dockerze identyfikator obrazu jest sprawdzany między etapami. `potwierdzenie.json` zapisuje tryb, czasy oraz sumy wejść, wyjść, diagnostyki i konfiguracji, a `materialy.json` łączy z tym zapisem oba PDF-y.

### Wynik jakości jednego kandydata

Koordynator może przekazać za pomocą `--jakosc PLIK` w etapie `calosc` albo `klasa` podsumowanie własnego pomiaru dla dokładnie tego SHA. Plik JSON zawiera `sha`, `zbior` (`rozwojowy` lub `niezalezny`), `sha256_manifestu`, `liczba_pdf`, `tp`, `fp`, `fn`, `valid_run` i `valid_contract`. Koordynator weryfikuje pochodzenie liczników i manifestu w oryginalnym raporcie przed przekazaniem podsumowania. Skrypt sprawdza SHA i format, oblicza F1 z liczników i oznacza nieważny pomiar jako diagnostyczny. Bez pliku slajd pokazuje brak pomiaru tej rewizji. [Historyczne wyniki A3 wraz z ograniczeniami](../../RAPORT_KONCOWY_A3.md)

### Plan na brak sieci albo awarię

Produkt działa lokalnie. Pokaz korzysta z wcześniej zbudowanego obrazu i uruchamia go z `--network none --pull never`. Usługa API jest poza pokazem. Przy awarii Docker lub SSH otwórz przygotowane wcześniej PDF-y z katalogu `materialy` oraz syntetyczne PDF-y z `proba/input` i `proba/rozszerzenie/input`. Na ekranie rezerwowym powiedz „To zapis próby na syntetycznych dokumentach”. Ekrany 1–4 pokazują wynik CLI, źródło kwoty, ręczną kontrolę i dodanie klasy. Przed finałem skopiuj gotowe materiały tej samej rewizji na sprzęt do prezentacji i sprawdź otwarcie bez sieci.

PDF-y śledzone w repozytorium to wcześniejszy zapis udokumentowany w [archiwalnym raporcie próby](RAPORT-PROBY.md). Do tej próby używaj PDF-ów wygenerowanych przez `buduj.py` z bieżącego `potwierdzenie.json`.
