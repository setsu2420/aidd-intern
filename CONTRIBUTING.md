# 贡献指南

感谢你对 AIDD-Intern 的关注！本文档将帮助你快速上手项目开发。

## 前置条件

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — 用于依赖管理与虚拟环境
- **Git**

## 本地开发环境搭建

```bash
# 1. 克隆仓库
git clone https://github.com/setsu2420/aidd-intern.git
cd aidd-intern

# 2. 安装依赖（含开发依赖）
uv sync --extra dev

# 3. 复制环境变量模板并填入必要的 API Key
cp .env.example .env

# 4. （可选）安装 CLI 到本地
uv tool install -e .

# 5. 启动开发服务器
./scripts/dev.sh
```

## 开发流程

### 分支命名

从 `main` 创建功能分支，推荐格式：

| 类型     | 格式                          | 示例                           |
| -------- | ----------------------------- | ------------------------------ |
| 功能     | `feat/<简要描述>`             | `feat/add-boltzgen-tool`       |
| 修复     | `fix/<简要描述>`              | `fix/session-timeout`          |
| 文档     | `docs/<简要描述>`             | `docs/update-contributing`     |
| 重构     | `refactor/<简要描述>`         | `refactor/tool-router`         |

### Commit 规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 风格：

```
feat: 添加 BoltzGen 工具集成
fix: 修复 session 超时后未正确重连的问题
docs: 更新贡献指南
test: 补充 protein_design workflow 单元测试
chore: 升级 ruff 至 0.8.x
```

## 代码规范

项目使用 [Ruff](https://docs.astral.sh/ruff/) 进行代码检查和格式化。

```bash
# 检查代码风格
uv run ruff check .

# 自动格式化
uv run ruff format .

# 仅检查格式（CI 模式）
uv run ruff format --check .
```

请确保提交前代码通过以上检查，CI 会自动验证。

## 测试

```bash
# 运行全部测试
uv run pytest

# 运行特定测试文件
uv run pytest tests/unit/test_protein_design_workflow.py

# 运行单元测试目录
uv run pytest tests/unit
```

新功能和 Bug 修复**必须**附带对应的测试用例。

## 提交 PR 流程

1. 在本地完成开发并确保所有检查通过：
   ```bash
   uv run ruff check .
   uv run ruff format --check .
   uv run pytest
   ```
2. 将分支推送到远程仓库。
3. 在 GitHub 上创建 Pull Request，填写 PR 模板中的各项内容。
4. 等待 CI 通过及代码审查。
5. 合并后删除远程功能分支。

> **注意**：请勿直接向 `main` 分支推送代码，所有变更须通过 PR 流程。

## 行为准则

我们致力于为所有参与者提供一个友好、安全、包容的社区环境。参与本项目即表示你同意：

- **尊重他人** — 尊重不同的观点和经验，使用包容性语言。
- **建设性沟通** — 提出建设性的反馈，接受合理的批评。
- **专注于项目** — 保持讨论与项目相关，避免人身攻击或政治争论。
- **负责任地报告问题** — 安全漏洞请参阅 [SECURITY.md](SECURITY.md)，不要在公开 Issue 中披露。

违反行为准则的参与者可能会被临时或永久移出社区。
