import os
import glob
from collections import defaultdict
from flask import Flask, jsonify, render_template, send_from_directory

# Reuse existing parser. Support running app.py directly (script) or as a package.
try:
    # When running as a package (python -m dywidenda.app)
    from . import dywidenda as parser
except Exception:
    # Fallback: load dywidenda.py from the same directory
    import importlib.util
    import pathlib
    spec = importlib.util.spec_from_file_location(
        "dywidenda",
        str(pathlib.Path(__file__).parent / "dywidenda.py"),
    )
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)


def get_aggregated_data(input_dir='input'):
    """Parse all CSV files in input_dir and return JSON-serializable aggregation."""
    pattern = os.path.join(input_dir, '*.csv')
    files = glob.glob(pattern)

    aggregated = defaultdict(list)
    grand_total = 0.0

    for fpath in files:
        fname = os.path.basename(fpath)
        source_name, _ = os.path.splitext(fname)

        try:
            result = parser.parse_dividend_file(fpath)
        except Exception:
            # skip files that fail to parse
            continue

        for stock, payments in result.items():
            for p in payments:
                # Convert to JSON-friendly types
                date_str = p['date'].strftime('%Y-%m-%d')
                amount = float(p['amount'])
                aggregated[stock].append({
                    'date': date_str,
                    'amount': amount,
                    'source': source_name,
                })
                grand_total += amount

    # Build stocks list with totals and per-source breakdowns
    stocks = []
    yearly = defaultdict(lambda: defaultdict(float))  # yearly[year][stock] = total
    for stock, payments in aggregated.items():
        total = sum(p['amount'] for p in payments)
        # per-source totals
        per_source = defaultdict(float)
        for p in payments:
            per_source[p.get('source', 'unknown')] += p['amount']
            # yearly aggregation
            year = int(p['date'][:4]) if isinstance(p['date'], str) else p['date'].year
            yearly[year][stock] += p['amount']

        stocks.append({
            'symbol': stock,
            'total': total,
            'per_source': dict(per_source),
            'payments': sorted(payments, key=lambda x: x['date'], reverse=True),
        })

    # Sort stocks by total desc
    stocks.sort(key=lambda s: s['total'], reverse=True)

    # Build yearly summary list of { year: { stock: total, ... } }
    yearly_summary = {year: dict(stocks) for year, stocks in sorted(yearly.items())}

    return {
        'stocks': stocks,
        'grand_total': grand_total,
        'yearly': yearly_summary,
    }


def create_app(static_folder=None, template_folder=None):
    # If no template_folder provided, use the templates directory next to this file
    if template_folder is None:
        template_folder = os.path.join(os.path.dirname(__file__), 'templates')
    if static_folder is None:
        static_folder = os.path.join(os.path.dirname(__file__), 'static')

    app = Flask(__name__, static_folder=static_folder, template_folder=template_folder)

    @app.route('/')
    def index():
        # Try normal Jinja rendering first; if the template loader fails for any
        # reason, fall back to returning the raw file contents from the
        # templates directory so the UI still loads.
        try:
            return render_template('index.html')
        except Exception:
            tpl_path = os.path.join(os.path.dirname(__file__), 'templates', 'index.html')
            try:
                with open(tpl_path, 'r', encoding='utf-8') as fh:
                    return fh.read()
            except Exception:
                # Last-resort: return a small error page
                return "<h1>Template not found</h1><p>index.html missing</p>", 500

    @app.route('/api/dividends')
    def api_dividends():
        data = get_aggregated_data()
        return jsonify(data)

    @app.route('/download/all.csv')
    def download_all():
        # Build CSV for all payments: symbol,date,amount,source
        import io
        import csv as _csv

        data = get_aggregated_data()
        buf = io.StringIO()
        writer = _csv.writer(buf)
        writer.writerow(['symbol', 'date', 'amount', 'source'])
        for s in data['stocks']:
            for p in s['payments']:
                writer.writerow([s['symbol'], p['date'], p['amount'], p.get('source', '')])
        csv_bytes = buf.getvalue().encode('utf-8')
        return app.response_class(csv_bytes, mimetype='text/csv', headers={
            'Content-Disposition': 'attachment; filename="dividends_all.csv"'
        })

    @app.route('/download/<symbol>.csv')
    def download_symbol(symbol):
        import io
        import csv as _csv

        data = get_aggregated_data()
        buf = io.StringIO()
        writer = _csv.writer(buf)
        writer.writerow(['symbol', 'date', 'amount', 'source'])
        found = False
        for s in data['stocks']:
            if s['symbol'] == symbol:
                found = True
                for p in s['payments']:
                    writer.writerow([s['symbol'], p['date'], p['amount'], p.get('source', '')])
                break
        if not found:
            return ('', 404)
        csv_bytes = buf.getvalue().encode('utf-8')
        return app.response_class(csv_bytes, mimetype='text/csv', headers={
            'Content-Disposition': f'attachment; filename="dividends_{symbol}.csv"'
        })

    @app.route('/favicon.ico')
    def favicon():
        # Serve favicon.ico from the static folder so browsers requesting
        # /favicon.ico get the file.
        try:
            return send_from_directory(app.static_folder, 'favicon.ico')
        except Exception:
            return '', 404

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True,host="0.0.0.0")
