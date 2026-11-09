# Paper2Run 协作规范

## 一、模块边界

| 模块 | 目录 | 负责人 |
| --- | --- | --- |
| 共享契约与流程集成 | `app/models.py`、`app/interfaces.py`、`app/pipeline/` | 集成负责人 |
| 仓库发现 | `app/repo_discovery/` | 仓库发现负责人 |
| 仓库检查 | `app/repo_inspection/` | 仓库检查负责人 |
| 报告生成 | `app/reporting/` | 报告生成负责人 |

每个人只修改自己负责的目录。跨目录修改必须先沟通，由对应负责人完成。

## 二、共享文件单写者规则

以下文件只能由集成负责人修改：

- `app/models.py`
- `app/config.py`
- `app/interfaces.py`
- `app/pipeline/`
- `scripts/run_paper.py`
- `pyproject.toml`
- `.github/`
- 根目录 `README.md`

其他成员需要增加模型字段、依赖或接口时，先提交 Issue 或说明，由集成负责人先修改契约。

## 三、分支和 PR

分支命名：

```text
feat/repo-discovery
feat/repo-inspection
feat/reporting
fix/<简短问题名>
docs/<文档主题>
```

开发流程：

```powershell
git switch main
git pull origin main
git switch -c feat/<模块名>
```

完成一个可以独立评审的小功能后提交 PR。PR 合并前需要：

1. 至少一位成员 Review；
2. GitHub Actions 测试通过；
3. 只包含当前模块的修改；
4. 不提交 `.venv/`、`artifacts/`、API Key 和测试运行产物。

## 四、跨模块接口

模块之间只通过 `app/interfaces.py` 中的接口和 `app/models.py` 中的 Pydantic 模型交互：

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

模块内部文件不能被其他模块直接导入。唯一例外是 `app/pipeline/`，它负责组合各模块。

## 五、测试要求

每个模块至少包含：

- 正常输入测试；
- 缺少信息时的测试；
- 非法或异常输入测试；
- 使用 fake 或 fixture，不依赖真实 GitHub、DSH 和 API Key。

提交 PR 前运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
