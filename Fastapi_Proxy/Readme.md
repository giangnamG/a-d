

### Cài lib
```
pip install -r requirements.txt
```

### Sửa forward service ở file proxy.py

```
HTTP_SERVER = AsyncClient(base_url="http://service", follow_redirects=False, verify=False,timeout=600)
```

### Chạy proxy

```
uvicorn --host 0.0.0.0 --port 5000 --reload proxy:app --no-server-header --no-date-header
```


### Sửa config nginx

```
                proxy_pass http://127.0.0.1:5000;
                proxy_set_header        Raw-URI $request_uri;
```
nginx -s reload