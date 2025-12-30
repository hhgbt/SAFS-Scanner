# **基于特征矢量的 Web 漏洞自适应探测与自动化渗透框架（V-APF）**

**Vector-based Adaptive Penetration-testing Framework (V-APF)**

------

## 一、项目综述

### 1.1 系统定位

V-APF 是一款**机器学习驱动**的自动化 Web 安全检测框架。通过对 Web 页面在“基线请求 vs. 探测请求”间的**语义指纹差异**进行量化，结合**随机森林 (Random Forest)** 模型，自动识别 SQLi / XSS 等漏洞并生成报告。

### 1.2 核心特性

- **13 维语义指纹**：长度差异、状态变化、延迟、报错关键词、DOM 相似度、反射、Header 变化等。
- **基线对比降噪**：实时获取 Baseline，与探测结果比对，降低业务差异干扰。
- **自动化流水线**：爬虫→特征提取→启发式打标→训练→预测扫描→报告生成全流程打通。
- **稳健抗噪**：弱信号/仅反射场景自动封顶分数；403/406/418/429 视为可能 WAF 命中并半衰分数。
- **自动利用链**：对高危条目串行调用 sqlmap / commix / beef-xss / msfconsole 获取证据。

------

## 二、系统架构与模块

| 模块 | 核心文件 | 功能 | 关键点 |
| --- | --- | --- | --- |
| 爬虫 | core/spider.py | BFS 深度 3，收集表单与 URL 参数，输出 targets.json | 支持通用 Cookie 注入、风险标记 |
| 特征提取 | core/extractor.py | httpx + Playwright 混合探测，生成 13 维向量 | 默认前 5 个 payload 做 3 变体扩充，限并发 5 |
| 变异引擎 | core/mutator.py | SQLi/XSS/通用三类变异策略 | 返回原始 + 变体，避免数量爆炸 |
| 启发式打标 | core/auto_labeler.py | 规则打标，生成 data/train_dataset.csv | 无害 payload 强制 0，阈值 0.65 |
| 训练 | core/train_model.py | log1p(|v1|/|v3|) + StandardScaler + RandomForest | n_estimators=100, max_depth=8, min_samples_leaf=2, class_weight {0:1.3,1:1.7} |
| 预测扫描 | core/predict_scanner.py | AI 评分、信号降噪、自动利用、报告落盘 | 并发默认 3，变异默认 1，阈值默认 0.55 |
| 报告生成 | core/report_generator.py | HTML/PDF 报告，去重与修复建议 | prob_effective、WAF/信号标签、自动利用摘要 |
| CLI 总入口 | main.py | train/scan 子命令 | `python main.py train` / `python main.py scan ...` |

------

## 三、特征工程

每次探测生成 $1\times13$ 特征向量，顺序与代码一致：

1) 长度差异：$(len_{probe}-len_{base})/\max(len_{base},1)$，截断 [-1,1]（训练阶段对 |v1| 做 $\log(1+x)$）。
2) 状态码变化：不同为 1 否则 0。
3) 延迟差异：$(t_{probe}-t_{base})/5$ 截断 [0,1]（训练阶段对 |v3| 做 $\log(1+x)$）。
4) 报错关键词命中：最多 5 个，归一化到 [0,1]。
5) DOM 相似度：difflib 快速比对，0~1。
6) 反射性：payload 是否出现在响应体，0/1。
7) Header 变化：Set-Cookie/Location 变更得分。
8-12) 预留位：当前填 0，保留扩展。
13) Content-Type 变化：不同为 1 否则 0。

训练阶段：对 v1、v3 做 $\log(1+|x|)$，其余直接 StandardScaler 归一化。

------

## 四、工作流

### 4.1 数据准备（train 模式）

1. 目标集：默认使用 data/targets_dvwa.json、data/targets_bwapp.json、data/targets_pikachu.json。
2. 提取：FeatureExtractor 逐目标探测，保存 data/features_*.json。
3. 合并：生成 data/features_all.json。
4. 打标：AutoLabeler 生成 data/train_dataset.csv（无害 payload 强制 0）。
5. 训练：VAPFTrainer 产出 models/vapf_rf_model.pkl 与 models/scaler.pkl。

### 4.2 预测扫描（scan 模式）

1. 输入：`python main.py scan --url <target> --scan_mode combo --threshold 0.55 --max-payloads 50 --concurrency 3 --mutation-count 1`。
2. 探测：httpx+Playwright 并发探测，弱信号/仅反射分数封顶 (0.50/0.55)，403/406/418/429 视作 WAF 半衰。
3. 自动利用：命中阈值的高危条目串行调用 sqlmap/commix/beef-xss/msfconsole（可配置路径/超时/数量）。
4. 报告：生成 HTML/PDF，命名为 reports/<sanitized_target>_YYYYMMDD_HHMMSS[\_deep].(html|pdf)。

### 4.3 判定逻辑

默认阈值 0.55，可按调优表调整。示例分级：

$$
Result = \begin{cases}
	ext{Vulnerable}, & P \ge 0.8 \\
	ext{Suspicious}, & 0.55 \le P < 0.8 \\
	ext{Safe}, & P < 0.55
\end{cases}
$$

------

## 五、最新模型表现（2025-12-30）

- 数据规模：训练 14848（正 6938）、测试 3713（正 1735）。
- 0.5 阈值：Precision 0.92 / Recall 0.96 / F1 0.94 / Accuracy 0.94；混淆矩阵 [[1838, 140], [68, 1667]]。
- 阈值调优：0.20→0.70 时 Recall 0.9631→0.9539，Precision 0.9202→0.9256，FP 145→133。
- 特征重要性：v4=0.5560，v5=0.1593，v6=0.1387，v1=0.1203，v2=0.0249，其余≈0。

------

## 六、评估与实践建议

- **减少误报**：降低并发或提高阈值；关注 prob_effective 与 WAF/信号标签。
- **减少漏报**：在盲注/缓慢站点可放宽阈值至 0.5 或增加 `--mutation-count` 与深度复验 `--deep-on-critical`。
- **环境准备**：`python -m pip install -r requirements.txt`，`python -m playwright install`，并确保 sqlmap/commix/beef-xss/msfconsole 在 PATH 或显式指定路径。
- **合规提示**：仅在授权范围内使用，报告中保留证据与命令，便于审计追溯。