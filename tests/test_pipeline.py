import os
import sqlite3

import pandas as pd

from main import (
    transform,
    create_database,
    load_to_database,
    run_query
)


# =========================================================
# TESTING TRANSFORM
# =========================================================

test_data = pd.DataFrame({
    "Country": ["Germany", "France", "Germany"],
    "GDP_USD_Million": ["4,308,854", "invalid", "4,308,854"],
    "Year": ["2023", "2023", "2023"]
})

clean_df, rejected_df, duplicate_df = transform(test_data)

assert len(clean_df) == 1
assert len(rejected_df) == 1
assert len(duplicate_df) == 1

assert rejected_df.iloc[0]["Country"] == "France"
assert duplicate_df.iloc[0]["Country"] == "Germany"

assert clean_df.iloc[0]["Country"] == "Germany"
assert clean_df.iloc[0]["GDP_USD_Million"] == 4308854.0
assert clean_df.iloc[0]["Year"] == 2023


test_data_2 = pd.DataFrame({
    "Country": ["Germany", "Germany", "Germany"],
    "GDP_USD_Million": ["4,308,854", "4,500,000", "4,308,854"],
    "Year": ["2023", "2024", "2023"]
})

clean_df, rejected_df, duplicate_df = transform(test_data_2)

assert len(clean_df) == 2
assert len(duplicate_df) == 1

assert clean_df["Year"].tolist() == [2023, 2024]
assert duplicate_df.iloc[0]["Year"] == 2023

print("PASSED: Basic data transformation test")


# =========================================================
# TESTING MISSING VALUES
# =========================================================

test_data_3 = pd.DataFrame({
    "Country": ["Germany", "France", "Germany"],
    "GDP_USD_Million": ["4,308,854", None, "4,308,854"],
    "Year": ["2023", "2023", None]
})

clean_df, rejected_df, duplicate_df = transform(test_data_3)

assert len(clean_df) == 1
assert len(rejected_df) == 2
assert len(duplicate_df) == 0

assert rejected_df["GDP_USD_Million"].isna().any()
assert rejected_df["Year"].isna().any()

print("PASSED: Missing values rejection test")


# =========================================================
# TESTING EMPTY STRINGS
# =========================================================

test_data_4 = pd.DataFrame({
    "Country": ["Germany", "", "France", "Spain"],
    "GDP_USD_Million": ["4,308,854", "3,000,000", "   ", "1,500,000"],
    "Year": ["2023", "2023", "2023", ""]
})

clean_df, rejected_df, duplicate_df = transform(test_data_4)

assert len(clean_df) == 1
assert len(rejected_df) == 3
assert len(duplicate_df) == 0

assert clean_df.iloc[0]["Country"] == "Germany"

print("PASSED: Empty strings rejection test")


# =========================================================
# TESTING REJECTED DATA BEFORE DUPLICATES
# =========================================================

test_data_5 = pd.DataFrame({
    "Country": ["Germany", "France", "Germany", "Germany"],
    "GDP_USD_Million": ["", "4,500,000", "4,329,990", "4,600,000"],
    "Year": ["2023", "2023", "2023", "2023"]
})

clean_df, rejected_df, duplicate_df = transform(test_data_5)

assert len(clean_df) == 2
assert len(rejected_df) == 1
assert len(duplicate_df) == 1

assert clean_df["Country"].tolist() == ["France", "Germany"]
assert rejected_df.iloc[0]["Country"] == "Germany"
assert duplicate_df.iloc[0]["Country"] == "Germany"

print("PASSED: Rejected before considering duplicates")


# =========================================================
# TESTING DATABASE
# =========================================================

test_db = "database/test_world_economies.db"

# Start every test run with a clean database
if os.path.exists(test_db):
    os.remove(test_db)


test_data_db = pd.DataFrame({
    "Country": ["Germany", "France"],
    "GDP_USD_Million": [4308854.0, 3031000.0],
    "Year": [2023, 2023]
})

create_database(test_db, write_log=False)
load_to_database(test_data_db, test_db)

conn = sqlite3.connect(test_db)
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM countries")
country_count = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM gdp_records")
gdp_count = cursor.fetchone()[0]

assert country_count == 2
assert gdp_count == 2

conn.close()

print("PASSED: Database working correctly")


# =========================================================
# TESTING DUPLICATE INSERTS
# =========================================================

load_to_database(test_data_db, test_db)

conn = sqlite3.connect(test_db)
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM countries")
country_count = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM gdp_records")
gdp_count = cursor.fetchone()[0]

assert country_count == 2
assert gdp_count == 2

conn.close()

print("PASSED: Duplicate database records ignored")


# =========================================================
# TESTING FOREIGN KEY CONSTRAINT
# =========================================================

conn = sqlite3.connect(test_db)
cursor = conn.cursor()

cursor.execute("PRAGMA foreign_keys = ON")

try:
    cursor.execute(
        """
        INSERT INTO gdp_records(
            country_id,
            year,
            gdp_usd_million
        )
        VALUES (?, ?, ?)
        """,
        (9999, 2023, 1000000.0)
    )

    conn.commit()

    assert False, "Foreign key constraint did not work"

except sqlite3.IntegrityError:
    print("PASSED: Foreign key constraint working correctly")

finally:
    conn.close()


# =========================================================
# TESTING SAME COUNTRY WITH DIFFERENT YEAR
# =========================================================

new_year_data = pd.DataFrame({
    "Country": ["Germany"],
    "GDP_USD_Million": [4500000.0],
    "Year": [2024]
})

load_to_database(new_year_data, test_db)

conn = sqlite3.connect(test_db)
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM countries")
country_count = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM gdp_records")
gdp_count = cursor.fetchone()[0]

assert country_count == 2
assert gdp_count == 3

conn.close()

print("PASSED: Same country can have GDP records for different years")


# =========================================================
# TESTING STORED DATA WITH JOIN
# =========================================================

conn = sqlite3.connect(test_db)
cursor = conn.cursor()

cursor.execute(
    """
    SELECT
        c.country_name,
        gr.year,
        gr.gdp_usd_million
    FROM countries AS c

    INNER JOIN gdp_records AS gr
        ON c.country_id = gr.country_id

    ORDER BY c.country_name, gr.year
    """
)

results = cursor.fetchall()

conn.close()

expected_results = [
    ("France", 2023, 3031000.0),
    ("Germany", 2023, 4308854.0),
    ("Germany", 2024, 4500000.0)
]

assert results == expected_results

print("PASSED: JOIN returned correct stored data")


# =========================================================
# TESTING RUN_QUERY
# =========================================================

results = run_query(test_db, write_log=False)

expected_query_results = [
    ("Germany", 2024, 4500000.0),
    ("Germany", 2023, 4308854.0),
    ("France", 2023, 3031000.0)
]

assert results == expected_query_results

print("PASSED: run_query returned correct results")


# =========================================================
# CLEANUP
# =========================================================

if os.path.exists(test_db):
    os.remove(test_db)

print("PASSED: Test database cleaned up")