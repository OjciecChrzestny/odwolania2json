# Plan Odwołania2JSON

Punktem odniesienia jest [specyfikacja i dane UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/f60ca6f9fcd1a624ba145dbc6c658bfb076ece79). Zbiór zawiera 60 katalogów przykładowych spraw oraz dokumenty negatywne. README i PDF zadania podają różne wagi finału. Oba przypisują 100% preselekcji jakości ekstrakcji mierzonej F1. Do potwierdzenia u mentora pozostają obowiązująca rubryka finału, reguły porównywania pól i dokładna reprezentacja pustego wyniku.

## Proponowany podział

- Osoba 1 odpowiada za CLI zgodne z kontraktem UZP, rekursywne przejście input, tekst z PDF, klasyfikację i ekstrakcję do schematów partnera. Wynik w output zachowuje względną ścieżkę i nazwę PDF ze zmienionym rozszerzeniem.
- Osoba 2 przygotowuje podział pełnymi sprawami, mapowanie PDF do wzorcowych JSON-ów i ocenę per pole oraz per typ dokumentu. Przykład pułapki: potwierdzenie_przelewu.pdf ma etykietę przelew.json. Identyczne dokumenty negatywne trzeba rozdzielić tak, aby nie zawyżały wyniku testu.
- Wspólny kontrakt to pliki wejścia i wyjścia. Osoba 2 może sprawdzać miernik na wzorcowym wyniku oraz celowo zmienionym polu przed ukończeniem ekstraktora.

## Decyzje do pierwszej próby

Python 3.13+, CLI, requirements.txt, otwarte komponenty, budżet sprzętowy i7 / 16 GB RAM / CPU. Pierwszą wersję oprzeć o tekst z PDF i reguły. Rozdzielić schemat dokumentu od kodu odczytu. Klasyfikować po treści. Brak rozpoznanej klasy ma skutkować pustym wynikiem według kontraktu UZP. Ustalić reprezentatywny zbiór walidacyjny przed strojeniem i zachować osobny zbiór końcowy.

OCR dodać po zmierzeniu braków warstwy tekstowej. Decyzję o modelu podjąć na podstawie błędów, czasu i przyrostu F1 na walidacji. Wariant przez API wymaga sprawdzenia warunków UZP dotyczących otwartości modelu, dostawcy i serwerów w UE/EOG oraz przekazania dostępu jury. Własny miernik oznaczyć jako przybliżenie, dopóki organizator nie potwierdzi szczegółów.

## Następny krok

Przepuścić przez CLI jedną sprawę zawierającą trzy klasy oraz dodatkowy dokument negatywny. Sprawdzić ścieżki wyjść i porównać wartości z etykietami. Następnie zapisać bazowy wynik na wydzielonej walidacji, wynik per klasa, najczęstsze błędy i czas przebiegu.

## Synchronizacja VPS

Push na main wywołuje GitHub Actions. Serwer przyjmuje dedykowany klucz wyłącznie do pobrania main, blokuje równoległe aktualizacje i wymaga czystego katalogu roboczego. Aktualizacja jest fast-forward. Stan można sprawdzić poleceniem `ssh hacknation 'cd ~/odwolania2json && git status --short --branch && git rev-parse HEAD'`. Po usunięciu przyczyny błędu można ponowić przebieg w Actions.
