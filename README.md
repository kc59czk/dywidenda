Dividends Dashboard
===================

Quick start

1. Create a virtualenv and install dependencies:

```powershell
python -m venv .venv; .\.venv\Scripts\Activate; pip install -r requirements.txt
```

2. Put your CSV files in the `input/` directory (already used by the parser).

3. Run the app

Quick (script):

```powershell
python app.py
```

Or (module) if you prefer to run as a module:

```powershell
python -m app
```

Note: `python -m dywidenda.app` will fail in this repository because there is a top-level file named `dywidenda.py`. Python will treat `dywidenda` as a plain module (not a package), so it can't find `dywidenda.app` as a submodule. If you want to use the `python -m dywidenda.app` form, I can convert the project into a proper package (move files into a `dywidenda/` package directory and add `__init__.py`).

4. Open http://127.0.0.1:5000 in your browser.

Notes
- The app re-uses `dywidenda.parse_dividend_file` to parse CSV files. It supports common encodings used for Polish text.
- The API endpoint `/api/dividends` returns aggregated JSON that the UI consumes.
