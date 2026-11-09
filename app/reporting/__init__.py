"""Export supplied analysis data as Markdown and Word report documents."""
import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

from docx import Document
from docx.shared import Mm, RGBColor, Pt
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from app.models import PaperReport


class ReportExportError(RuntimeError):
    """Both report documents could not be exported safely."""


@dataclass(frozen=True)
class _TextBlock:
    text: str


@dataclass(frozen=True)
class _CodeBlock:
    text: str


@dataclass(frozen=True)
class _TableColumn:
    label: str
    width: int
    role: Literal["value", "identity", "note"] = "value"


@dataclass(frozen=True)
class _TableBlock:
    columns: list[_TableColumn]
    rows: list[list[str]]
    identity_label: str = ""

    @property
    def headers(self) -> list[str]:
        return [column.label for column in self.columns]


_Block: TypeAlias = _TextBlock | _CodeBlock | _TableBlock


def _sections(report: PaperReport) -> list[tuple[str, list[_Block]]]:
    evidence = []
    def refs(items):
        labels = []
        for item in items:
            if item not in evidence:
                evidence.append(item)
            label = f"[E{evidence.index(item) + 1}]"
            if label not in labels:
                labels.append(label)
        return "、".join(labels) or "未提供证据"
    paper = report.paper
    metadata = [f"标题：{paper.title}", "作者：" + ("、".join(paper.authors) or "未提供")]
    for label, value in [("年份", paper.year), ("出版信息", paper.venue), ("DOI", paper.doi), ("链接", paper.url), ("摘要", paper.abstract)]:
        metadata.append(f"{label}：{value if value is not None else '未提供'}")
    metadata.append("论文信息证据：" + refs(paper.evidence))
    available = {"found": "已找到", "not_found": "未找到", "uncertain": "无法确认"}
    official = {"official": "官方", "likely_official": "可能官方", "third_party": "第三方", "unknown": "无法确认"}
    scope = {"core": "核心", "training": "训练", "evaluation": "评测", "optional": "可选", "unknown": "无法确认"}
    category = {"dataset": "数据集", "model": "模型", "framework": "框架", "hardware": "硬件", "training": "训练设置", "evaluation": "评测信息", "other": "其他"}
    status = {"match": "一致", "mismatch": "不一致", "missing_in_repository": "仓库缺失", "missing_in_paper": "论文缺失", "unknown": "无法确认"}
    def value(v):
        return str(v) if v is not None else "未提供"
    def table(columns: list[_TableColumn], rows: list[list[str]], identity_label: str = "") -> _TableBlock:
        return _TableBlock(columns, rows, identity_label)
    repo = [f"仓库可用状态：{available[report.code_availability]}（未提供证据）", f"选中仓库：{value(report.selected_repo_url)}（未提供证据）"]
    if report.repo_candidates:
        repo.append(table([_TableColumn("候选仓库", 30, "identity"), _TableColumn("所有者", 18), _TableColumn("名称", 18), _TableColumn("官方状态", 18), _TableColumn("置信度", 14), _TableColumn("说明", 18, "note"), _TableColumn("证据", 14)], [[r.url, value(r.owner), value(r.name), official[r.official_status], str(r.confidence), value(r.notes), refs(r.evidence)] for r in report.repo_candidates], identity_label="候选仓库"))
    else:
        repo.append("未提供候选仓库信息。")
    dependencies = []
    def deps(label, items):
        dependencies.append(label)
        if items:
            dependencies.append(table([_TableColumn("名称", 22), _TableColumn("版本", 28), _TableColumn("用途", 18), _TableColumn("置信度", 12), _TableColumn("证据", 14)], [[d.name, value(d.version), scope[d.scope], str(d.confidence), refs([d.source])] for d in items]))
        else:
            dependencies.append(f"未提供{label}信息。")
    deps("汇总依赖", report.dependencies)
    inspection = report.repo_inspection
    commands = []
    if inspection is None:
        dependencies.append("未提供仓库检查结果。")
        commands.append("未提供仓库检查结果，运行入口与命令尚未提供。")
    else:
        deps("仓库检查依赖", inspection.dependencies)
        dependencies.extend([f"检查仓库：{inspection.repo_url}（未提供证据）", f"README 路径：{value(inspection.readme_path)}（未提供证据）", f"仓库结构说明：{value(inspection.structure_summary)}（未提供证据）"])
        dependencies.append(table([_TableColumn("依赖清单路径", 45), _TableColumn("清单类型", 22), _TableColumn("证据", 27)], [[m.path, str(m.kind), refs([m.evidence])] for m in inspection.manifests]) if inspection.manifests else "未提供依赖清单信息。")
        for entry in inspection.entry_points:
            commands.append("入口及入口命令证据：" + refs(entry.evidence))
            commands.extend([f"运行入口：{entry.path}（置信度：{entry.confidence}）", _CodeBlock(entry.command)] if entry.command is not None else [f"运行入口：{entry.path}；未提供入口命令。"])
        for command in inspection.run_commands:
            commands.extend(["运行命令（未提供证据）", _CodeBlock(command)])
        if not commands:
            commands.append("未提供运行入口与命令信息。")
    conditions = [table([_TableColumn("类别", 22), _TableColumn("参数", 28), _TableColumn("值", 18), _TableColumn("置信度", 12), _TableColumn("证据", 14)], [[category[p.category], p.name, p.value, str(p.confidence), refs(p.evidence)] for p in report.experiment_parameters])] if report.experiment_parameters else ["未提供论文实验条件信息。"]
    comparison = report.experiment_comparison
    comparisons = ["未提供参数对照结果。"] if comparison is None else ([table([_TableColumn("类别", 14), _TableColumn("参数", 28, "identity"), _TableColumn("论文值", 18), _TableColumn("仓库值", 18), _TableColumn("状态", 18), _TableColumn("说明", 18, "note"), _TableColumn("证据", 14)], [[category[i.category], i.name, value(i.paper_value), value(i.repo_value), status[i.status], value(i.notes), refs(i.evidence)] for i in comparison.items], identity_label="参数")] if comparison.items else ["未提供参数对照条目。"])
    warnings = []
    for context, missing, messages in [("报告", report.missing_items, report.warnings), ("仓库检查", [], inspection.warnings if inspection else []), ("参数对照", comparison.missing_items if comparison else [], comparison.warnings if comparison else [])]:
        for item in missing:
            warnings.append(f"{context}缺失项：{item.field}；{item.description}；原因：{value(item.reason)}（未提供证据）")
        warnings.extend(f"{context}警告：{message}（未提供证据）" for message in messages)
    overview = ["本报告文档整理已有分析数据，供准备复现论文时查阅。", f"上游仓库可用状态：{available[report.code_availability]}。", f"已提供候选仓库 {len(report.repo_candidates)} 个、汇总依赖 {len(report.dependencies)} 项、论文实验条件 {len(report.experiment_parameters)} 项。", "仓库检查结果：" + ("已提供。" if inspection else "未提供。"), "参数对照结果：" + ("已提供。" if comparison else "未提供。"), f"已有缺失项与警告 {len(warnings)} 条，详见对应章节。"]
    evidence_blocks = []
    for number, item in enumerate(evidence, 1):
        evidence_blocks.append(f"[E{number}] 来源：{item.kind}；位置：{item.locator}")
        if item.page is not None:
            evidence_blocks.append(f"第 {item.page} 页")
        if item.quote is not None:
            evidence_blocks.append("原文引用：" + item.quote)
        if item.url is not None:
            evidence_blocks.append("链接：" + item.url)
    sections = [("概览", overview), ("论文基本信息", metadata), ("代码仓库及官方状态", repo), ("依赖与环境", dependencies), ("运行入口与命令", commands), ("论文实验条件", conditions), ("参数对照", comparisons), ("缺失项与警告", warnings or ["未提供缺失项与警告信息。"]), ("证据", evidence_blocks or ["未提供证据。"]) ]
    return [(heading, [_TextBlock(block) if isinstance(block, str) else block for block in blocks]) for heading, blocks in sections]



def _literal(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"([\\`*{}\[\]#_!|>~])", r"\\\1", text)
    # A line break does not stop CommonMark from recognizing a new list or rule.
    text = re.sub(r"(?m)^([ \t]*)([-+])(?=[ \t])", r"\1\\\2", text)
    text = re.sub(r"(?m)^([ \t]*\d{1,9})([.)])(?=[ \t])", r"\1\\\2", text)
    text = re.sub(r"(?m)^([ \t]*)([-=])(?=[-= \t]*$)", r"\1\\\2", text)
    return text.replace("\n", "<br>\n")


def _markdown_block(block: _Block) -> str:
    if isinstance(block, _TextBlock):
        return _literal(block.text)
    if isinstance(block, _CodeBlock):
        fence = "`" * max(3, max((len(m) + 1 for m in re.findall(r"`+", block.text)), default=3))
        return fence + "text\n" + block.text + "\n" + fence
    headers, rows = block.headers, block.rows
    def row(values):
        return "| " + " | ".join(_literal(v).replace("<br>\n", "<br>") for v in values) + " |"
    return "\n".join([row(headers), row(["---"] * len(headers))] + [row(r) for r in rows])


def _set_style_font(style, font_name: str) -> None:
    """Pin all script slots so inherited Office themes cannot split Chinese glyphs."""
    style.font.name = font_name
    properties = style.element.get_or_add_rPr()
    fonts = properties.get_or_add_rFonts()
    for attribute in list(fonts.attrib):
        if "theme" in attribute.lower():
            del fonts.attrib[attribute]
    for slot in ["ascii", "hAnsi", "eastAsia", "cs"]:
        fonts.set(qn("w:" + slot), font_name)
    fonts.set(qn("w:hint"), "eastAsia")
    language = properties.find(qn("w:lang"))
    if language is None:
        language = OxmlElement("w:lang")
        properties.append(language)
    language.set(qn("w:val"), "zh-CN")
    language.set(qn("w:eastAsia"), "zh-CN")


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
                f"## {heading}\n\n" + "\n\n".join(_markdown_block(line) for line in lines) for heading, lines in sections
            ) + "\n"
            document = Document()
            section = document.sections[0]
            section.page_width, section.page_height = Mm(210), Mm(297)
            section.top_margin = section.bottom_margin = Mm(20)
            section.left_margin = section.right_margin = Mm(22)
            normal = document.styles["Normal"]
            _set_style_font(normal, "宋体")
            normal.font.size = Pt(11)
            normal.paragraph_format.space_after = Pt(6)
            normal.paragraph_format.line_spacing = 1.15
            for name in ["Title", "Heading 1", "Title Char", "Heading 1 Char"]:
                style = document.styles[name]
                _set_style_font(style, "黑体")
                style.font.color.rgb = RGBColor(0, 0, 0)
                for element in style.element.iter():
                    for attribute in ["w:themeColor", "w:themeTint", "w:themeShade"]:
                        element.attrib.pop(qn(attribute), None)
                for border in list(style.element.iter(qn("w:pBdr"))):
                    border.getparent().remove(border)
            document.add_heading("论文复现分析报告", 0)
            for heading, lines in sections:
                document.add_heading(heading, 1)
                for index, line in enumerate(lines):
                    if isinstance(line, _TextBlock):
                        paragraph = document.add_paragraph(line.text)
                        if index + 1 < len(lines) and isinstance(lines[index + 1], _TableBlock):
                            paragraph.paragraph_format.keep_with_next = True
                    elif isinstance(line, _CodeBlock):
                        run = document.add_paragraph().add_run(line.text)
                        run.font.name = "Consolas"
                    else:
                        visible = [i for i, column in enumerate(line.columns) if column.role != "note"]
                        headers = [line.columns[i].label for i in visible]
                        rows = [[row[i] for i in visible] for row in line.rows]
                        notes = []
                        note_column = next((i for i, column in enumerate(line.columns) if column.role == "note"), None)
                        if note_column is not None:
                            identity_column = next(i for i, column in enumerate(line.columns) if column.role == "identity")
                            note_label = line.columns[note_column].label
                            notes = [f"{line.identity_label} {row[identity_column]}；{note_label}：{row[note_column]}" for row in line.rows]
                        t = document.add_table(rows=1, cols=len(headers))
                        t.style = "Table Grid"
                        t.autofit = False
                        weights = [line.columns[i].width for i in visible]
                        for column, weight in zip(t.columns, weights):
                            column.width = Mm(166 * weight / sum(weights))
                        t.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
                        for cell, text in zip(t.rows[0].cells, headers):
                            cell.text = text
                        for row in rows:
                            for cell, text in zip(t.add_row().cells, row):
                                cell.text = text
                        for index, row in enumerate(t.rows):
                            for cell, column in zip(row.cells, t.columns):
                                cell.width = column.width
                                margins = OxmlElement("w:tcMar")
                                for side in ["top", "left", "bottom", "right"]:
                                    edge = OxmlElement("w:" + side)
                                    edge.set(qn("w:w"), "65")
                                    edge.set(qn("w:type"), "dxa")
                                    margins.append(edge)
                                cell._tc.get_or_add_tcPr().append(margins)
                                for paragraph in cell.paragraphs:
                                    paragraph.paragraph_format.keep_with_next = index == 0
                                    paragraph.paragraph_format.space_after = Pt(3)
                                    wrap = OxmlElement("w:wordWrap")
                                    paragraph._p.get_or_add_pPr().append(wrap)
                                    for run in paragraph.runs:
                                        run.font.size = Pt(10)
                                        run.bold = index == 0
                        for note in notes:
                            document.add_paragraph(note)
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
