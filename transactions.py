"""transactions.py

Robust transaction analysis module for hist.csv
- Reads CSV with encoding fallbacks
- Normalizes column names and types
- Computes summary statistics
- Produces several plots saved as PNG in an output directory
- Provides a CLI entrypoint

Usage:
    python transactions.py --input C:\\path\\to\\hist.csv --outdir output

"""
from __future__ import annotations
import argparse
import os
import io
import sys
from typing import Tuple, Dict, Any
from pathlib import Path

# Import third-party libraries with a helpful error if missing
try:
    import pandas as pd
    import matplotlib
    # Use a non-interactive backend so plotting works inside Flask threads/processes
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import seaborn as sns
    import numpy as np
    from datetime import datetime
except Exception as e:  # ImportError or similar
    msg = (
        "Missing required Python packages for transactions analysis.\n"
        "Please install the dependencies listed in requirements.txt, for example:\n"
        "    python -m pip install -r requirements.txt\n"
        "The modules required include: pandas, matplotlib, seaborn, numpy\n"
        f"Underlying error: {e}"
    )
    print(msg, file=sys.stderr)
    raise SystemExit(1)

# Set plotting style
sns.set(style="whitegrid")
plt.rcParams.update({"figure.max_open_warning": 0})

COMMON_ENCODINGS = ["utf-8", "cp1250", "iso-8859-2", "cp852", "latin2"]


def read_csv_with_encodings(path: str, delimiter: str = ";", decimal: str = ",") -> pd.DataFrame:
    """Try reading CSV using common encodings until one succeeds.

    Returns a pandas DataFrame with raw contents.
    """
    last_exc = None
    for enc in COMMON_ENCODINGS:
        try:
            # Use pandas read_csv which understands decimal and thousands parameters
            df = pd.read_csv(path, delimiter=delimiter, decimal=decimal, encoding=enc)
            return df
        except Exception as e:
            last_exc = e
            continue
    raise last_exc if last_exc is not None else ValueError("Failed to read CSV")


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names and types for the transaction CSV.

    Expected columns in the provided hist.csv: 'data', 'tytuł operacji', 'szczegóły', 'kwota'
    We'll normalize names to ascii-friendly keys: date, title, details, amount
    """
    # Create a copy to avoid mutating caller's df
    df = df.copy()

    # Normalize column names (strip, lower)
    colmap = {c: c.strip().lower() for c in df.columns}
    df.rename(columns=colmap, inplace=True)

    # Map known Polish column names to english keys
    rename_map = {}
    for c in df.columns:
        if c.startswith('data'):
            rename_map[c] = 'date'
        elif 'tytu' in c:
            rename_map[c] = 'title'
        elif 'szcz' in c or 'szczeg' in c:
            rename_map[c] = 'details'
        elif 'kwota' in c or 'amount' in c:
            rename_map[c] = 'amount'
    df.rename(columns=rename_map, inplace=True)

    # Ensure required columns exist
    for required in ('date', 'title', 'amount'):
        if required not in df.columns:
            raise ValueError(f"Required column '{required}' not found in CSV columns: {list(df.columns)}")

    # Parse date column
    df['date'] = pd.to_datetime(df['date'], errors='coerce', format='%Y-%m-%d')

    # Clean amount: remove spaces, convert to numeric (decimal comma already handled by read_csv)
    # Ensure numeric dtype
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')

    # Fill missing details/title with empty strings
    if 'details' not in df.columns:
        df['details'] = ''
    if 'title' not in df.columns:
        df['title'] = ''

    # Derive extra columns
    df['year_month'] = df['date'].dt.to_period('M').astype(str)
    df['year'] = df['date'].dt.year
    df['month'] = df['date'].dt.month

    # Detect instrument codes (e.g., futures like FW20Z2520) from title or details
    import re
    instr_re = re.compile(r'([A-Z]{2,}[0-9A-Z_\-]{2,})')

    def find_instrument(row):
        txt = ' '.join([str(row.get('title', '')), str(row.get('details', ''))])
        m = instr_re.search(txt)
        return m.group(1) if m else 'Other'

    df['instrument'] = df.apply(find_instrument, axis=1)

    return df


def summary_stats(df: pd.DataFrame) -> Dict[str, Any]:
    """Compute summary statistics from normalized dataframe."""
    total_transactions = len(df)
    net_result = df['amount'].sum()
    positives = df[df['amount'] > 0]['amount'].sum()
    negatives = df[df['amount'] < 0]['amount'].sum()
    date_min = df['date'].min()
    date_max = df['date'].max()

    # Monthly totals
    monthly = df.groupby('year_month')['amount'].sum().sort_index()

    # Top days
    daily = df.groupby('date')['amount'].sum().sort_values(ascending=False)

    return {
        'total_transactions': int(total_transactions),
        'net_result': float(net_result),
        'positives': float(positives),
        'negatives': float(negatives),
        'date_min': str(date_min) if pd.notna(date_min) else None,
        'date_max': str(date_max) if pd.notna(date_max) else None,
        'monthly': monthly,
        'daily': daily,
    }


def plot_and_save(df: pd.DataFrame, outdir: str = 'output') -> Dict[str, str]:
    """Produce plots (PNG) and save them to outdir. Returns dict of plot name -> filepath."""
    os.makedirs(outdir, exist_ok=True)
    outputs = {}

    # 1) Monthly Profit/Loss Overview (bar)
    monthly = df.groupby('year_month')['amount'].sum().sort_index()
    fig, ax = plt.subplots(figsize=(12, 6))
    colors = ['green' if x >= 0 else 'red' for x in monthly.values]
    monthly.plot(kind='bar', color=colors, ax=ax)
    ax.set_title('Monthly Profit/Loss Overview')
    ax.set_ylabel('Amount (PLN)')
    plt.xticks(rotation=45)
    fn = os.path.join(outdir, 'monthly_overview.png')
    fig.tight_layout()
    fig.savefig(fn)
    plt.close(fig)
    outputs['monthly_overview'] = fn

    # 2) Cumulative Profit/Loss Over Time
    df_sorted = df.sort_values('date')
    df_sorted['cumulative'] = df_sorted['amount'].cumsum()
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(df_sorted['date'], df_sorted['cumulative'], color='blue')
    ax.fill_between(df_sorted['date'], df_sorted['cumulative'], alpha=0.2, color='blue')
    ax.set_title('Cumulative Profit/Loss Over Time')
    ax.set_ylabel('Cumulative Amount (PLN)')
    plt.xticks(rotation=45)
    fn = os.path.join(outdir, 'cumulative.png')
    fig.tight_layout()
    fig.savefig(fn)
    plt.close(fig)
    outputs['cumulative'] = fn

    # 3) Transaction Type Distribution (pie) - try to infer types from title
    def infer_type(title: str, details: str) -> str:
        t = str(title).lower()
        d = str(details).lower()
        if 'sprzeda' in t or 'sprzeda' in d:
            return 'Sales'
        if 'kup' in t or 'kup' in d:
            return 'Purchases'
        if 'depozyt' in t or 'depozyt' in d:
            return 'Deposit'
        if 'prowiz' in t or 'prowiz' in d:
            return 'Commission'
        if 'przelew' in t or 'przelew' in d:
            return 'Transfer'
        return 'Other'

    df['tx_type'] = df.apply(lambda r: infer_type(r.get('title', ''), r.get('details', '')), axis=1)
    type_counts = df.groupby('tx_type')['amount'].sum().sort_values()
    fig, ax = plt.subplots(figsize=(8, 6))
    # Pie charts don't support negative values. If any type sum is negative,
    # render a signed horizontal bar chart instead (positive/negative colors).
    if (type_counts < 0).any():
        colors = ['green' if x >= 0 else 'red' for x in type_counts.values]
        type_counts.plot(kind='barh', color=colors, ax=ax)
        ax.set_title('Transaction Type Distribution (signed net amount)')
        ax.set_xlabel('Amount (PLN)')
        fn = os.path.join(outdir, 'type_distribution_bars.png')
    else:
        type_counts.plot(kind='pie', autopct='%1.1f%%', ax=ax)
        ax.set_title('Transaction Type Distribution (by net amount)')
        ax.set_ylabel('')
        fn = os.path.join(outdir, 'type_distribution.png')

    fig.tight_layout()
    fig.savefig(fn)
    plt.close(fig)
    outputs['type_distribution'] = fn

    # 4) Top 20 days by transaction volume (horizontal bar)
    daily = df.groupby('date')['amount'].sum().sort_values(ascending=False).head(20)
    fig, ax = plt.subplots(figsize=(10, 8))
    colors = ['green' if x >= 0 else 'red' for x in daily.values]
    daily.plot(kind='barh', color=colors, ax=ax)
    ax.set_title('Top 20 Days by Transaction Volume')
    ax.invert_yaxis()
    fn = os.path.join(outdir, 'top20_days.png')
    fig.tight_layout()
    fig.savefig(fn)
    plt.close(fig)
    outputs['top20_days'] = fn

    # 5) Cumulative performance by instrument (futures-aware)
    fig, ax = plt.subplots(figsize=(12, 6))
    instruments = [ins for ins in df['instrument'].unique() if ins and ins != 'Other']
    for ins in instruments:
        ins_df = df[df['instrument'] == ins].sort_values('date')
        if ins_df.empty:
            continue
        ins_df = ins_df.copy()
        ins_df['cumulative'] = ins_df['amount'].cumsum()
        ax.plot(ins_df['date'], ins_df['cumulative'], label=ins)
    if instruments:
        ax.set_title('Cumulative Performance by Instrument')
        ax.set_xlabel('Date')
        ax.set_ylabel('Cumulative Amount (PLN)')
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        fn = os.path.join(outdir, 'cumulative_by_instrument.png')
        fig.tight_layout()
        fig.savefig(fn)
        plt.close(fig)
        outputs['cumulative_by_instrument'] = fn

    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='transactions.py', description='Analyze historical transactions CSV and produce plots.')
    parser.add_argument('--input', '-i', default='./tmp/hist.csv', help='Path to input CSV (default: Downloads/hist.csv)')
    parser.add_argument('--outdir', '-o', default='output', help='Directory to write PNG outputs')
    args = parser.parse_args(argv)

    try:
        print(f"Reading CSV: {args.input}")
        raw = read_csv_with_encodings(args.input)
        df = normalize_dataframe(raw)
        stats = summary_stats(df)

        print('Summary:')
        print(f"  Transactions: {stats['total_transactions']}")
        print(f"  Net result: {stats['net_result']:,.2f} PLN")
        print(f"  Positive total: {stats['positives']:,.2f} PLN")
        print(f"  Negative total: {stats['negatives']:,.2f} PLN")
        if stats['date_min'] and stats['date_max']:
            print(f"  Period: {stats['date_min']} to {stats['date_max']}")

        outputs = plot_and_save(df, outdir=args.outdir)
        print('\nSaved plots:')
        for k, v in outputs.items():
            print(f"  {k}: {v}")

        return 0
    except Exception as e:
        print('Error:', e)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())