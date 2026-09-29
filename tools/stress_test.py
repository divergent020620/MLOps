#!/usr/bin/env python3
"""
Cube Studio 压测脚本
用法:
  python3 stress_test.py http://192.168.11.11 --concurrent 100          # API 并发压测
  python3 stress_test.py http://192.168.11.11 --notebooks 5              # 创建 N 个 Notebook
  python3 stress_test.py http://192.168.11.11 --services 5               # 创建 N 个 Service
  python3 stress_test.py http://192.168.11.11 --all                       # 全部跑一遍
"""
import requests, json, time, sys, os, threading, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

requests.packages.urllib3.disable_warnings()

SESSION_COOKIE = None
BASE_URL = ""

# ============================================================
# 工具函数
# ============================================================

def login(url, user="admin", password="admin"):
    """登录获取 session"""
    global SESSION_COOKIE
    s = requests.Session()
    r = s.post(f"{url}/login/", json={"username": user, "password": password, "provider": "db"}, verify=False, timeout=10)
    if r.status_code == 200 and 'access_token' not in r.text:
        SESSION_COOKIE = s.cookies
        print(f"  登录成功: {user}")
        return s
    # try access_token
    r2 = s.post(f"{url}/api/v1/security/login", json={"username": user, "password": password, "provider": "db"}, verify=False, timeout=10)
    if r2.status_code == 200:
        SESSION_COOKIE = s.cookies
        print(f"  登录成功: {user}")
        return s
    print(f"  登录失败: {r.status_code} {r2.status_code}")
    return s

def api_get(path, params=None):
    """带 session 的 GET"""
    s = requests.Session()
    s.cookies.update(SESSION_COOKIE) if SESSION_COOKIE else None
    return s.get(f"{BASE_URL}{path}", params=params, verify=False, timeout=30)

def api_post(path, json_data=None):
    """带 session 的 POST"""
    s = requests.Session()
    s.cookies.update(SESSION_COOKIE) if SESSION_COOKIE else None
    return s.post(f"{BASE_URL}{path}", json=json_data, verify=False, timeout=30)

def now():
    return datetime.now().strftime("%H:%M:%S")

# ============================================================
# 压测 1: API 并发
# ============================================================

# 常用 API 端点列表
API_ENDPOINTS = [
    "/myapp/navbar_right",
    "/pipeline_modelview/api/",
    "/task_modelview/api/",
    "/job_template_modelview/api/",
    "/notebook_modelview/api/",
    "/service_modelview/api/",
    "/inferenceservice_modelview/api/",
    "/images_modelview/api/",
    "/project_modelview/api/",
    "/dimension_table_modelview/api/",
    "/dataset_modelview/api/",
    "/docker_modelview/api/",
    "/runhistory_modelview/api/",
    "/chat_modelview/api/",
    "/announcement_modelview/api/",
    "/etl_pipeline_modelview/api/",
    "/health",
]

def hit_api(endpoint, idx):
    """单次 API 请求"""
    t0 = time.time()
    try:
        r = api_get(endpoint)
        elapsed = time.time() - t0
        return {"idx": idx, "endpoint": endpoint, "status": r.status_code, "time": round(elapsed, 3), "size": len(r.content)}
    except Exception as e:
        return {"idx": idx, "endpoint": endpoint, "status": 0, "time": round(time.time()-t0,3), "error": str(e)[:60]}

def stress_api(concurrent=100):
    """并发 API 压测"""
    print(f"\n{'='*60}")
    print(f"  API 并发压测 (concurrent={concurrent})")
    print(f"{'='*60}")

    # 构造请求列表：循环使用端点
    tasks = [API_ENDPOINTS[i % len(API_ENDPOINTS)] for i in range(concurrent)]

    t0 = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=concurrent) as pool:
        futures = {pool.submit(hit_api, ep, i): i for i, ep in enumerate(tasks)}
        for f in as_completed(futures):
            results.append(f.result())

    total = time.time() - t0
    success = [r for r in results if r['status'] == 200]
    failures = [r for r in results if r['status'] != 200]
    times = sorted([r['time'] for r in success])

    print(f"\n  总请求: {len(results)} | 成功: {len(success)} | 失败: {len(failures)}")
    print(f"  总耗时: {total:.1f}s | QPS: {len(success)/total:.1f}")
    print(f"  响应时间: min={times[0]:.2f}s  avg={sum(times)/len(times):.2f}s  p50={times[len(times)//2]:.2f}s  p95={times[int(len(times)*0.95)]:.2f}s  p99={times[int(len(times)*0.99)]:.2f}s  max={times[-1]:.2f}s")

    if failures:
        print(f"\n  失败详情 (前5):")
        for f in failures[:5]:
            print(f"    [{f['endpoint']}] status={f['status']} error={f.get('error','?')}")

    # 端点分布
    ep_stats = {}
    for r in success:
        ep = r['endpoint']
        if ep not in ep_stats:
            ep_stats[ep] = []
        ep_stats[ep].append(r['time'])
    print(f"\n  端点耗时分布:")
    for ep, ts in sorted(ep_stats.items(), key=lambda x: sum(x[1])/len(x[1]), reverse=True)[:10]:
        print(f"    {ep:50s}  n={len(ts):3d}  avg={sum(ts)/len(ts):.2f}s  max={max(ts):.2f}s")

    return {"qps": len(success)/total, "success": len(success), "fail": len(failures)}

# ============================================================
# 压测 2: 并发创建 Notebook
# ============================================================

NOTEBOOK_TEMPLATES = []

def find_notebook_templates():
    """查找可用的 notebook 模板"""
    global NOTEBOOK_TEMPLATES
    r = api_get("/notebook_modelview/api/list/")
    try:
        data = r.json()
        NOTEBOOK_TEMPLATES = []
        for item in data.get("result", []):
            NOTEBOOK_TEMPLATES.append({
                "id": item.get("id"),
                "name": item.get("name", "unknown"),
                "images": item.get("images", ""),
                "project_id": item.get("project_id", ""),
                "resource_memory": item.get("resource_memory", "1Gi"),
                "resource_cpu": item.get("resource_cpu", "1"),
            })
        print(f"  找到 {len(NOTEBOOK_TEMPLATES)} 个 Notebook 模板")
    except:
        print("  无法解析 Notebook 模板列表")

def create_notebook(idx):
    """创建单个 Notebook（模拟）"""
    t0 = time.time()
    name = f"stress-test-nb-{idx}-{int(time.time())}"
    payload = {
        "name": name,
        "images": "ccr.ccs.tencentyun.com/cube-studio/notebook:jupyter-tensorflow-2.9.0",
        "resource_memory": "1Gi",
        "resource_cpu": "1",
        "working_dir": "/mnt",
        "volume_mount": "kubeflow-user-workspace(pvc):/mnt",
        "node_selector": "cpu=true,notebook=true",
        "image_pull_policy": "IfNotPresent",
    }
    try:
        r = api_post("/notebook_modelview/api/add", payload)
        elapsed = time.time() - t0
        return {"idx": idx, "name": name, "status": r.status_code, "time": round(elapsed,3),
                "resp": r.json() if r.status_code == 200 else r.text[:100]}
    except Exception as e:
        return {"idx": idx, "name": name, "status": 0, "time": round(time.time()-t0,3), "error": str(e)[:80]}

def stress_notebooks(count=5):
    """并发创建 Notebook"""
    print(f"\n{'='*60}")
    print(f"  Notebook 并发创建 (count={count})")
    print(f"{'='*60}")

    results = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=count) as pool:
        futures = {pool.submit(create_notebook, i): i for i in range(count)}
        for f in as_completed(futures):
            results.append(f.result())

    total = time.time() - t0
    success = [r for r in results if r['status'] == 200]
    failures = [r for r in results if r['status'] != 200]

    print(f"\n  创建结果: 成功={len(success)} 失败={len(failures)}")
    print(f"  总耗时: {total:.1f}s")

    for r in results:
        status = "OK" if r['status'] == 200 else "FAIL"
        print(f"    [{status}] {r['name']}  {r['time']:.2f}s  {r.get('resp','') if status=='FAIL' else ''}")

    # 列出当前运行的 notebooks
    r = api_get("/notebook_modelview/api/list/")
    if r.status_code == 200:
        try:
            data = r.json()
            items = data.get("result", [])
            running = [i for i in items if i.get("status") == "Running"]
            print(f"\n  当前 Notebook 总数: {len(items)}, Running: {len(running)}")
        except:
            pass

    # 清理
    if success:
        print(f"\n  如需清理测试 Notebook，在 UI 中删除名称含 'stress-test-nb' 的即可")

    return {"success": len(success), "fail": len(failures)}

# ============================================================
# 压测 3: 并发创建 Service/推理服务
# ============================================================

def create_service(idx):
    """创建单个推理服务"""
    t0 = time.time()
    name = f"stress-test-svc-{idx}-{int(time.time())}"
    payload = {
        "name": name,
        "label": f"stress-test-{idx}",
        "images": "ccr.ccs.tencentyun.com/cube-studio/kfserving:latest",
        "replicas": 1,
        "resource_memory": "1Gi",
        "resource_cpu": "1",
        "ports": "80",
        "service_type": "cluster",
        "model_name": "test-model",
        "model_path": "test",
    }
    try:
        r = api_post("/inferenceservice_modelview/api/add", payload)
        elapsed = time.time() - t0
        return {"idx": idx, "name": name, "status": r.status_code, "time": round(elapsed,3)}
    except Exception as e:
        return {"idx": idx, "name": name, "status": 0, "time": round(time.time()-t0,3), "error": str(e)[:80]}

def stress_services(count=5):
    """并发创建 Service"""
    print(f"\n{'='*60}")
    print(f"  Service 并发创建 (count={count})")
    print(f"{'='*60}")

    results = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=count) as pool:
        futures = {pool.submit(create_service, i): i for i in range(count)}
        for f in as_completed(futures):
            results.append(f.result())

    total = time.time() - t0
    success = [r for r in results if r['status'] == 200]
    failures = [r for r in results if r['status'] != 200]

    print(f"\n  创建结果: 成功={len(success)} 失败={len(failures)}")
    print(f"  总耗时: {total:.1f}s")

    for r in results:
        status = "OK" if r['status'] == 200 else "FAIL"
        print(f"    [{status}] {r['name']}  {r['time']:.2f}s  {r.get('error','')}")

    return {"success": len(success), "fail": len(failures)}

# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cube Studio 压测工具")
    parser.add_argument("url", help="Cube Studio 地址, 如 http://192.168.11.11")
    parser.add_argument("--concurrent", type=int, default=100, help="API 并发数 (默认: 100)")
    parser.add_argument("--notebooks", type=int, default=5, help="并发创建的 Notebook 数量")
    parser.add_argument("--services", type=int, default=5, help="并发创建的 Service 数量")
    parser.add_argument("--all", action="store_true", help="全部测试")
    parser.add_argument("--api-only", action="store_true", help="仅 API 测试")
    parser.add_argument("--user", default="admin", help="用户名")
    parser.add_argument("--password", default="admin", help="密码")
    args = parser.parse_args()

    BASE_URL = args.url.rstrip("/")

    print(f"\n{'#'*60}")
    print(f"  Cube Studio 压测 - {BASE_URL}")
    print(f"  时间: {now()}")
    print(f"{'#'*60}")

    # 登录
    login(BASE_URL, args.user, args.password)
    if not SESSION_COOKIE:
        print("  无法登录，退出")
        sys.exit(1)

    # 收集空载基线
    print(f"\n--- 空载基线 (采样 20 次) ---")
    t0 = time.time()
    for _ in range(20):
        api_get("/health")
    baseline_time = time.time() - t0
    print(f"  /health * 20: {baseline_time:.1f}s (avg {(baseline_time/20)*1000:.0f}ms/req)")

    results = {}

    # API 压测
    if args.all or args.api_only or args.concurrent > 0:
        results['api'] = stress_api(args.concurrent)

    # Notebook 压测
    if args.all and args.notebooks > 0:
        results['notebooks'] = stress_notebooks(args.notebooks)

    # Service 压测
    if args.all and args.services > 0:
        results['services'] = stress_services(args.services)

    # 汇总
    print(f"\n{'='*60}")
    print(f"  压测完成 - {now()}")
    print(f"{'='*60}")
    for k, v in results.items():
        print(f"  {k}: {v}")
