# `core/mutator.py` 模块文档

## 概述

`core/mutator.py` 是 **ML-AdaptPentest** 框架中的 Payload 变异引擎。它的主要作用是接收一个原始的攻击载荷（Payload），通过多种混淆、编码和变形技术生成一系列变体（Mutations）。

这些变体旨在绕过 Web 应用防火墙 (WAF) 或简单的输入过滤器，从而提高漏洞检测的成功率。该模块被设计为可迭代生成器，支持按优先级逐步产出变体，避免一次性生成过多无效载荷。

## 功能特性

1.  **大小写变形 (Case Flipping)**：
    *   生成全小写、全大写以及大小写交替（如 `SeLeCt`）的变体，用于绕过区分大小写的关键词过滤。

2.  **编码混淆 (Encoding Obfuscation)**：
    *   **URL 编码**：对 Payload 进行一次或多次 URL 编码（如 `%27` 代替 `'`）。
    *   **双重 URL 编码**：绕过只解码一次的过滤器。

3.  **注释注入 (Comment Injection)**：
    *   主要针对 SQL 注入，将空格替换为内联注释 `/**/`，干扰基于正则的关键词检测（如将 `UNION SELECT` 变为 `UNION/**/SELECT`）。

4.  **空白字符变异 (Whitespace Variation)**：
    *   使用 `+`、`%20` 或 `%09`（Tab）等不同形式替换空格，测试后端解析逻辑的差异。

5.  **同形字符替换 (Homoglyph Substitution)**：
    *   利用 Unicode 同形字（看起来一样但编码不同），将拉丁字母替换为西里尔字母等（如 `a` -> `а`）。这在某些宽字节处理不当的场景下可能绕过过滤。

6.  **截断攻击 (Null Byte Injection)**：
    *   在 Payload 末尾追加空字节 `\x00` 或 `%00`，尝试截断后端的文件路径或查询语句。

7.  **随机组合策略**：
    *   当基础策略用尽后，随机组合多种变换（如“先大写再 URL 编码”），探索更复杂的绕过路径。

## 实现细节

### 核心类 `Mutator`

*   `__init__(self, max_attempts: int = 10)`:
    *   初始化变异器，设置最大生成的变体数量限制，防止无限循环。

*   `generate(self, payload: str)`:
    *   这是一个生成器函数 (`yield`)，按以下顺序产出变体：
        1.  **大小写变体**：`case_flip`。
        2.  **URL 编码**：单次及双重编码。
        3.  **注释注入**：`inject_comments`。
        4.  **空白符变体**：`space_tab_variants`。
        5.  **同形字**：`homoglyphs`。
        6.  **截断字符**：空字节注入。
        7.  **随机组合**：如果上述规则生成的数量未达到 `max_attempts`，则随机选取 1-3 种变换进行叠加。
    *   内部维护一个 `seen` 集合，确保产出的变体不重复。

### 辅助函数

*   `case_flip(s)`: 返回小写、大写及交替大小写的字符串。
*   `url_encode(s, times)`: 使用 `urllib.parse.quote` 进行编码。
*   `inject_comments(s)`: 将空格替换为 `/**/` 或 `/* */`。
*   `homoglyphs(s)`: 基于预定义的 `HOMOGLYPHS` 字典替换字符。

## 使用示例

```python
from core.mutator import Mutator

# 初始化变异器，最多生成 5 个变体
mutator = Mutator(max_attempts=5)
original_payload = "' OR 1=1 -- "

print(f"Original: {original_payload}")

for i, variant in enumerate(mutator.generate(original_payload)):
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
