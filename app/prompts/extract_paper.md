{{base_rules}}

# 任务：抽取论文信息

从提供的论文内容中抽取可用于复现的信息。

## 论文元数据

{{paper_metadata}}

## 按页划分的论文正文

{{paper_pages}}

## 输出 Schema

{{output_schema}}

## 必须完成的内容

1. 填充 `PaperMetadata`。
2. 将论文正文中明确出现的论文、项目或 GitHub URL 写入 `RepoCandidate`。
3. 将实验条件写入 `ExperimentParameter`，包括可获得的：
   - 数据集
   - 模型
   - 框架
   - 硬件
   - 训练设置
   - 评测流程
   - 评价指标
4. 将所有缺失或存在歧义的必需字段写入 `MissingItem`。
5. 对扫描页、内容冲突和抽取不确定项写入 warnings。

## 证据要求

- 每一条来自论文的 Evidence 都必须包含从 1 开始的页码。
- 每一个实验参数都必须附带简短、逐字对应的原文引用。
- `code_availability` 在本阶段统一保留为 `uncertain`，仓库验证由后续步骤完成。
- 本任务不得访问代码仓库，也不得进行网络搜索。
- 不得仅因为论文里出现某个 URL 就判断该仓库是官方实现。
- 论文没有写出的字段不得推断。