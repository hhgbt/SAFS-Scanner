<!-- .github/copilot-instructions.md -->
# Copilot 使用说明（针对本仓库）

本文件为 AI 编码代理（Copilot、GPT 代码助手等）提供可执行、基于仓库事实的指导，帮助快速理解并对仓库进行修改或增强。

概要
- 这是一个针对 DVWA 风格 Web 应用的轻量级 Playwright 爬虫，入口文件为 [spider.py](spider.py).
- 主要依赖：`playwright`（见 [requirements.txt](requirements.txt)）。必须执行 `playwright install` 下载浏览器二进制。

关键设计与数据流
- 启动流程：`main()` -> 构造 `DVWASpider` -> `asyncio.run(spider.run(...))`。
- run() 中关键步骤：登录（`login()`）→ 读取/设置安全等级（`get_security_level()`/`set_security_level()`）→ 打开 `index.php` 并从左侧导航(`#main_menu_list a`)收集链接 → 逐页抓取（`crawl_targets()`）→ 提取锚点与表单 → 写入 JSON（默认 `targets.json`）。
- 输出格式（简化示例）：

```json
{
  "base_url": "http://127.0.0.1/dvwa",
  "pages": [
    {
      "url": "http://127.0.0.1/dvwa/vuln.php",
      "level": "medium",
      "anchors": ["..."],
      "forms": [{"action":"...","method":"POST","inputs":[{"name":"...","type":"text"}]}]
    }
  ]
}
```

项目约定与实现细节（重要，按优先级）
- 登录选择器：代码在 `login()` 中使用 `input[name="username"]`, `input[name="password"]` 以及 `input[name="Login"]`。如果目标页面登录 HTML 不一致，应优先修改此处。
- 安全等级：使用 `select[name="security"]` 与提交按钮 `input[name="seclev_submit"]`。常见值：`low|medium|high|impossible`。
- 左侧导航：爬虫依赖 `#main_menu_list a` CSS 选择器来发现主要页面；若目标站点改版，先更新此选择器再运行。
- 表单提取：会收集 `input, textarea, select` 并保留 `option` 列表（包括 `selected` 标志）。字段名为空的 input 会以空字符串记录。
- 相对 URL 归一化：脚本尝试把 `/xxx`、相对路径与绝对 URL 转成完整 URL；此逻辑在 `_extract_anchors_from_page`。

开发/运行流程（快速可复制命令）
- 创建虚拟环境（可选）：

```bash
python -m venv .venv
source .venv/bin/activate
```

- 安装依赖并安装 Playwright 浏览器：

```bash
python -m pip install -r requirements.txt
python -m playwright install
```

- 运行爬虫（可见模式便于调试）：

```bash
python spider.py --no-headless --base http://127.0.0.1/dvwa --user admin --pass password --level medium --output targets.json
```

调试与常见问题定位
- 登录失败：先使用浏览器打开 `${base}/login.php` 检查表单 `name`/`id`，并更新 `login()` 中的选择器。
- 找不到导航链接：检查首页的导航容器是否仍为 `#main_menu_list`，或在 `index.php` 中查找替代选择器。
- Playwright 错误或缺少浏览器：确保已运行 `python -m playwright install`，并使用兼容的 `playwright` 版本（见 [requirements.txt](requirements.txt)）。

修改建议（可直接下手的改进点）
- 若需对不同目标站点适配，优先将选择器提取到模块级常量或配置文件，避免硬编码。
- 输出扩展：若需要额外上下文（HTTP 状态、响应时间、页面标题），在 `crawl_targets()` 中读取并附加到 `page_entry`。

参考文件
- 主程序：[spider.py](spider.py)
- 依赖：[requirements.txt](requirements.txt)

如果上面有缺失或不清楚的地方，请指出具体要点（例如：想让代理生成测试用例、增加 auth header、或改为同步实现），我会按需调整此文件。欢迎反馈。
