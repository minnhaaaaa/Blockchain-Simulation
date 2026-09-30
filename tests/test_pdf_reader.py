import io
import json

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from agentguard.pdf_reader import extract
from agentguard.tools import ToolError, _read_pdf, ToolContext
from tests.test_agent_provider import app, configured, call, create  # noqa: F401


def pdf_bytes(texts, password=None):
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject(); stream.set_data(f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    if password: writer.encrypt(password)
    output = io.BytesIO(); writer.write(output); return output.getvalue()


def test_all_pages_and_continuations_are_real():
    source = pdf_bytes(["A" * 2200, "Second page", "Third page"])
    result = extract(source, max_chars=1000)
    assert result["total_pages"] == 3
    assert result["next_cursor"] == {"page": 1, "offset": 1000}
    content = ""; count = 0
    while True:
        content += "".join(p["text"] for p in result["pages"]); count += 1
        if not result["next_cursor"]: break
        result = extract(source, **result["next_cursor"], max_chars=1000)
    assert "A" * 2200 in content and "Second page" in content and "Third page" in content
    assert count == 3


def test_blank_scan_encryption_and_bad_cursor():
    source = pdf_bytes([""])
    assert extract(source)["pages"][0]["status"] == "no_extractable_text"
    with pytest.raises(ValueError, match="encrypted"): extract(pdf_bytes(["private"], "password"))
    with pytest.raises(ValueError, match="Invalid PDF page"): extract(source, page=2)
    with pytest.raises(ValueError, match="not a PDF"): extract(b"not a PDF")
    with pytest.raises(ValueError, match="offset"): extract(source, offset=999)


def test_pdf_agent_uses_uploaded_pages_and_signed_receipt(app, monkeypatch):
    fixture, provider = app
    data = pdf_bytes(["Read from the uploaded PDF", "Another actual page"])
    uploaded = fixture.client.post("/api/artifacts", data={"file": (io.BytesIO(data), "document.pdf")}).get_json()
    job_id = create(app, [uploaded["artifact_id"]]); calls = []
    def chat(messages, tools):
        calls.append(messages)
        if len(calls) == 1:
            assert any(t["function"]["name"] == "pdf__read" for t in tools)
            return call("pdf__read", {"artifact_id": uploaded["artifact_id"]})
        value = json.loads(messages[-1]["content"])["value"]
        assert value["total_pages"] == 2 and value["next_cursor"] is None
        assert "Another actual page" in value["pages"][1]["text"]
        return {"content": value["pages"][0]["text"]}
    monkeypatch.setattr(provider, "chat", chat)
    response = fixture.client.post(f"/api/jobs/{job_id}/run")
    assert response.status_code == 202, response.get_json()
    assert response.get_json()["state"] == "completed"
    detail = fixture.client.get(f"/api/jobs/{job_id}").get_json()
    receipt = next(e for e in detail["events"] if e["event_type"] == "action.completed")
    assert receipt["payload"]["status"] == "success"
    with pytest.raises(ToolError, match="declared"):
        _read_pdf(ToolContext(fixture.room, job_id, fixture.runtime.data_root, fixture.artifacts), {"artifact_id": uploaded["artifact_id"]}, [])
