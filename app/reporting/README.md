# 报告文档导出

```python
from pathlib import Path
from app.models import PaperReport
from app.reporting import PaperReportRenderer, ReportExportError

# analysis_data 是符合共享模型的上游分析数据。
report = PaperReport.model_validate(analysis_data)
try:
    markdown_path, word_path = PaperReportRenderer().render(report, Path("output/new-report"))
except ReportExportError as error:
    print(error)
```

自动创建输出目录，成功时返回 `report.md` 和 `report.docx` 的路径。只呈现传入信息，不联网或运行论文代码。缺少分析信息会在文档中说明。

任一目标已存在时拒绝覆盖；请使用新目录。目录异常、写入或 Word 生成失败会抛出 `ReportExportError`，原始异常保留为 cause，本次已创建的不完整文件会被清理，原有文件保留。

Markdown 对普通内容作字面转义，命令使用动态长度围栏保持原文。Word 使用 A4、固定列宽及重复表头；表头与第一条数据保持相邻，后续行允许跨页。
