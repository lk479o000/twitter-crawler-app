from __future__ import annotations

import pathlib
from typing import Dict, List, Tuple

import pandas as pd


def normalize_company_name(name: str) -> str:
    """
    统一公司名称格式：
    - 去除首尾空白
    - 将连续空白压缩为单个空格
    - 统一为大写
    """
    if not isinstance(name, str):
        name = "" if pd.isna(name) else str(name)
    stripped = name.strip()
    # 将所有空白字符（空格、制表、全角空格等）标准化为空格，再压缩
    normalized_space = " ".join(stripped.replace("\u3000", " ").split())
    return normalized_space.upper()


def read_first_column_as_list(excel_path: str | pathlib.Path) -> List[str]:
    """
    从 Excel 读取第一列为列表（忽略表头与空值）
    """
    excel_path = str(excel_path)
    df = pd.read_excel(excel_path, engine="openpyxl", header=0)
    first_col_name = df.columns[0]
    series = df[first_col_name].dropna()
    values = [str(v) for v in series.tolist() if str(v).strip() != ""]
    return values


def build_name_mapping(original_names: List[str]) -> Tuple[Dict[str, str], List[str]]:
    """
    基于原始名称列表，生成：原始名称 -> 标准化名称 的映射，以及去重后的标准化名称列表
    """
    mapping: Dict[str, str] = {}
    normalized_unique: Dict[str, None] = {}
    for original in original_names:
        normalized = normalize_company_name(original)
        mapping[original] = normalized
        normalized_unique.setdefault(normalized, None)
    unique_list = list(normalized_unique.keys())
    return mapping, unique_list


def save_mapping_to_csv(mapping: Dict[str, str], output_csv: str | pathlib.Path) -> None:
    """
    保存映射为 CSV，列：original_name, normalized_name
    """
    rows = [{"original_name": k, "normalized_name": v} for k, v in mapping.items()]
    df = pd.DataFrame(rows)
    df.to_csv(str(output_csv), index=False, encoding="utf-8")


def save_names_to_csv(names: List[str], output_csv: str | pathlib.Path, header: str = "normalized_name") -> None:
    """
    保存名称列表为单列 CSV
    """
    pd.DataFrame({header: names}).to_csv(str(output_csv), index=False, encoding="utf-8")


def prepare_from_excel(excel_path: str | pathlib.Path, names_output_csv: str | pathlib.Path, mapping_output_csv: str | pathlib.Path) -> Tuple[List[str], Dict[str, str]]:
    """
    读取 Excel 第一列 -> 规范化与去重 -> 保存标准化名称列表与映射表
    返回：(标准化唯一名称列表, 原始->标准化映射)
    """
    originals = read_first_column_as_list(excel_path)
    mapping, unique_normalized = build_name_mapping(originals)
    save_names_to_csv(unique_normalized, names_output_csv, header="normalized_name")
    save_mapping_to_csv(mapping, mapping_output_csv)
    return unique_normalized, mapping



