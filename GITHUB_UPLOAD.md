# CompareX — GitHub 上传清单

本仓库仅包含**源代码与文档资源**，不包含构建产物、虚拟环境或用户本地配置。

## 应上传的文件与目录

| 路径 | 说明 |
|------|------|
| `main.py` | 应用入口 |
| `config.py` | 全局配置 |
| `logger_config.py` | 日志配置 |
| `requirements.txt` | 运行依赖 |
| `requirements-build.txt` | 打包依赖 |
| `CompareX.spec` | PyInstaller 规格 |
| `README.md` / `README_EN.md` | 中英文说明 |
| `core/` | 文件夹管理、图像加载、指标等 |
| `ui/` | 界面与对话框 |
| `utils/` | 工具函数 |
| `i18n/` | 国际化文案 |
| `extensions/` | 自定义工具扩展 |
| `packaging/` | PyInstaller 运行时钩子 |
| `scripts/` | 打包脚本（macOS / Windows） |
| `assets/` | 图标、README 截图（不含 `comparex.iconset/`） |

## 不应上传（已在 .gitignore 中排除）

| 路径 | 原因 |
|------|------|
| `dist/`、`build/` | PyInstaller 构建产物 |
| `.build-venv/` | 打包用虚拟环境 |
| `__pycache__/` | Python 字节码缓存 |
| `assets/comparex.iconset/` | icns 生成中间文件 |
| `.DS_Store` | macOS 元数据 |

## 用户本地数据（不在仓库内）

应用运行时数据保存在用户主目录，**不会**进入 Git：

```text
~/.imagecompare_fluent/
├── cache/          # 缩略图与图像缓存
└── config/         # 工作区、历史、主题、自定义工具等
    ├── workspace.json
    ├── workspace_history.json   ← 对比历史列表
    └── ...
```

上传前已清空本机 `workspace_history.json` 与 `workspace.json` 中的个人路径。

## 首次推送命令

```bash
cd CompareX
git init
git add .
git commit -m "Initial commit: CompareX image comparison tool"
gh repo create CompareX --private --source=. --remote=origin --push
```
