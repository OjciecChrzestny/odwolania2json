# Panel operatora

Na przydzielonej VM panel działa pod `127.0.0.1:8765`. Na swoim komputerze zestaw tunel SSH do tej VM.

```sh
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8765:127.0.0.1:8765 LOGIN@HOST
```

Otwórz `http://127.0.0.1:8765`, wybierz **Wgraj własny PDF**, a następnie **Przetwórz PDF**. Polski OCR i odczyt brakującej kwoty używają tych samych reguł oraz tego samego limitu 1 EUR co [partia jurorska](../RUN.md). Każde wgranie tworzy osobny przebieg, maksymalny rozmiar jednego PDF-u wynosi 32 MiB.

W sekcji **Dowód i decyzja** wybierz pole i kliknij **Otwórz stronę dowodu**. Porównaj stronę i odczytaną wartość. Możesz zapisać akceptację lub korektę. Decyzja zostaje w dzienniku operatora, a surowy JSON zawiera wynik ekstrakcji. W [syntetycznym skanie](../delivery/compose/skan-syntetyczny.pdf) kwota 123,45 zł pochodzi ze strony 1.

Na własnej maszynie po wczytaniu obrazu jednorazowe polecenie `./run-jury.sh panel` uruchamia usługę. Jej dane trafiają do `panel-demo/`, oddzielnie od katalogów wejściowych jury.
