# 贡献指南

感谢您对本项目的关注！我们欢迎所有形式的贡献。

## 📜 行为准则

参与本项目即表示您同意遵守我们的 [行为准则](CODE_OF_CONDUCT.md)。

## 💡 如何贡献

### 报告 Bug

1. 搜索现有 Issues，确保该问题尚未被报告
2. 使用 Bug 报告模板创建 Issue
3. 提供详细的复现步骤和环境信息

### 提出功能需求

1. 搜索现有 Issues/Discussions
2. 使用功能需求模板创建 Issue
3. 详细描述使用场景和预期的解决方案

### 提交代码

1. Fork 仓库
2. 基于 `main` 分支创建功能分支
3. 遵循现有代码风格
4. 提交 Pull Request

## 🔧 开发流程

### 环境搭建

```bash
git clone https://github.com/xiejianjun000/{REPO}.git
cd {REPO}
npm install
```

### 分支策略

| 分支 | 说明 |
|------|------|
| `main` | 主分支，稳定可发布 |
| `feature/*` | 功能开发分支 |
| `bugfix/*` | Bug 修复分支 |

### 提交规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```
<type>(<scope>): <subject>
```

- `feat` - 新功能
- `fix` - Bug 修复
- `docs` - 文档更新
- `chore` - 构建/工具变动
- `refactor` - 重构
- `test` - 测试

## 🧪 测试

```bash
npm test
```

## 🔍 代码审查

所有 PR 需要至少一位维护者审查通过后方可合并。
