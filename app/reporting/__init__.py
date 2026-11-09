"""Export supplied analysis data as Markdown and Word report documents."""
from pathlib import Path
import html
import re
from docx import Document
from docx.shared import Mm, RGBColor, Pt
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from app.models import PaperReport


class ReportExportError(RuntimeError):
    """Both report documents could not be exported safely."""


def _sections(report: PaperReport) -> list[tuple[str, list[str]]]:
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
    def table(headers, rows):
        return (headers, rows)
    repo = [f"仓库可用状态：{available[report.code_availability]}（未提供证据）", f"选中仓库：{value(report.selected_repo_url)}（未提供证据）"]
    if report.repo_candidates:
        repo.append(table(["候选仓库", "所有者", "名称", "官方状态", "置信度", "说明", "证据"], [[r.url, value(r.owner), value(r.name), official[r.official_status], str(r.confidence), value(r.notes), refs(r.evidence)] for r in report.repo_candidates]))
    else:
        repo.append("未提供候选仓库信息。")
    dependencies = []
    def deps(label, items):
        dependencies.append(label)
        if items:
            dependencies.append(table(["名称", "版本", "用途", "置信度", "证据"], [[d.name, value(d.version), scope[d.scope], str(d.confidence), refs([d.source])] for d in items]))
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
        dependencies.append(table(["依赖清单路径", "清单类型", "证据"], [[m.path, str(m.kind), refs([m.evidence])] for m in inspection.manifests]) if inspection.manifests else "未提供依赖清单信息。")
        for entry in inspection.entry_points:
            commands.append("入口及入口命令证据：" + refs(entry.evidence))
            commands.extend([f"运行入口：{entry.path}（置信度：{entry.confidence}）", ("code", entry.command)] if entry.command is not None else [f"运行入口：{entry.path}；未提供入口命令。"])
        for command in inspection.run_commands:
            commands.extend(["运行命令（未提供证据）", ("code", command)])
        if not commands:
            commands.append("未提供运行入口与命令信息。")
    conditions = [table(["类别", "参数", "值", "置信度", "证据"], [[category[p.category], p.name, p.value, str(p.confidence), refs(p.evidence)] for p in report.experiment_parameters])] if report.experiment_parameters else ["未提供论文实验条件信息。"]
    comparison = report.experiment_comparison
    comparisons = ["未提供参数对照结果。"] if comparison is None else ([table(["类别", "参数", "论文值", "仓库值", "状态", "说明", "证据"], [[category[i.category], i.name, value(i.paper_value), value(i.repo_value), status[i.status], value(i.notes), refs(i.evidence)] for i in comparison.items])] if comparison.items else ["未提供参数对照条目。"])
    warnings = []
    for context, missing, messages in [("报告", report.missing_items, report.warnings), ("仓库检查", [], inspection.warnings if inspection else []), ("参数对照", comparison.missing_items if comparison else [], comparison.warnings if comparison else [])]:
        for item in missing:
            warnings.append(f"{context}缺失项：{item.field}；{item.description}；原因：{value(item.reason)}")
        warnings.extend(f"{context}警告：{message}" for message in messages)
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
    return [("概览", overview), ("论文基本信息", metadata), ("代码仓库及官方状态", repo), ("依赖与环境", dependencies), ("运行入口与命令", commands), ("论文实验条件", conditions), ("参数对照", comparisons), ("缺失项与警告", warnings or ["未提供缺失项与警告信息。"]), ("证据", evidence_blocks or ["未提供证据。"]) ]



def _literal(text):
    text = html.escape(text, quote=False)
    return re.sub(r"([\\`*{}\[\]#_!|>~])", r"\\\1", text).replace("\n", "<br>\n")


def _markdown_block(block):
    if isinstance(block, str):
        return _literal(block)
    if block[0] == "code":
        fence = "`" * max(3, max((len(m) + 1 for m in re.findall(r"`+", block[1])), default=3))
        return fence + "text\n" + block[1] + "\n" + fence
    headers, rows = block
    def row(values):
        return "| " + " | ".join(_literal(v).replace("<br>\n", "<br>") for v in values) + " |"
    return "\n".join([row(headers), row(["---"] * len(headers))] + [row(r) for r in rows])


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
            normal.font.name = "宋体"
            normal.font.size = Pt(11)
            normal.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "宋体")
            normal.paragraph_format.space_after = Pt(6)
            normal.paragraph_format.line_spacing = 1.15
            for name in ["Title", "Heading 1"]:
                style = document.styles[name]
                style.font.color.rgb = RGBColor(0, 0, 0)
                style.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "黑体")
                for element in style.element.iter():
                    for attribute in ["w:themeColor", "w:themeTint", "w:themeShade"]:
                        element.attrib.pop(qn(attribute), None)
                for border in list(style.element.iter(qn("w:pBdr"))):
                    border.getparent().remove(border)
            document.add_heading("论文复现分析报告", 0)
            for heading, lines in sections:
                document.add_heading(heading, 1)
                for line in lines:
                    if isinstance(line, str):
                        document.add_paragraph(line)
                    elif line[0] == "code":
                        run = document.add_paragraph().add_run(line[1])
                        run.font.name = "Consolas"
                    else:
                        headers, rows = line
                        t = document.add_table(rows=1, cols=len(headers))
                        t.style = "Table Grid"
                        t.autofit = False
                        weights = {7: [22, 13, 14, 15, 10, 18, 12], 5: [22, 28, 18, 12, 14], 3: [45, 22, 27]}[len(headers)]
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
