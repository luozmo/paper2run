# 报告导出需求对齐

## 当前范围

2026-11-09：用户负责 Markdown、Word 报告导出。本轮仅对齐需求、记录术语和决定，不实现功能。最终共同确认需求后，仍需用户授权开始实现。

阅读基线为 main 的 1a731c7，已读 README 第三节、CONTRIBUTING.md、app/interfaces.py、app/models.py、app/pipeline/orchestrator.py 和相关契约、流水线测试。

## 用户已确认

- Q1：完成可提交给小组并接入流水线的报告模块。两种格式均实际生成；处理正常数据、缺失数据和异常情况，并有对应测试。具体排版与验收细节待继续讨论。
- Q2：主要读者是读过论文、准备复现的计算机专业学生。报告帮助其查找代码、准备环境、核对实验条件；中期 PPT 可引用报告内容。
- Q3：只组织、呈现上游分析数据。导出过程不调用大模型、不搜索仓库、不重新判断实验参数；如实展示上游提供的未知、缺失或冲突。两种格式使用同一份内容依据。

## 仓库现有约束

- 主要实现目录为 app/reporting/；共享模型、接口、依赖与流水线由集成负责人维护。
- 现有 ReportRenderer.render 接收 PaperReport、output_dir，返回 list[Path]。
- 未找到仓库时流水线仍会调用导出模块；repo_inspection、experiment_comparison 可为空。
- 项目已声明 python-docx 依赖。
- 模块测试采用 fake 或 fixture，不依赖真实 GitHub、DSH 或 API Key。

## 待讨论

报告章节、证据呈现、缺失与矛盾信息、文档语言与排版、输出文件规则、失败行为、具体验收样例。

尚未做出需要 ADR 记录的高成本架构取舍。
