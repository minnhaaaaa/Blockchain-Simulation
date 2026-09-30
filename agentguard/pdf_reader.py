"""Bounded PDF text extraction. Runs in a separate, time-limited process.

No cloud/OCR charges: extraction happens on the operator's node. Page and character
cursors make truncation explicit; a scan is never reported as successfully read.
"""
import io
import json
import sys

from pypdf import PdfReader


def extract(data, page=1, offset=0, max_chars=12000):
    if not data.startswith(b"%PDF-"):
        raise ValueError("This file is not a PDF. Use artifact.read_text for plain text.")
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ValueError("This PDF is encrypted. Upload an unlocked copy.")
    total = len(reader.pages)
    if not 1 <= page <= total or offset < 0 or not 1000 <= max_chars <= 16000:
        raise ValueError("Invalid PDF page, offset or character limit.")
    pages = []; remaining = max_chars; cursor = None
    while page <= total:
        source = reader.pages[page - 1]
        content = source.get_contents()
        if content and len(content.get_data()) > 8_000_000:
            raise ValueError(f"Page {page} exceeds the safe extraction size. Split or simplify this PDF.")
        text = source.extract_text() or ""
        if offset > len(text):
            raise ValueError("PDF offset exceeds the page text length.")
        chunk = text[offset:offset + remaining]
        pages.append({"page": page, "offset": offset, "text": chunk,
                      "characters_on_page": len(text), "status": "text_extracted" if text.strip() else "no_extractable_text"})
        remaining -= len(chunk)
        if offset + len(chunk) < len(text):
            cursor = {"page": page, "offset": offset + len(chunk)}; break
        page += 1; offset = 0
        # Also bound metadata for documents with many blank/scanned pages.
        if page <= total and (remaining <= 0 or len(pages) >= 20):
            cursor = {"page": page, "offset": 0}; break
    return {"total_pages": total, "pages": pages, "next_cursor": cursor,
            "notice": "Text layer only. Tables may lose layout. Pages with no extractable text need OCR; do not infer their contents. Follow next_cursor for the remaining document."}


def main():
    # Bound even decompression-heavy or malformed documents, not just their upload size.
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    except ImportError:
        pass
    try:
        result = extract(sys.stdin.buffer.read(), int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]))
        print(json.dumps({"value": result}, ensure_ascii=False))
    except Exception as error:
        message = str(error) if isinstance(error, ValueError) else "PDF could not be parsed safely. Upload a valid, text-searchable PDF."
        print(json.dumps({"error": message[:400]}))


if __name__ == "__main__":
    main()
