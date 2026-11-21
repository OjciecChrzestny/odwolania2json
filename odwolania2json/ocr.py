"""Opcjonalny OCR uruchamiany lokalnie dla stron bez warstwy tekstowej."""
from contextlib import closing
from functools import partial


def prepare_ocr(data):
    try:
        from pypdfium2 import PdfDocument
        from tesserocr import PyTessBaseAPI
    except ImportError as exc:
        raise ValueError("OCR wymaga instalacji requirements-ocr.txt") from exc
    if not (data / "pol.traineddata").is_file():
        raise ValueError(f"Brak pol.traineddata w {data}")
    return partial(recognize, PdfDocument, PyTessBaseAPI, data)


def recognize(document_type, api_type, data, path, limit):
    with closing(document_type(path)) as pdf, api_type(path=str(data), lang="pol") as api:
        api.SetVariable("user_defined_dpi", "180")
        for index in range(limit):
            with closing(pdf[index]) as page:
                scale = min(2.5, 2200 / max(page.get_size()))
                best = ""
                for angle in (0, 90, 270, 180):
                    with closing(page.render(scale=scale, rotation=angle, grayscale=True)) as bitmap:
                        api.SetImageBytes(bytes(bitmap.buffer), bitmap.width, bitmap.height,
                                          bitmap.n_channels, bitmap.stride)
                        text = api.GetUTF8Text()
                        if len(text) > len(best):
                            best = text
                        if len(text.split()) >= 8 and api.MeanTextConf() >= 55:
                            break
                yield index, best
