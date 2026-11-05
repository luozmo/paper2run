# Paper2Run

Paper2Run 是一个面向计算机学生的论文复现信息助手。输入论文 PDF 后，系统使用 DeepSeek Harness（DSH）Agent 提取代码仓库候选、实验条件、环境参数和证据来源，并输出经过 Pydantic 校验的结构化报告。

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

## 5. 运行一次论文分析

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

查看帮助：

```powershell
.\.venv\Scripts\python.exe scripts\run_paper.py --help
```

命令会将最终 `PaperReport` 输出到标准输出，同时把完整结果保存到任务工作区。

## 6. 输出文件

每次任务会生成：

```text
artifacts/dsh-workspace/jobs/<job_id>/workspace/
├─ paper_text.json
├─ prompt.md
└─ result.json
```

| 文件                | 说明                             |
| ------------------- | -------------------------------- |
| `paper_text.json` | 按页提取的论文文本和 PDF 元数据  |
| `prompt.md`       | 实际发送给 DSH 的完整中文 Prompt |
| `result.json`     | 经过 Pydantic 校验的最终报告     |

## 7. 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

当前预期：

```text
13 passed
```

测试覆盖数据模型、PDF 解析、Prompt 安全、DSH Agent 文件写入、非法 JSON 处理和不安全 `job_id` 拒绝。DSH Agent 单元测试使用 fake runner，不访问真实 API。

## 8. 当前已验证能力

已完成一次真实 DSH 端到端测试，能够提取：

- 数据集
- 模型
- 框架
- 硬件
- batch size
- 学习率
- 训练轮数
- 随机种子
- 评价指标

论文中的 GitHub 链接会被标记为候选仓库，并通过 `official_status` 和 `code_availability` 表示当前无法确认其官方状态。

# 二、项目与文件说明

## 1. 当前项目结构

```text
paper2run/
├─ app/
│  ├─ __init__.py
│  ├─ config.py
│  ├─ models.py
│  ├─ pdf_loader.py
│  ├─ prompt_loader.py
│  ├─ dsh_agent.py
│  └─ prompts/
│     ├─ base_rules.md
│     └─ extract_paper.md
├─ tests/
│  ├─ test_models.py
│  ├─ test_pdf_loader.py
│  ├─ test_prompt_loader.py
│  └─ test_dsh_agent.py
├─ scripts/
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
  → 渲染中文 Prompt
  → 调用 DSH Agent
  → 返回结构化 PaperReport JSON
  → 使用 Pydantic 校验
  → 保存结果文件
```

## 3. 文件说明

| 文件                             | 作用                                               |
| -------------------------------- | -------------------------------------------------- |
| `app/config.py`                | 管理路径、DSH 配置和模型参数                       |
| `app/models.py`                | 定义 PDF、仓库、依赖、实验参数、证据和最终报告模型 |
| `app/pdf_loader.py`            | 按页读取 PDF 文本、页码和元数据                    |
| `app/prompt_loader.py`         | 加载中文 Prompt、替换变量并阻止路径穿越            |
| `app/dsh_agent.py`             | 串联 PDF、Prompt、DSH 调用和结果校验               |
| `app/prompts/base_rules.md`    | 定义证据、安全和输出规则                           |
| `app/prompts/extract_paper.md` | 定义论文信息抽取任务                               |
| `scripts/setup_dsh.ps1`        | 安装并验证本地 DSH runtime                         |
| `tests/`                       | 覆盖模型、PDF、Prompt 和 Agent 的测试              |

# 三、待完成工作（？

1. 由于大多数论文没有标准自己的github仓库，需要根据论文标题、作者、DOI 和链接搜索 GitHub 仓库，区分官方实现、疑似官方实现、第三方复现和无法确认等
2. 读取并解析仓库依赖文件，对照论文与仓库的实验参数，并根据上述内容由agent自动生成 Markdown 和 Word 报告
3. 完成中期汇报ppt
