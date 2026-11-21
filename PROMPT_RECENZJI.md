# Prompt do niezależnej recenzji planu Odwołania2JSON

Jesteś recenzentem technicznym projektu na 24-godzinny hackathon UZP. Oceń, czy plan pozwoli dostarczyć lokalne CLI do ekstrakcji danych z PDF i maksymalizować F1 na nieznanych sprawach. Odpowiedz po polsku. Zwróć jeden plan bez podziału na osoby.

## Materiał do oceny

Przeczytaj PLAN.md, evaluation/score.py i evaluation/validation-10.json w prywatnym repozytorium [Odwołania2JSON](https://github.com/OjciecChrzestny/odwolania2json). Jeśli pracujesz z załącznikami, użyj tych trzech plików. Zestaw je z [przypiętą specyfikacją, słownikiem i schematami UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/de135d20811caf630f3e94dc655ba5eebd9a6710) oraz [oficjalnym PDF-em](https://mudnibfuppwadjkynscc.supabase.co/storage/v1/object/public/task-files/057d36b5-cb92-4062-9393-983cb8a96088/files/aeabc57d-7420-4069-946e-2c4de71d87ed.pdf). Wskaż ewentualne zmiany w aktualnym README organizatora względem wersji przypiętej. Oznacz źródła, do których faktycznie miałeś dostęp.

## Pytania recenzenckie

1. Czy juror z Pythonem 3.13+, procesorem i7 i 16 GB RAM może na podstawie planu przejść od folderu PDF do poprawnego drzewa wyników? Sprawdź wymagania dla trzech typów dokumentów, negatywów i pustych wyników. Odróżnij wymagania od założeń i wypisz sprzeczności między źródłami.
2. Prześledź działanie miernika na zamianie dwóch rachunków, niewłaściwej kolejności listy, null, brakującym pliku i błędnie rozpoznanym negatywie. Oceń, kiedy lokalne mikro-F1 może zawyżyć albo zaniżyć wynik jury. Oddziel ukończone próby kontrolne od niezmierzonej skuteczności ekstraktora.
3. Oceń dobór 10 spraw, duplikaty PDF-ów i szablonów, separację etykiet od ekstraktora oraz odłożenie końcowego zbioru przed strojeniem. Czy na dwóch negatywach i dziesięciu odwołaniach da się uzasadnić proponowaną decyzję modelową?
4. Oceń porównanie A (reguły), B (reguły + Qwen3.5-9B przez OVHcloud) i C (reguły + Mistral Small 3.2 24B przez Scaleway). Zachowaj wybrane modele dla pierwszej próby. Sprawdź równoważność wejść, dobór pierwszego zarzutu, automatyczne wyprowadzenie opisu z ID, fallback, koszty, czas i warunki UZP dla API. Wskaż, co ten eksperyment rzeczywiście mierzy.
5. Ustal, czy kolejność prac mieści się w 24 godzinach. Wskaż minimalny przebieg, realistyczny budżet czasu i co odłożyć w razie opóźnienia. Dla każdej proponowanej zmiany określ obserwowalny warunek ukończenia.

## Wynik

Zacznij od decyzji: można wdrażać / można wdrażać po wskazanych poprawkach / istotny brak. Następnie podaj maksymalnie pięć ustaleń w kolejności wpływu na wynik, z odniesieniem do konkretnej sekcji, funkcji lub źródła i przykładem skutku. Zaproponuj minimalny diff do PLAN.md lub gotowe brzmienie zmienionych sekcji. Jeżeli plan jest wystarczający, uzasadnij pozostawienie go bez zmian. Zakończ jednym następnym krokiem i pytaniami do mentora, których odpowiedzi mogą zmienić implementację. Zakres tej recenzji to ocena i propozycja poprawek. Pracuj bez kluczy API, wywołań modeli na dokumentach i publikowania zmian.
