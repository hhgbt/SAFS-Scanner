<!-- .github/copilot-instructions.md -->
# Copilot 使用说明（针对本仓库）

本文件为 AI 编码代理提供基于仓库事实的修改指引，涵盖爬虫、特征提取、训练与扫描流程。

概要
- 整体目标：基于特征矢量的 Web 漏洞自适应探测与自动化渗透框架（V-APF），核心入口为 [main.py](main.py)。
- 主要依赖：`playwright`、`httpx`、`scikit-learn` 等（见 [requirements.txt](requirements.txt)）；首次需要 `python -m playwright install` 下载浏览器二进制。

关键设计与数据流
- CLI 两条主链：`python main.py train`（提取→合并→打标→训练）与 `python main.py scan ...`（在线预测+报告+自动利用）。
- 爬虫：通用/专用模式在 [core/spider.py](core/spider.py)；输出 targets*.json 供提取器使用。
- 特征提取与打标： [core/extractor.py](core/extractor.py) 生成 13 维特征，[core/auto_labeler.py](core/auto_labeler.py) 产出 data/train_dataset.csv。
- 模型：随机森林 + StandardScaler，训练与保存见 [core/train_model.py](core/train_model.py)。
- 实战扫描： [core/predict_scanner.py](core/predict_scanner.py) 负责评分、降噪、自动利用与报告生成（HTML/PDF）。

爬虫要点（core/spider.py）
- 通用模式：`UniversalSpider` 支持 Cookie 注入登录，BFS 深度默认 3，自动过滤静态资源，输出包含 `injection_points` 与 `baseline` 指纹（响应长度、状态码、响应时间、DOM hash）。
- DVWA 模式：`--dvwa` 触发 `DVWASpider`，自动遍历 low/medium/high/impossible，多等级合并写入单一 JSON。每个等级会自动登录（admin/password）并注入 `security` Cookie。
- bWAPP 模式：`--bwapp` 触发 `BWAPPSpider`，使用 bee/bug 登录 portal，并在 A.I.M. 模式下直接加载内置漏洞页列表（SQLi/XSS/命令注入/SSRF 等）。等级代码 0/1/2 对应 low/medium/high。
- Pikachu 模式：`--pikachu` 触发 `PikachuSpider`，通过 overpermission 登录拿 Session，随后全站 BFS。
- 注入点发现：表单与 URL query 都带 `risk_level` 标记，空值字段填占位符 `SAFS_TEST_PAYLOAD`，利于后续特征提取。

运行示例
- 安装依赖与浏览器：

```bash
python -m pip install -r requirements.txt
python -m playwright install
```

- 一键训练：

```bash
python main.py train
```

- 扫描并生成报告：

```bash
python main.py scan \
  --url "http://testphp.vulnweb.com/listproducts.php?cat=1" \
  --scan_mode combo --threshold 0.55 --max-payloads 50 \
  --concurrency 3 --mutation-count 1 --report-format both
```

- 仅跑爬虫（举例 DVWA 多等级）：

```bash
python core/spider.py --base http://127.0.0.1/dvwa --dvwa --cookie "PHPSESSID=xxx" --no-headless --output data/targets_dvwa.json
```

调试与常见问题定位
- Playwright 报错或缺少浏览器：确认已执行 `python -m playwright install`，并使用仓库中的版本。
- 登录/权限问题：DVWA、bWAPP、Pikachu 入口和表单选择器已写死在各自的 `auto_login` 中；若目标部署改版，优先更新对应选择器或登录路径。
- 爬虫无输出或缺页：检查 `--base` 是否带尾斜杠，确认目标允许使用提供的 Cookie，必要时降低深度或移除静态资源过滤。

修改建议（按优先级）
- 适配新靶场：优先新增派生 Spider，复用 `UniversalSpider` 的 BFS/指纹逻辑，避免在核心类里塞特定站点逻辑。
- 输出扩展：若需更多上下文（标题、headers、响应体摘要），在 `UniversalSpider.find_injection_points` 或 `get_page_fingerprint` 中追加字段。
- 扫描参数：在 [main.py](main.py) 补充 CLI 选项，传递到 `SAFSPredictScanner.scan_url`，保持默认值与 README 一致。

参考文件
- CLI 与流程：[main.py](main.py)
- 爬虫实现：[core/spider.py](core/spider.py)
- 特征与模型：[core/extractor.py](core/extractor.py)、[core/train_model.py](core/train_model.py)
- 扫描与报告：[core/predict_scanner.py](core/predict_scanner.py)、[core/report_generator.py](core/report_generator.py)
- 依赖列表：[requirements.txt](requirements.txt)

如需进一步补充（例如新增测试用例、增加授权头支持、或调整自动利用策略），请指出具体需求。欢迎反馈。
