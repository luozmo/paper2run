# 报告生成模块验收

2026-11-09，集成分支 feat/reporting。功能与审查修正对应提交 e6b1a18a3c147dff2e5210ca386007d46e928173；此后仅更新工单和验收文档。

## 实际执行

- 在项目根目录执行 `.venv/Scripts/python.exe -m pytest -q`，结果为 **29 passed in 0.98s**，退出码 0。开始实现前基线为 16 项通过。
- 以公开的 PaperReportRenderer.render 入口验证实际 Markdown 和 Word 内容、可选数据缺失、依赖与参数冲突、重复证据、字面文本、同名文件保护、受控写入失败和非目录输出等行为。
- 顺序实施四张本地工单，每张由新的 GPT-6.1 Sol 实现子智能体在独立分支和工作区完成，再由合并子智能体合入集成分支。
- TDD 的实际红绿过程见各工单完成记录。工单 01 的部分保护测试在新增时已通过，未宣称这些测试经历过失败。

原始测试输出、环境依赖清单、参与验证的源码字节归档及版本记录保存于忽略的 `artifacts/reporting-implementation/`：final-pytest.txt、test-environment.txt、verified-source.zip 和 verified-revision.txt。源码归档含报告模块、共享模型和接口、测试及项目依赖声明；未归档解释器和依赖包二进制。

## Word 页面检查

使用构造数据生成 complete、complex、minimal 三组报告，并保存每组原始 input.json。样例不代表真实论文抽取结果。

打包的 render_docx.py 已实际尝试，因当前 Windows 运行时无 soffice 而失败，日志为 packaged-renderer.txt。未使用或安装桌面 LibreOffice；改用本机 Word 16.0 COM 在隐藏实例中只读打开样例并导出 PDF，再使用 bundled Poppler 将 PDF 渲染为 PNG。

最终检查对象位于 `artifacts/reporting-implementation/final-samples/`：

| 样例 | 最终页数 | 实际检查范围 | 结果 |
| --- | --- | --- | --- |
| complete | 3 | 全部 3 页 | 中文、标题层级、完整分析表格、冲突和证据可读 |
| complex | 4 | 全部 4 页 | 25 条仓库依赖跨页重复表头；长链接、特殊字符、多行命令和长说明无明显截断或重叠 |
| minimal | 2 | 全部 2 页 | 主要章节保留，缺少分析数据与证据时有明确提示 |

初次页面检查发现标题与依赖表格分离，以及长说明挤在窄表格列中的问题。已将表格前标签与表格保持相邻，并将候选仓库及参数说明完整放到 Word 表格后的对应段落。修正后重新生成并查看上述全部 9 页，未发现明显截断、重叠、缺字或表格溢出。

## Standards

独立规范审查核对 CONTRIBUTING、README 协作规则及模块说明，未发现可确认的文档规范违规。一项非阻塞建议是内容块原先使用隐式字符串与元组协议，属于 Primitive Obsession / Repeated Switches 的设计判断。已用三类私有内容块明确表示文本、命令和表格，保持公开接口不变。

## Spec

独立规格审查发现 1 项 P2：缺失项和警告没有明确标注未提供证据。已补齐报告、仓库检查和参数对照的对应提示，并以公开导出入口添加失败后通过的回归测试。无确认的额外范围扩张；修正代码及最终页面由集成代理复核。

规范轴：0 项硬性违规，1 项设计建议已落实。规格轴：1 项 P2 已修复，无已知未处理项。

## 交付边界

四张本地工单已完成。实现和测试仅涉及报告生成模块及对应测试，没有更改共享模型、接口、依赖、命令行或流水线。正式业务接入仍由集成负责人维护。模块不调用真实 GitHub、DSH 或模型 API，本次没有验证上游论文抽取或仓库分析效果。

代码在本地 feat/reporting 分支提交，未推送远程、未创建 Issue 或 PR。正式使用方式见模块 README。
