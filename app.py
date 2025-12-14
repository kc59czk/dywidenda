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

# Import transactions analysis module (same fallback pattern)
try:
    from . import transactions as txmod
except Exception:
    import importlib.util
    import pathlib
    spec = importlib.util.spec_from_file_location(
        "transactions",
        str(pathlib.Path(__file__).parent / "transactions.py"),
    )
    txmod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(txmod)


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

    @app.route('/api/transactions')
    def api_transactions():
        # Run transactions analysis and return JSON summary (no heavy plotting here)
        input_path = os.path.expanduser(r'C:\Users\czk\Downloads\hist.csv')
        try:
            raw = txmod.read_csv_with_encodings(input_path)
            df = txmod.normalize_dataframe(raw)
            stats = txmod.summary_stats(df)
            # Convert pandas Series to lists/dicts for JSON
            stats_serializable = dict(stats)
            stats_serializable['monthly'] = stats['monthly'].to_dict()
            stats_serializable['daily'] = {str(k): float(v) for k, v in stats['daily'].items()}
            return jsonify(stats_serializable)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            app.logger.error('Error in /api/transactions: %s', tb)
            return (jsonify({'error': str(e), 'traceback': tb}), 500)

    @app.route('/transactions')
    def transactions_ui():
        # Use caching to avoid regenerating plots on every request.
        input_path = os.path.expanduser(r'C:\Users\czk\Downloads\hist.csv')
        cache_dir = os.path.join(app.static_folder, 'transactions')
        meta_path = os.path.join(cache_dir, 'meta.json')

        def needs_generation() -> bool:
            # If no cache dir or meta, we need to generate
            if not os.path.isdir(cache_dir):
                return True
            if not os.path.isfile(meta_path):
                return True
            try:
                import json
                meta = json.load(open(meta_path, 'r', encoding='utf-8'))
                # Compare mtime of input file
                if not os.path.exists(input_path):
                    return True
                on_disk = os.path.getmtime(input_path)
                return float(meta.get('input_mtime', 0)) < float(on_disk)
            except Exception:
                return True

        def start_background_generation():
            # Create a background thread to generate plots and write meta.json
            import threading, json, time

            def worker():
                lock_path = os.path.join(cache_dir, 'generating.lock')
                try:
                    os.makedirs(cache_dir, exist_ok=True)
                    # touch lock
                    open(lock_path, 'w').close()
                    raw = txmod.read_csv_with_encodings(input_path)
                    df = txmod.normalize_dataframe(raw)
                    stats = txmod.summary_stats(df)
                    outputs = txmod.plot_and_save(df, outdir=cache_dir)
                    # write metadata
                    meta = {
                        'input_mtime': os.path.getmtime(input_path),
                        'generated_at': time.time(),
                        'outputs': outputs,
                    }
                    json.dump(meta, open(os.path.join(cache_dir, 'meta.json'), 'w', encoding='utf-8'))
                except Exception:
                    app.logger.exception('Background generation failed')
                finally:
                    try:
                        os.remove(lock_path)
                    except Exception:
                        pass

            t = threading.Thread(target=worker, daemon=True)
            t.start()

        # If generation needed and not already running, start it and show status
        if needs_generation():
            lock = os.path.join(cache_dir, 'generating.lock')
            if not os.path.exists(lock):
                start_background_generation()
            # show status page while generating
            return render_template('transactions_status.html')

        # Otherwise load cached meta and render page with images and stats
        try:
            import json
            meta = json.load(open(meta_path, 'r', encoding='utf-8'))
            outputs = meta.get('outputs', {})
            images = [os.path.join('static', 'transactions', os.path.basename(p)) for p in outputs.values()]
            # Load stats by re-reading file quickly
            raw = txmod.read_csv_with_encodings(input_path)
            df = txmod.normalize_dataframe(raw)
            stats = txmod.summary_stats(df)
            return render_template('transactions.html', stats=stats, images=images)
        except Exception as e:
            app.logger.exception('Failed to render cached transactions')
            return (f"<h1>Error rendering transactions</h1><pre>{e}</pre>"), 500

    @app.route('/transactions/status')
    def transactions_status():
        cache_dir = os.path.join(app.static_folder, 'transactions')
        lock = os.path.join(cache_dir, 'generating.lock')
        meta = os.path.join(cache_dir, 'meta.json')
        status = {
            'generating': os.path.exists(lock),
            'has_meta': os.path.exists(meta),
        }
        return jsonify(status)

    @app.route('/transactions/regenerate')
    def transactions_regenerate():
        cache_dir = os.path.join(app.static_folder, 'transactions')
        lock = os.path.join(cache_dir, 'generating.lock')
        # remove meta to force regeneration
        try:
            if os.path.exists(lock):
                return jsonify({'status': 'already generating'}), 202
            if os.path.isdir(cache_dir):
                import glob
                for f in glob.glob(os.path.join(cache_dir, '*')):
                    try:
                        os.remove(f)
                    except Exception:
                        pass
            # start background generation by visiting /transactions (it will kick off worker)
            # but we can also directly start the worker here by invoking logic
            # For simplicity, redirect to /transactions which will start generation if needed
            return ("<html><body>Regeneration started. <a href=\"/transactions\">Go back</a></body></html>"), 202
        except Exception as e:
            app.logger.exception('Failed to start regeneration')
            return jsonify({'error': str(e)}), 500

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
