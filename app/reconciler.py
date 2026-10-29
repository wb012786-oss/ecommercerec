"""
多平台电商账单解析与对账
支持：多文件标准化 → 按订单号/日期+金额匹配 → 差异报告
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from dateutil import parser as date_parser

from .config import COLUMN_ALIASES, PLATFORM_KEYWORDS


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s).strip().lower())


def detect_platform(filename: str, sample_text: str = "") -> str:
    blob = (filename + " " + sample_text).lower()
    for name, kws in PLATFORM_KEYWORDS.items():
        if name == "通用":
            continue
        for kw in kws:
            if kw.lower() in blob:
                return name
    return "通用"


def detect_columns(df: pd.DataFrame) -> dict[str, str | None]:
    mapping: dict[str, str | None] = {k: None for k in COLUMN_ALIASES}
    used: set[str] = set()
    for std, aliases in COLUMN_ALIASES.items():
        for col in df.columns:
            if col in used:
                continue
            n = _norm(col)
            for a in aliases:
                an = _norm(a)
                if an == n or an in n or n in an:
                    mapping[std] = col
                    used.add(col)
                    break
            if mapping[std]:
                break
    return mapping


def parse_date(val: Any) -> str | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, (pd.Timestamp, datetime)):
        return pd.Timestamp(val).strftime("%Y-%m-%d")
    s = str(val).strip()
    if not s:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y%m%d",
        "%Y.%m.%d",
    ):
        try:
            return datetime.strptime(s[:19], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    try:
        return date_parser.parse(s, fuzzy=True).strftime("%Y-%m-%d")
    except Exception:
        return None


def clean_amount(val: Any) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip().replace(",", "").replace("，", "").replace("¥", "").replace("￥", "")
    s = re.sub(r"[^\d.\-]", "", s)
    if not s or s in ("-", "."):
        return None
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def load_raw(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        for enc in ("utf-8-sig", "utf-8", "gbk", "gb2312"):
            try:
                return pd.read_csv(path, encoding=enc, dtype=str)
            except UnicodeDecodeError:
                continue
        raise ValueError("无法识别 CSV 编码")
    return pd.read_excel(path, dtype=str)


def standardize_file(
    path: Path, original_name: str, file_tag: str
) -> tuple[pd.DataFrame, dict]:
    """单文件 → 标准流水 + 元信息"""
    meta: dict[str, Any] = {
        "filename": original_name,
        "tag": file_tag,
        "platform": "通用",
        "rows_raw": 0,
        "rows_valid": 0,
        "warnings": [],
        "column_mapping": {},
    }
    try:
        raw = load_raw(path)
    except Exception as e:
        meta["warnings"].append(f"读取失败: {e}")
        return pd.DataFrame(), meta

    meta["rows_raw"] = len(raw)
    if raw.empty:
        meta["warnings"].append("文件为空")
        return pd.DataFrame(), meta

    # 平台：文件名 + 前几列表头
    header_blob = " ".join(str(c) for c in raw.columns)
    meta["platform"] = detect_platform(original_name, header_blob)

    mapping = detect_columns(raw)
    meta["column_mapping"] = {k: v for k, v in mapping.items() if v}

    if not mapping.get("amount") and not mapping.get("order_id"):
        # 猜金额列
        for col in raw.columns:
            sample = raw[col].head(40).apply(clean_amount)
            if sample.notna().sum() >= max(3, len(sample) // 4):
                mapping["amount"] = col
                meta["warnings"].append(f"金额列未明确，已猜测「{col}」")
                break

    if not mapping.get("amount"):
        meta["warnings"].append("无法识别金额列")
        return pd.DataFrame(), meta

    out = pd.DataFrame()
    out["金额"] = raw[mapping["amount"]].apply(clean_amount)

    if mapping.get("order_id"):
        out["订单号"] = (
            raw[mapping["order_id"]]
            .astype(str)
            .str.strip()
            .str.replace(r"\.0$", "", regex=True)
        )
        out.loc[out["订单号"].isin(["", "nan", "None", "none"]), "订单号"] = None
    else:
        out["订单号"] = None
        meta["warnings"].append("无订单号列，将主要按「日期+金额」匹配")

    out["日期"] = (
        raw[mapping["date"]].apply(parse_date) if mapping.get("date") else None
    )
    out["手续费"] = (
        raw[mapping["fee"]].apply(clean_amount) if mapping.get("fee") else None
    )
    out["状态"] = (
        raw[mapping["status"]].astype(str).str.strip() if mapping.get("status") else None
    )
    out["商品"] = (
        raw[mapping["product"]].astype(str).str.strip() if mapping.get("product") else None
    )
    out["店铺"] = (
        raw[mapping["shop"]].astype(str).str.strip() if mapping.get("shop") else None
    )
    out["来源文件"] = original_name
    out["来源标签"] = file_tag
    out["识别平台"] = meta["platform"]

    out = out[out["金额"].notna()].copy()
    meta["rows_valid"] = len(out)

    if out.empty:
        meta["warnings"].append("无有效金额行")
    return out.reset_index(drop=True), meta


def _match_key_order(row: pd.Series) -> str | None:
    oid = row.get("订单号")
    if oid and str(oid) not in ("None", "nan", ""):
        return f"OID:{str(oid).strip()}"
    return None


def _match_key_date_amt(row: pd.Series) -> str | None:
    d = row.get("日期")
    a = row.get("金额")
    if d and a is not None:
        return f"DA:{d}|{float(a):.2f}"
    return None


def reconcile(frames: list[pd.DataFrame], metas: list[dict]) -> dict:
    """
    多文件对账：
    - 优先订单号精确匹配
    - 其次 日期+金额
    - 输出：全部标准化、匹配成功、仅在某文件、金额不一致
    """
    if not frames:
        return {
            "all": pd.DataFrame(),
            "matched": pd.DataFrame(),
            "only": {},
            "amount_mismatch": pd.DataFrame(),
            "summary": {},
        }

    tagged = []
    for i, df in enumerate(frames):
        if df.empty:
            continue
        d = df.copy()
        d["_idx"] = range(len(d))
        d["_file_i"] = i
        tagged.append(d)

    if not tagged:
        return {
            "all": pd.DataFrame(),
            "matched": pd.DataFrame(),
            "only": {},
            "amount_mismatch": pd.DataFrame(),
            "summary": {"有效文件数": 0},
        }

    all_df = pd.concat(tagged, ignore_index=True)

    # 构建 key
    all_df["_key_oid"] = all_df.apply(_match_key_order, axis=1)
    all_df["_key_da"] = all_df.apply(_match_key_date_amt, axis=1)

    n_files = len(frames)
    file_labels = [m.get("tag") or m.get("filename") or f"文件{i+1}" for i, m in enumerate(metas)]

    matched_rows = []
    amount_mismatch_rows = []
    used = set()  # (file_i, idx)

    # 1) 订单号匹配（跨文件）
    oid_groups = all_df.dropna(subset=["_key_oid"]).groupby("_key_oid")
    for key, grp in oid_groups:
        files_present = grp["_file_i"].unique()
        if len(files_present) < 2:
            continue
        # 取每个文件第一笔做代表比较金额
        reps = grp.drop_duplicates("_file_i")
        amounts = reps["金额"].tolist()
        if len(set(round(a, 2) for a in amounts)) == 1:
            for _, r in reps.iterrows():
                used.add((int(r["_file_i"]), int(r["_idx"])))
            matched_rows.append({
                "匹配方式": "订单号",
                "匹配键": key.replace("OID:", ""),
                "金额": amounts[0],
                "涉及文件数": len(files_present),
                "日期": reps["日期"].iloc[0],
                "商品": reps["商品"].iloc[0] if "商品" in reps else "",
            })
        else:
            for _, r in reps.iterrows():
                used.add((int(r["_file_i"]), int(r["_idx"])))
                amount_mismatch_rows.append({
                    "匹配方式": "订单号",
                    "订单号": key.replace("OID:", ""),
                    "来源标签": r["来源标签"],
                    "来源文件": r["来源文件"],
                    "金额": r["金额"],
                    "日期": r["日期"],
                    "说明": "同订单号金额不一致",
                })

    # 2) 日期+金额匹配（未用过的）
    rest = all_df[~all_df.apply(lambda r: (int(r["_file_i"]), int(r["_idx"])) in used, axis=1)]
    da_groups = rest.dropna(subset=["_key_da"]).groupby("_key_da")
    for key, grp in da_groups:
        files_present = grp["_file_i"].unique()
        if len(files_present) < 2:
            continue
        reps = grp.drop_duplicates("_file_i")
        for _, r in reps.iterrows():
            used.add((int(r["_file_i"]), int(r["_idx"])))
        matched_rows.append({
            "匹配方式": "日期+金额",
            "匹配键": key.replace("DA:", ""),
            "金额": reps["金额"].iloc[0],
            "涉及文件数": len(files_present),
            "日期": reps["日期"].iloc[0],
            "商品": reps["商品"].iloc[0] if "商品" in reps else "",
        })

    # 3) 仅在某一文件
    only: dict[str, pd.DataFrame] = {}
    for i in range(n_files):
        label = file_labels[i]
        sub = all_df[all_df["_file_i"] == i]
        mask = sub.apply(lambda r: (int(r["_file_i"]), int(r["_idx"])) not in used, axis=1)
        only_df = sub[mask].drop(columns=[c for c in sub.columns if c.startswith("_")], errors="ignore")
        only[label] = only_df.reset_index(drop=True)

    matched_df = pd.DataFrame(matched_rows) if matched_rows else pd.DataFrame(
        columns=["匹配方式", "匹配键", "金额", "涉及文件数", "日期", "商品"]
    )
    mismatch_df = pd.DataFrame(amount_mismatch_rows) if amount_mismatch_rows else pd.DataFrame(
        columns=["匹配方式", "订单号", "来源标签", "来源文件", "金额", "日期", "说明"]
    )

    # 汇总
    total_amt = {file_labels[i]: float(frames[i]["金额"].sum()) if not frames[i].empty else 0.0 for i in range(n_files)}
    only_amt = {k: float(v["金额"].sum()) if not v.empty else 0.0 for k, v in only.items()}
    only_cnt = {k: len(v) for k, v in only.items()}

    summary = {
        "有效文件数": sum(1 for f in frames if not f.empty),
        "标准化总笔数": len(all_df),
        "匹配成功组数": len(matched_df),
        "金额不一致笔数": len(mismatch_df),
        **{f"仅在「{k}」笔数": only_cnt.get(k, 0) for k in file_labels},
        **{f"仅在「{k}」金额合计": round(only_amt.get(k, 0), 2) for k in file_labels},
        **{f"「{k}」总金额": round(total_amt.get(k, 0), 2) for k in file_labels},
    }

    # 平台分布
    if "识别平台" in all_df.columns:
        plat = all_df.groupby("识别平台")["金额"].agg(["count", "sum"])
        summary["平台分布"] = {
            str(idx): {"笔数": int(r["count"]), "金额": round(float(r["sum"]), 2)}
            for idx, r in plat.iterrows()
        }

    clean_all = all_df.drop(columns=[c for c in all_df.columns if c.startswith("_")], errors="ignore")

    return {
        "all": clean_all,
        "matched": matched_df,
        "only": only,
        "amount_mismatch": mismatch_df,
        "summary": summary,
        "file_labels": file_labels,
        "metas": metas,
    }


def run_reconcile(
    paths: list[Path], names: list[str]
) -> tuple[dict, list[dict]]:
    frames = []
    metas = []
    for i, (p, name) in enumerate(zip(paths, names)):
        tag = f"文件{chr(65+i)}"  # A B C ...
        df, meta = standardize_file(p, name, tag)
        frames.append(df)
        metas.append(meta)

    result = reconcile(frames, metas)
    return result, metas
