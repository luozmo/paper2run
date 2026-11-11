from docx import Document
from app.models import PaperReport, PaperMetadata
from app.reporting import PaperReportRenderer

def test_minimal_report_exports_both_readable_formats(tmp_path):
    paths = PaperReportRenderer().render(PaperReport(paper=PaperMetadata(title="中文论文", authors=["张三"])), tmp_path / "new")
    assert [p.name for p in paths] == ["report.md", "report.docx"]
    md = paths[0].read_text(encoding="utf-8")
    word = "\n".join(p.text for p in Document(paths[1]).paragraphs)
    for text in ["中文论文", "张三", "概览", "论文基本信息", "代码仓库及官方状态", "依赖与环境", "运行入口与命令", "论文实验条件", "参数对照", "缺失项与警告", "证据", "未提供仓库检查结果", "未提供参数对照结果"]:
        assert text in md and text in word
    assert round(Document(paths[1]).sections[0].page_width.mm) == 210

import pytest
from pathlib import Path
from app.reporting import ReportExportError

@pytest.mark.parametrize("name", ["report.md", "report.docx"])
def test_existing_report_is_preserved(tmp_path, name):
    (tmp_path / name).write_bytes(b"original")
    with pytest.raises(ReportExportError):
        PaperReportRenderer().render(PaperReport(paper=PaperMetadata(title="Test")), tmp_path)
    assert list(tmp_path.iterdir()) == [tmp_path / name]
    assert (tmp_path / name).read_bytes() == b"original"


def test_failed_word_write_cleans_only_new_reports(tmp_path, monkeypatch):
    original_open = Path.open
    (tmp_path / "keep.txt").write_text("keep")
    def controlled_open(path, *args, **kwargs):
        if path.name == "report.docx":
            raise PermissionError("controlled filesystem failure")
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", controlled_open)
    with pytest.raises(ReportExportError, match="controlled filesystem failure"):
        PaperReportRenderer().render(PaperReport(paper=PaperMetadata(title="Test")), tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["keep.txt"]


def test_non_directory_output_fails_without_changes(tmp_path):
    target = tmp_path / "file"
    target.write_bytes(b"original")
    with pytest.raises(ReportExportError):
        PaperReportRenderer().render(PaperReport(paper=PaperMetadata(title="Test")), target)
    assert target.read_bytes() == b"original"

from app.models import (RepoCandidate, RepoInspectionResult, DependencyInfo, Evidence,
    RepositoryEntryPoint, RepoManifest, ExperimentParameter, ExperimentComparison,
    ExperimentComparisonItem, MissingItem)


def test_complete_analysis_preserves_conflicts_and_context_in_both_documents(tmp_path):
    source = Evidence(kind="repo_file", locator="requirements.txt")
    report = PaperReport(
        paper=PaperMetadata(title="完整论文", authors=["李四"], year=2025, venue="会议"),
        code_availability="not_found", selected_repo_url="https://example.org/selected",
        repo_candidates=[RepoCandidate(url="https://example.org/candidate", owner="team", name="research", official_status="likely_official", notes="作者线索")],
        dependencies=[DependencyInfo(name="torch", version="1.0", scope="training", source=source)],
        repo_inspection=RepoInspectionResult(repo_url="https://example.org/inspected", readme_path="README.md", structure_summary="src 包含训练实现", manifests=[RepoManifest(path="requirements.txt", kind="requirements", evidence=source)], dependencies=[DependencyInfo(name="torch", version="2.0", source=source)], entry_points=[RepositoryEntryPoint(path="src/train.py", command="python src/train.py\n--epochs 20")], run_commands=["python evaluate.py"], warnings=["仓库检查警告"]),
        experiment_parameters=[ExperimentParameter(name=c, value="值-" + c, category=c) for c in ["dataset", "model", "framework", "hardware", "training", "evaluation"]],
        experiment_comparison=ExperimentComparison(items=[ExperimentComparisonItem(name=s, paper_value="论文-" + s, repo_value="仓库-" + s, status=s, notes="说明-" + s) for s in ["match", "mismatch", "missing_in_repository", "missing_in_paper", "unknown"]], missing_items=[MissingItem(field="seed", description="随机种子待补", reason="上游未找到")], warnings=["对照警告"]),
        missing_items=[MissingItem(field="license", description="许可待补")], warnings=["报告警告"])
    paths = PaperReportRenderer().render(report, tmp_path)
    doc = Document(paths[1])
    word = "\n".join([p.text for p in doc.paragraphs] + [c.text for t in doc.tables for r in t.rows for c in r.cells])
    md = paths[0].read_text(encoding="utf-8")
    for value in ["未找到", "https://example.org/selected", "https://example.org/candidate", "可能官方", "作者线索", "汇总依赖", "仓库检查依赖", "1.0", "2.0", "训练", "src 包含训练实现", "requirements.txt", "README.md", "src/train.py", "python evaluate.py", "一致", "不一致", "仓库缺失", "论文缺失", "无法确认", "说明-mismatch", "随机种子待补", "上游未找到", "许可待补", "仓库检查警告", "对照警告", "报告警告", "值-dataset", "值-model", "值-framework", "值-hardware", "值-training", "值-evaluation"]:
        assert value in md and value in word, value
    assert doc.tables
    assert "python src/train.py\n--epochs 20" in word


def test_present_but_empty_modules_are_not_negative_findings(tmp_path):
    report = PaperReport(paper=PaperMetadata(title="部分数据"), repo_inspection=RepoInspectionResult(repo_url="https://example.org/repo"), experiment_comparison=ExperimentComparison())
    paths = PaperReportRenderer().render(report, tmp_path)
    md = paths[0].read_text(encoding="utf-8")
    doc = Document(paths[1])
    word = "\n".join(p.text for p in doc.paragraphs)
    for text in ["未提供仓库检查依赖信息", "未提供参数对照条目", "未提供运行入口与命令信息"]:
        assert text in md and text in word
    assert doc.styles["Normal"].font.size.pt == 11

def test_evidence_reused_and_traceable_in_both_documents(tmp_path):
    source = Evidence(kind="paper", locator="paper.pdf", page=3, quote="Original quotation", url="https://example.org/paper")
    paths = PaperReportRenderer().render(PaperReport(paper=PaperMetadata(title="Trace", evidence=[source]), experiment_parameters=[ExperimentParameter(name="batch", value="32", evidence=[source])]), tmp_path)
    doc = Document(paths[1])
    for output in [paths[0].read_text(encoding="utf-8"), "\n".join([p.text for p in doc.paragraphs] + [c.text for t in doc.tables for r in t.rows for c in r.cells])]:
        assert output.replace("\\", "").count("[E1]") >= 3
        assert "[E2]" not in output
        for text in ["paper.pdf", "第 3 页", "Original quotation", "https://example.org/paper"]:
            assert text in output

def test_unrelated_repository_fields_do_not_inherit_candidate_evidence(tmp_path):
    report = PaperReport(paper=PaperMetadata(title="No evidence"), selected_repo_url="https://example.org/selected", repo_candidates=[RepoCandidate(url="https://example.org/selected", evidence=[Evidence(kind="web", locator="source-only")])])
    paths = PaperReportRenderer().render(report, tmp_path)
    for output in [paths[0].read_text(encoding="utf-8"), "\n".join(p.text for p in Document(paths[1]).paragraphs)]:
        assert "选中仓库：https://example.org/selected（未提供证据）" in output
        assert "仓库可用状态：无法确认（未提供证据）" in output

def test_literal_markup_and_embedded_fences_remain_content(tmp_path):
    report = PaperReport(paper=PaperMetadata(title="<b>*literal*</b> & entity"), repo_inspection=RepoInspectionResult(repo_url="https://example.org/repo", run_commands=["echo hi\n```\necho bye"]))
    paths = PaperReportRenderer().render(report, tmp_path)
    md = paths[0].read_text(encoding="utf-8")
    assert "&lt;b&gt;\\*literal\\*&lt;/b&gt; &amp; entity" in md
    assert "````text\necho hi\n```\necho bye\n````" in md


def test_markdown_table_syntax_is_not_escaped_with_cell_data(tmp_path):
    report = PaperReport(
        paper=PaperMetadata(title="表格语法"),
        repo_candidates=[RepoCandidate(url="https://example.org/repo", name="---")],
    )
    markdown_path, _ = PaperReportRenderer().render(report, tmp_path)
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "| --- | --- | --- | --- | --- | --- | --- |" in markdown.splitlines()
    assert r"| \--- |" in markdown  # Literal cell data remains escaped.


def test_multiline_prose_keeps_list_and_rule_markers_literal(tmp_path):
    literal = "first\n+ literal\n- literal\n1. literal\n2) literal\n---\n===\n  + indented"
    report = PaperReport(paper=PaperMetadata(title="字面文本", abstract=literal))
    markdown_path, word_path = PaperReportRenderer().render(report, tmp_path)
    markdown = markdown_path.read_text(encoding="utf-8")
    for expected in [r"\+ literal", r"\- literal", r"1\. literal", r"2\) literal", r"\---", r"\===", r"  \+ indented"]:
        assert expected in markdown
    assert "摘要：" + literal in [p.text for p in Document(word_path).paragraphs]


@pytest.mark.parametrize("newline", ["\r\n", "\r"])
def test_windows_and_legacy_newlines_render_as_literal_line_breaks(tmp_path, newline):
    literal = newline.join(["first", "+ literal", "1. literal", "---", "==="])
    source = Evidence(kind="paper", locator="page 1", quote=literal)
    report = PaperReport(paper=PaperMetadata(title="换行", abstract=literal, evidence=[source]))
    markdown_path, word_path = PaperReportRenderer().render(report, tmp_path)
    # The Windows file writer may use CRLF; reject stray CR inside field content.
    markdown = markdown_path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    expected = r"first<br>" + "\n" + r"\+ literal<br>" + "\n" + r"1\. literal<br>" + "\n" + r"\---<br>" + "\n" + r"\==="
    assert "摘要：" + expected in markdown
    assert "原文引用：" + expected in markdown
    assert "\r" not in markdown
    assert "摘要：" + literal.replace("\r\n", "\n").replace("\r", "\n") in [
        p.text for p in Document(word_path).paragraphs
    ]


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_command_newline_styles_keep_the_same_logical_lines(tmp_path, newline):
    command = newline.join(["python train.py", "python evaluate.py"])
    report = PaperReport(
        paper=PaperMetadata(title="Command newlines"),
        repo_inspection=RepoInspectionResult(repo_url="https://example.org/repo", run_commands=[command]),
    )
    markdown_path, word_path = PaperReportRenderer().render(report, tmp_path)
    markdown = markdown_path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert "```text\npython train.py\npython evaluate.py\n```" in markdown
    assert "\r" not in markdown
    assert "python train.py\npython evaluate.py" in [p.text for p in Document(word_path).paragraphs]

def test_word_tables_repeat_headers_and_anchor_first_row(tmp_path):
    paths = PaperReportRenderer().render(PaperReport(paper=PaperMetadata(title="Layout"), repo_candidates=[RepoCandidate(url="https://example.org/" + "long" * 100)]), tmp_path)
    table = Document(paths[1]).tables[0]
    assert table.rows[0]._tr.xpath('./w:trPr/w:tblHeader')
    assert all(p.paragraph_format.keep_with_next for c in table.rows[0].cells for p in c.paragraphs)
    assert not any(p.paragraph_format.keep_with_next for c in table.rows[1].cells for p in c.paragraphs)

def test_missing_items_and_all_warning_contexts_explicitly_lack_evidence(tmp_path):
    report = PaperReport(
        paper=PaperMetadata(title="证据标记"),
        missing_items=[MissingItem(field="seed", description="论文未说明随机种子")],
        warnings=["训练脚本无法运行"],
        repo_inspection=RepoInspectionResult(repo_url="https://example.org", warnings=["检查不完整"]),
        experiment_comparison=ExperimentComparison(
            missing_items=[MissingItem(field="batch", description="批量大小缺失")],
            warnings=["参数无法核对"]),
    )
    paths = PaperReportRenderer().render(report, tmp_path)
    outputs = [paths[0].read_text(encoding="utf-8"), "\n".join(p.text for p in Document(paths[1]).paragraphs)]
    for output in outputs:
        for statement in [
            "报告缺失项：seed；论文未说明随机种子；原因：未提供（未提供证据）",
            "报告警告：训练脚本无法运行（未提供证据）",
            "仓库检查警告：检查不完整（未提供证据）",
            "参数对照缺失项：batch；批量大小缺失；原因：未提供（未提供证据）",
            "参数对照警告：参数无法核对（未提供证据）",
        ]:
            assert statement in output

def test_word_notes_remain_associated_and_table_labels_stay_with_tables(tmp_path):
    report = PaperReport(
        paper=PaperMetadata(title="版式"),
        repo_candidates=[RepoCandidate(url="https://example.org/repo", notes="候选说明全文")],
        dependencies=[DependencyInfo(name="torch", source=Evidence(kind="repo_file", locator="requirements.txt"))],
        experiment_comparison=ExperimentComparison(items=[ExperimentComparisonItem(name="batch", notes="参数说明全文")]),
    )
    paths = PaperReportRenderer().render(report, tmp_path)
    doc = Document(paths[1])
    paragraphs = [p.text for p in doc.paragraphs]
    assert "候选仓库 https://example.org/repo；说明：候选说明全文" in paragraphs
    assert "参数 batch；说明：参数说明全文" in paragraphs
    assert all("说明" not in [c.text for c in t.rows[0].cells] for t in doc.tables)
    assert next(p for p in doc.paragraphs if p.text == "汇总依赖").paragraph_format.keep_with_next
    md = paths[0].read_text(encoding="utf-8")
    assert "候选说明全文" in md and "参数说明全文" in md


def test_word_table_layouts_fit_distinct_column_roles(tmp_path):
    report = PaperReport(
        paper=PaperMetadata(title="列角色"),
        repo_candidates=[RepoCandidate(url="https://example.org/repo", owner="team")],
        experiment_comparison=ExperimentComparison(items=[
            ExperimentComparisonItem(name="learning_rate", paper_value="0.01", repo_value="0.02")
        ]),
    )
    _, word_path = PaperReportRenderer().render(report, tmp_path)
    candidate, comparison = Document(word_path).tables
    # URLs need more room than owner names; parameter names need more than categories.
    assert candidate.columns[0].width > candidate.columns[1].width
    assert comparison.columns[1].width > comparison.columns[0].width


def test_word_headings_use_explicit_chinese_fonts_without_theme_fallback(tmp_path):
    from docx.oxml.ns import qn

    _, word_path = PaperReportRenderer().render(
        PaperReport(paper=PaperMetadata(title="论文复现分析报告")), tmp_path
    )
    document = Document(word_path)
    for style_name in ["Title", "Heading 1", "Title Char", "Heading 1 Char"]:
        properties = document.styles[style_name].element.find(qn("w:rPr"))
        fonts = properties.find(qn("w:rFonts"))
        assert not any("theme" in name.lower() for name in fonts.attrib)
        for slot in ["ascii", "hAnsi", "eastAsia", "cs"]:
            assert fonts.get(qn("w:" + slot)) == "黑体"
        language = properties.find(qn("w:lang"))
        assert language is not None and language.get(qn("w:eastAsia")) == "zh-CN"
