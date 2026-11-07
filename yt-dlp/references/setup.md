# 环境与排错

## 安装来源

先检查 `command -v yt-dlp` 和 `yt-dlp --version`，必要时用对应 Python 的 `-m pip show yt-dlp yt-dlp-ejs` 判断来源。沿用现有包管理器、虚拟环境或独立二进制的升级方式，不混用多个安装来源。

若用户授权新建独立 Python 环境，可选择一个用户管理的虚拟环境；以下 VENV_DIR 为实际环境目录的占位符：

```bash
python3 -m venv "VENV_DIR"
"VENV_DIR/bin/python" -m pip install -U "yt-dlp[default]"
"VENV_DIR/bin/yt-dlp" --version
```

以后通过该环境的命令运行，或由用户将其加入 PATH。不要为绕过 `externally-managed-environment` 而默认启用 `break-system-packages`。FFmpeg 和 JavaScript runtime 通过当前平台适用的方法安装。

## YouTube JavaScript 支持

YouTube 提取需要兼容的 EJS challenge solver 和受支持的 JavaScript runtime。pip 的 `yt-dlp[default]` 会按依赖约束安装 EJS；其他发行形式按官方 EJS 文档检查，不另装未经约束的版本。

用 `command -v deno` 或 `command -v node` 检查已有 runtime，再检查版本。Deno 默认启用；Node 可用 `--js-runtimes node` 启用。若不在 PATH 中，使用 `--js-runtimes "node:/path/to/node"`，其中路径必须替换为本机发现的可执行文件。不要假定用户有特定版本的 nvm 或预设配置。支持的最低版本以官方文档为准。

## 失败处理

1. 用 `yt-dlp --verbose --simulate --no-playlist "PAGE_URL"` 在本地诊断版本、配置、代理和 extractor 错误；不直接发布完整日志。
2. 检查 URL、格式和 runtime。若疑似站点变化造成的 extractor/signature/player 错误，在授权范围内按原安装来源更新。pip 环境使用其 Python 执行 `-m pip install -U "yt-dlp[default]"`；官方可更新二进制使用 `yt-dlp -U`。
3. 确有需要且用户同意切换 nightly 时，pip 命令才增加 `--pre`。更新后重试一次，仍失败则报告证据和下一步，避免无限更新或重试。
4. 只有错误涉及登录或所需访问身份，且已获授权时，才尝试 `--cookies-from-browser "BROWSER"`；不导出明文 cookies 文件。
5. 检查地域、代理、临时 URL 过期和站点支持情况；DRM 内容停止处理。

## 官方依据

- [安装与升级](https://github.com/yt-dlp/yt-dlp/wiki/Installation)
- [YouTube EJS 与 JavaScript runtime](https://github.com/yt-dlp/yt-dlp/wiki/EJS)
