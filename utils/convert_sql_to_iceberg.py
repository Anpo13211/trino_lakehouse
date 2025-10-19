"""
Convert PostgreSQL DDL to Iceberg DDL format
"""

import os
import re
import sys


def convert_postgres_type_to_iceberg(pg_type: str) -> str:
    """
    Convert PostgreSQL data type to Iceberg/Trino data type
    """
    pg_type = pg_type.strip().lower()
    
    # Character types
    if pg_type.startswith('char(') or pg_type.startswith('character('):
        return pg_type.upper().replace('CHARACTER(', 'CHAR(')
    if pg_type.startswith('varchar(') or pg_type.startswith('character varying('):
        size = re.search(r'\((\d+)\)', pg_type)
        if size:
            return f"VARCHAR({size.group(1)})"
        return "VARCHAR"
    if pg_type == 'text':
        return "VARCHAR"
    
    # Numeric types
    if pg_type == 'integer' or pg_type == 'int' or pg_type == 'int4':
        return "INTEGER"
    if pg_type == 'bigint' or pg_type == 'int8':
        return "BIGINT"
    if pg_type == 'smallint' or pg_type == 'int2':
        return "SMALLINT"
    if pg_type == 'double precision' or pg_type == 'float8':
        return "DOUBLE"
    if pg_type == 'real' or pg_type == 'float4':
        return "REAL"
    if pg_type.startswith('decimal(') or pg_type.startswith('numeric('):
        return pg_type.upper().replace('NUMERIC', 'DECIMAL')
    
    # Date/Time types
    if pg_type == 'timestamp' or pg_type.startswith('timestamp('):
        return "TIMESTAMP"
    if pg_type == 'date':
        return "DATE"
    if pg_type == 'time' or pg_type.startswith('time('):
        return "TIME"
    
    # Boolean
    if pg_type == 'boolean' or pg_type == 'bool':
        return "BOOLEAN"
    
    # Default: return as-is (uppercase)
    return pg_type.upper()


def convert_postgres_ddl_to_iceberg(postgres_sql: str, schema_name: str = None) -> str:
    """
    Convert PostgreSQL DDL to Iceberg DDL
    """
    lines = postgres_sql.split('\n')
    iceberg_lines = []
    
    in_create_table = False
    columns = []
    table_name = None
    
    for line in lines:
        stripped = line.strip()
        
        # Skip empty lines initially
        if not stripped:
            if in_create_table:
                iceberg_lines.append('')
            continue
        
        # Handle DROP TABLE
        if stripped.upper().startswith('DROP TABLE'):
            # Extract table name
            match = re.search(r'DROP TABLE IF EXISTS ["\']?(\w+)["\']?', stripped, re.IGNORECASE)
            if match:
                tbl = match.group(1)
                if schema_name:
                    iceberg_lines.append(f"DROP TABLE IF EXISTS {schema_name}.{tbl};")
                else:
                    iceberg_lines.append(f"DROP TABLE IF EXISTS {tbl};")
            iceberg_lines.append('')
            continue
        
        # Handle CREATE TABLE
        if stripped.upper().startswith('CREATE TABLE'):
            in_create_table = True
            match = re.search(r'CREATE TABLE ["\']?(\w+)["\']?', stripped, re.IGNORECASE)
            if match:
                table_name = match.group(1)
                if schema_name:
                    iceberg_lines.append(f"CREATE TABLE IF NOT EXISTS {schema_name}.{table_name} (")
                else:
                    iceberg_lines.append(f"CREATE TABLE IF NOT EXISTS {table_name} (")
            columns = []
            continue
        
        # Handle column definitions
        if in_create_table:
            # Skip PRIMARY KEY constraints
            if 'PRIMARY KEY' in stripped.upper():
                continue
            
            # Skip CONSTRAINT definitions
            if stripped.upper().startswith('CONSTRAINT'):
                continue
            
            # Handle closing parenthesis
            if stripped.startswith(')'):
                # Write all columns
                for i, col in enumerate(columns):
                    if i < len(columns) - 1:
                        iceberg_lines.append(f"  {col},")
                    else:
                        iceberg_lines.append(f"  {col}")
                iceberg_lines.append(');')
                iceberg_lines.append('')
                in_create_table = False
                columns = []
                table_name = None
                continue
            
            # First, remove DEFAULT clauses from the line (Iceberg doesn't support them)
            # Handle: DEFAULT NULL, DEFAULT 'value', DEFAULT value, DEFAULT (expression)
            line_no_default = re.sub(r'DEFAULT\s+(?:NULL|\'[^\']*\'|\"[^\"]*\"|\([^)]*\)|[^\s,]+)', '', stripped.rstrip(','), flags=re.IGNORECASE).strip()
            
            # Normalize whitespace (multiple spaces to single space)
            line_normalized = re.sub(r'\s+', ' ', line_no_default).strip()
            
            # Parse column definition
            # Format: "column_name" type [NOT NULL]
            # Type can be: integer, varchar(n), decimal(p,s), double precision, etc.
            # Use a more specific pattern to capture types correctly
            col_match = re.match(r'["\']?(\w+)["\']?\s+((?:double\s+precision|character\s+varying|\w+)(?:\([^)]+\))?)\s*(.*)', line_normalized, re.IGNORECASE)
            if col_match:
                col_name = col_match.group(1)
                col_type = col_match.group(2)
                col_constraints = col_match.group(3)
                
                # Convert type
                iceberg_type = convert_postgres_type_to_iceberg(col_type)
                
                # Build column definition
                col_def = f"{col_name} {iceberg_type}"
                
                # Handle NOT NULL (Iceberg supports this)
                # Make sure we match the full "NOT NULL" phrase, not just "NOT"
                if re.search(r'\bNOT\s+NULL\b', col_constraints, re.IGNORECASE):
                    col_def += " NOT NULL"
                
                columns.append(col_def)
    
    return '\n'.join(iceberg_lines)


def process_dataset(dataset_name: str, schema_name: str = None):
    """
    Convert postgres.sql to iceberg.sql for a dataset
    """
    dataset_path = f"zero-shot_datasets/{dataset_name}"
    postgres_file = os.path.join(dataset_path, "schema_sql", "postgres.sql")
    iceberg_file = os.path.join(dataset_path, "schema_sql", "iceberg.sql")
    
    if not os.path.exists(postgres_file):
        print(f"Skipping {dataset_name}: postgres.sql not found")
        return False
    
    # Read PostgreSQL DDL
    with open(postgres_file, 'r', encoding='utf-8') as f:
        postgres_sql = f.read()
    
    # Convert to Iceberg DDL
    iceberg_sql = convert_postgres_ddl_to_iceberg(postgres_sql, schema_name or dataset_name)
    
    # Write Iceberg DDL
    os.makedirs(os.path.dirname(iceberg_file), exist_ok=True)
    with open(iceberg_file, 'w', encoding='utf-8') as f:
        f.write(iceberg_sql)
    
    print(f"✓ Converted {dataset_name}: {postgres_file} -> {iceberg_file}")
    return True


def find_all_datasets_with_postgres_sql():
    """
    Find all datasets that have schema_sql/postgres.sql
    """
    datasets = []
    zero_shot_dir = "zero-shot_datasets"
    if not os.path.exists(zero_shot_dir):
        return datasets
    
    for item in os.listdir(zero_shot_dir):
        item_path = os.path.join(zero_shot_dir, item)
        if os.path.isdir(item_path):
            postgres_file = os.path.join(item_path, "schema_sql", "postgres.sql")
            if os.path.exists(postgres_file):
                datasets.append(item)
    
    return sorted(datasets)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Convert PostgreSQL DDL to Iceberg DDL format"
    )
    parser.add_argument(
        "dataset",
        type=str,
        nargs='?',
        help="Dataset name. If not specified, converts all datasets."
    )
    parser.add_argument(
        "--with-schema",
        action="store_true",
        help="Include schema name (iceberg.dataset_name) in table names"
    )
    
    args = parser.parse_args()
    
    print("=== PostgreSQL to Iceberg DDL Converter ===\n")
    
    if args.dataset:
        # Convert specific dataset
        schema_name = f"iceberg.{args.dataset}" if args.with_schema else None
        success = process_dataset(args.dataset, schema_name)
        if success:
            print("\n✓ Conversion complete")
        else:
            print("\n✗ Conversion failed")
            sys.exit(1)
    else:
        # Convert all datasets
        datasets = find_all_datasets_with_postgres_sql()
        if not datasets:
            print("No datasets with postgres.sql found")
            sys.exit(1)
        
        print(f"Found {len(datasets)} datasets with postgres.sql\n")
        
        success_count = 0
        for dataset in datasets:
            schema_name = f"iceberg.{dataset}" if args.with_schema else None
            if process_dataset(dataset, schema_name):
                success_count += 1
        
        print(f"\n=== Summary ===")
        print(f"✓ Successfully converted: {success_count}/{len(datasets)} datasets")


if __name__ == "__main__":
    main()

