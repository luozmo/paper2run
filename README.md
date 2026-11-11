# Paper2Run

Paper2Run 是一个面向计算机学生的论文复现信息助手。输入论文 PDF 后，系统会使用 DeepSeek Harness（DSH）Agent 抽取论文信息，检索并获取 GitHub 仓库，解析依赖与运行入口，比较论文和仓库的实验条件，并生成经过 Pydantic 校验的 JSON、Markdown 和 Word 报告。

# 一、安装与使用

## 1. 获取代码

```bash
git clone https://github.com/luozmo/paper2run.git
cd paper2run
```

## 2. 环境要求

- Python 3.10+
- Git
- Node.js 24.9+
- DeepSeek API Key
- DeepSeek Harness SDK
- GitHub 网络访问
- 可选：`GITHUB_TOKEN`，用于提高 GitHub API 速率限制
- Windows x64、Linux 或 macOS

当前开发环境为 Windows x64。

## 3. 安装 Python 环境

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

网络较慢时可以使用国内镜像：

```powershell
python -m pip install -e ".[dev]" --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

## 4. 准备 DSH

DSH 仍在 Developer Preview 阶段。

### 4.1 使用安装脚本

在项目根目录执行：

```powershell
.\scripts\setup_dsh.ps1
```

脚本会自动完成：

- 检查 Node.js 版本
- 创建本地 DSH 目录
- 查找 `pnpm`、`corepack` 或 `npx`
- 安装 `@deepseek-ai/dsh@0.2.1-rc.5`
- 批准原生模块构建
- 重建原生依赖
- 执行 `dsh --version` 验证安装

成功后应看到：

```text
DSH setup completed successfully.
DSH version: 0.2.1-rc.5
```

### 4.2 手动安装

> 创建 `artifacts/dsh-runtime` 用于安装 DSH，创建 `artifacts/dsh-home-sdk` 用于保存本地凭据，并进入 runtime 目录执行后续命令。

```powershell
New-Item -ItemType Directory -Force artifacts\dsh-runtime
New-Item -ItemType Directory -Force artifacts\dsh-home-sdk
New-Item -ItemType Directory -Force artifacts\dsh-workspace
Set-Location artifacts\dsh-runtime
```

在 `artifacts\dsh-runtime\package.json` 创建：

```json
{
  "private": true,
  "type": "module"
}
```

在 `artifacts\dsh-runtime\pnpm-workspace.yaml` 创建：

```yaml
allowBuilds:
  '@deepseek-ai/dsh-subprocess-local': true
  '@google/genai': true
  koffi: true
  node-pty: true
  protobufjs: true
```

安装并验证：

```powershell
pnpm add @deepseek-ai/dsh@0.2.1-rc.5
pnpm rebuild
$env:DSH_HOME = (Resolve-Path ..\dsh-home-sdk).Path
.\node_modules\.bin\dsh.cmd --version
Set-Location ..\..
```

### 4.3 配置凭据

在项目根目录创建：

```text
artifacts/dsh-home-sdk/.credentials.yaml
```

内容：

```yaml
version: 1
refs:
  DEEPSEEK_API_KEY: "sk-你的真实Key"
```

注意：

- `artifacts/` 已被 `.gitignore` 忽略
- 不要提交 API Key
- DSH 使用标准 `sdk` profile
- `sdk-minimal` 不读取 `.credentials.yaml`

## 5. 运行一次完整论文分析

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe scripts\run_paper.py path\to\paper.pdf
```

指定任务 ID：

```powershell
.\.venv\Scripts\python.exe scripts\run_paper.py `
  path\to\paper.pdf `
  --job-id demo-paper-001
```

指定模型：

```powershell
.\.venv\Scripts\python.exe scripts\run_paper.py `
  path\to\paper.pdf `
  --job-id demo-paper-001 `
  --model deepseek-v4-flash
```

手动指定 GitHub 仓库，覆盖自动发现结果：

```powershell
.\.venv\Scripts\python.exe scripts\run_paper.py `
  path\to\paper.pdf `
  --job-id demo-paper-001 `
  --repo-url https://github.com/owner/repository
```

查看帮助：

```powershell
.\.venv\Scripts\python.exe scripts\run_paper.py --help
```

命令会依次完成论文抽取、仓库发现与获取、仓库检查、参数比较和报告生成。最终 `PaperReport` JSON 输出到标准输出，Markdown 和 Word 文件路径输出到标准错误。

未传入 `--repo-url` 时系统自动发现仓库；传入后使用指定仓库覆盖自动选择结果。同一个 `job_id` 下如果报告文件已存在，渲染器会拒绝覆盖，请使用新的任务 ID 或清理对应任务目录。

## 6. 输出文件

每次任务会生成：

```text
artifacts/dsh-workspace/jobs/<job_id>/
├─ workspace/
│  ├─ paper_text.json
│  ├─ prompt.md
│  ├─ result.json
│  └─ report/
│     ├─ report.md
│     └─ report.docx
└─ repositories/
   └─ owner--repo/
```

| 文件                     | 说明                                      |
| ------------------------ | ----------------------------------------- |
| `paper_text.json`      | 按页提取的论文文本和 PDF 元数据           |
| `prompt.md`            | 实际发送给 DSH 的完整中文 Prompt          |
| `result.json`          | 包含仓库检查与参数比较的最终报告          |
| `report/report.md`     | Markdown 格式分析报告                     |
| `report/report.docx`   | Word 格式分析报告                         |
| `repositories/`        | 自动获取的仓库缓存，不提交 Git            |

## 7. 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

当前预期：

```text
57 passed
```

测试覆盖数据模型、PDF 解析、Prompt 安全、DSH Agent、流水线接口、仓库检查、报告生成和 CLI 串联。仓库发现模块目前通过真实 GitHub 获取和克隆冒烟测试验证。

## 8. 当前已验证能力

已在 RTLScout 论文上完成真实端到端测试：

- 15 页 PDF 全部可解析，约 5.1 万字符
- 自动定位官方仓库 `huawei-csl/rtlscout`，置信度 0.99
- 解析 9 项仓库依赖
- 发现 16 个入口脚本和 20 条运行命令
- 生成 32 项论文与仓库参数对照
- 成功输出 `result.json`、`report.md` 和 `report.docx`
- 完整测试 57 项通过

当前 32 项参数均被标记为仓库缺失，说明静态依赖与命令匹配可用，但自由文本参数的语义匹配仍需继续增强。

# 二、项目与文件说明

## 1. 当前项目结构

```text
paper2run/
├─ app/
│  ├─ __init__.py
│  ├─ config.py
│  ├─ models.py
│  ├─ interfaces.py
│  ├─ pdf_loader.py
│  ├─ prompt_loader.py
│  ├─ dsh_agent.py
│  ├─ prompts/
│  │  ├─ base_rules.md
│  │  └─ extract_paper.md
│  ├─ pipeline/
│  │  ├─ __init__.py
│  │  └─ orchestrator.py
│  ├─ repo_discovery/
│  │  ├─ github.py
│  │  ├─ ranking.py
│  │  ├─ service.py
│  │  └─ urls.py
│  ├─ repo_inspection/
│  │  ├─ comparison.py
│  │  ├─ dependencies.py
│  │  ├─ entrypoints.py
│  │  ├─ files.py
│  │  ├─ manifests.py
│  │  └─ service.py
│  └─ reporting/
│     └─ __init__.py
├─ tests/
│  ├─ test_contracts.py
│  ├─ test_pipeline.py
│  ├─ test_models.py
│  ├─ test_pdf_loader.py
│  ├─ test_prompt_loader.py
│  ├─ test_dsh_agent.py
│  ├─ test_repo_inspection.py
│  ├─ test_reporting.py
│  └─ test_run_paper_cli.py
├─ scripts/
│  ├─ run_paper.py
│  └─ setup_dsh.ps1
├─ artifacts/                 # 本地运行产物，不提交 Git
├─ data/
├─ pyproject.toml
├─ README.md
└─ .gitignore
```

## 2. 当前处理流程

```text
论文 PDF
  → 按页提取文本
  → DSH Agent 抽取论文信息
  → Pydantic 校验 PaperReport
  → GitHub 仓库发现
  → 获取仓库
  → 解析依赖、入口与运行命令
  → 比较论文与仓库实验条件
  → 生成 Markdown/Word 报告
  → 保存最终 result.json
```

## 3. 文件说明

| 文件                             | 作用                                               |
| -------------------------------- | -------------------------------------------------- |
| `app/config.py`                | 管理路径、DSH 配置和模型参数                       |
| `app/models.py`                | 定义 PDF、仓库、依赖、实验参数、证据和最终报告模型 |
| `app/interfaces.py`            | 定义仓库发现、仓库检查和报告渲染的服务接口         |
| `app/pdf_loader.py`            | 按页读取 PDF 文本、页码和元数据                    |
| `app/prompt_loader.py`         | 加载中文 Prompt、替换变量并阻止路径穿越            |
| `app/dsh_agent.py`             | 串联 PDF、Prompt、DSH 调用和结果校验               |
| `app/pipeline/`                | 串联完整分析流程                                   |
| `app/repo_discovery/`          | GitHub 检索、仓库获取、候选排序和官方状态判断      |
| `app/repo_inspection/`         | 依赖、入口、运行命令解析及实验条件比较             |
| `app/reporting/`               | 生成 Markdown 和 Word 报告                         |
| `app/prompts/base_rules.md`    | 定义证据、安全和输出规则                           |
| `app/prompts/extract_paper.md` | 定义论文信息抽取任务                               |
| `scripts/setup_dsh.ps1`        | 安装并验证本地 DSH runtime                         |
| `scripts/run_paper.py`         | 命令行完整分析入口                                 |
| `tests/`                       | 覆盖模型、流程、模块和 CLI 的测试                  |

# 三、协作说明

完整的协作规范见 [CONTRIBUTING.md](CONTRIBUTING.md)。所有成员开始开发前应先阅读该文件。

## 1. 模块边界

| 模块 | 主要目录 | 负责内容 |
| --- | --- | --- |
| 共享契约与流程集成 | `app/models.py`、`app/interfaces.py`、`app/pipeline/` | 数据模型、模块接口、流水线集成 |
| 仓库发现 | `app/repo_discovery/` | GitHub 检索、仓库获取、候选仓库排序与官方状态判断 |
| 仓库检查 | `app/repo_inspection/` | 依赖文件解析、入口与运行命令分析、论文与仓库实验条件比较 |
| 报告生成 | `app/reporting/` | Markdown 和 Word 报告渲染 |

每个人应只修改自己负责的模块目录。需要跨模块修改时，先与对应负责人确认。

## 2. 分支与 PR

不要把所有人的修改都直接堆到 `main` 分支。每个功能从最新的 `main` 创建独立分支：

```powershell
git switch main
git pull origin main
git switch -c feat/repo-discovery
```

推荐分支名：

```text
feat/repo-discovery
feat/repo-inspection
feat/reporting
fix/<问题名>
docs/<文档主题>
```

完成一个可独立评审的小功能后提交 Pull Request。PR 合并前应满足：

1. 只包含当前模块的修改；
2. 不提交 `.venv/`、`artifacts/`、API Key 和运行产物。

## 3. 共享文件单写者规则

以下文件由集成负责人统一维护，避免多人同时修改造成冲突：

- `app/models.py`
- `app/config.py`
- `app/interfaces.py`
- `app/pipeline/`
- `scripts/run_paper.py`
- `pyproject.toml`
- `.github/`
- 根目录 `README.md`

需要新增共享模型字段、依赖或接口时，先说明需求，由集成负责人修改共享契约并合并后，其他成员再同步最新 `main`。

## 4. 模块接口

各模块只通过统一的 Pydantic 模型和 `app/interfaces.py` 中的协议交互：

```text
RepoDiscoveryService
  → list[RepoCandidate]
  → Path

RepoInspectionService
  → RepoInspectionResult
  → ExperimentComparison

ReportRenderer
  → list[Path]
```

不要让一个业务模块直接导入另一个业务模块的内部文件。模块组合统一放在 `app/pipeline/` 中完成。

## 5. 提交前检查

同步主分支：

```powershell
git fetch origin
git rebase origin/main
```

运行完整测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

测试未通过时不要提交 PR。

# 四、待完成工作

1. 增强 YAML、配置文件、CLI 参数和 README 的语义匹配，减少自由文本实验参数被误判为缺失。
2. 实现隔离环境配置、最小运行路径和沙箱实验执行。
3. 使用多篇不同领域论文建立评测集，统计仓库发现、依赖解析和参数比较准确率。
4. 继续优化报告中的差异高亮和缺失项定位。
5. 完成图形界面。
