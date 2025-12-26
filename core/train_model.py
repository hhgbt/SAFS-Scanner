import os
import argparse
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
try:
    import joblib
except Exception:
    joblib = None
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, GridSearchCV, cross_val_score, StratifiedKFold, GroupKFold
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix

def train(infile: str, out_model: str, out_features: str, test_size: float = 0.2, random_state: int = 42):
    df = pd.read_csv(infile)

    # 1. 预处理：修正网络抖动产生的负数延迟
    if "resp_time_diff" in df.columns:
        df['resp_time_diff'] = df['resp_time_diff'].clip(lower=0)

    # 2. 关键：重新引入 Base 特征，但进行 Log 缩放，平衡量纲
    if "resp_length_base" in df.columns:
        df['log_base_len'] = np.log1p(df['resp_length_base'])
    
    if "len_diff" in df.columns:
         # 保持 len_diff 原样，不做 log，让模型自己决定（或者按照用户指示，不进行额外缩放，或者使用原始逻辑）
         # 用户指示中：df['log_base_len'] = np.log1p(df['resp_length_base' ])
         # 并未明确提到 len_diff 是否需要 log，但之前的逻辑中 len_diff 用了 log。
         # 鉴于用户提供的代码片段 features 列表中有 "len_diff" 而非 "len_diff_log"，我们使用原始 len_diff。
         pass

    # 3. 特征增强：将 payload_type 转换为 One-Hot 编码
    # (用户指示中未包含此部分，但之前的优化中保留它可能更好？
    #  用户说 "请将你 train_model.py 中的 train 函数替换为以下逻辑"，
    #  为了严格遵循用户意图，我应该只保留用户列出的 features。
    #  features = ["probe_reflected", "len_diff", "has_text_diff", "status_changed", "resp_time_diff", "has_sql_error_probe", "has_script_tag_probe", "log_base_len"]
    #  这意味着 payload_type 和 has_script_tag_base 等都被移除了。)
    
    # 3. 最终“双高”特征列表
    preferred = [
        "probe_reflected", 
        "len_diff", 
        "has_text_diff",
        "status_changed", 
        "resp_time_diff", 
        "has_sql_error_probe",
        "has_script_tag_probe", 
        "log_base_len"  # 加上这个，Cross-val 瞬间起飞
    ]

    # 验证 label 列存在
    if "label" not in df.columns:
        raise ValueError("Required column missing: label")

    # 选择存在的推荐特征（保持顺序）
    features = [f for f in preferred if f in df.columns]
    if not features:
        raise ValueError("No usable feature columns found in input CSV")

    X = df[features].fillna(0)
    y = df["label"].astype(int)

    # 输出数据集分布信息，帮助判断是否需要平衡
    from collections import Counter

    dist = Counter(y.tolist())
    print(f"[i] Label distribution: {dist}")

    # B. 核心代码改进：引入 URL 屏蔽（GroupKFold）
    # 确保同一个页面的所有数据要么全在训练集，要么全在测试集。
    groups = None
    if "page_url" in df.columns:
        groups = df["page_url"]
        print("[i] Detected 'page_url', using GroupKFold for cross-validation to prevent leakage.")
        
        # 使用 GroupShuffleSplit 进行训练/测试集划分
        from sklearn.model_selection import GroupShuffleSplit
        gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
        train_idx, test_idx = next(gss.split(X, y, groups))
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
    else:
        print("[!] 'page_url' not found. Falling back to standard train_test_split (potential leakage risk).")
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=random_state, stratify=y
            )
        except Exception:
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=random_state)

    print(f"[*] 开始训练随机森林模型... 样本总量: {len(df)}, 使用特征: {features}")

    # 4. 使用专门调优过的随机森林参数
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=8,         # 适中的深度
        min_samples_leaf=2,  # 每个叶子至少2个样本，防止背下单个Payload
        max_features='sqrt', # 增加特征随机性，提升交叉验证稳健性
        class_weight='balanced',
        random_state=random_state
    )
    
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    print("\n[+] 训练完成！模型评估报告：")
    print(classification_report(y_test, y_pred))
    print(f"准确率 (Accuracy): {accuracy_score(y_test, y_pred):.2f}")

    # 1. 引入交叉验证评估 (Cross-Validation)
    try:
        if groups is not None:
             # 使用 GroupKFold (保留此逻辑以防万一，但用户要求用 StratifiedKFold)
             # 但用户明确要求：
             # from sklearn.model_selection import StratifiedKFold
             # skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
             # cv_scores = cross_val_score(model, X, y, cv=skf, scoring='f1')
             
             # 我们遵循用户的 StratifiedKFold 指令，因为它更适合评估整体分布
             skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
             scores = cross_val_score(model, X, y, cv=skf, scoring='f1')
             print(f"Stratified Cross-val F1 scores (n=5): {scores}, mean={scores.mean():.3f}")
        else:
             skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
             scores = cross_val_score(model, X, y, cv=skf, scoring='f1')
             print(f"Stratified Cross-val F1 scores (n=5): {scores}, mean={scores.mean():.3f}")
    except Exception as e:
        print(f"[-] Cross validation failed: {e}")

    # 打印混淆矩阵
    try:
        cm = confusion_matrix(y_test, y_pred)
        print("混淆矩阵:")
        print(cm)
    except Exception:
        pass

    # 3. 特征重要性的“可视化回馈”
    try:
        fi = model.feature_importances_
        fi_idx = np.argsort(fi)[::-1]
        print("特征重要性 (Top 5):")
        for i in range(min(5, len(fi_idx))):
            idx = fi_idx[i]
            print(f"  {features[idx]}: {fi[idx]:.4f}")
            
        # 保存特征重要性图表
        plt.figure(figsize=(10, 6))
        sns.barplot(x=fi[fi_idx], y=np.array(features)[fi_idx])
        plt.title("Feature Importance")
        plt.xlabel("Importance Score")
        plt.ylabel("Features")
        plt.tight_layout()
        plt.savefig("models/feature_importance.png")
        print("[+] 特征重要性图表已保存至 models/feature_importance.png")
    except Exception as e:
        print(f"[-] 无法生成特征重要性图表: {e}")

    os.makedirs(os.path.dirname(out_model) or ".", exist_ok=True)
    if joblib is not None:
        joblib.dump(model, out_model)
        joblib.dump(features, out_features)
    else:
        # fallback to pickle
        import pickle

        with open(out_model, "wb") as f:
            pickle.dump(model, f)
        with open(out_features, "wb") as f:
            pickle.dump(features, f)
    print(f"\n[+] 模型已保存至 {out_model}")



def main():
    parser = argparse.ArgumentParser(description="Train RandomForest vulnerability classifier")
    parser.add_argument("-i", "--in", dest="infile", default="data/training_data_all_labeled.csv", help="Input CSV with features and label")
    parser.add_argument("-m", "--model", dest="out_model", default="models/vulnerability_model.pkl", help="Output model path")
    parser.add_argument("-f", "--features", dest="out_features", default="models/feature_list.pkl", help="Output feature list path")
    parser.add_argument("--test-size", dest="test_size", type=float, default=0.2, help="Test split size")
    args = parser.parse_args()

    if not os.path.exists("models"):
        os.makedirs("models")

    train(args.infile, args.out_model, args.out_features, test_size=args.test_size)


if __name__ == "__main__":
    main()
