from app import create_app
app = create_app()
client = app.test_client()
res = client.get('/download/all.csv')
print('status', res.status_code)
print('len', len(res.data))
print(res.data[:200].decode('utf-8', errors='ignore'))
