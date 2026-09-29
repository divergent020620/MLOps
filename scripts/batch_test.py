import os, datetime, socket, json

now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
username = os.environ.get('USERNAME', 'unknown')
hostname = socket.gethostname()

result = {
    "test": "batch_inference",
    "time": now,
    "node": hostname,
    "user": username,
    "cwd": os.getcwd(),
    "mnt_files": os.listdir('/mnt') if os.path.exists('/mnt') else [],
    "datasets_exist": os.path.exists('/mnt/datasets'),
}

out_dir = f'/mnt/{username}/batch_results'
os.makedirs(out_dir, exist_ok=True)
out_file = os.path.join(out_dir, f'batch_test_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
with open(out_file, 'w') as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

if os.path.exists(out_file):
    with open(out_file) as f:
        print(f'[VERIFY]{json.load(f)}')