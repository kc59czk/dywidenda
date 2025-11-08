from app import create_app
app = create_app()
client = app.test_client()
res = client.get('/api/dividends')
print('status', res.status_code)
print('stocks', len(res.json.get('stocks', [])))
