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
