# Eksperyment A/B/C

- **A** — reguły z `19f702fc58e685f85f2fae14557d14f2c5453cfd`. Zachowany pomiar jest opisany w [RAPORT_A.md](../../RAPORT_A.md).
- **B** — Qwen3.5-9B w OVHcloud AI Endpoints.
- **C** — Mistral Small 3.2 24B Instruct 2506 w Scaleway Generative APIs.

B i C bazują na tym samym czytniku, klasyfikatorze i selektorze A. [Patch](selector-a.patch) udostępnia wyłącznie w trybie eksperymentu dokładny tekst decyzji w pamięci. Dla zarzutu numerowanego jest to fragment nagłówka ograniczony regułą A. Gdy A rozpoznaje czynność na podstawie wcześniejszego opisu, adapter otrzymuje ten opis. Rozpoznany, niepusty fragment kwalifikuje się do B/C również przy awaryjnym ID A. Bez wiarygodnego fragmentu zostaje wynik A. Numer strony dopasowania, początek i koniec stron fragmentu, offset, reguła i SHA-256 dokładnego UTF-8 trafiają do diagnostyki poza `output/`. Zwykłe `python -m odwolania2json` działa jak A także po zastosowaniu patcha.

Po poprawnej odpowiedzi eksperyment podmienia tylko `OdwolanieKIO.czynnosc_powod_id` i `OdwolanieKIO.czynnosc_opis`. Opis pochodzi z konfiguracji A zweryfikowanej z [publicznym słownikiem UZP z rewizji de135d2](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/de135d20811caf630f3e94dc655ba5eebd9a6710/oczekiwane-json/czynnosc_powod_id_dict.md). Lokalna kopia ma usuniętą końcową spację w wierszu ID 11. Data czynności i pozostałe pola zachowują wartości A. Każda nieudana próba zachowuje bajty A, zapisuje kod przyczyny i pozwala kontynuować partię.

Dowód rozszerzonej kwalifikacji i opis pól diagnostycznych zawiera [raport regresji](RAPORT_FRAGMENT_BC.md).

## Odbiór offline na Linuksie

W czystej kopii gałęzi z Pythonem 3.13, po instalacji `python -m pip install -r requirements.txt`:

```sh
LANDLOCK=1 PYTHON=python sh experiments/abc/test-offline.sh
```

Odbiór tworzy tymczasowy klon, stosuje w nim patch oraz uruchamia testy eksperymentu i bazowe regresje A. `LANDLOCK=1` wymaga kompilatora C i Linuksa z Landlock ABI 4. W tym trybie odbiór sprawdza odmowę lokalnego połączenia TCP i uruchamia testy z zablokowanym TCP. Na systemie bez Landlocka polecenie działa bez `LANDLOCK=1`, z blokadą gniazd Pythona w testach adapterów. Testy korzystają z fikcyjnej konfiguracji i lokalnych atrap transportu oraz odpowiedzi.

W rzeczywistym czytniku i selektorze A sprawdzono dwie strony, ograniczenie nagłówka pierwszego zarzutu, następny zarzut z odmiennym ID, pierwszy punkt listy, wcześniejszy opis czynności oraz przypadek bez wiarygodnego fragmentu. Podstawiono też pojedynczy wynik OCR na dokument i wariant, aby potwierdzić jedno wywołanie OCR i zachowanie numeru strony.

Próba techniczna porównania objęła 32 wygenerowane PDF-y. B i C miały 10/10 identycznych żądań po usunięciu pola `model`, po jednym powrocie do A i po 1080/72 tokeny wejścia/wyjścia **podane przez atrapy**. Każdy wariant odziedziczył jeden celowo odrzucony przelew, `valid_run=false` i 0/2 fałszywych rozpoznań negatywów. Wartości poniżej sprawdzają raport i miernik na syntetykach. Pomiar jakości, kosztu i czasu odpowiedzi dostawców wymaga osobnej próby z API.

| Wariant | TP / FP / FN | Mikro-F1 | Zmiana względem A | Trafienia ID |
| --- | ---: | ---: | ---: | ---: |
| A | 172 / 2 / 8 | 0,971751 | — | 9/10 |
| B | 174 / 0 / 6 | 0,983051 | +1,130 pkt proc. | 10/10 |
| C | 172 / 2 / 8 | 0,971751 | 0 pkt proc. | 9/10 |

## Przyszłe porównanie zapisanych A/B/C

Polecenie porównania działa lokalnie na istniejących przebiegach. Test techniczny uruchamia je na syntetycznym manifeście i sprawdza także odrzucenie niedozwolonej zmiany daty.

```sh
python -m experiments.abc.compare --dataset "$UZP_DATA" --manifest "$MANIFEST" \
  --a "$A" --b "$BC_RUN/B" --c "$BC_RUN/C" > "$BC_RUN/comparison.json"
```

`A` wskazuje zachowany prywatny przebieg z `input/`, `output/`, `diagnostics/extraction.json` i `time.txt`. `UZP_DATA` to lokalny checkout UZP na `de135d20811caf630f3e94dc655ba5eebd9a6710`, a `MANIFEST` wskazuje manifest tego samego zapisanego przebiegu. Dla przyszłego porównania walidacyjnego będzie to [zamrożony manifest 32 dokumentów](../../evaluation/validation-10.json). Porównanie kontroluje hashe neutralnych wejść, hashe odtworzonego A, klasy, strony OCR, niezmienność pozostałych pól oraz pary skrótów wspólnych żądań. Używa istniejącego `evaluation/score.py` i walidatora kontraktu. Oblicza TP/FP/FN, mikro-F1, zmianę w pkt proc., wyniki per klasa, różnice pól per dokument, trafienia ID, fałszywe rozpoznania, powroty do A i telemetrykę. Błąd `valid_run=false` pozostaje widoczny w raporcie. W zapisanym A jest czas partii, a czasy pojedynczych dokumentów A nie były rejestrowane. Czas dokumentu B/C obejmuje hash, odczyt, ekstrakcję i ewentualny transport. Czas partii obejmuje również zapis przez CLI A.

Po osobnej zgodzie na pomiar z API i na przekazanie fragmentów należy zastosować patch w odrębnej kopii kodu, użyć kopii neutralnych PDF-ów z zapisanego A i zachować te same ustawienia lokalnego OCR. `BC_RUN` ma być nowym katalogiem przebiegu, a `OCR_DATA` katalogiem z tą samą przypiętą wersją `pol.traineddata`. Przygotować zależności OCR zgodnie z [README A](../../README.md#opcjonalny-ocr). Warianty generują dwa osobne drzewa.

```sh
git apply --check experiments/abc/selector-a.patch
git apply experiments/abc/selector-a.patch
mkdir "$BC_RUN"
cp -a "$A/input" "$BC_RUN/input"
python -m experiments.abc.run --variant B --input "$BC_RUN/input" --run "$BC_RUN/B" --ocr-data "$OCR_DATA" --live
python -m experiments.abc.run --variant C --input "$BC_RUN/input" --run "$BC_RUN/C" --ocr-data "$OCR_DATA" --live
```

W kosztorysie live używana jest stawka katalogowa dla wykazanych tokenów. Raport podaje liczbę prób bez informacji o użyciu, a koszt rzeczywisty pochodzi z rozliczenia operatora. Próba z atrapami zwraca koszt `null`. Raport zapisuje przyczyny awarii jako kody, bez treści żądań, odpowiedzi, kluczy i komunikatów od dostawców.

## Dostawcy i warunki, sprawdzone 21.11.2026

| Wariant | Model API i endpoint | Operator, serwery w UE/EOG | EUR za 1 mln tokenów wej./wyj. | Licencja modelu |
| --- | --- | --- | ---: | --- |
| B | `Qwen3.5-9B`, `https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions` | OVH SAS dla usługi europejskiej, Gravelines we Francji według tabeli regionów AI Endpoints | 0,10 / 0,15 | Apache 2.0 |
| C | `mistral-small-3.2-24b-instruct-2506`, `https://api.scaleway.ai/v1/chat/completions` | Scaleway SAS, serverless w Paryżu we Francji, centrum obsługuje OPCORE | 0,15 / 0,35 | Apache 2.0 |

OVHcloud podaje 9,7 mld parametrów i deklaruje brak przechowywania treści, z zachowaniem informacji potrzebnych do rozliczeń. AI Endpoints podlega warunkom Public Cloud, załącznik 10. Przed użyciem należy potwierdzić podmiot i region dla konkretnego konta i usługi. [Katalog Qwen](https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/qwen-3-5-9b/) · [Cennik w EUR](https://www.ovhcloud.com/fr/public-cloud/prices/) · [Regiony](https://www.ovhcloud.com/fr/public-cloud/regions-availability/) · [Warunki](https://www.ovhcloud.com/fr/terms-and-conditions/contracts/) · [Informacje o usłudze](https://www.ovhcloud.com/fr/public-cloud/ai-endpoints/) · [Podmioty UE i USA](https://corporate.ovhcloud.com/sites/default/files/2024-12/dpef_en_2024.pdf) · [Licencja Qwen](https://huggingface.co/Qwen/Qwen3.5-9B/blob/main/LICENSE)

Scaleway deklaruje brak zbierania, czytania lub ponownego użycia treści wejść i odpowiedzi. Metadane operacyjne podlegają polityce usługi. [Modele i identyfikatory](https://www.scaleway.com/en/docs/generative-apis/reference-content/supported-models/) · [Cennik](https://www.scaleway.com/en/generative-apis/) · [Paryż i OPCORE](https://www.scaleway.com/en/docs/generative-apis/faq/) · [Warunki usługi](https://www-uploads.scaleway.com/Conditions_Particulieres_Services_IA_61a1a5f301.pdf) · [Polityka prywatności](https://www.scaleway.com/en/docs/generative-apis/reference-content/data-privacy/) · [Licencja Mistral](https://huggingface.co/mistralai/Mistral-Small-3.2-24B-Instruct-2506/blob/main/LICENSE)

Wspólne ustawienia to `temperature=0`, `top_p=1`, `max_tokens=512`, `stream=false` i `response_format=json_schema` z polem całkowitym i enumeracją 1–12. Adapter wykonuje najwyżej jedną próbę na dokument. Limit czasu operacji HTTPS wynosi 30 s. Qwen może zużywać limit wyjścia na rozumowanie zgodnie z ustawieniami operatora. Odpowiedź zatrzymana przez limit powoduje powrót do A. Dokumentacja obu usług opisuje wyjście strukturalne. Obsługa parametrów, limit, dostęp do modeli i faktyczne opóźnienie wymagają potwierdzenia w przyszłej próbie. [OVHcloud Structured Output](https://docs.ovhcloud.com/en/guides/public-cloud/ai-machine-learning/ai-endpoints-structured-output) · [Scaleway Structured Outputs](https://www.scaleway.com/en/docs/generative-apis/how-to/use-structured-outputs/)

Dla wybranego modelu przygotować osobny projekt z aktywnym rozliczaniem, sprawdzić limity żądań i tokenów oraz prywatnie potwierdzić dostęp z konta jurora na jego scenariuszu. Budżet i limit powinny objąć rozgrzewkę, pełną partię i powtórzenie. W Scaleway użyć aplikacji IAM z `GenerativeApisModelAccess` i zweryfikować limity organizacji po aktywacji płatności oraz ewentualnym KYC. W OVHcloud użyć klucza projektu AI Endpoints z wygaśnięciem po ocenie i zweryfikować limit projektu. Przekazać właściwy sekret przez bezpieczny, jednorazowy kanał poza Git. Juror wstrzykuje go do środowiska jako `OVH_AI_ENDPOINTS_ACCESS_TOKEN` albo `SCALEWAY_SECRET_KEY`. Po ocenie unieważnić klucz i pozostawić dostępną lokalną ścieżkę A. [OVHcloud dostęp](https://docs.ovhcloud.com/en/guides/public-cloud/ai-machine-learning/ai-endpoints-getting-started) · [Scaleway IAM](https://www.scaleway.com/en/docs/generative-apis/api-cli/using-generative-apis/) · [Scaleway limity](https://www.scaleway.com/en/docs/generative-apis/reference-content/rate-limits/)

**Następny krok dla koordynatora** — przejrzeć patch i po osobnym upoważnieniu potwierdzić dostęp oraz obsługę wspólnego kontraktu na dozwolonej próbce przed uruchomieniem pomiaru. Odbiór techniczny nie otwierał danych, etykiet ani wyników walidacji i testu końcowego.
