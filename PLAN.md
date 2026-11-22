# Odwołania2JSON — plan implementacji

## Plan do finału po publikacji A3

**Baza produktu** to `ec654135812a8579829d7258e78eda5ab8438108` na prywatnym GitHubie i naszym VPS. Obraz ekstraktora odpowiada `497818864c69b63f3687ff75499c5ea908255f93`. Różnica między tymi rewizjami to instrukcja `RUN.md`. Czaty 01, 05, 06, 07, 15 i 17 zakończyły konsultacje tej rundy na VPS. Poniżej są zlecenia do wykonania oraz kryteria ich odbioru.

### Za co jury przyznaje punkty

W preselekcji liczy się F1 na co najmniej 10 nieujawnionych sprawach. Do finału przechodzą maksymalnie trzy zespoły. W finale F1 daje 50%, a rozbudowa pozostałe 50%. Jury ocenia kod, opis architektury i prezentację. Aktualne README przewiduje 1–20 pkt za dodawanie typów dokumentów i klas danych oraz 1–10 pkt za dodatkowe funkcje, w tym GUI. Zapowiada też korektę szczegółowej punktacji LLM. Pierwotny PDF dzielił finał na 50/30/20. Do planowania przyjmujemy § 2 regulaminu i aktualne README. W tej rundzie używamy reguł A3 i lokalnego OCR. [Regulamin, § 2](https://mudnibfuppwadjkynscc.supabase.co/storage/v1/object/public/task-files/057d36b5-cb92-4062-9393-983cb8a96088/files/aa36e74b-f96c-46cf-9970-5937ed203222.pdf#page=2) · [Kryteria w README jury](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/eadffbce531eeac876d0f7e62c1cc6e857b05796/README.md#7-kryteria-oceny) · [Pierwotny opis zadania](https://mudnibfuppwadjkynscc.supabase.co/storage/v1/object/public/task-files/057d36b5-cb92-4062-9393-983cb8a96088/files/aeabc57d-7420-4069-946e-2c4de71d87ed.pdf#page=4)

### Co już działa

| Próba na naszym VPS | Wynik i znaczenie |
|---|---|
| 30 publicznych skanów organizatora | Mikro-F1 pól 60,08%, 152 TP, 45 FP i 157 FN. Rozpoznano 3/10 przelewów, 10/10 odwołań i 10/10 pełnomocnictw. Siedem przelewów dostało 0 B, więc przebieg jest nieważny w lokalnym protokole. Same odwołania mają 80 FN, pełnomocnictwa 31, przelewy 46. Te 30 PDF-ów było już w historii projektu. |
| 128 rozwojowych PDF-ów | 99,9265% po przeliczeniu tych samych wyjść względem poprawionych etykiet. Publikację poprzedziły 172 testy i zgodność 128/128 wyjść bajt w bajt. Na osobnej jawnej partii 150 dokumentów przy ograniczeniu do 2 vCPU i 16 GB czas wyniósł 56,81 s. OCR objął tam 25 PDF-ów. |
| Konfiguracja dokumentów i danych | Wcześniejszy odbiór czwartej klasy `zawiadomienie` potwierdził 3/3 przykłady, źródła 6/6 pól i zgodne wyjścia dla 3 klas konkursowych z 8 negatywami. W bieżącej konsultacji na jednym obrazie sprawdzono 3 nowe syntetyczne PDF-y w 4 profilach. Kopia konfiguracji już rozpoznawanego zawiadomienia dodała obiekt `miejsce_posiedzenia` z polami `budynek` i `sala`. Oba wskazały stronę 2, brak sali dał `null`, podobny komunikat pozostał 0 B, a powrót do profilu konkursowego odtworzył wszystkie bajty. |
| Operator | CLI udostępnia `review list/show/accept/correct`, czytelność stron, dowód pola i wersjonowany dziennik SQLite. Slajdy i ekrany zapasowe już istnieją. Interaktywny GUI wymaga implementacji. |

Dowody odbioru są na naszym VPS pod `~/uzp-parallel/koordynacja/runda-96f88b6/`, w szczególności `jury-2026-11-22/odbior-pomiarow.json`, `przekazania/15-rc2.md` oraz `plan-final-ec65413/proba-obiektu.json`. [Obecny pokaz konfiguracji](demo/rozszerzalnosc/README.md) · [Obsługa decyzji operatora](odwolania2json/review.py)

### Zlecenia dla istniejących czatów

| Czat | Zlecenie i zależność | Obserwowalny warunek ukończenia |
|---|---|---|
| 01 · dane | Przez 90 min szukaj w publicznych ZIP-ach BIP i na platformach zamawiających pełnych odwołań z załącznikami. Przez 30 min weryfikuj źródła, SHA-256 PDF-ów, odciski stron, rodziny szablonów i odbiorców. Trzymaj etykiety poza ekstraktorem. | Są dwie pieczęcie z 11 kompletnymi sprawami i 84 PDF-ami, ale 0/10 potwierdzonych na wyłącznie niewidzianych szablonach. Dziewięć ma układ znany lub pokrewny, dwie nierozstrzygnięte dzielą jeden układ. Do strojenia dopuszczamy 10 niezależnych pełnych spraw po weryfikacji rodzin oraz osobną próbę przelewów. W niej dziś 6 pozytywów pochodzi z 4 oryginałów i dotyczy 2 instytucji. Celem zespołu jest 6 różnych oryginałów, co najmniej 3 instytucje, w tym 2 poza UZP, oraz mylący negatyw z osobnego źródła. Opublikuj liczby i decyzję o dopuszczeniu. |
| 06 · niezależny pomiar | Przed pracą na nowej rezerwie przygotuj wersję protokołu porównującą wydanie `ec65413` z następcą. Obecny `compare_once.py` w trybie produkcyjnym wymaga bazy `96f88b6`. Zachowaj możliwość odtworzenia protokołu 06. | Kontrola syntetyczna przyjmuje właściwą bazę, odrzuca złą bazę oraz powtórne użycie pieczęci. W raporcie zamrożone SHA kodu, narzędzi, konfiguracji i obrazów. Pary przed/po mają identyczne wejścia i etykiety. DEV128, publiczne 30, nowe sprawy i osobne przelewy mają osobne mianowniki. [Miernik](evaluation/score.py) · [Jednorazowe porównanie](evaluation/compare_once.py) |
| 07, potem 08 · przelewy | 07 przygotowuje diagnozę siedmiu pominięć na publicznych skanach. Po pieczęci krzyżuje stary/poszerzony odczyt OCR ze starymi/zmienionymi regułami na tych samych odczytach. Osobno sprawdza dowody na dalszych stronach i przypadki Santander/Alior. Po odbiorze klasy 08 sprawdza przypisanie rachunku nadawcy Pekao. | Dla każdego z 7 PDF-ów podaj etap utraty, klasę i różnicę po zmianie. Celem promocji jest ważny przebieg na 30 i wzrost F1. Osobny test ma rozpoznać 2/2 wykonane przelewy i zachować 4/4 mylące negatywy 0 B. Dla rachunków podaj TP/FP/FN każdej roli, pełne zamiany i jednostronne błędy. W historycznej szóstce baza to 9/12 rachunków i 0 zamian. Nazwy plików w testach są neutralne i celowo mylące. |
| 12 i 13 · pisma | Na jawnych wynikach pogrupuj brakujące pola w odwołaniach i pełnomocnictwach. Po zamknięciu klasy przelewu koordynator wybiera najwyżej jedną następną zmianę na podstawie liczby odzyskiwalnych pól i ryzyka. | Liczba TP/FP/FN przed i po dla wskazanego pola. Każdy odzysk ma podstawę w PDF. Na DEV128 zostaje 40/40 pierwszych ID zarzutu, 8/8 negatywów 0 B i brak niewyjaśnionych strat. |
| 15 · rozszerzalność | Przygotuj do samodzielnego powtórzenia dwa zadania jurora na tym samym obrazie. Najpierw juror dodaje jedną klasę plikiem JSON. Następnie w kopii profilu dodaje klasę danych `miejsce_posiedzenia` do już rozpoznawanego zawiadomienia. Na kopii klasy UZP sprawdza jeszcze dodatkowe pole `numer_pisma` w odwołaniu. 06 lub juror przygotowuje neutralny PDF o innym układzie i wcześniej zapisuje oczekiwane wartości oraz strony. | Pokaż diff ograniczony do konfiguracji oraz skrót tego samego obrazu. Nowa wartość, brak wartości, źródło pola i podobny negatyw zgadzają się z wzorcem. Porównaj wszystkie wcześniejsze pola, wycofaj zmianę i odtwórz 11/11 plików kontrolnych bajt w bajt. Do pakietu wejdą instrukcja, przykład oraz krótki opis przejścia od sygnału przez regułę pola do walidacji. [Loader i schemat](odwolania2json/model.py) · [Operacje na polach](odwolania2json/operations.py) |
| 05 · GUI, z odbiorem 03 i 04 | Zbuduj jeden opcjonalny ekran offline na `127.0.0.1`, uruchamiany osobno od konkursowego CLI. Juror wkłada własny PDF do `input/` i uruchamia zwykłe CLI. Panel czyta gotową diagnostykę i JSON oraz korzysta ze wspólnej obsługi decyzji. Przygotuj osobny profil Compose dla panelu. 03 sprawdza zgodność dowodu, 04 sprawdza statusy i dziennik. Najpierw dostarcz kolejkę, powód kontroli, rzeczywisty PDF otwarty na właściwej stronie i JSON obok. Następnie dodaj akceptację lub korektę pola z bieżącym `review_id`. | Operator widzi czytelność strony osobno od poprawności ekstrakcji. Przy dokładnym dopasowaniu widzi cytat, a przy samym numerze strony otwiera tę stronę. Na 3 jawnych PDF-ach działa przejście klawiaturą do źródła. Dla wersji z zapisem po restarcie odczytujemy 2/2 decyzje, podmiana PDF-u odrzuca dawną decyzję, 3/3 surowe JSON-y zachowują SHA i negatyw ma 0 B. Pliki użytkownika pozostają lokalne. [Dowody](odwolania2json/field_evidence.py) · [Czytelność stron](odwolania2json/scan_quality.py) |
| 16, 17 i koordynator · wydanie | 16 odtwarza czysty start z `RUN.md` i sprawdza przygotowany obraz na naszym VPS. 17 robi z prezenterem dwie próby na tym samym SHA, w tym jedną z awarią. Koordynator sam odbiera diff i pomiary oraz wybiera wydanie. | Niezależny start bez sieci, komplet drzewa wyjść, ważna regresja 128 i 150/150 wyników poniżej 45 min przy 2 vCPU/16 GB. Jawny wynik ma podany zestaw i ważność. Dwie minuty to cel próby, faktyczny czas prezentacji potwierdza organizator. [Komenda jurora](RUN.md) · [Scenariusz](delivery/final/SCENARIUSZ.md) |

Silnik obsługuje obiekty i pola z istniejącymi operacjami, np. tekst lub datę. Nowy typ skalarny i budowa listy rekordów z powtarzalnych dopasowań wymagają obecnie odpowiedniej operacji w kodzie. Pokaz wskazuje tę granicę. Dowód działania GUI to wykonana czynność operatora. Trafność autoakceptacji wymaga niezależnych ocen człowieka i dodatniego mianownika. Do tego czasu dokumenty z niedostatecznym dowodem pozostają w kolejce.

### Harmonogram 22 listopada według czasu Warszawy

Jedna zmiana produktu jest wdrażana naraz. W tym samym czasie inne czaty mogą pozyskiwać dane, diagnozować, przygotowywać konfiguracje i odbierać gotowy fragment. Każdy wykonawca pracuje na wydzielonej gałęzi na naszym VPS. Ciężkie OCR i Docker korzystają ze wspólnych blokad. Koordynator uruchamia pełną regresję oraz ewentualne jednorazowe porównanie.

| Okno robocze | Wynik i decyzja |
|---|---|
| 02:00–04:00 | 01 pracuje nad pieczęcią. Równolegle 15 przygotowuje dowód konfiguracyjny, 06 sprawdza protokół, 07 przygotowuje diagnozę. 05 ma pierwsze 90 min na działający podgląd kolejki i PDF-u, następnie 30 min na odbiór. Pełny panel z edycją szacowano na ok. dzień pracy. |
| 04:00–06:30 | Jeśli 01 potwierdzi dopuszczenie danych, 07 dostaje 60–90 min na pierwszą poprawkę po ustaleniu przyczyny. Pozostały czas dajemy na powtórkę i odbiór. Przy brakującej pieczęci kontynuujemy pozyskiwanie danych, GUI i niezależną próbę konfiguracji. Strojenie oraz końcowy F1 pozostają wtedy otwarte. |
| 06:30–07:30 | Zmieniamy najwyżej jeden następny element. Pierwszeństwo ma wykazany błąd roli w Pekao lub powtarzalna strata w pismach. Jeżeli po 60 min nie ma odtwarzalnego zysku, zachowujemy ostatni odebrany wariant. |
| 07:30–09:15 | 06 i koordynator sprawdzają obie rewizje na identycznych jawnych zestawach, wszystkie zmienione wyniki, klasy, błędy ról i czasy. Dla samych zmian GUI lub demonstracji wymagamy zgodności bajtowej 128/128. Po zamrożeniu kandydata i dopuszczeniu danych koordynator zleca najwyżej jedno porównanie ślepe. |
| 09:15–09:45 | 16 zamyka obraz, instrukcję, źródła, opis architektury i pakiet demonstracyjny na naszym VPS. Kandydat rezerwowy to `ec65413`. Do 09:45 przewidujemy odrębną decyzję zespołu w sprawie VM jury. |
| Do 10:15 | 17 mierzy próbę z człowiekiem. Przy celu 120 s przewidujemy 30 s na PDF, JSON i jakość, 35 s na GUI, 40 s na zmianę konfiguracji i 15 s zapasu. Po 10 s zablokowanego pokazu przechodzimy do CLI lub jawnie oznaczonego zapisu offline. Gdy zabraknie czasu, najpierw odkładamy edycję pól w GUI i kolejną poprawkę ekstrakcji. Zachowujemy pokaz klasy i danych oraz bezobsługowe CLI. |

UZP odcina dostęp zespołu do VM o 11:00. Dokument pomija strefę, dlatego do planowania przyjęliśmy czas Warszawy. Godziny 09:45 i 10:15 są zapasem zespołu. Bieżące zlecenie obejmuje przygotowanie na własnym VPS. [Instrukcja VM](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/eadffbce531eeac876d0f7e62c1cc6e857b05796/VM.md)

**Pierwszy krok wykonawczy** to otwarcie dwugodzinnego okna 01 na dane. W tym samym oknie 05 może dostarczyć realny podgląd jurora, a 15 utrwalić drugi przykład rozszerzalności.

## Wcześniejsze założenia i przebieg projektu

Juror wkłada własne PDF-y do `input/` i jednym poleceniem uzyskuje odpowiadające im pliki w `output/`. Laptop i7 z 16 GB RAM pozostaje wewnętrznym celem sprzętowym projektu. UZP zapowiedziało zmianę sposobu testowania. Wersja konkursowa działa lokalnie na CPU, w Pythonie 3.13+, z zależnościami w `requirements.txt`. Wspólna gałąź łączy A3, lokalny OCR, dystrybucję Compose i osobny pokaz konfiguracji. B i C są eksperymentem dotyczącym pojedynczej decyzji o pierwszym zarzucie.

**Historyczny wybór do pierwszego testu końcowego.** Wybrano A2 z lokalnym OCR ze względu na dwa odzyskane syntetyczne przelewy i zgodność 128 JSON-ów rozwojowych z A. Wynik walidacji 0,9878 przy `valid_run=false` pozostaje historycznym wynikiem A. Konfiguracja wbudowana zawiera trzy klasy konkursowe. Pokaz rozszerzenia i Compose mają własne instrukcje odbioru. Opcjonalny eksperyment B/C korzysta teraz z selektora A3 w tej samej wersji repozytorium. [Odbiór bez API](experiments/abc/README.md) [Raport A](RAPORT_A.md) · [Raport A2](RAPORT_A2.md)

## Stan prac nad A3 z 21 listopada

Stan na 21.11.2026, 19:46 czasu polskiego. Rozwijamy A3. Mierzona wersja `5de75693429d9699368b958cd54eda4dd76e4900` jest na `main`. Kolejne poprawki A3 będą miały własne SHA, co pozwoli przypisać wynik do konkretnej wersji kodu.

| Etap planu | Stan i dowód |
| --- | --- |
| H0–12, dane i podstawowy produkt | Sprawdzono rozłączność zbiorów, CLI dla trzech klas i dokumentów obcych oraz niezależność treści JSON od nazwy PDF-u w 256 próbach. Pytania o szczegóły miernika jury pozostają otwarte. |
| H12–15, jakość ekstrakcji | Na 128 rozwojowych PDF-ach A3 osiągnął 99,63% mikro-F1. Wśród 120 dokumentów trzech klas diagnostyka nie odnotowała użycia OCR. W ośmiu fikcyjnych przypadkach dobranych do poprawek A3 spełnił osiem oczekiwań, a A2 trzy. Jednorazowy test 10 pełnych spraw zamrożonych przed pracami nad A3 obejmował 30 PDF-ów z OCR i dał 55,67%, `valid_run=false` oraz `valid_contract=true`. Osiem przelewów otrzymało pliki 0 B. Wracamy do tego etapu. [Raport pojedynczego pomiaru A3](RAPORT_KONCOWY_A3.md) |
| H15–17, porównanie B/C | Adaptery przeszły próby na atrapach. Wpływ rzeczywistych modeli na F1 pozostaje niezmierzony. Decyzja o zastosowaniu LLM jest otwarta. |
| H17–20, odbiór techniczny i próba końcowa | CLI natywne i Compose dały zgodne wyniki na 6/6 PDF-ach. Dodanie klasy konfiguracją zachowało 11/11 plików regresji, w tym 8/8 pustych negatywów. Pokaz przeszedł na czystej kopii na VPS. Pomiar skanów został już wykorzystany. Do następnego niezależnego pomiaru odłożyć świeże pełne sprawy przed strojeniem. [Odbiór techniczny A3](RAPORT_A3.md) |
| H20–24, zgłoszenie | Są instrukcja, slajdy i ekrany rezerwowe. Przed wysyłką trzeba uaktualnić wyniki, potwierdzić dostęp do prywatnego repozytorium z konta jurora, zmierzyć próbę z prezentującym oraz zachować potwierdzenie zgłoszenia. |

**Aktualizacja UZP.** Organizator zapowiedział nowe wytyczne oceny LLM i zmianę sposobu testowania. Punktacja modeli 1B i 4B pozostaje otwarta. Opublikowany limit przetwarzania to 45 minut na 150 PDF-ów. Wersję do zgłoszenia trzeba zmierzyć na partii tej wielkości. Dotychczasowy pomiar 58,35 s dotyczy 30 PDF-ów. [README UZP z 21 listopada](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/0b360a9da4b482a6a280696df6714404e0953505/README.md#sposób-punktacji-llm)

## Kontrakt UZP i robocze decyzje

Podstawą danych jest [rewizja UZP de135d2](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/de135d20811caf630f3e94dc655ba5eebd9a6710). Repozytorium zawiera 60 spraw, 196 ścieżek PDF i 180 etykiet JSON. Na sprawdzonym późniejszym `7590db8` README jest identyczne. UZP poprawiło opisy ID 6 w etykietach spraw 19, 23, 25, 44 i 55. Zamrożone pomiary używają pierwotnej rewizji. [Porównanie UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/compare/de135d20811caf630f3e94dc655ba5eebd9a6710...7590db84f39281b36f774d14f8961cdeb2a0c4c4)

| Obszar | Implementacja i odbiór |
|---|---|
| Uruchomienie i drzewo wyników | Docelowe komendy to `python -m pip install -r requirements.txt` i `python -m odwolania2json` w katalogu głównym. CLI korzysta z argparse, pathlib i json oraz wyłącznie z komponentów open source. Klasyfikować po treści i zachować ścieżkę oraz nazwę bazową, np. `input/K/x.pdf` → `output/K/x.json`. Obsłużyć kilka dokumentów jednej klasy w sprawie. Po zmianie wejścia wynik zawiera wyłącznie bieżące pliki. Pusty folder daje zero wyników. |
| Negatyw i błędy odczytu | UZP wymaga pustego pliku `.json` dla dokumentu obcego. Do odpowiedzi mentora zapisujemy dokładnie 0 bajtów. W rozpoznanym typie zachowujemy strukturę i dopuszczalne `null`. Uszkodzenie lub nieczytelny skan ma własny komunikat i status w diagnostyce, a przetwarzanie pozostałych PDF-ów trwa dalej. |
| Przelew | Odczytać wszystkie sześć pól. Są to `data_operacji`, liczbowa `kwota`, `tytul`, `numer_transakcji` oraz ciągi `z_rachunku` i `na_rachunek` w prawidłowych rolach. Zachować zera w identyfikatorach. Numer transakcji występuje w 10/10 przelewów walidacyjnych. |
| Pełnomocnictwo | Odwzorować listę mocodawców wraz z ich danymi i podpisującymi oraz listę pełnomocników. Sprawdzić wielu uczestników i brakujące wartości. |
| Odwołanie | Rozdzielić odwołującego, zamawiającego i pełnomocników oraz numery BZP, TED i numer wewnętrzny. Datę czynności, ID 1–12 i opis wiązać z pierwszym zarzutem. Przy braku wiarygodnej daty czynności zwrócić `null`. Opis generować ze słownika na podstawie ID. |
| Struktura i pochodzenie pól | Przepisać wzorce UZP do walidowalnych schematów klas. Wzorce odwołania i pełnomocnictwa zawierają komentarze, a przykład odwołania ma także brakujący przecinek. Sprawdzić klucze, typy, listy i dopuszczalne braki na danych rozwojowych. Poza `output/` zapisywać stronę oraz regułę wskazującą wartość pola. |
| Czytnik i konfiguracja | Zacząć od pypdf, porównać tekst zwykły i `layout` na tych samych stronach rozwojowych. Od pierwszej klasy wczytywać z konfiguracji sygnały rozpoznania, schemat i operacje ekstrakcji. Rozważyć pdfplumber przy pomyłkach kolumn i ról. Lokalny Tesseract z językiem polskim włączać po pomiarze odzyskanych pól, czasu i kosztu instalacji na skanie mieszanym i obróconym. |

[README i kontrakt UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/de135d20811caf630f3e94dc655ba5eebd9a6710/README.md) · [Schematy i słownik](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/de135d20811caf630f3e94dc655ba5eebd9a6710/oczekiwane-json)

## Zamrożony podział 40/10/10

| Zbiór | Pełne sprawy | Odwołania / pełnomocnictwa / przelewy | Negatywy | Razem |
|---|---:|---|---:|---:|
| [Rozwojowy](evaluation/development-40.json) | 40 | 40 / 40 / 40 | 8 | 128 |
| [Walidacyjny](evaluation/validation-10.json) | 10 | 10 / 10 / 10 | 2 | 32 |
| [Końcowy](evaluation/final-10.json) | 10 | 10 / 10 / 10 | 1 | 31 |

**Test końcowy** obejmuje sprawy `03, 08, 12, 14, 24, 29, 31, 39, 47, 51`. Zawiera każdy PDF z tych katalogów, w tym dokument obcy należący do sprawy 24. SHA-256 pliku `final-10.json` po normalizacji końców wierszy do LF wynosi `f36fffc9127520e0caad2df4413a2e6769b2b4d9e2dc1de5de9c668e9efa0a8b`.

**Walidacja** obejmuje sprawy `04, 09, 16, 22, 27, 33, 37, 44, 50, 56`. Zachowano pierwotny manifest z negatywami w 04 i 37. **Rozwój** obejmuje pozostałe 40 całych spraw, w tym negatyw w 10, oraz siedem dodatkowych, unikatowych negatywów z `dane/negatywne/`. Ich neutralne foldery `case_61`–`case_67` służą wyłącznie do podawania pojedynczego pliku i nie zwiększają liczby spraw UZP.

**Dobór końcowy.** Wybór oparto na numerach spraw, obecności dokumentu obcego i układzie pierwszej strony. Pozostawiono w rozwoju sprawy 19, 23, 25 i 55 ze znanymi poprawkami etykiet oraz 32, 53 i 57 omawiane podczas przeglądu szablonów. Spośród wolnych spraw z dodatkowym PDF-em przypisano 24 do testu i 10 do rozwoju. Sprawy połączone przez jednakowy ścisły odcisk układu dowolnej z trzech klas traktowano łącznie przy wyborze do testu. W zakresach 01–10, 11–20, 21–30, 31–40 wybrano po dwie sprawy, a w 41–50 i 51–60 po jednej. W dwóch ostatnich zakresach wybrano razem 47 i 51, które mają ten sam układ przelewu. Pozostałe wolne miejsca w pierwszych czterech zakresach zajęły dopuszczalne numery o najmniejszym SHA-256 napisu ASCII `odwolania2json/final-v1/NN`. Dobór nie korzystał z wartości pól ani wyników ekstrakcji.

**Kontrola hashy.** Dla każdej z trzech par zbiorów przecięcie numerów pełnych spraw, SHA-256 bajtów PDF i SHA-256 treści etykiet po ujednoliceniu LF wyniosło **0**. Wszystkie 180 etykiet mają różne hashe LF. Z 196 źródłowych ścieżek PDF pozostaje 191 różnych plików. Pięć kopii z `dane/negatywne/` pominięto, zachowując oryginały w sprawach 04, 10, 24 i 37. Sprawa 10 ma dwie takie kopie. Pliki źródłowe nadal leżą w kompletnym repozytorium UZP, dlatego każde wejście należy zbudować wyłącznie z manifestu przypisanego do próby.

**Wspólne szablony.** Audyt pierwszej strony w pypdf 6.21.4 porównuje osobno każdą klasę. Ścisły odcisk obejmuje obrót i wymiary strony oraz pozycję, font i rozmiar pisma pierwszych sześciu niepustych fragmentów tekstu. Szerszy wzorzec to kolejność co najmniej dwóch różnych, z góry wymienionych nagłówków po ujednoliceniu wielkości liter, odstępów i końcowego dwukropka. W tabeli podano liczbę różnych wspólnych sekwencji nagłówków.

| Para | Odwołanie | Pełnomocnictwo | Przelew | Negatyw |
|---|---:|---:|---:|---:|
| Rozwój – walidacja | 6 | 4 | 2 | 1 |
| Rozwój – test końcowy | 6 | 2 | 1 | 0 |
| Walidacja – test końcowy | 3 | 1 | 1 | 0 |

Wśród porównywalnych stron wykryto **0 wspólnych ścisłych odcisków** między testem końcowym a pozostałymi zbiorami. Rozwój i walidacja współdzielą po jednym takim odcisku dla odwołania (49, 58 i walidacyjne 56) oraz przelewu (59 i walidacyjne 56). Poniższe przykłady pokazują szersze rodziny obecne w każdym zbiorze.

- W odwołaniach z 15 / 09 / 08 powtarza się kolejność „Odwołujący → Zamawiający → Dotyczy → Odwołanie” (rozwój / walidacja / test).
- W pełnomocnictwach z 01 / 37 / 31 powtarzają się nagłówki pełnomocnictwa, mocodawcy i przyjęcia pełnomocnictwa.
- Przelewy z 40 / 44 / 47 mają wspólną kolejność zleceniodawcy i jego rachunku, odbiorcy i jego rachunku, daty operacji i tytułu.

Ścisły odcisk dało się policzyć dla 180/180 dokumentów trzech klas i 7/11 unikatowych negatywów. Szerszą sekwencję rozpoznano w 59/60 odwołań, 37/60 pełnomocnictw, 49/60 przelewów i 3/11 negatywów. To porównanie cech pierwszej strony, a część rodzin przechodzi między zbiorami. Wynik końcowy opisuje nowe **sprawy** w tej próbce. Pojedynczy negatyw w teście ma wartość przykładu kontrolnego.

**Rozdzielenie danych.** Proces przygotowania kopiuje wskazany `pdf` do ścieżki `input` z manifestu. Ekstraktor dostaje wyłącznie takie PDF-y, bez dostępu do repozytorium UZP, oryginalnych nazw, etykiet i manifestów. Osobny proces oceny czyta mapowanie na `reference`. Podczas rozwoju diagnozujemy błędy na zbiorze rozwojowym. Walidacja służy do jednego porównania zamrożonych A/B/C. Test końcowy uruchamiamy raz po zapisaniu wersji kodu, konfiguracji i wyboru wariantu. Po tym biegu zapisujemy ograniczenia i raport.

Poniższe polecenia należy wykonać z katalogu projektu, przy kopii UZP w `../hacknation-2026`.

```sh
git -C ../hacknation-2026 rev-parse HEAD
python evaluation/check_splits.py ../hacknation-2026
python -m unittest discover -s evaluation -p "test_*.py"
```

Oczekiwany HEAD UZP to `de135d20811caf630f3e94dc655ba5eebd9a6710`. Powtórzenie audytu szablonów wymaga `python -m pip install pypdf==6.21.4` i `python evaluation/check_splits.py ../hacknation-2026 --templates`. Kontrola samych hashy korzysta z biblioteki standardowej. Miernik obsługuje etykiety LF i CRLF również dla starego manifestu walidacji. PDF-y porównuje bajt po bajcie.

## Kolejność pracy i warunki ukończenia

Godziny od startu w sobotę 21 listopada o 11:00 czasu polskiego. Szkic projektu w HackTribe należy założyć **przed 20:00 w sobotę**. Zgłoszenie końcowe zamyka się **w niedzielę 22 listopada o 11:00**. Cel wewnętrzny to wysyłka do 10:00. [Przewodnik HackNation](https://hacknation.pl/przewodnik-uczestnika) · [Instrukcja HackTribe](https://hacknation.pl/api/public/przewodnik/1f73a661-0852-4e9e-b3ed-58c93bce6456?asset=aa346c52-8bd9-44ac-9499-364e44c4b6b4)

| Budżet | Odbieralny wynik |
|---|---|
| H0–2 | Zamrożony podział i rozłączność spraw oraz hashy są sprawdzone. Ustalić z mentorem reprezentację pustego wyniku i reguły F1, zapisać decyzję i wersję kontraktu. |
| H2–6 | Z czystego środowiska uruchomić pierwsze CLI na rozwojowym `case_01/doc_02.pdf`. Wynikiem jest `output/case_01/doc_02.json` z sześcioma polami przelewu zgodnymi z referencją. Konfiguracja zawiera sygnały klasy, schemat i reguły. |
| H6–12 | Jedna sprawa przechodzi przez trzy klasy i dokument obcy. Dodatkowe próby obejmują zmianę nazw, dwie instancje tej samej klasy, pusty folder, nieczytelny skan, uszkodzony PDF i ponowny bieg po usunięciu wejścia. Walidator sprawdza zbiór ścieżek, format negatywu, klucze i typy osobno od mikro-F1. Przed H9 sprawdzić, czy szkic w HackTribe wskazuje UZP. |
| H12–15 | Poprawić największe straty na danych rozwojowych. Rozróżnić jakość tekstu, kolumny, klasyfikację, role i normalizację. Zamrozić kod A, selektor pierwszego zarzutu, prompt i parametry. Policzyć A na wszystkich 32 walidacyjnych PDF-ach i zapisać wyjścia, czas oraz szczyt RAM. |
| H15–17 | Przeprowadzić porównanie opisane poniżej. Jeśli pełne A jest opóźnione, czas na B/C przechodzi na ekstrakcję i próbę wydania. W pierwszej kolejności odłożyć GUI i dodatkowy czytnik. Rozbudowę OCR uzależnić od wykazanych strat na skanach. |
| H17–20 | Zapisać SHA kandydata i wybór wariantu przed otwarciem testu końcowego. Przeprowadzić jeden pomiar końcowy i próbę dodania klasy. Z czystej kopii na CPU do 16 GB uruchomić natywnie i przez Compose tę samą sprawę. Wariant A ma dać identyczne JSON-y. Zapisać zimny czas instalacji, czas partii, RAM, wynik i ograniczenia. |
| H20–23 | Konto z dostępem jurora klonuje prywatne repozytorium i samodzielnie przechodzi od własnych PDF-ów do JSON-ów według README. Sprawdzić domyślną komendę, montowanie wejścia i wyjścia w Compose, licencje, dokumentację klas i działający limit klucza przekazanego poza Git, jeśli wydanie go wymaga. Przećwiczyć pokaz z zegarem i bez sieci. Wysłać tytuł, link do prototypu i materiały w formularzu, w tym prezentację PDF do 10 MB zgodnie z instrukcją HackTribe. Zachować potwierdzenie. |
| H23–24 | Godzina rezerwy na dostarczenie materiałów lub poprawienie dostępu jurora. |

## Historyczny plan porównania A/B/C na 10 sprawach

**Pytanie.** Jak zmienia się mikro-F1 pełnego przebiegu, gdy regułę wyznaczającą `czynnosc_powod_id` pierwszego zarzutu zastępuje odpowiedź modelu? Klasyfikacja, czytnik, tekst, wybór fragmentu i wszystkie pozostałe pola są wspólne. Każdy wariant wyprowadza `czynnosc_opis` z tego samego słownika. Poprawne ID i poprawny opis mogą dać dwa trafienia wynikające z jednej decyzji.

1. **Przygotować A i adaptery.** Na danych rozwojowych sprawdzić selektor na odwołaniu z dwoma różnymi zarzutami, ustalić postępowanie przy braku przesłanek i zweryfikować schemat odpowiedzi dla 12 ID. Zarejestrować stronę oraz hash fragmentu. Przygotować odpowiedzi testowe na brak klucza, 429, timeout i wadliwy JSON.
2. **Porównać uzgodnionych kandydatów.** A to reguły. B dodaje Qwen3.5-9B przez OVHcloud AI Endpoints w Gravelines. C dodaje Mistral Small 3.2 24B Instruct 2506 przez Scaleway Generative APIs w Paryżu. Oba modele są na Apache 2.0. Przypiąć rzeczywiste identyfikatory i parametry generacji. Po wyniku A wykonać próbę dostępu na krótkim fikcyjnym zarzucie. Sekrety `OVH_AI_ENDPOINTS_ACCESS_TOKEN` i `SCALEWAY_SECRET_KEY` odczytuje odpowiedni adapter. Tylko dokument rozpoznany przez wspólny klasyfikator jako odwołanie uruchamia model. Oba modele otrzymują ten sam fragment i instrukcję, bez referencji. Dla każdej awarii zapisać przyczynę, zastosować regułę A i dokończyć partię.
3. **Zmierzyć efekt i koszt.** Dla wszystkich 32 wyników zapisać TP/FP/FN, mikro-F1 i zmianę względem A w pkt proc., macierz klas, dokładność ID z mianownikiem 10, fałszywe rozpoznania z mianownikiem 2, błędnie wybrane fragmenty, przypadki poprawione i pogorszone oraz użycia reguły awaryjnej. Zmierzyć tokeny wejścia i wyjścia, koszt po stawce danego dostawcy, czas na dokument i czas partii. Punkt odniesienia w EUR za milion tokenów wejścia/wyjścia to 0,10/0,15 dla Qwena (katalog podaje 9,7 mld parametrów) i 0,15/0,35 dla Mistrala. Do wydania zapisać stawkę i datę pomiaru, licencję, firmę świadczącą API i lokalizację serwerów w UE/EOG. [Model OVHcloud](https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/qwen-3-5-9b/) · [Cennik OVHcloud](https://www.ovhcloud.com/fr/public-cloud/prices/) · [Cennik Scaleway](https://www.scaleway.com/en/pricing/model-as-a-service/) · [Region Scaleway](https://www.scaleway.com/en/docs/generative-apis/faq/)
4. **Wybrać przed testem końcowym.** Warunkiem kwalifikacji są poprawne drzewo, struktura JSON i działający powrót do A. Przy remisie F1 z A wybrać A. Przy równym dodatnim zysku modeli preferować mniejszy po sprawdzeniu czasu, kosztu i awarii. Walidacja obejmuje 7 z 12 ID. Jeden wynik zmienia dokładność ID o 10 pkt proc., a jeden negatyw odsetek błędnych rozpoznań o 50 pkt proc. Zapisujemy zakres dowodu i numer wersji kandydata.

### Jak czytać wynik miernika

`fields()` porównuje niepuste wartości wraz z typem i ścieżką, w tym indeksem listy. Ścisłe mikro-F1 wynosi `2TP/(2TP+FP+FN)`. Złe podstawienie daje FP i FN. Pominięta wartość daje FN, a niepusta wartość wydobyta z negatywu daje FP. `valid_run` i `false_positive_documents` trzeba czytać razem z F1. Zaplanowany walidator struktury powinien dodatkowo wskazywać konkretną ścieżkę błędnego pola. Ewentualny wynik po normalizacji raportować osobno.

| Kontrola na walidacji | Obserwacja |
|---|---|
| Referencje jako predykcja | 331 TP, 0 FP, 0 FN, F1 1,0000. Potwierdzone także po zmianie zakończeń wierszy etykiet na LF. |
| Zamiana rachunków lub zamiana miejsc dwóch pełnomocników w 04 | W każdej próbie 329 TP, 2 FP, 2 FN. Indeksy zachowują kolejność. |
| Brak klucza, którego wzorcowa wartość to `null` | F1 nadal 1,0000. Zastąpienie niepustej daty przez `null` daje 1 FN. |
| Brak pliku przelewu / brak pliku negatywu | Oba przebiegi mają `valid_run=false`. W przykładzie brak przelewu daje 6 FN, brak negatywu pozostawia F1 1,0000. |
| Jedno błędne pole w negatywie | 1 FP i 1 błędny dokument. Obiekt zawierający tylko pole `null` daje 0 FP pól i 1 błędny dokument. Miernik akceptuje dla negatywu zarówno 0 bajtów, jak i `{}`. |
| Zamiana rachunków, pominięta kwota i pole w negatywie | 328 TP, 3 FP, 3 FN, F1 0,9909. |
| Poprawne ID z opisami wyprowadzonymi ze słownika | 10/10 ID, 330 TP, 1 FP, 1 FN, F1 0,9970. Przypięta etykieta w sprawie 44 zapisuje spójnik „i” w miejscu ukośnika. |

Mikro-F1 może zawyżać wynik przy wymaganych kluczach lub silniejszej karze za błędną klasę. Może go zaniżać, jeżeli jury akceptuje alternatywną kolejność list i normalizuje tekst. Powyższe liczby opisują próby kontrolne miernika. Wyniki ekstraktora są w raportach A, A2 i A3.

Polecenie walidacyjne to `python evaluation/score.py ../hacknation-2026 wyniki-walidacja`. Opcja `--manifest` wybiera inną próbę. Dopiero po zamrożeniu wydania wykonać `python evaluation/score.py ../hacknation-2026 wyniki-koncowe --manifest evaluation/final-10.json`. [Miernik](evaluation/score.py) · [Kontrola podziału](evaluation/check_splits.py)

## Odbiór produktu i pokrycie kryteriów

| Moment | Dowód dla jurora lub UZP |
|---|---|
| Zgłoszenie | Tytuł i link GitHub do działającego prototypu. Własne wyniki i dokumentacja techniczna są dodatkami do zgłoszenia. W przypadku prywatnego repozytorium sprawdzić klonowanie i start z uprawnionego konta odbiorcy. |
| Preselekcja | Wyłącznie F1 na co najmniej 10 nieujawnionych sprawach. Do finału UZP przechodzą maksymalnie trzy zespoły. Lokalny wynik ma podaną rewizję danych, SHA programu i zasady miernika. |
| Finał | Według § 2 regulaminu zadania 50% za F1 i 50% za łatwość rozbudowy. Jury ocenia kod, opis architektury i treść prezentacji. README wymienia wielkość modelu, dodawanie klas i funkcje dodatkowe. UZP pracuje nad szczegółową punktacją LLM. Szczegółowy PDF podaje 50/30/20, a ogólny przewodnik wydarzenia wymienia pięciu finalistów. W tym zadaniu stosujemy regulamin UZP. |
| Przekazanie przez zwycięzcę | § 3 ust. 5 wiąże wypłatę z umową przeniesienia praw i przekazaniem kodu, instrukcji uruchomienia, konfiguracji Docker Compose oraz dokumentacji architektury, konfiguracji istniejącej klasy i dodania nowej. Compose sprawdzamy wcześniej na tym samym wydaniu. Rozwiązania zewnętrzne wskazujemy w prezentacji zgodnie z § 4. |

**Dowód rozszerzalności.** Profil demonstracyjny dodaje `zawiadomienie.json` z sygnałami, schematem i regułami dwóch pól. Pokaz ujawnia wartości `sygnatura` i `termin` oraz stronę i regułę terminu. Profil konkursowy daje 0 bajtów dla syntetycznych zawiadomień. Odbiór sprawdza 11/11 ścieżek i sum SHA-256 oraz 8/8 pustych negatywów rozwojowych. [Instrukcja pokazu](demo/rozszerzalnosc/README.md)

**Odbiór kolejnej poprawki A3.** Czysta kopia ma przejść testy CLI, pokaz rozszerzenia, porównanie bajtów i diagnostyki natywnego A3 z Compose oraz ocenę na 128 PDF-ach rozwojowych i odrębnych skanach. Pokaz dwuminutowy obejmuje własny PDF, źródło pola oraz dodanie klasy. [Odbiór Compose](delivery/compose/README.md)

[Regulamin zadania, § 2–4](https://mudnibfuppwadjkynscc.supabase.co/storage/v1/object/public/task-files/057d36b5-cb92-4062-9393-983cb8a96088/files/aa36e74b-f96c-46cf-9970-5937ed203222.pdf) · [Szczegółowy opis PDF](https://mudnibfuppwadjkynscc.supabase.co/storage/v1/object/public/task-files/057d36b5-cb92-4062-9393-983cb8a96088/files/aeabc57d-7420-4069-946e-2c4de71d87ed.pdf) · [FAQ HackNation](https://hacknation.pl/faq)

**Do potwierdzenia u mentora.** Jak jury traktuje brak pliku, `null`, typy liczb, permutacje list i normalizację? Czy negatyw ma dokładnie 0 bajtów? Jak postępować przy nieczytelnym skanie, braku podstawy do ID i niezgodności opisu z kanonicznym słownikiem? Jak są oceniane A bez modelu, limity API, kanał przekazania klucza, dostęp do repozytorium i czas pokazu?

**Historyczny odbiór RC1 z A2.** Zamrożono `1937848079584ec72aa1307f1305637e93607e1c` po zaliczeniu odbioru CLI, OCR, Compose, rozszerzenia i development na VPS. Pomiar końcowy tej rewizji i materiały pokazu są w paczce przekazania. [Raport odbioru RC](RAPORT_RC1.md) · [Raport końcowy](RAPORT_KONCOWY.md) · [Instrukcja jurora](delivery/final/INSTRUKCJA-JURORA.md)

**Najbliższy termin organizacyjny.** Szkic w HackTribe musi istnieć i wskazywać zadanie UZP przed 20:00 w sobotę 21 listopada. Na godzinę tego zapisu w materiałach projektu brakuje potwierdzenia. Termin finalnego zgłoszenia to 11:00 w niedzielę 22 listopada. [Przewodnik HackNation](https://hacknation.pl/przewodnik-uczestnika)

**Przelewy A3.** Wersja `1503772` przeszła odbiór na VPS. Mikro-F1 na 40 skanach rozwojowych wzrosło z 81,63% do 90,17%, a 128 dotychczasowych plików wynikowych pozostało identycznych bajtowo. Odłożony generator KontoBank dał 98,11% na jednym układzie. Na polskiej ilustracji Pekao24 poprawnie rozpoznano klasę, lecz pominięto oba widoczne pola. [Raport i polecenia weryfikacji](RAPORT_PRZELEWY_A3.md)

**Rezerwa KARR.** Dwa nowe układy, BNP Paribas i Millenet, zamrożono przed strojeniem A3. Wersja `59fcf1a` uzyskała na słabych skanach 41,67% mikro-F1. Odczytała 3/3 kwot i 1/3 dat. Obie faktury dały po 0 B, a 128/128 wyników rozwojowych pozostało identycznych bajtowo. Warunek poprawnego odczytu kwoty i daty na obu nowych układach spełnił tylko Millenet. Ważny wynik pochodzi z Docker Compose na VPS. Pierwsze uruchomienie bez kontenera przerwał `SIGSEGV`. [Raport, rozbicie na pola i pliki odbioru](RAPORT_KARR_A3.md)

**Przelewy przez Scaleway API.** Mistral Small 3.2 24B na czterech zamrożonych wycinkach z 44 rozwojowych PDF-ów odzyskał 3/3 brakujących kwot. Wpisał datę wygenerowania w miejsce daty operacji. Mikro-F1 wszystkich pól wyniosło 76,82% wobec 76,19% dla A3. Czas wzrósł z 51,92 s do 86,93 s. [Pomiar, przyczyna błędu i polecenie weryfikacji](experiments/transfer_api/RAPORT.md)

**Niezależna rezerwa przelewów.** Osiem dokumentów zamrożono przed zmianą selektora daty. Na trzech publicznych potwierdzeniach i dwóch negatywach każdy wariant uzyskał diagnostycznie 27,27%. Jedno rzeczywiste potwierdzenie dostało plik 0 B, więc miernik oznaczył przebieg jako nieważny. Na trzech syntetycznych próbach poprawiona data podniosła F1 z 96,97% do 100%. Na 44 znanych słabych skanach A3 uzyskał 76,19%, wariant kwotowy 76,99%, a oba pola 77,25%. Regresja 128/128 pozostała bajtowo zgodna. API pozostaje eksperymentalne. [Odtworzenie, źródła i błędy](experiments/transfer_api/RAPORT_REZERWA.md)

**Klasyfikacja wykonanych przelewów.** W pierwszej odłożonej próbie A3 rozpoznało 2/3 przelewy, a oba negatywy dały 0 B. Na drugiej, zamrożonej przed kolejną poprawką, wersja `4edfd0c` uzyskała 3/3 i 2/2. F1 klasy wyniosło 100%, a ścisłe mikro-F1 sześciu pól 41,38% przy zerze kompletnych przelewów. Wszystkie 128 wyników UZP pozostało identycznych bajtowo. Starszy skan Alior z BIP nadal daje 0 B. [Dwa pierwsze pomiary, rozbicie na pola i polecenia weryfikacji](RAPORT_KLASYFIKACJA_PRZELEWOW.md)

## Czytelność skanu i akceptacja wyniku przez człowieka

**Stan prac.** Poniższe wymaganie produktowe jest zaplanowane. Istniejąca diagnostyka CLI stanowi jego punkt wyjścia.

Każdy PDF ma mieć w raporcie obok drzewa wyników dwie osobne oceny. Pierwsza opisuje czytelność stron (czytelna, częściowo czytelna, nieczytelna). Druga wskazuje decyzję dla dokumentu (można przyjąć automatycznie, wymaga weryfikacji). Czytelny obraz może dać błędny numer lub niejednoznaczną rolę. W raporcie użytkownik zobaczy listę dokumentów do weryfikacji, konkretną stronę, pole, powód i fragment źródłowy, który może sprawdzić w PDF. Dla uszkodzonego pliku raport opisze błąd otwarcia. Decyzję człowieka (akceptacja lub korekta) zapisujemy w osobnym dzienniku powiązanym z hashem PDF-u i wersją wyniku. Drzewo konkursowe zachowuje schematy UZP i pliki 0 B dla negatywów.

Do weryfikacji kierujemy m.in. nieodczytaną istotną stronę, sprzeczne dowody klasy, niepewny negatyw, brak widocznej wymaganej wartości, wadliwą sumę kontrolną oraz rachunek bez jednoznacznego przypisania do strony transakcji. Dopuszczalny brak pola ma własny powód. Wysoka pewność OCR, czytelna warstwa tekstowa i poprawny schemat same nie uzasadniają automatycznej akceptacji.

**Odbiór.** Przed doborem progów odłożyć osobne dokumenty z ręczną oceną czytelności stron i poprawności pól. Próba ma zawierać trzy klasy UZP, czytelne negatywy, słabe skany, wielostronicowy dokument z jedną nieczytelną stroną oraz czytelne potwierdzenie z niejednoznacznymi rachunkami. Na zbiorze odłożonym pokazać liczby błędnie zaakceptowanych dokumentów, wszystkich błędnych dokumentów skierowanych do kontroli, poprawnych skierowanych do kontroli i odsetek dokumentów akceptowanych automatycznie. Osobno pokazać wykrywalność nieczytelnych stron. Każdy automatycznie zaakceptowany błąd krytyczny blokuje włączenie automatycznej akceptacji danego profilu. Pusta grupa automatycznie zaakceptowanych nie dostarcza dowodu jej trafności. Do czasu pomiaru profil wymaga weryfikacji. W demonstracji juror otwiera wskazaną stronę, sprawdza dowód, zatwierdza lub poprawia pole i widzi zapis decyzji.

**Rachunki nadawcy i odbiorcy.** Na sześciu nowych potwierdzeniach do sześciu odbiorców, w tym pięciu spoza UZP, A3 `25fc429` podniosło mikro-F1 obu rachunków z 40,00% do 85,71%. Liczba poprawnych wartości wzrosła z 3/12 do 9/12, przy zerze błędnych numerów i zamian w obu wersjach. Regresja 128/128 jest zgodna bajtowo. Santander nadal daje 0 B dla wykonanego przelewu, więc wynik sześciu pól na całej próbie, 68,85% wobec 54,55%, ma status diagnostyczny. [Pomiar, błędy, kod i powtórzenie oceny](RAPORT_RACHUNKI_A3.md)

**Następny krok eksperymentu.** Wdrożyć listę dokumentów do weryfikacji z przyczyną, stroną i podstawą dla wskazanego pola. W pierwszym odbiorze operator widzi i może poprawić wynik dla brakującego rachunku, a niepewny negatyw nie może otrzymać automatycznej akceptacji. Otwartą rezerwę rachunków wykorzystać do regresji, a ocenę błędnych automatycznych akceptacji i pokrycia wykonać na odrębnej próbie zgodnie z sekcją o czytelności skanu.

**Warunek gotowości CLI do wydania.** Odtworzyć i usunąć `SIGSEGV` na osobnych skanach rozwojowych. Odbiór wymaga zakończenia całego folderu przez CLI bez kontenera i przez Compose oraz bajtowej zgodności ich wyników. Rezerwa KARR v2 po pomiarze służy do regresji. W kolejce produktowej pozostają pierwszy zarzut na dalszych stronach i rozróżnianie pełnomocników od osób podpisujących.

Dokumentacja czytników: [pypdf](https://pypdf.readthedocs.io/en/stable/user/extract-text.html) · [pdfplumber](https://github.com/jsvine/pdfplumber) · [dane językowe Tesseract](https://tesseract-ocr.github.io/tessdoc/Data-Files-in-different-versions.html).

## Synchronizacja VPS

Push na main wywołuje GitHub Actions. Serwer przyjmuje dedykowany klucz wyłącznie do pobrania main, blokuje równoległe aktualizacje i wymaga czystego katalogu roboczego. Aktualizacja jest fast-forward. Stan można sprawdzić poleceniem `ssh hacknation 'cd ~/odwolania2json && git status --short --branch && git rev-parse HEAD'`. Po usunięciu przyczyny błędu można ponowić przebieg w Actions.
