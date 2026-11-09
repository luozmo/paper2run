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
