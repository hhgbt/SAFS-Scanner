# `train_model.py` 模块文档

## 概述

`core/train_model.py` 是 **ML-AdaptPentest** 框架的核心组件之一，负责训练用于检测 Web 漏洞的机器学习模型。该脚本读取预处理后的 CSV 训练数据，使用随机森林（Random Forest）算法进行训练，并保存训练好的模型和特征列表供后续扫描使用。

## 核心功能

1.  **数据加载与预处理**：
    *   读取 CSV 格式的训练数据（默认为 `data/training_data_all_labeled.csv`）。
    *   **特征清洗**：针对 `resp_time_diff`（响应时间差）特征，将负值（网络波动噪声）强制归零，防止模型学习错误规律。
    *   自动填充缺失值 (NaN -> 0)。
    *   检查标签列 `label` 是否存在。

2.  **特征选择**：
    *   **动态特征优先**：为了提高模型的泛化能力，我们刻意剔除了“静态指纹”特征（如页面绝对长度 `resp_length_base`、绝对响应时间 `resp_time_base`）。
    *   **核心特征**：强迫模型专注于学习**变化量**（如 `len_diff`, `resp_time_diff`）和**异常状态**（如 `has_sql_error_probe`），确保模型在面对不同结构的网站时依然有效。
    *   内置推荐特征列表（`preferred`），自动过滤掉输入文件中不存在的特征。

3.  **模型训练与优化**：
    *   **算法**：使用随机森林分类器 (`RandomForestClassifier`)，因其对高维特征和非线性关系具有良好的鲁棒性，且对特征缩放不敏感。
    *   **类别平衡**：启用 `class_weight='balanced'`，自动调整权重以应对正负样本不平衡问题。
    *   **网格搜索 (Grid Search)**：通过 `GridSearchCV` 自动寻找最佳超参数组合（如 `n_estimators`, `max_depth`），提升模型性能。

4.  **模型评估与验证**：
    *   **数据集划分**：使用 `train_test_split` 按 8:2 比例划分训练集和测试集（启用分层采样 `stratify`）。
    *   **交叉验证 (Cross-Validation)**：在全量数据上执行 K-Fold 交叉验证（默认 5 折），计算平均 F1 分数，评估模型的泛化能力和稳定性。
    *   **详细报告**：输出分类报告（Precision, Recall, F1-score）、准确率 (Accuracy) 和混淆矩阵。

5.  **可视化回馈**：
    *   计算并打印 Top 5 特征重要性。
    *   生成并保存特征重要性柱状图 (`models/feature_importance.png`)，帮助直观理解模型决策依据。

6.  **模型持久化**：
    *   将训练好的模型对象和特征列表序列化保存为 `.pkl` 文件，供后续扫描模块加载使用。

## 实现细节

### 1. 特征选择

脚本定义了一个推荐的特征优先级列表 (`preferred`)，主要包括：
*   **响应差异类**：`len_diff` (长度差异), `resp_time_diff` (时间差异), `has_text_diff` (文本差异), `status_changed` (状态码变化)。
*   **Payload 反射类**：`probe_reflected`。
*   **错误检测类**：`has_sql_error_probe`, `has_sql_error_base`。
*   **标签检测类**：`has_script_tag_probe` 等。

脚本会自动检测输入 CSV 中包含哪些列，并只使用存在的列进行训练。

### 2. 训练流程 (`train` 函数)

1.  **加载数据**：`pd.read_csv(infile)`。
2.  **数据划分**：使用 `train_test_split` 将数据分为训练集和测试集（默认 80% 训练，20% 测试），并启用分层采样 (`stratify=y`) 以保持类别比例。
3.  **模型初始化**：创建 `RandomForestClassifier` 实例。
4.  **参数搜索**：
    *   定义参数网格：`{"n_estimators": [50, 100], "max_depth": [None, 10, 20]}`。
    *   执行 `GridSearchCV` 寻找最优参数组合。
5.  **最终拟合**：使用最佳参数在训练集上拟合模型。
6.  **评估与输出**：在测试集上进行预测，打印各项评估指标。
7.  **保存**：将模型和特征列表保存到指定路径。

### 3. 命令行接口 (`main` 函数)

支持通过命令行参数自定义输入输出路径：

```bash
python3 core/train_model.py [选项]
```

**参数说明**：
*   `-i`, `--in`: 输入的 CSV 训练数据路径 (默认: `data/training_data_all_labeled.csv`)。
*   `-m`, `--model`: 输出的模型文件路径 (默认: `models/vulnerability_model.pkl`)。
*   `-f`, `--features`: 输出的特征列表文件路径 (默认: `models/feature_list.pkl`)。
*   `--test-size`: 测试集占比 (默认: 0.2)。

## 依赖库

*   `pandas`: 数据处理。
*   `scikit-learn` (`sklearn`): 机器学习算法、模型选择与评估。
*   `joblib` (可选): 模型序列化。
*   `numpy`: 数值计算。

## 使用示例

**基本用法（使用默认路径）：**
```bash
python3 core/train_model.py
```

**指定输入输出文件：**
```bash
python3 core/train_model.py -i data/my_dataset.csv -m models/my_model.pkl -f models/my_features.pkl
```
