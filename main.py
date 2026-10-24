import sqlite3
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup as BS


# Path files
log_file = "logs/log_file.txt"
db_name = "database/World_Economies.db"

# Define URL
url = (
    "https://web.archive.org/web/20230902185326/"
    "https://en.wikipedia.org/wiki/List_of_countries_by_GDP_%28nominal%29"
)


def l_m(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H-%M-%S")

    with open(log_file, "a") as file:
        file.write(f"{timestamp} - {message}\n")


def extract(url):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=15
        )

        response.raise_for_status()

    except requests.RequestException as e:
        l_m(f"Extraction HTTP error: {e}")
        raise

    soup = BS(response.text, "html.parser")

    table = soup.find_all("table")

    gdp_table = table[2]
    rows = gdp_table.find_all("tr")

    data = []

    for row in rows[2:]:
        cols = row.find_all(["th", "td"])

        country = cols[0].get_text(strip=True)

        if country == "World":
            continue

        country_data = {
            "Country": cols[0].get_text(strip=True),
            "GDP_USD_Million": cols[2].get_text(strip=True),
            "Year": cols[3].get_text(strip=True)
        }

        data.append(country_data)

    return pd.DataFrame(data)


def transform(df):
    df = df.copy()

    df["GDP_USD_Million"] = df["GDP_USD_Million"].str.replace(",", "")

    df["GDP_USD_Million"] = pd.to_numeric(
        df["GDP_USD_Million"],
        errors="coerce"
    )

    df["Year"] = df["Year"].str.extract(r"(\d{4})")

    df["Year"] = pd.to_numeric(
        df["Year"],
        errors="coerce"
    )

    # Establish required columns
    required_columns = [
        "Country",
        "GDP_USD_Million",
        "Year"
    ]

    # Replacing empty string or spaces with NA
    df[required_columns] = df[required_columns].replace(
        r"^\s*$",
        pd.NA,
        regex=True
    )

    # True if any required value is missing in the row
    missing_mask = df[required_columns].isna().any(axis=1)

    # Separate rows with missing required values
    rejected_df = df[missing_mask].copy()

    # Keep only valid rows for further transformation
    df = df[~missing_mask].copy()

    df["Year"] = df["Year"].astype(int)

    duplicate_df = df[
        df.duplicated(
            subset=["Country", "Year"],
            keep="first"
        )
    ].copy()

    df = df.drop_duplicates(
        subset=["Country", "Year"]
    )

    return df, rejected_df, duplicate_df


def save_data(clean_df, rejected_df, duplicate_df):
    clean_df.to_csv(
        "data/valid_gdp.csv",
        index=False
    )

    rejected_df.to_csv(
        "data/rejected_gdp.csv",
        index=False
    )

    duplicate_df.to_csv(
        "data/duplicated_country.csv",
        index=False
    )


def create_database(db_name, write_log=True):
    conn = sqlite3.connect(db_name)

    try:
        cursor = conn.cursor()

        cursor.execute(
            "PRAGMA foreign_keys = ON"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS countries(
                country_id INTEGER PRIMARY KEY AUTOINCREMENT,
                country_name TEXT NOT NULL UNIQUE
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS gdp_records(
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                country_id INTEGER NOT NULL,
                year INTEGER NOT NULL,
                gdp_usd_million REAL NOT NULL,
                FOREIGN KEY (country_id)
                    REFERENCES countries(country_id),
                UNIQUE (country_id, year)
            )
            """
        )

        conn.commit()

        if write_log:
            l_m("Database was created")

    except sqlite3.Error as e:
        if write_log:
            l_m(
                f"We had an error while trying to execute SQL: {e}"
            )

        conn.rollback()
        raise

    finally:
        conn.close()


def load_to_database(df, db_name):
    conn = sqlite3.connect(db_name)

    try:
        cursor = conn.cursor()

        cursor.execute(
            "PRAGMA foreign_keys = ON"
        )

        for index, row in df.iterrows():
            country = row["Country"]

            cursor.execute(
                """
                INSERT OR IGNORE INTO countries(
                    country_name
                )
                VALUES(?)
                """,
                (country,)
            )

        for index, row in df.iterrows():
            country = row["Country"]

            cursor.execute(
                """
                SELECT country_id
                FROM countries
                WHERE country_name = ?
                """,
                (country,)
            )

            country_record = cursor.fetchone()

            if country_record is None:
                raise ValueError(
                    f"Country not found: {country}"
                )

            country_id = country_record[0]

            cursor.execute(
                """
                INSERT OR IGNORE INTO gdp_records(
                    country_id,
                    year,
                    gdp_usd_million
                )
                VALUES (?, ?, ?)
                """,
                (
                    country_id,
                    int(row["Year"]),
                    float(row["GDP_USD_Million"])
                )
            )

        conn.commit()

    except sqlite3.Error as e:
        l_m(
            f"We had an error while trying to execute SQL: {e}"
        )

        print(
            f"We had an error while trying to execute SQL: {e}"
        )

        conn.rollback()
        raise

    except Exception as e:
        conn.rollback()

        l_m(
            f"Database loading error: {e}"
        )

        raise

    finally:
        conn.close()


def run_query(db_name, write_log=True):
    conn = sqlite3.connect(db_name)

    try:
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

            ORDER BY gr.gdp_usd_million DESC
            LIMIT 10;
            """
        )

        results = cursor.fetchall()

        for row in results:
            print(row)

        if write_log:
            l_m("Query worked")

        return results

    finally:
        conn.close()


def main():
    l_m(
        "Preliminaries completed. Initiating ETL process"
    )

    l_m("Starting Extraction")

    df = extract(url)

    l_m("Extraction completed")

    l_m(
        f"Before transformation: {len(df)}"
    )

    # Checking NA values before transformation
    invalid_gdp = pd.to_numeric(
        df["GDP_USD_Million"].str.replace(",", ""),
        errors="coerce"
    ).isna().sum()

    l_m(
        f"Duplicated countries before transformation: "
        f"{df.duplicated(subset=['Country', 'Year']).sum()}"
    )

    l_m(
        f"Invalid GDP values before cleaning: {invalid_gdp}"
    )

    l_m("Starting data transformation")

    clean_df, rejected_df, duplicate_df = transform(df)

    save_data(
        clean_df,
        rejected_df,
        duplicate_df
    )

    l_m(
        f"Rejected GDP records: {len(rejected_df)}"
    )

    l_m(
        f"Duplicated country records: {len(duplicate_df)}"
    )

    l_m(
        f"Duplicated countries after transformation: "
        f"{clean_df.duplicated(subset=['Country', 'Year']).sum()}"
    )

    l_m(
        f"After transformation: {len(clean_df)}"
    )

    l_m("Transformation completed")

    l_m("Creating Database")

    create_database(db_name)

    l_m("Loading data into Data Base")

    load_to_database(
        clean_df,
        db_name
    )

    l_m("Running queries to test the db")

    run_query(db_name)


if __name__ == "__main__":
    main()