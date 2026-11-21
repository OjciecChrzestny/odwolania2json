"""Regression for OCR logging when the process cannot reopen /dev/null."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from odwolania2json.ocr import prepare_ocr


class OCRStartupTest(unittest.TestCase):
    def test_page_and_line_apis_use_the_already_open_stderr(self):
        renderer = SimpleNamespace(PdfDocument=Mock())
        api = Mock()
        modules = {"pypdfium2": renderer, "tesserocr": SimpleNamespace(PyTessBaseAPI=api)}

        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules, modules):
            data = Path(directory)
            (data / "pol.traineddata").touch()
            ocr = prepare_ocr(data)
            ocr.api_type(path=directory, lang="pol")
            ocr.api_type(path=directory, lang="pol", psm=7)

        self.assertEqual(api.call_args_list, [
            call(path=directory, lang="pol", variables={"debug_file": ""}),
            call(path=directory, lang="pol", psm=7, variables={"debug_file": ""}),
        ])
