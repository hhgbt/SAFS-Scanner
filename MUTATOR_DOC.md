# `core/mutator.py` 模块文档

## 概述

`core/mutator.py` 是 V-APF 的 Payload 变异引擎。它接收原始载荷并按漏洞类型（SQLi/XSS/通用）执行混淆、编码和轻量变形，生成若干变体以绕过基础过滤或 WAF。默认 `count=3` 时返回“原始载荷 + 最多 3 个变体”。

## 功能特性

核心策略（按类型划分，内部随机选择，支持小概率二阶叠加）：
- **SQLi**：空格→`/**/`、空格→`+`、`OR/AND`→`||/&&`、随机大小写、引号转义、`=`→` like `、前置随机注释。
- **XSS**：标签大小写混淆、`alert`→`prompt/confirm`、URL 编码、`>` 拆分、`javascript:` 插入制表符、`onerror` 拆行。
- **通用**：追加注释/空字节 `%00`、全量 URL 编码、尾部随机空格等。

## 实现细节

### 核心类 `SAFSMutator`

* `mutate(self, base_payload, count=3)`：
    * 基于关键词粗分类 SQLi/XSS/通用，选择对应策略随机生成变体；默认返回原始载荷 + 至多 `count` 个新变体。
    * 使用 `set` 去重，最多尝试 `count*10` 次；有 30% 概率基于已有变体做二阶变换。
* 兼容别名：`PayloadMutator = SAFSMutator`（供旧代码引用）。

## 使用示例

```python
from core.mutator import SAFSMutator

mutator = SAFSMutator()
original_payload = "' OR 1=1 -- "

print(f"Original: {original_payload}")

for i, variant in enumerate(mutator.mutate(original_payload, count=3)):
    print(f"Variant {i+1}: {variant}")
```

**可能输出：**
```text
Original: ' OR 1=1 -- 
Variant 1: ' or 1=1 -- 
Variant 2: ' OR 1=1 -- 
Variant 3: ' oR 1=1 -- 
Variant 4: %27%20OR%201%3D1%20--%20
Variant 5: %2527%2520OR%25201%253D1%2520--%2520
```
