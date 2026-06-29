import zipfile

from safeai.extractors import extract_documents


def test_extract_text_markdown_csv_json_and_docx_zip_xml(tmp_path):
    md = tmp_path / "a.md"
    md.write_text("# 标题\n张三 电话13812345678", encoding="utf-8")
    csv = tmp_path / "b.csv"
    csv.write_text("name,phone\n李四,13900001111\n", encoding="utf-8")
    js = tmp_path / "c.json"
    js.write_text('{"person": "王五", "email": "user@example.com"}', encoding="utf-8")
    docx = tmp_path / "d.docx"
    with zipfile.ZipFile(docx, "w") as archive:
        archive.writestr(
            "word/document.xml",
            "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
            "<w:body><w:p><w:r><w:t>赵六 合同HT-2026-009</w:t></w:r></w:p></w:body></w:document>",
        )

    docs = extract_documents([md, csv, js, docx], root=tmp_path)
    texts = {doc.path.name: doc.text for doc in docs if doc.status == "ok"}

    assert "张三" in texts["a.md"]
    assert "李四" in texts["b.csv"]
    assert "王五" in texts["c.json"]
    assert "赵六" in texts["d.docx"]


def test_extract_documents_skips_symlink_escape(tmp_path):
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("张三 13812345678", encoding="utf-8")
    inside = tmp_path / "inside.md"
    inside.write_text("李四 13900001111", encoding="utf-8")
    link = tmp_path / "escape.md"
    link.symlink_to(outside)

    docs = extract_documents([tmp_path], root=tmp_path)
    source_ids = {doc.source_id for doc in docs}

    assert "inside.md" in source_ids
    assert "escape.md" not in source_ids
