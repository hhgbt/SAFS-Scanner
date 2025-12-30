import argparse
import asyncio
import json
import os
from typing import List

from core.auto_labeler import AutoLabeler
from core.extractor import FeatureExtractor
from core.predict_scanner import VAPFPredictScanner
from core.train_model import VAPFTrainer


def merge_features(feature_files: List[str], output_path: str = "data/features_all.json"):
    all_vectors = []
    for file in feature_files:
        if not os.path.exists(file):
            print(f"[!] 跳过缺失的特征文件: {file}")
            continue
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    print(f"[*] 载入 {file}: {len(data)} 条向量")
                    all_vectors.extend(data)
                else:
                    print(f"[!] {file} 非列表，已跳过")
        except Exception as e:
            print(f"[!] 读取 {file} 失败: {e}")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_vectors, f, indent=2)
    print(f"[+] 合并完成 -> {output_path}，总计 {len(all_vectors)} 条")


def run_training(target_files: List[str]):
    produced = []
    for idx, target in enumerate(target_files, start=1):
        if not os.path.exists(target):
            print(f"[!] 目标文件不存在，跳过: {target}")
            continue
        print(f"\n=== [提取] {target} -> data/features_{idx}.json ===")
        extractor = FeatureExtractor()
        asyncio.run(extractor.process_file(target, headless=True))
        out_path = f"data/features_{idx}.json"
        extractor.save_vectors(out_path)
        produced.append(out_path)

    if not produced:
        print("[!] 未生成任何特征文件，终止训练流程。")
        return

    print("\n=== [合并] 生成 data/features_all.json ===")
    merge_features(produced, "data/features_all.json")

    print("\n=== [打标] 生成 data/train_dataset.csv ===")
    labeler = AutoLabeler("data/features_all.json")
    labeler.process("data/train_dataset.csv")

    print("\n=== [训练] 训练 RandomForest 并保存模型 ===")
    trainer = VAPFTrainer("data/train_dataset.csv")
    trainer.train()
    trainer.save()


def run_scan(
    url: str,
    method: str,
    scan_mode: str,
    threshold: float,
    headless: bool,
    max_payloads: int,
    deep_on_critical: bool,
    deep_mode: str,
    deep_max_payloads: int,
    report_name: str | None = None,
    report_dir: str = "reports",
    sqlmap_path: str = "sqlmap",
    exploit_timeout: int = 300,
    exploit_max: int = 1,
    beef_xss_path: str = "beef-xss",
    msfconsole_path: str = "msfconsole",
    commix_path: str = "commix",
    critical_threshold: float | None = None,
    concurrency: int = 3,
    mutation_count: int = 1,
    headers: dict | None = None,
    report_format: str = "both",
):
    # brute 模式视为 combo 强化版：高覆盖 + 额外变异
    if scan_mode == "brute":
        scan_mode_effective = "combo"
        mutation_count = max(mutation_count, 2)
    else:
        scan_mode_effective = scan_mode
    scanner = VAPFPredictScanner(default_headers=headers)
    print("\n=== [扫描] 轻量首轮 ===")
    asyncio.run(scanner.scan_url(
        url,
        method=method,
        params=None,
        scan_mode=scan_mode_effective,
        threshold=threshold,
        headless=headless,
        max_payloads=max_payloads,
        report_name=report_name,
        report_dir=report_dir,
        report_format=report_format,
        critical_threshold=critical_threshold,
        concurrency=concurrency,
        mutation_count=mutation_count,
        headers=headers,
        sqlmap_path=sqlmap_path,
        exploit_timeout=exploit_timeout,
        exploit_max=exploit_max,
        beef_xss_path=beef_xss_path,
        msfconsole_path=msfconsole_path,
        commix_path=commix_path,
    ))

    if deep_on_critical:
        crit_thresh = critical_threshold if critical_threshold is not None else threshold
        has_critical = any(r.get("prob_effective", r.get("prob", 0.0)) >= crit_thresh for r in scanner.final_results)
        if has_critical:
            print("\n=== [深度复验] 发现 CRITICAL，启动二次扫描 ===")
            deep_mode_effective = "combo" if deep_mode == "brute" else deep_mode
            deep_mutation_count = max(mutation_count, 2) if deep_mode == "brute" else mutation_count
            deep_scanner = VAPFPredictScanner(default_headers=headers)
            deep_suffix = "deep" if report_name else None
            asyncio.run(deep_scanner.scan_url(
                url,
                method=method,
                params=None,
                scan_mode=deep_mode_effective,
                threshold=threshold,
                headless=headless,
                max_payloads=deep_max_payloads,
                report_name=report_name,
                report_dir=report_dir,
                report_format=report_format,
                critical_threshold=critical_threshold,
                concurrency=concurrency,
                mutation_count=deep_mutation_count,
                headers=headers,
                report_suffix=deep_suffix,
                sqlmap_path=sqlmap_path,
                exploit_timeout=exploit_timeout,
                exploit_max=exploit_max,
                beef_xss_path=beef_xss_path,
                msfconsole_path=msfconsole_path,
                commix_path=commix_path,
            ))
        else:
            print("\n[*] 未发现 CRITICAL，跳过深度复验。")


def main():
    parser = argparse.ArgumentParser(description="V-APF 一键集成 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_train = sub.add_parser("train", help="训练模式：爬取/提取/打标/训练一条龙")
    p_train.add_argument(
        "--targets",
        nargs="+",
        default=[
            "data/targets_dvwa.json",
            "data/targets_bwapp.json",
            "data/targets_pikachu.json",
        ],
        help="目标 JSON 列表（默认使用仓库内标准三套）"
    )

    p_scan = sub.add_parser("scan", help="扫描模式：即时预测并生成报告")
    p_scan.add_argument("--url", required=True, help="目标 URL，GET 可自带 query")
    p_scan.add_argument("--method", default="GET", choices=["GET", "POST"], help="HTTP 方法")
    p_scan.add_argument("--scan_mode", default="combo", choices=["single", "all", "combo", "brute"], help="扫描模式（brute=高覆盖 combo）")
    p_scan.add_argument("--threshold", type=float, default=0.55, help="判定阈值（默认 0.55）")
    headless_group = p_scan.add_mutually_exclusive_group()
    headless_group.add_argument("--headless", dest="headless", action="store_true", help="启用无头（默认）")
    headless_group.add_argument("--no-headless", dest="headless", action="store_false", help="关闭无头，便于调试")
    p_scan.set_defaults(headless=True)
    p_scan.add_argument("--max-payloads", type=int, default=50, help="限制基础 payload 数量（默认 50）")
    p_scan.add_argument("--deep-on-critical", action="store_true", help="若发现 CRITICAL，自动执行二次深度扫描")
    p_scan.add_argument("--deep-mode", default="combo", choices=["single", "all", "combo", "brute"], help="深度扫描模式（默认 combo，brute=高覆盖 combo）")
    p_scan.add_argument("--deep-max-payloads", type=int, default=25, help="深度扫描的基础 payload 数量（默认 25）")
    p_scan.add_argument("--report-name", default=None, help="自定义报告基名（自动附加时间戳）；默认按 URL 生成")
    p_scan.add_argument("--report-dir", default="reports", help="报告输出目录（默认 reports）")
    p_scan.add_argument("--report-format", default="both", choices=["both", "html", "pdf"], help="报告格式：both/html/pdf（默认 both）")
    p_scan.add_argument("--critical-threshold", type=float, default=None, help="自定义 CRITICAL 判定阈值（默认与 threshold 相同）")
    p_scan.add_argument("--concurrency", type=int, default=3, help="并发探测数（默认 3，减小可降低波动）")
    p_scan.add_argument("--mutation-count", type=int, default=1, help="每个基础 payload 的变异数量（默认 1，增加可扩宽覆盖）")
    p_scan.add_argument("--header", action="append", help="自定义 Header，格式 'Key: Value'，可重复指定")
    # 自动利用配置（始终开启）
    p_scan.add_argument("--sqlmap-path", default="sqlmap", help="sqlmap 可执行路径（默认 sqlmap）")
    p_scan.add_argument("--exploit-timeout", type=int, default=600, help="利用步骤超时秒数（默认 600，时间盲注友好）")
    p_scan.add_argument("--exploit-max", type=int, default=5, help="最多触发的高危条目数量（默认 5）")
    p_scan.add_argument("--beef-xss-path", default="beef-xss", help="BeEF-XSS 可执行路径（默认 beef-xss）")
    p_scan.add_argument("--msfconsole-path", default="msfconsole", help="Metasploit msfconsole 可执行路径（默认 msfconsole）")
    p_scan.add_argument("--commix-path", default="commix", help="Commix 可执行路径（默认 commix）")

    args = parser.parse_args()

    if args.command == "train":
        run_training(args.targets)
    elif args.command == "scan":
        headers_dict = {}
        if args.header:
            for h in args.header:
                if ":" in h:
                    k, v = h.split(":", 1)
                    headers_dict[k.strip()] = v.strip()
        headers_dict = headers_dict or None
        run_scan(
            url=args.url,
            method=args.method,
            scan_mode=args.scan_mode,
            threshold=args.threshold,
            headless=args.headless,
            max_payloads=args.max_payloads,
            deep_on_critical=args.deep_on_critical,
            deep_mode=args.deep_mode,
            deep_max_payloads=args.deep_max_payloads,
            report_name=args.report_name,
            report_dir=args.report_dir,
            report_format=args.report_format,
            sqlmap_path=args.sqlmap_path,
            exploit_timeout=args.exploit_timeout,
            exploit_max=args.exploit_max,
            beef_xss_path=args.beef_xss_path,
            msfconsole_path=args.msfconsole_path,
            commix_path=args.commix_path,
            critical_threshold=args.critical_threshold,
            concurrency=args.concurrency,
            mutation_count=args.mutation_count,
            headers=headers_dict,
        )


if __name__ == "__main__":
    main()
