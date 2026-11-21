"""Page observations from the existing text and OCR passes, without source content."""

# The existing OCR reader requires at least this many tokens for its early
# orientation exit. Sparse OCR is still useful for extraction.
OCR_MIN_TOKENS = 8


def observation(page, status, reason, source=None, *, characters=0, tokens=0):
    return {"page": page, "status": status, "reason": reason, "source": source,
            "alphanumeric_chars": characters, "tokens": tokens}


def native_observation(page, text, usable, skipped):
    characters = sum(map(str.isalnum, text))
    replaced = "\ufffd" in text
    if not characters and not replaced:
        return observation(page, "unassessed", skipped)
    if replaced:
        status, reason = "partial", "native_replacement_character"
    elif usable:
        status, reason = "readable", "native_text"
    else:
        status, reason = "partial", "native_fragment"
    return observation(page, status, reason, "text", characters=characters, tokens=len(text.split()))


def ocr_observation(previous, text, usable):
    characters = sum(map(str.isalnum, text))
    tokens = len(text.split())
    if not characters and "\ufffd" not in text:
        if previous["status"] != "unassessed":
            return previous
        status, reason = "unreadable", "ocr_no_text"
    elif not usable or "\ufffd" in text:
        status, reason = "partial", "ocr_fragment"
    elif tokens < OCR_MIN_TOKENS:
        status, reason = "partial", "ocr_sparse_text"
    else:
        status, reason = "readable", "ocr_text"
    return observation(previous["page"], status, reason, "ocr", characters=characters, tokens=tokens)


def without_ocr_result(previous, reason):
    if previous["status"] != "unassessed":
        return previous
    return observation(previous["page"], "unassessed", reason)


def quality_report(pages, read_error=None):
    statuses = {page["status"] for page in pages or ()}
    if not statuses or statuses == {"unassessed"}:
        status = "unassessed"
    elif statuses == {"readable"}:
        status = "readable"
    elif statuses <= {"unassessed", "unreadable"}:
        status = "unreadable"
    else:
        status = "partial"
    return {
        "status": status,
        "reason": read_error or ("all_pages_readable" if status == "readable" else "pages_need_review"),
        "page_count": None if pages is None else len(pages),
        "pages": pages if pages is not None else [],
        "review_pages": [page["page"] for page in pages or () if page["status"] != "readable"],
    }
