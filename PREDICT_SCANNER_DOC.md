# V-APF Predict Scanner Documentation

`core/predict_scanner.py` 是 V-APF 的实时预测与漏洞扫描模块。它集成了特征提取、变异引擎和 AI 模型，负责对目标 URL 执行主动探测并生成最终报告。当前默认阈值 `DEFAULT_THRESHOLD = 0.65`，默认探测并发 3，可通过命令行直接传 URL/参数/阈值/模式/变异数/并发/运行选项（无头/有头、限流），无需改代码。

## 功能概览

该模块主要完成以下任务：
1.  **AI 引擎加载**: 初始化随机森林模型 (`models/safs_rf_model.pkl`) 和标准化器 (`models/scaler.pkl`)，特征工程与训练侧一致。
2.  **基准建立 (Baselining)**: 获取目标页面的正常响应作为比对基准，记录基线状态码。
3.  **智能探测 (Intelligent Probing)**:
    -   结合 `SAFSMutator` 生成变异 Payload（默认每个基础 Payload 生成 1 个变体，可用 `--mutation-count` 调整）。
    -   利用 `FeatureExtractor` 提取每次探测的 13 维特征向量。
4.  **实时推理 (Real-time Inference)**: 标准化后送入模型，执行“反射/弱信号降噪”封顶（反射-only 上限 0.50，弱信号上限 0.55；SQL/CMD/XSS 形态可旁路）。
5.  **并发与限流**: `asyncio.Semaphore(concurrency)` 控制探测并发（默认 3）；`--max-payloads` 截断基础 Payload；`--mutation-count` 控制变异数。
6.  **自动利用**: 按特征触发 `sqlmap`/`beef-xss`/`commix`/`msfconsole`，串行执行，预算由 `--exploit-max` 控制（默认 1）。
7.  **报告生成**: 自动生成 HTML 与/或 PDF；无可注入参数也会输出空报告以记录扫描。

## 扫描模式 (Scan Modes)

扫描器支持三种探测模式，以适应不同的测试场景（可配合 `--max-payloads` 限制基础 Payload 数量，加速与控资源）：

1.  **`single` (默认)**:
    -   **逻辑**: 逐个遍历每个参数，对其进行 Payload 注入，其他参数保持默认值。
    -   **特点**: 精度最高，能准确定位漏洞参数。
    -   **并发**: 针对同一个参数的所有 Payload 测试任务并行执行。

2.  **`combo`**:
    -   **逻辑**: 随机挑选 2-3 个参数进行组合注入（同时注入 Payload）。
    -   **特点**: 用于发现多参数关联漏洞或 WAF 绕过（如参数污染）。

3.  **`all`**:
    -   **逻辑**: 同时对所有参数注入相同的 Payload。
    -   **特点**: 暴力测试，用于快速触发全局异常。

## 关键类与方法

### `SAFSPredictScanner`

-   **`__init__(model_path, scaler_path)`**:
    -   加载模型与标准化器；初始化 `FeatureExtractor` 与 `SAFSMutator`。
    -   自动利用串行队列 `exploit_sem=1`，探测并发在 `scan_url` 中按 `concurrency` 配置。

-   **`scan_url(target_url, method, params, scan_mode, threshold, headless=True, max_payloads=None, concurrency=3, mutation_count=1, ... )`**:
    -   核心扫描入口；建立基线后按模式调度探测，空参数时直接生成空报告。
    -   `threshold`: 判定阈值（默认 0.65）。
    -   `headless`: 默认无头；Linux 无 `DISPLAY` 时强制降级无头。
    -   `max_payloads`: 限制基础 Payload 数量；`mutation_count`: 控制每个基础 Payload 生成的变体数（默认 1）。
    -   `concurrency`: 探测并发（默认 3）。
    -   `report-name/dir/suffix/format`: 报告输出定制；`exploit-max`: 自动利用预算。
    -   WAF 检测：状态码 403/406/418/429 视为拦截并折半置信度。

-   **`_scan_single_payload(...)`**:
    -   执行单次探测 -> 特征提取 -> 标准化 -> AI 预测。
    -   反射/弱信号会被封顶降噪；WAF 状态码触发标记与置信度折半。

## 性能优化

-   **并发控制**: `concurrency` 默认 3，可调。
-   **特征复用**: 复用 `FeatureExtractor` 的 13 维计算与训练同款标准化器，推理一致。
-   **限流选项**: `--max-payloads` 截断基础 payload；`--mutation-count` 控制每个基础 payload 的变异数。
-   **无头自动降级**: 在无图形环境（如服务器/CI）误用有头模式时，自动切换为无头，避免 Playwright 因缺少 XServer 退出。

## 输出结果

扫描完成后，默认在 `reports/` 目录下生成按目标 URL 派生并带时间戳的文件名，可用下列参数定制：
- `--report-name`: 自定义报告基名（自动追加时间戳）。
- `--report-dir`: 自定义输出目录（默认 `reports`）。
- `--report-suffix`: 追加自定义后缀（如模式名）。
- `--report-format`: 仅 HTML / 仅 PDF / both（默认 both）。

仍会生成 HTML 与 PDF（按 format 选择）：
-   **HTML 报告**: 交互式图表 + 详情。
-   **PDF 报告**: Playwright 渲染。

说明：即使本次 URL 无可注入参数或扫描过程中出现异常，仍会输出“空报告”，用于记录目标与时间。

## 使用示例

通常通过 Python 或命令行调用，传入 URL 即可：

```python
import asyncio
from core.predict_scanner import SAFSPredictScanner

async def main():
    scanner = SAFSPredictScanner()
    await scanner.scan_url(
        "http://127.0.0.1/pikachu/vul/sqli/sqli_str.php?name=test&submit=submit",
        scan_mode="single",
        threshold=0.65
    )

if __name__ == "__main__":
    asyncio.run(main())
```

### 命令行用法（无需改代码）

```bash
python -m core.predict_scanner \
    --url "http://target.com/vuln.php?name=test" \
    --method GET \
    --scan_mode single \
    --threshold 0.65 \
    --param extra=123 \
    --headless         # 默认无头，可省略；也可显式指定
    # --no-headless    # 本机有桌面环境时可视化调试使用
    # --report-name myrun   # 可选：自定义报告基名
    # --report-dir outdir   # 可选：自定义报告目录
```

- `--url` 必填；GET 可自带 query。
- `--param key=value` 可多次传入补充/覆盖参数；若不传且是 GET，会自动解析 URL query。
- `--scan_mode` 取 `single/all/combo`；`--threshold` 默认 0.65，可调高降 FP、调低提 Recall。
- `--headless` / `--no-headless` 互斥开关：默认无头；Linux 无 `DISPLAY` 时会自动降级无头。
- `--max-payloads N`：限制基础 Payload 数量；`--mutation-count K` 控制每个基础 Payload 变异数（默认 1）。
- `--concurrency M`：控制探测并发（默认 3）。

### 轻量快速扫描（推荐用于受限环境）

```bash
# 全参数同时注入，限制基础 Payload=1，尽快产出报告
python -m core.predict_scanner \
    --url "http://demo.testfire.net/bank/login.aspx?uid=test&pass=pass" \
    --method GET \
    --scan_mode all \
    --threshold 0.65 \
    --max-payloads 1 \
    --headless \
    --report-name testfire_login
```

### 更细粒度的参数探测（单参模式，适度限流）

```bash
python -m core.predict_scanner \
    --url "http://demo.testfire.net/bank/login.aspx?uid=test&pass=pass" \
    --method GET \
    --scan_mode single \
    --threshold 0.65 \
    --max-payloads 5 \
    --headless
```

### 在无桌面服务器“有头”调试（不推荐，需虚拟 X）

```bash
xvfb-run -a python -m core.predict_scanner \
    --url "http://demo.testfire.net/bank/login.aspx?uid=test&pass=pass" \
    --method GET \
    --scan_mode single \
    --threshold 0.65 \
    --max-payloads 5 \
    --no-headless
```

提示：若看到 `StandardScaler was fitted without feature names` 的 sklearn 提示，为信息级告警，不影响结果。
