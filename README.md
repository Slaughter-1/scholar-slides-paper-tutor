# Scholar Slides + Paper Tutor

这个仓库包含两个互相配合的 Codex skills：

- `scholar-slides`：基于论文原文和证据进行论文分析、检查点审核与学术汇报生成。
- `paper-tutor`：在 Scholar Slides 分析结果之上，提供证据约束下的论文讲解、学习笔记与阅读完成资产。

两个 skill 保持单向数据流：Scholar Slides 是只读上游证据源，Paper Tutor 不会反向修改 Scholar Slides 项目或演示文稿。

## 仓库结构

```text
scholar-slides-paper-tutor/
├── scholar-slides/
│   ├── SKILL.md
│   ├── bin/
│   ├── references/
│   ├── schemas/
│   └── runtime/
└── paper-tutor/
    ├── SKILL.md
    ├── agents/
    └── references/
```

## 安装

把两个目录复制到 Codex 的 skills 目录。Windows PowerShell 示例：

```powershell
$skillRoot = Join-Path $env:USERPROFILE '.codex\skills'
Copy-Item -Recurse -Force '.\scholar-slides' $skillRoot
Copy-Item -Recurse -Force '.\paper-tutor' $skillRoot
```

Scholar Slides 还需要在其 `runtime` 目录安装 Python 与 Node.js 依赖：

```powershell
Set-Location "$skillRoot\scholar-slides\runtime"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt
npm install
npx playwright install chromium
```

将 `scholar-slides\bin` 加入 `PATH` 后可检查环境：

```powershell
scholar-slides --version
scholar-slides doctor --json
```

当前 Scholar Slides 版本：`0.3.0`。

## 说明

仓库只包含可复现的源文件和依赖清单，不包含本机 `.venv`、`node_modules`、缓存或生成的论文项目。`scholar-slides/LICENSE` 中保留了 Scholar Slides 的 MIT 许可证。
