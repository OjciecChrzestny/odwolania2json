"""Appeal roles and counsel must come from their own physical header."""
from dataclasses import replace
from unittest import TestCase

from odwolania2json.extract import extract
from odwolania2json.model import Document, load_classes, schema_errors

COVER = "Krajowa Izba Odwoławcza\n"
BODY = "\nODWOŁANIE\nWnoszę odwołanie.\nZarzut nr 1: zaniechanie odrzucenia oferty."
A = "Odwolujacy"
Z = "Zamawiajacy"


def simple_tsv(columns):
    rows = []
    for line, pair in enumerate(columns, 1):
        for left, text in zip((35, 620), pair):
            for index, word in enumerate(text.split(), 1):
                width = len(word) * 8
                rows.append(f"5\t1\t1\t1\t{line}\t{index}\t{left}\t{line * 28}\t{width}\t18\t91\t{word}")
                left += width + 8
    return "\n".join(rows)


class AppealPartiesTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()

    def appeal(self, *pages, tsv=None, ocr=True):
        quality = {"pages": [
            {"page": number, "source": "ocr" if ocr else "text"}
            for number in range(1, len(pages) + 1)
        ]}
        doc = replace(Document.from_pages(pages), scan_quality=quality, ocr_layout_tsv=tsv)
        value, diagnostic = extract(doc, self.classes)
        self.assertEqual(diagnostic["class"], "odwolanie")
        self.assertEqual(list(schema_errors(value, self.classes["odwolanie"]["schema"])), [])
        return value, diagnostic["fields"]

    def test_wrapped_roles_and_distinct_offices(self):
        data, fields = self.appeal(
            COVER + "Odwolujacy\nZorza\nRozwiązania sp. z o.o., ul. Niebieska 12\n"
            "reprezentowany\nprzez adw. Lena\nSarna\n"
            "Kancelaria Prawna Sarna i Partnerzy, ul. Słoneczna 12\n"
            "e-mail: lena@example.invalid\n"
            "Zamawiajacy\nGmina Wrzosy\nul. Gminna 40\n"
            "reprezentowany przez r. pr. Maria Lilia\nAdres: Kancelaria Gminna\n"
            "e-mail: gmina@example.invalid" + BODY,
        )
        appellant, = data[A]
        self.assertEqual(appellant["nazwa"], "Zorza Rozwiązania sp. z o.o.")
        self.assertEqual(appellant["przez-pelnomocnika"], 1)
        self.assertEqual(appellant["pelnomocnik"], {
            "imie_nazwisko": "Lena Sarna", "nazwa": "Kancelaria Prawna Sarna i Partnerzy",
            "mail": "lena@example.invalid",
        })
        self.assertEqual([row["nazwa"] for row in data[Z]], ["Gmina Wrzosy"])
        self.assertEqual(fields[f"{A}.0.pelnomocnik.mail"]["snippet"], "lena@example.invalid")

    def test_quoted_and_footer_contact_do_not_attach_to_appellant(self):
        data, _ = self.appeal(
            COVER + "Odwołujący: Orzech Systemy S.A.\n"
            "Pełnomocnik: radca prawny Tadeusz Bez\n"
            "„Kontakt z poprzedniej sprawy: fikcja@example.invalid”\n"
            "Do wiadomości: stopka@example.invalid\n"
            "Zamawiający: Gmina Maki\n"
            "Pełnomocnik: adw. Laura Jasna\nmail: nabywca@example.invalid" + BODY,
        )
        self.assertEqual(data[A][0]["pelnomocnik"]["imie_nazwisko"], "Tadeusz Bez")
        self.assertIsNone(data[A][0]["pelnomocnik"]["mail"])

    def test_geometry_separates_two_columns_of_one_page(self):
        columns = [
            ("Odwołujący:", "Zamawiający:"),
            ("Brzoza S.A.", "Gmina Paprocie"),
            ("reprezentowany przez adw. Iga Żuraw", "ul. Polna 5"),
            ("Kancelaria Żuraw i Partnerzy", "e-mail: urzad@example.invalid"),
            ("e-mail: iga@example.invalid", ""),
            ("ODWOŁANIE", ""),
        ]
        flat = "\n".join(" ".join(p for p in pair if p) for pair in columns[:-1])
        data, fields = self.appeal(COVER + flat + BODY, tsv=simple_tsv(columns))
        self.assertEqual(data[A][0]["nazwa"], "Brzoza S.A.")
        self.assertEqual(data[Z][0]["nazwa"], "Gmina Paprocie")
        self.assertEqual(data[A][0]["pelnomocnik"]["mail"], "iga@example.invalid")
        self.assertEqual(fields[f"{A}.0.pelnomocnik.mail"]["source"], "ocr")
        self.assertEqual(fields[f"{A}.0.pelnomocnik.mail"]["page"], 1)

    def test_later_physical_page_has_its_own_locations(self):
        data, fields = self.appeal(
            COVER + "Pismo przewodnie\nDokument na kolejnej stronie.",
            "Odwołujący:\nLas i Projekt S.A.\n"
            "reprezentowany przez r. pr. Wanda Klon\nE-mail: wanda@example.invalid\n"
            "Zamawiający:\nGmina Łąka" + BODY,
        )
        self.assertEqual(data[A][0]["pelnomocnik"]["mail"], "wanda@example.invalid")
        self.assertEqual(fields[f"{A}.0.pelnomocnik.mail"]["page"], 2)

    def test_multiple_buyers_retain_order_and_integer_flags(self):
        data, _ = self.appeal(
            COVER + "Odwołujący\nProjekt Trawa S.A.\n"
            "Zamawiający – lider: Gmina Kłos\nZamawiający – partner: Gmina Żyto" + BODY,
        )
        self.assertEqual([(row["nazwa"], row["prowadzacy_postepowanie"]) for row in data[Z]],
                         [("Gmina Kłos", 1), ("Gmina Żyto", 0)])
        self.assertIs(type(data[A][0]["przez-pelnomocnika"]), int)

    def test_buyer_representation_does_not_flow_upward(self):
        data, _ = self.appeal(
            COVER + "Odwołujący: Granat Usługi S.A.\n"
            "Zamawiający: Gmina Sady\nreprezentowany przez adw. Judyta Zając\n"
            "E-mail: kancelaria-gminna@example.invalid" + BODY,
        )
        self.assertEqual(data[A][0]["przez-pelnomocnika"], 0)
        self.assertTrue(all(value is None for value in data[A][0]["pelnomocnik"].values()))

    def test_labeled_mail_with_repeated_surname_has_a_single_supported_boundary(self):
        data, fields = self.appeal(
            COVER + "Odwołujący: Modrzew S.A.\n"
            "reprezentowany przez pełnomocnika:\nradca prawny Iga Żuraw\n"
            "Kancelaria Żuraw\nE-mail: i.zurawqzuraw-prawo.example.invalid\n"
            "Zamawiający: Gmina Niska" + BODY,
        )
        self.assertEqual(data[A][0]["pelnomocnik"]["mail"], "i.zuraw@zuraw-prawo.example.invalid")
        mail = fields[f"{A}.0.pelnomocnik.mail"]
        self.assertEqual((mail["source"], mail["page"], mail["precision"]), ("ocr", 1, "page"))
        self.assertNotIn("snippet", mail)

    def test_no_address_repaired_from_a_bare_copyright_or_different_surname(self):
        for broken in ("p.klonqnowak-praktyka.example.invalid", "p.klon-©qinna-kancelaria.example.invalid",
                       "z.klonqklon-prawo.example.invalid"):
            with self.subTest(broken=broken):
                data, _ = self.appeal(
                    COVER + "Odwołujący: Dąb z Zachodu S.A.\n"
                    "reprezentowany przez pełnomocnika:\nadw. Paweł Klon\n"
                    f"Kancelaria Klon\ne-mail: {broken}\nZamawiający: Gmina Sosny" + BODY,
                )
                self.assertIsNone(data[A][0]["pelnomocnik"]["mail"])

    def test_joint_buyers_use_the_order_of_the_two_identified_sections(self):
        data, _ = self.appeal(
            COVER + "Odwołujący: Klon i Partner Sp. z 0.0.\n"
            "Zamawiający: Zamawiający wspólnie udzielający zamówienia:\n"
            "1) Gmina Łąki\nul. Jasna 12\n"
            "— Zamawiający prowadzący postępowanie\n"
            "2) Miasto Zalesie\nul. Polna 15" + BODY,
        )
        self.assertEqual(data[A][0]["nazwa"], "Klon i Partner Sp. z o.o.")
        self.assertEqual([row["nazwa"] for row in data[Z]], ["Gmina Łąki", "Miasto Zalesie"])

    def test_consortium_leader_name_and_labeled_business_name(self):
        for header, expected in (
            ("Konsorcjum wykonawców:\n1) Topola Północ sp. k. (Lider Konsorcjum)\n"
             "NIP: 0000000001\n2) Opal S.A. (Partner Konsorcjum)", "Topola Północ sp. k."),
            ("Alicja Wiosna prowadząca działalność gospodarczą pod firmą\n"
             "Alicja Wiosna Biuro Oleander\nul. Polna 88", "Alicja Wiosna Biuro Oleander"),
        ):
            with self.subTest(expected=expected):
                data, _ = self.appeal(COVER + f"Odwołujący: {header}\nZamawiający: Gmina Promyk" + BODY)
                self.assertEqual([row["nazwa"] for row in data[A]], [expected])

    def test_copy_recipient_never_replaces_appellant_counsel(self):
        data, fields = self.appeal(
            COVER + "Zamawiający: Gmina Złota\nOdwołujący: Spółka Werbena S.A.\n"
            "Kopię otrzymuje inny wykonawca:\nreprezentowany przez adw. Emilia Mięta\n"
            "Biuro Wydmowe Sp. z o.o.\nE-mail: wydmy@example.invalid" + BODY,
        )
        self.assertEqual(data[A][0]["przez-pelnomocnika"], 0)
        self.assertTrue(all(value is None for value in data[A][0]["pelnomocnik"].values()))
        self.assertFalse(any(name.startswith(f"{A}.0.pelnomocnik.") for name in fields))

    def test_distribution_office_does_not_fill_separately_confirmed_counsel_office(self):
        own = (COVER + "Zamawiający: Gmina Zielna\nOdwołujący: Brzoza Północ S.A.\n"
               "zastępowana przez adw. Teresa Jaskółka\n")
        tail = "Rozdzielnik dokumentu:\nKopię otrzymuje:\nBiuro Mewa Sp. z o.o.\n"
        for real_office in ("", "Kancelaria Własna Jaskółka\n"):
            with self.subTest(own=bool(real_office)):
                data, fields = self.appeal(own + real_office + tail + BODY)
                counsel = data[A][0]["pelnomocnik"]
                self.assertEqual(counsel["imie_nazwisko"], "Teresa Jaskółka")
                self.assertEqual(counsel["nazwa"], "Kancelaria Własna Jaskółka" if real_office else None)
                self.assertEqual(fields[f"{A}.0.pelnomocnik.imie_nazwisko"]["page"], 1)
