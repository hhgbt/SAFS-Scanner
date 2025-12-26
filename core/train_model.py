import os
import argparse
import pandas as pd
try:
    import joblib
except Exception:
    joblib = None
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score


def train(infile: str, out_model: str, out_features: str, test_size: float = 0.2, random_state: int = 42):
    df = pd.read_csv(infile)

    # 推荐特征优先级（脚本会自动选择存在的列）
    preferred = [
        "probe_reflected",
        "len_diff",
        "has_text_diff",
        "status_changed",
        "resp_time_diff",
        "resp_time_base",
        "resp_time_probe",
        "resp_length_base",
        "resp_length_probe",
        "has_sql_error_probe",
        "has_sql_error_base",
        "has_script_tag_probe",
        "has_script_tag_base",
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

    # 保证按标签分层划分（若类别数过少则回退）
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, stratify=y
        )
    except Exception:
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=random_state)

    print(f"[*] 开始训练随机森林模型... 样本总量: {len(df)}, 使用特征: {features}")

    # 使用 class_weight='balanced' 以缓解标签不平衡
    model = RandomForestClassifier(n_estimators=100, random_state=random_state, class_weight='balanced')
    # 简单的参数调优（小网格，避免长时间运行）
    try:
        from sklearn.model_selection import GridSearchCV, StratifiedKFold

        param_grid = {"n_estimators": [50, 100], "max_depth": [None, 10, 20]}
        cv_splits = 5
        # 根据每类样本数调整折数
        min_class_count = min(dist.values()) if dist else 0
        if min_class_count < cv_splits:
            cv_splits = max(2, min_class_count)
        cv = StratifiedKFold(n_splits=cv_splits, shuffle=True, random_state=random_state)
        gs = GridSearchCV(model, param_grid, cv=cv, scoring="f1", n_jobs=-1)
        gs.fit(X_train, y_train)
        model = gs.best_estimator_
        print(f"[i] GridSearch 最佳参数: {gs.best_params_}")
    except Exception:
        model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    print("\n[+] 训练完成！模型评估报告：")
    print(classification_report(y_test, y_pred))
    print(f"准确率 (Accuracy): {accuracy_score(y_test, y_pred):.2f}")

    # 交叉验证评估（如果样本能支撑）
    try:
        from sklearn.model_selection import cross_val_score

        cv_n = 5
        min_class_count = min(dist.values()) if dist else 0
        if min_class_count < cv_n:
            cv_n = max(2, min_class_count)
        scores = cross_val_score(model, X, y, cv=cv_n, scoring="f1")
        print(f"Cross-val F1 scores (n={cv_n}): {scores}, mean={scores.mean():.3f}")
    except Exception:
        pass

    # 打印混淆矩阵与类别分布
    try:
        from sklearn.metrics import confusion_matrix

        cm = confusion_matrix(y_test, y_pred)
        print("混淆矩阵:")
        print(cm)
    except Exception:
        pass

    # 特征重要性
    try:
        import numpy as np

        fi = model.feature_importances_
        fi_idx = np.argsort(fi)[::-1]
        print("特征重要性:")
        for i in fi_idx:
            print(f"  {features[i]}: {fi[i]:.4f}")
    except Exception:
        pass

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
    parser.add_argument("-i", "--in", dest="infile", default="data/training_data_labeled.csv", help="Input CSV with features and label")
    parser.add_argument("-m", "--model", dest="out_model", default="models/vulnerability_model.pkl", help="Output model path")
    parser.add_argument("-f", "--features", dest="out_features", default="models/feature_list.pkl", help="Output feature list path")
    parser.add_argument("--test-size", dest="test_size", type=float, default=0.2, help="Test split size")
    args = parser.parse_args()

    if not os.path.exists("models"):
        os.makedirs("models")

    train(args.infile, args.out_model, args.out_features, test_size=args.test_size)


if __name__ == "__main__":
    main()
