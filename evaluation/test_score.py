"""Regression checks for the UZP reference hashes on Windows and Linux."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from score import checked_file


class ReferenceHashTest(unittest.TestCase):
    def test_reference_hashes_survive_checkout_line_endings(self):
        lf = b'{\n  "test": 1\n}\n'
        crlf = lf.replace(b"\n", b"\r\n")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for checkout, manifest in ((lf, crlf), (crlf, lf)):
                with self.subTest(checkout=checkout):
                    path = root / "reference.json"
                    digest = hashlib.sha256(manifest).hexdigest()
                    path.write_bytes(checkout)
                    self.assertEqual(checked_file(root, path.name, digest, reference=True), path)
                    path.write_bytes(checkout.replace(b"1", b"2"))
                    with self.assertRaises(ValueError):
                        checked_file(root, path.name, digest, reference=True)

    def test_pdf_hash_always_compares_original_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "input.pdf"
            path.write_bytes(b"%PDF-1.7\r\n")
            with self.assertRaises(ValueError):
                checked_file(root, path.name, hashlib.sha256(b"%PDF-1.7\n").hexdigest())
