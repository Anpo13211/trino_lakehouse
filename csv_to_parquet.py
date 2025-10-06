#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq


# ---------------- Sniff helpers ----------------

CANDIDATE_DELIMS = [",", "\t", "|", ";"]

def _looks_like_header(cells):
    # 英字・数字・アンダースコアを多く含むとヘッダっぽいとみなす簡易判定
    if not cells:
        return False
    score = 0
    for c in cells:
        if not c:
            continue
        if c.isidentifier():
            score += 1
        elif c.replace("-", "").replace("_", "").isalnum():
            score += 0.5
    return score >= max(1, len(cells) * 0.6)

def sniff_csv_format(path, max_bytes=64 * 1024):
    """
    軽量スニッファ：複数の区切り候補で先頭数行を分割して
    - 列数の安定性（行ごとの列数ぶれの少なさ）
    - 列数の現実性（極端な1列/超多列を減点）
    - 先頭行がヘッダっぽいか
    を総合して delimiter と has_header を推定
    """
    with open(path, "rb") as f:
        sample = f.read(max_bytes)
    text = sample.decode("utf-8-sig", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()][:200]

    best = None
    for delim in CANDIDATE_DELIMS:
        splits = [ln.split(delim) for ln in lines]
        widths = [len(s) for s in splits] or [0]
        if not widths:
            continue
        width_mode = max(set(widths), key=widths.count)
        stability = widths.count(width_mode) / max(1, len(widths))
        width_penalty = 0.0 if 2 <= width_mode <= 2000 else 0.5
        header_guess = _looks_like_header(splits[0])
        score = stability - width_penalty + (0.1 if header_guess else 0.0)

        cand = dict(delimiter=delim, has_header=header_guess, score=score, width=width_mode)
        if best is None or cand["score"] > best["score"]:
            best = cand

    if best is None:
        return ",", True
    return best["delimiter"], best["has_header"]


# ---------------- stats / schema helpers ----------------

def load_column_statistics(dataset_path: str) -> dict:
    stats_file = os.path.join(dataset_path, "column_statistics.json")
    if os.path.exists(stats_file):
        with open(stats_file, "r") as f:
            return json.load(f)
    return {}

def _arrow_type_from_name(name: str) -> pa.DataType:
    t = (name or "").lower()
    if t in {"int", "integer", "int64"}:
        return pa.int64()
    if t in {"float", "double", "float64"}:
        return pa.float64()
    if t in {"bool", "boolean"}:
        return pa.bool_()
    if t in {"date"}:
        return pa.date32()
    if t in {"timestamp", "datetime"}:
        return pa.timestamp("ms")
    return pa.string()

def build_column_types(stats_data: dict, table_name: str) -> dict:
    if table_name not in stats_data or not isinstance(stats_data[table_name], dict):
        return {}
    table_stats = stats_data[table_name]
    return {col: _arrow_type_from_name(spec.get("datatype", "string"))
            for col, spec in table_stats.items()}

def expected_num_columns(stats_data: dict, table_name: str):
    if table_name in stats_data and isinstance(stats_data[table_name], dict):
        n = len(stats_data[table_name])
        return max(1, n)
    return None  # 不明


# ---------------- converter ----------------

def convert_csv_to_parquet(dataset_name: str, csv_file: str, output_dir: str, stats_data: dict) -> str:
    print(f"Converting {csv_file} -> Parquet ...")
    table_name = Path(csv_file).stem

    column_types = build_column_types(stats_data, table_name)
    exp_cols = expected_num_columns(stats_data, table_name)

    # 1) 区切り＆ヘッダ自動判定（環境変数で上書き可能）
    delim, has_header = sniff_csv_format(csv_file)
    delim = os.environ.get("CSV_DELIMITER_OVERRIDE", delim)
    has_header_env = os.environ.get("CSV_HAS_HEADER_OVERRIDE", "")
    if has_header_env.lower() in {"0", "false", "no"}:
        has_header = False
    elif has_header_env.lower() in {"1", "true", "yes"}:
        has_header = True

    read_opts = pacsv.ReadOptions(
        use_threads=True,
        block_size=1 << 22,
        autogenerate_column_names=not has_header,
        skip_rows=0,
        skip_rows_after_names=0
    )
    parse_opts = pacsv.ParseOptions(
        delimiter=delim,
        quote_char='"',
        double_quote=True,
        escape_char=False,
        newlines_in_values=True
    )
    convert_opts = pacsv.ConvertOptions(
        column_types=column_types if has_header else None,
        strings_can_be_null=True,
        null_values=["", "NULL", "null", "NaN", "nan"]
    )

    def try_read(d, header_flag):
        ro = pacsv.ReadOptions(
            use_threads=True,
            block_size=1 << 22,
            autogenerate_column_names=not header_flag
        )
        po = pacsv.ParseOptions(
            delimiter=d, quote_char='"', double_quote=True,
            escape_char=False, newlines_in_values=True
        )
        co = pacsv.ConvertOptions(
            column_types=column_types if header_flag else None,
            strings_can_be_null=True,
            null_values=["", "NULL", "null", "NaN", "nan"]
        )
        return pacsv.read_csv(csv_file, read_options=ro, parse_options=po, convert_options=co)

    # 2) 読み込み + フォールバック（期待列数ベース）
    try:
        table = pacsv.read_csv(csv_file, read_options=read_opts, parse_options=parse_opts, convert_options=convert_opts)
        if table.num_columns <= 1:
            # 期待列数>1 なのに 1列 → 区切り推定ミスの可能性でフォールバック
            if exp_cols is not None and exp_cols > 1:
                raise ValueError("Suspicious single-column parse; fallback trying other delimiters.")
            # exp_cols が 1 or 不明 → 正当な1列として受け入れる
    except Exception:
        success = None
        for d in CANDIDATE_DELIMS:
            for header_flag in (True, False):
                try:
                    t = try_read(d, header_flag)
                    # 成功判定：期待列数が分かるなら一致、分からなければ >=1
                    if (exp_cols is not None and t.num_columns == exp_cols) or \
                       (exp_cols is None and t.num_columns >= 1):
                        success = t
                        print(f"Fallback succeeded with delimiter={repr(d)}, has_header={header_flag}, cols={t.num_columns}")
                        break
                except Exception:
                    pass
            if success:
                break
        if not success:
            raise
        table = success

    # 2.5) ヘッダなし・1列・統計にカラム名があるならリネーム
    if table.num_columns == 1 and not has_header and table_name in stats_data:
        # 統計JSONの最初のキーを列名に採用（順序が重要ならOrderedDictでJSONを読む）
        first_col = next(iter(stats_data[table_name].keys()))
        table = table.rename_columns([first_col])

    # 3) 出力
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{table_name}.parquet")
    pq.write_table(
        table,
        output_file,
        compression="snappy",
        use_dictionary=True,
        data_page_size=1 << 20
    )
    print(f"✓ Created {output_file}")
    return output_file


def process_dataset(dataset_name: str):
    dataset_path = f"zero-shot_datasets/{dataset_name}"
    if not os.path.exists(dataset_path):
        print(f"Error: Dataset directory {dataset_path} not found")
        return

    print(f"\n=== Processing dataset: {dataset_name} ===")
    stats_data = load_column_statistics(dataset_path)
    print(f"Loaded statistics for {len(stats_data)} tables")

    output_dir = f"zero-shot_datasets/{dataset_name}/parquet_data"
    os.makedirs(output_dir, exist_ok=True)

    csv_files = [os.path.join(dataset_path, f)
                 for f in os.listdir(dataset_path)
                 if f.lower().endswith((".csv", ".tsv", ".txt"))]

    if not csv_files:
        print(f"No CSV files found in {dataset_path}")
        return

    print(f"Found {len(csv_files)} CSV files")
    ok = 0
    for csv_file in csv_files:
        try:
            convert_csv_to_parquet(dataset_name, csv_file, output_dir, stats_data)
            ok += 1
        except Exception as e:
            print(f"Error converting {csv_file}: {e}")

    print(f"\n✓ Successfully converted {ok} files to Parquet")


def main():
    if len(sys.argv) != 2:
        print("Usage: python csv_to_parquet.py <dataset_name>")
        print("Example: python csv_to_parquet.py walmart")
        sys.exit(1)

    dataset_name = sys.argv[1]
    process_dataset(dataset_name)


if __name__ == "__main__":
    main()
