"""Export supplied analysis data as Markdown and Word report documents."""
from pathlib import Path
from docx import Document
from docx.shared import Mm
from app.models import PaperReport


class ReportExportError(RuntimeError):
    """Both report documents could not be exported safely."""


def _sections(report: PaperReport) -> list[tuple[str, list[str]]]:
    paper = report.paper
    metadata = [f"标题：{paper.title}", "作者：" + ("、".join(paper.authors) or "未提供")]
    for label, value in [("年份", paper.year), ("出版信息", paper.venue), ("DOI", paper.doi), ("链接", paper.url), ("摘要", paper.abstract)]:
        metadata.append(f"{label}：{value if value is not None else '未提供'}")
    return [
        ("概览", ["本报告文档整理已有分析数据，供准备复现论文时查阅。"]),
        ("论文基本信息", metadata),
        ("代码仓库及官方状态", ["未提供候选仓库信息。", "未提供选中仓库信息。"]),
        ("依赖与环境", ["未提供汇总依赖信息。", "未提供仓库检查结果。"]),
        ("运行入口与命令", ["未提供运行入口与命令信息。"]),
        ("论文实验条件", ["未提供论文实验条件信息。"]),
        ("参数对照", ["未提供参数对照结果。"]),
        ("缺失项与警告", ["未提供缺失项与警告信息。"]),
        ("证据", ["未提供证据。"]),
    ]


class PaperReportRenderer:
    """Implement the ReportRenderer protocol without external service calls."""

    def render(self, report: PaperReport, output_dir: Path) -> list[Path]:
        directory = Path(output_dir)
        paths = [directory / "report.md", directory / "report.docx"]
        created = []
        try:
            directory.mkdir(parents=True, exist_ok=True)
            if any(path.exists() for path in paths):
                raise FileExistsError("目标报告已存在，请使用新目录")
            sections = _sections(report)
            markdown = "# 论文复现分析报告\n\n" + "\n\n".join(
                f"## {heading}\n\n" + "\n\n".join(lines) for heading, lines in sections
            ) + "\n"
            document = Document()
            section = document.sections[0]
            section.page_width, section.page_height = Mm(210), Mm(297)
            section.top_margin = section.bottom_margin = Mm(20)
            section.left_margin = section.right_margin = Mm(22)
            document.add_heading("论文复现分析报告", 0)
            for heading, lines in sections:
                document.add_heading(heading, 1)
                for line in lines:
                    document.add_paragraph(line)
            with paths[0].open("x", encoding="utf-8") as stream:
                created.append(paths[0])
                stream.write(markdown)
            with paths[1].open("xb") as stream:
                created.append(paths[1])
                document.save(stream)
            return paths
        except Exception as error:
            for path in created:
                path.unlink(missing_ok=True)
            raise ReportExportError(f"报告导出失败：{error}") from error
