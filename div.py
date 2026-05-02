import csv
import sqlite3
from datetime import datetime
from collections import defaultdict

DB_PATH = "dividends.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS dividends (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        ticker TEXT NOT NULL,
        amount REAL NOT NULL,
        currency TEXT NOT NULL,
        account TEXT NOT NULL,
        source_file TEXT,
        UNIQUE(date, ticker, amount, account)
    )
    """)

    conn.commit()
    conn.close()


def parse_amount(amount_str):
    # "609,50" -> 609.50
    return float(amount_str.replace(',', '.'))


def extract_ticker(operation):
    # "Wypłata dywidendy PCCROKITA"
    return operation.replace('Wypłata dywidendy', '').strip()
    return operation.split('dywidendy')[-1].strip()


def parse_dividend_file(file_path, account):
    encodings = ['utf-8', 'cp1250', 'iso-8859-2', 'cp852', 'latin2']
    last_error = None

    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                reader = csv.reader(f, delimiter=';')

                header = next(reader)  # skip header

                results = []

                for row in reader:
                    if len(row) < 4:
                        continue

                    date_str = row[0]
                    operation = row[1]
                    amount_str = row[3]
                    currency = row[4] if len(row) > 4 else 'PLN'

                    if 'Wyp' in operation and 'dywidendy' in operation:
                        ticker = extract_ticker(operation)
                        date = datetime.strptime(date_str, '%Y-%m-%d').date()
                        amount = parse_amount(amount_str)

                        results.append((
                            str(date),
                            ticker,
                            amount,
                            currency,
                            account,
                            file_path
                        ))

                return results

        except Exception as e:
            last_error = e

    raise Exception(f"Failed to process {file_path}: {last_error}")


def insert_dividends(rows):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.executemany("""
    INSERT OR IGNORE INTO dividends
    (date, ticker, amount, currency, account, source_file)
    VALUES (?, ?, ?, ?, ?, ?)
    """, rows)

    conn.commit()
    conn.close()


# ---- RUN ----

if __name__ == "__main__":
    init_db()

    ike_rows = parse_dividend_file("input/ike.csv", "IKE")
    ikze_rows = parse_dividend_file("input/ikze.csv", "IKZE")
    gpw_rows = parse_dividend_file("input/gpw.csv", "GPW")

    insert_dividends(ike_rows + ikze_rows + gpw_rows)

    print(f"Inserted {len(ike_rows) + len(ikze_rows) + len(gpw_rows)} rows (duplicates ignored)")