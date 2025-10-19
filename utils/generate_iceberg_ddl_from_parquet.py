"""
Generate Iceberg DDL from actual Parquet file schemas
"""

import os
import sys
import pyarrow as pa
import pyarrow.parquet as pq


# SQL reserved keywords that need to be quoted
SQL_RESERVED_KEYWORDS = {
    'order', 'group', 'table', 'select', 'from', 'where', 'join', 'inner', 'outer',
    'left', 'right', 'on', 'as', 'and', 'or', 'not', 'null', 'true', 'false',
    'insert', 'update', 'delete', 'create', 'drop', 'alter', 'index', 'key',
    'primary', 'foreign', 'unique', 'constraint', 'references', 'default',
    'check', 'like', 'in', 'between', 'exists', 'case', 'when', 'then', 'else',
    'end', 'union', 'all', 'distinct', 'having', 'limit', 'offset', 'by',
    'asc', 'desc', 'cast', 'interval', 'timestamp', 'date', 'time',
}


def quote_if_reserved(identifier: str) -> str:
    """
    Quote identifier if it's a SQL reserved keyword
    """
    if identifier.lower() in SQL_RESERVED_KEYWORDS:
        return f'"{identifier}"'
    return identifier


def convert_arrow_type_to_iceberg(arrow_type: pa.DataType) -> str:
    """
    Convert PyArrow data type to Iceberg/Trino data type
    """
    type_str = str(arrow_type)
    
    # Integer types
    if type_str == 'int8':
        return "TINYINT"
    if type_str == 'int16':
        return "SMALLINT"
    if type_str == 'int32':
        return "INTEGER"
    if type_str == 'int64':
        return "BIGINT"
    
    # Unsigned integers (map to next larger signed type)
    if type_str == 'uint8':
        return "SMALLINT"
    if type_str == 'uint16':
        return "INTEGER"
    if type_str == 'uint32':
        return "BIGINT"
    if type_str == 'uint64':
        return "DECIMAL(20,0)"  # BIGINT may overflow
    
    # Floating point
    if type_str == 'float':
        return "REAL"
    if type_str == 'double':
        return "DOUBLE"
    
    # Decimal
    if type_str.startswith('decimal'):
        # Extract precision and scale
        return arrow_type.__str__().upper().replace('DECIMAL', 'DECIMAL')
    
    # String types
    if type_str == 'string' or type_str == 'large_string':
        return "VARCHAR"
    if type_str.startswith('string['):
        # Fixed-length string - not directly supported, use VARCHAR
        return "VARCHAR"
    
    # Binary
    if type_str == 'binary' or type_str == 'large_binary':
        return "VARBINARY"
    
    # Boolean
    if type_str == 'bool':
        return "BOOLEAN"
    
    # Date/Time
    if type_str == 'date32' or type_str == 'date64':
        return "DATE"
    if type_str.startswith('timestamp'):
        return "TIMESTAMP"
    if type_str.startswith('time'):
        return "TIME"
    
    # Null type (column with all nulls)
    if type_str == 'null':
        return "VARCHAR"  # Default to VARCHAR for null columns
    
    # Default: VARCHAR for unknown types
    print(f"  [warn] Unknown Arrow type '{type_str}', using VARCHAR")
    return "VARCHAR"


def generate_ddl_from_parquet(dataset_name: str, full_table_name: str = None):
    """
    Generate Iceberg DDL based on actual Parquet file schemas
    
    Args:
        dataset_name: Name of the dataset
        full_table_name: Full table name template (e.g., "iceberg.{dataset}.{table}")
    """
    parquet_dir = f"zero-shot_datasets/{dataset_name}/parquet_data"
    
    if not os.path.exists(parquet_dir):
        print(f"Error: {parquet_dir} not found")
        return None
    
    parquet_files = sorted([f for f in os.listdir(parquet_dir) if f.endswith('.parquet')])
    
    if not parquet_files:
        print(f"No parquet files found in {parquet_dir}")
        return None
    
    ddl_lines = []
    
    for pfile in parquet_files:
        table_name = pfile.replace('.parquet', '')
        file_path = os.path.join(parquet_dir, pfile)
        
        try:
            # Read parquet schema
            parquet_file = pq.ParquetFile(file_path)
            schema = parquet_file.schema_arrow
            
            # Quote table name if it's a reserved keyword
            quoted_table_name = quote_if_reserved(table_name)
            
            # Generate full table name
            if full_table_name:
                full_name = full_table_name.format(table=quoted_table_name)
            else:
                full_name = quoted_table_name
            
            # Generate DROP TABLE
            ddl_lines.append(f"DROP TABLE IF EXISTS {full_name};")
            ddl_lines.append("")
            
            # Generate CREATE TABLE
            ddl_lines.append(f"CREATE TABLE IF NOT EXISTS {full_name} (")
            
            # Generate columns
            columns = []
            for i, field in enumerate(schema):
                col_name = field.name
                arrow_type = field.type
                iceberg_type = convert_arrow_type_to_iceberg(arrow_type)
                
                # Quote column name if it's a reserved keyword
                quoted_col_name = quote_if_reserved(col_name)
                
                # Check if nullable
                # In Iceberg, columns are nullable by default, so we only add NOT NULL if needed
                # However, Parquet doesn't enforce NOT NULL, so we'll keep all as nullable
                columns.append(f"  {quoted_col_name} {iceberg_type}")
            
            # Write columns
            for i, col_def in enumerate(columns):
                if i < len(columns) - 1:
                    ddl_lines.append(f"{col_def},")
                else:
                    ddl_lines.append(f"{col_def}")
            
            ddl_lines.append(");")
            ddl_lines.append("")
            
        except Exception as e:
            print(f"Error reading {pfile}: {e}")
            continue
    
    return '\n'.join(ddl_lines)


def process_dataset(dataset_name: str, with_schema: bool = False):
    """
    Generate Iceberg DDL for a dataset from Parquet files
    """
    # For scaled_* datasets, use the name without scaled_ prefix for schema/table names
    schema_dataset_name = dataset_name.replace("scaled_", "", 1) if dataset_name.startswith("scaled_") else dataset_name
    
    # Generate full table name template: iceberg.{dataset}.{table}
    # Use schema_dataset_name instead of dataset_name for the template
    if with_schema:
        full_table_name = f"iceberg.{schema_dataset_name}.{{table}}"
    else:
        full_table_name = None
    
    ddl = generate_ddl_from_parquet(dataset_name, full_table_name)
    
    if not ddl:
        return False
    
    # Save to file
    # For scaled_* datasets, save to the directory without scaled_ prefix
    save_dataset_name = schema_dataset_name  # This already has scaled_ removed if applicable
    filename = "iceberg.sql"
    output_file = f"zero-shot_datasets/{save_dataset_name}/schema_sql/{filename}"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(ddl)
    
    print(f"✓ Generated {dataset_name}: {output_file}")
    return True


def find_all_datasets_with_parquet():
    """
    Find all datasets that have parquet_data directory
    """
    datasets = []
    zero_shot_dir = "zero-shot_datasets"
    if not os.path.exists(zero_shot_dir):
        return datasets
    
    for item in os.listdir(zero_shot_dir):
        item_path = os.path.join(zero_shot_dir, item)
        if os.path.isdir(item_path):
            parquet_dir = os.path.join(item_path, "parquet_data")
            if os.path.exists(parquet_dir):
                datasets.append(item)
    
    return sorted(datasets)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate Iceberg DDL from actual Parquet file schemas"
    )
    parser.add_argument(
        "dataset",
        type=str,
        nargs='?',
        help="Dataset name. If not specified, processes all datasets with parquet_data."
    )
    parser.add_argument(
        "--with-schema",
        action="store_true",
        help="Include full table name (iceberg.dataset_name.table_name) in DDL"
    )
    
    args = parser.parse_args()
    
    print("=== Iceberg DDL Generator (from Parquet) ===\n")
    
    if args.dataset:
        # Process specific dataset
        success = process_dataset(args.dataset, args.with_schema)
        if success:
            print("\n✓ DDL generation complete")
        else:
            print("\n✗ DDL generation failed")
            sys.exit(1)
    else:
        # Process all datasets
        datasets = find_all_datasets_with_parquet()
        if not datasets:
            print("No datasets with parquet_data found")
            sys.exit(1)
        
        print(f"Found {len(datasets)} datasets with parquet_data\n")
        
        success_count = 0
        for dataset in datasets:
            if process_dataset(dataset, args.with_schema):
                success_count += 1
        
        print(f"\n=== Summary ===")
        print(f"✓ Successfully generated: {success_count}/{len(datasets)} datasets")


if __name__ == "__main__":
    main()

