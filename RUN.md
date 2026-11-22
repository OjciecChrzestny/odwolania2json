# Uruchomienie oceny na VM

Umieść PDF-y w `/opt/solution/input/`. W powłoce administratora, w katalogu `/opt/solution`, wykonaj jedno polecenie.

```sh
./run-jury.sh
```

Wyniki znajdziesz w `output/`, w tych samych podkatalogach co pliki wejściowe. Dokument obcy daje plik JSON o rozmiarze 0 B. Diagnostyka stron, pól i błędów odczytu jest w `diagnostics/last-run.json`. Kod wyjścia 0 oznacza ukończoną partię, 1 oznacza co najmniej jeden błąd odczytu, a 2 błąd konfiguracji lub zapisu.

## Automatyczny OCR i budżet API

Program odczytuje warstwę tekstową wszystkich stron. W razie potrzeby kieruje do polskiego OCR do **6 różnych stron każdego PDF-u**. Każdy dokument ma osobny limit, także w dużej partii.

Jeżeli rozpoznanemu przelewowi ze skanem na pierwszej stronie brakuje kwoty, aplikacja szuka wycinka z cyframi. Gdy znajdzie odpowiedni wiersz, może odczytać kwotę przez **Scaleway Generative APIs**, modelem `mistral-small-3.2-24b-instruct-2506`. Do usługi trafiają obraz wycinków liczbowych i etykiety z zamkniętego słownika. W razie braku klucza, błędu usługi lub wyczerpania limitu aplikacja oddaje lokalny wynik.

Klucz dla jury znajduje się w `/opt/solution/.env` jako `SCALEWAY_SECRET_KEY`, z uprawnieniami `0600`. Skrypt montuje go tylko do odczytu. Limit wynosi **1 EUR łącznie dla aplikacji na VM**. CLI i panel dzielą 20 rezerwacji po 0,05 EUR. Rezerwacja poprzedza wysłanie żądania i obejmuje także błędy transportu. Powtórzenie tego samego PDF-u wykorzystuje wcześniejszy wynik lub informację o próbie. Ewidencja jest w `.llm-jury/usage.sqlite3` i musi pozostać na miejscu między uruchomieniami. Panel i CLI wybierają tryb automatycznie.

## Przygotowanie obrazu przed oceną

Na przydzielonej VM obraz `odwolania2json-jury:auto-20261122` jest już zainstalowany. Na własnej maszynie pobierz obraz z [wydania](https://github.com/OjciecChrzestny/odwolania2json/releases), wczytaj go przez `docker image load -i odwolania2json-auto-obraz.tar.gz` i utwórz katalogi `input/` i `output/`. Źródła i pliki uruchomieniowe powinny pochodzić z tego samego wydania. Z czystego repozytorium obraz zbudujesz poniższym poleceniem.

```sh
docker build --target jury --label "org.opencontainers.image.revision=$(git rev-parse HEAD)" -t odwolania2json-jury:auto-20261122 .
```

Usługa panelu na VM uruchamia się po restarcie. [Panel operatora](docs/operator.md)
