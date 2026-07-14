"""Document parsing — generates real docx/xlsx files and parses them."""

import io

from etki.extraction.parsers import parse_document


def test_parse_plain_text_filters_short_lines():
    data = "rapora filtre eklensin\nSSO entegrasyonu yapılsın\nab\n".encode()
    _, items = parse_document("notlar.txt", data)
    assert "rapora filtre eklensin" in items
    assert "ab" not in items  # short/meaningless lines are filtered out


def test_parse_csv_rows():
    data = "id,talep\n1,rapora filtre eklensin\n2,kripto ödeme eklensin\n".encode()
    _, items = parse_document("crler.csv", data)
    assert any("rapora filtre" in it for it in items)
    assert any("kripto" in it for it in items)


def test_parse_docx_paragraphs():
    from docx import Document

    document = Document()
    document.add_paragraph("rapora filtre eklensin")
    document.add_paragraph("SSO entegrasyonu yapılsın")
    buffer = io.BytesIO()
    document.save(buffer)
    _, items = parse_document("talepler.docx", buffer.getvalue())
    assert len(items) == 2
    assert "SSO entegrasyonu yapılsın" in items


def test_parse_xlsx_rows():
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Talep"])
    sheet.append(["rapora filtre eklensin"])
    sheet.append(["kripto para ile ödeme eklensin"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    _, items = parse_document("crler.xlsx", buffer.getvalue())
    assert any("rapora filtre" in it for it in items)
    assert any("kripto" in it for it in items)
