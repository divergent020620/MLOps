from flask import Flask, request, jsonify
app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def hello():
    if request.method == 'GET':
        return 'hello world'
    elif request.method == 'POST':
        data = request.get_json(silent=True) or {}
        name = data.get('name', 'world')
        return jsonify({'message': f'hello {name}'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
