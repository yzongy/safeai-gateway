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


def test_extract_documents_allows_explicit_hidden_file(tmp_path):
    hidden_dir = tmp_path / ".safeai" / "demo_inputs"
    hidden_dir.mkdir(parents=True)
    hidden_file = hidden_dir / "explicit.md"
    hidden_file.write_text("张三 电话13812345678", encoding="utf-8")

    docs = extract_documents([hidden_file], root=tmp_path)

    assert len(docs) == 1
    assert docs[0].status == "ok"
    assert "张三" in docs[0].text


def test_extract_legacy_doc_with_local_textutil_converter(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    textutil = bin_dir / "textutil"
    textutil.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' '张三 旧版DOC 电话13812345678'\n",
        encoding="utf-8",
    )
    textutil.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    doc = tmp_path / "legacy.doc"
    doc.write_bytes(b"synthetic legacy doc fixture")

    docs = extract_documents([doc], root=tmp_path)

    assert len(docs) == 1
    assert docs[0].status == "ok"
    assert docs[0].media_type == "application/msword"
    assert "旧版DOC" in docs[0].text


def test_extract_legacy_doc_fails_closed_without_converter(tmp_path, monkeypatch):
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    doc = tmp_path / "legacy.doc"
    doc.write_bytes(b"synthetic legacy doc fixture")

    docs = extract_documents([doc], root=tmp_path)

    assert len(docs) == 1
    assert docs[0].status == "error"
    assert docs[0].error_code == "doc_dependency_missing"
    assert "synthetic legacy doc fixture" not in docs[0].error_message


def test_extract_legacy_doc_fails_closed_when_converter_fails(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    textutil = bin_dir / "textutil"
    textutil.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    textutil.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    doc = tmp_path / "legacy.doc"
    doc.write_bytes(b"synthetic legacy doc fixture")

    docs = extract_documents([doc], root=tmp_path)

    assert len(docs) == 1
    assert docs[0].status == "error"
    assert docs[0].error_code == "doc_extract_failed"
    assert "synthetic legacy doc fixture" not in docs[0].error_message
