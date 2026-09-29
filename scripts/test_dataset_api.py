#!/usr/bin/env python3
"""
测试 Jupyter Notebook → Cube Studio 后端数据集 API 的认证流程
在 notebook pod 内运行: python3 /tmp/test_dataset_api.py
"""
import urllib.request
import json
import os

# 模拟 JupyterLab extension 的请求行为
# apiBase = window.location.origin + '/dataset_modelview/api'
# 实际后端地址（通过 Istio ingress）
API_URL = "http://192.168.11.11:30080/dataset_modelview/api/jupyter_list"

print("=" * 60)
print("测试: Jupyter → Cube Studio 数据集 API")
print("=" * 60)

# 1. 不带任何认证信息（模拟未登录）
print("\n[测试1] 不带 Cookie")
try:
    req = urllib.request.Request(API_URL)
    resp = urllib.request.urlopen(req, timeout=10)
    body = resp.read().decode()[:200]
    print(f"  HTTP {resp.status}")
    print(f"  Body: {body}")
except urllib.error.HTTPError as e:
    body = e.read().decode()[:200]
    print(f"  HTTP {e.code}")
    print(f"  Body: {body}")

# 2. 只带 myapp_username cookie（模拟跨域 cookie）
print("\n[测试2] 只带 myapp_username=admin Cookie")
try:
    req = urllib.request.Request(API_URL)
    req.add_header('Cookie', 'myapp_username=admin')
    resp = urllib.request.urlopen(req, timeout=10)
    body = resp.read().decode()[:200]
    print(f"  HTTP {resp.status}")
    print(f"  Body: {body}")
except urllib.error.HTTPError as e:
    body = e.read().decode()[:500]
    print(f"  HTTP {e.code}")
    print(f"  Body: {body}")

# 3. 带完整请求头（模拟浏览器 fetch credentials: 'include'）
print("\n[测试3] 模拟浏览器请求（Referer + 标准 headers）")
try:
    req = urllib.request.Request(API_URL)
    req.add_header('Accept', 'application/json')
    req.add_header('Referer', f'http://192.168.11.11:30080/notebook/jupyter/admin-hdfs/lab')
    req.add_header('User-Agent', 'Mozilla/5.0 Chrome/136.0')
    # 不手动设 cookie，让 urllib 自己处理
    resp = urllib.request.urlopen(req, timeout=10)
    body = resp.read().decode()[:200]
    print(f"  HTTP {resp.status}")
    print(f"  Body: {body}")
except urllib.error.HTTPError as e:
    body = e.read().decode()[:500]
    print(f"  HTTP {e.code}")
    print(f"  Body: {body}")

print("\n" + "=" * 60)
print("结论: 如果浏览器已登录 Cube Studio，session cookie 会自动带上")
print("测试2返回401 → AUTH_PLATFORM_ACCESS 未开启（或不认 myapp_username）")
print("浏览器正常请求会带 Flask session cookie → 应该能通过认证")
print("=" * 60)
