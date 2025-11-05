from app import create_app

app = create_app()
client = app.test_client()
res = client.get('/favicon.ico')
print('favicon status:', res.status_code)
print('content-length:', res.content_length)
print('mimetype:', res.mimetype)