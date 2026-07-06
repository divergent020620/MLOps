# proxy.py — 启动后在浏览器访问 http://localhost:8080，即可在终端看到所有请求详情

from flask import Flask, request
app = Flask(__name__)

@app.route('/', defaults={'path': ''}, methods=['GET','POST','PUT','DELETE','PATCH'])
@app.route('/<path:path>', methods=['GET','POST','PUT','DELETE','PATCH'])
def catch(path):
    print(f"\n{'='*50}")
    print(f"{request.method} {request.full_path}")
    print(f"Headers: {dict(request.headers)}")
    if request.data:
        print(f"Body: {request.data.decode()}")
    return 'ok'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
