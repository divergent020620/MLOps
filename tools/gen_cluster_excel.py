#!/usr/bin/env python3
"""生成双 Sheet 集群资源 Excel 报表"""
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side, numbers
from openpyxl.utils import get_column_letter

wb = Workbook()

# ============================================================
# 通用样式
# ============================================================
header_font = Font(name="微软雅黑", bold=True, size=11, color="FFFFFF")
header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

title_font = Font(name="微软雅黑", bold=True, size=14, color="1F4E79")
subtitle_font = Font(name="微软雅黑", bold=True, size=12, color="2E75B6")
cell_font = Font(name="微软雅黑", size=10)
bold_font = Font(name="微软雅黑", bold=True, size=10)
warn_font = Font(name="微软雅黑", bold=True, size=10, color="FF0000")

cell_align = Alignment(horizontal="center", vertical="center")
left_align = Alignment(horizontal="left", vertical="center", wrap_text=True)

thin_border = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin")
)

section_fill = PatternFill(start_color="D6E4F0", end_color="D6E4F0", fill_type="solid")
warn_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
sum_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")

def style_header(ws, row, cols):
    for c in range(1, cols + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border

def style_row(ws, row, cols, font=cell_font, fill=None):
    for c in range(1, cols + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = font
        cell.alignment = cell_align
        cell.border = thin_border
        if fill:
            cell.fill = fill

def auto_width(ws, max_width=40):
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            if cell.value:
                lines = str(cell.value).split("\n")
                for line in lines:
                    # 中文字符算 2 个宽度
                    w = sum(2 if ord(c) > 127 else 1 for c in line)
                    max_len = max(max_len, w)
        ws.column_dimensions[col_letter].width = min(max_len + 4, max_width)

# ============================================================
# Sheet 1: 生产集群
# ============================================================
ws1 = wb.active
ws1.title = "生产集群"

# 标题
ws1.merge_cells("A1:H1")
ws1.cell(row=1, column=1, value="Cube Studio 生产集群资源分析（10.240.x.x 网段）").font = title_font
ws1.cell(row=1, column=1).alignment = Alignment(horizontal="center", vertical="center")
ws1.row_dimensions[1].height = 30

ws1.merge_cells("A2:H2")
ws1.cell(row=2, column=1, value="采集时间：2026-07-15  |  6 节点（3 master + 3 worker）  |  已运行 42 天").font = Font(name="微软雅黑", size=9, color="666666")
ws1.cell(row=2, column=1).alignment = Alignment(horizontal="center", vertical="center")

# ---- 表1: 节点总览 ----
row = 4
ws1.merge_cells(f"A{row}:H{row}")
ws1.cell(row=row, column=1, value="一、节点总览").font = subtitle_font
row += 1

node_headers = ["节点", "IP", "角色", "OS", "K8s 版本", "系统盘", "数据盘 /bdm", "NFS"]
for c, h in enumerate(node_headers, 1):
    ws1.cell(row=row, column=c, value=h)
style_header(ws1, row, len(node_headers))
row += 1

nodes = [
    ["k8s-master1", "10.240.125.39", "control-plane", "Kylin V10", "v1.28.2", "/ 15G (57%)", "300G (76%) ⚠", "NFS 服务端"],
    ["k8s-master2", "10.240.125.48", "control-plane", "Kylin V10", "v1.28.2", "/ 15G (48%)", "300G (2%)", "挂载 master1:/bdm/share_bdm"],
    ["k8s-master3", "10.240.125.77", "control-plane", "Kylin V10", "v1.28.2", "/ 15G (48%)", "300G (2%)", "挂载 master1:/bdm/share_bdm"],
    ["k8s-worker1", "10.240.125.80", "worker", "Kylin V10", "v1.28.2", "—", "—", "—"],
    ["k8s-worker2", "10.240.125.82", "worker", "Kylin V10", "v1.28.2", "—", "—", "—"],
    ["k8s-worker3", "10.240.125.83", "worker", "Kylin V10", "v1.28.2", "—", "—", "—"],
]
for n in nodes:
    for c, v in enumerate(n, 1):
        ws1.cell(row=row, column=c, value=v)
    style_row(ws1, row, len(node_headers))
    # 标红 master1 磁盘
    if "76%" in str(n[6]):
        ws1.cell(row=row, column=7).font = warn_font
        ws1.cell(row=row, column=7).fill = warn_fill
    row += 1

# ---- 表2: 各节点 Pod 明细 ----
row += 1
ws1.merge_cells(f"A{row}:H{row}")
ws1.cell(row=row, column=1, value="二、各节点 Pod 明细（实际占用 — CPU / 内存）").font = subtitle_font
row += 1

pod_headers = ["节点", "CPU 合计", "内存合计", "Pod 名称", "Pod CPU", "Pod 内存", "说明", ""]
for c, h in enumerate(pod_headers, 1):
    ws1.cell(row=row, column=c, value=h)
style_header(ws1, row, len(pod_headers))
row += 1

# 按节点组织的 Pod 数据
pod_data = [
    # master1
    ("k8s-master1", "225m", "16.2Gi", [
        ("kubeflow-dashboard", "3m", "3884Mi", "Flask 后端"),
        ("dashboard-worker", "2m", "2016Mi", "Celery Worker"),
        ("prometheus-k8s", "31m", "1512Mi", "监控 DB（42 天积累）"),
        ("mysql", "3m", "955Mi", "数据库（Pod 方式）"),
        ("kube-apiserver", "40m", "810Mi", ""),
        ("kubeflow-watch", "1m", "397Mi", ""),
        ("dashboard-schedule", "26m", "224Mi", "Celery Beat"),
        ("dashboard-frontend", "0m", "178Mi", "Nginx"),
        ("etcd", "27m", "174Mi", ""),
        ("grafana", "3m", "135Mi", ""),
        ("node-exporter", "1m", "48Mi", ""),
        ("prometheus-operator", "1m", "43Mi", ""),
        ("kube-controller-manager", "1m", "38Mi", ""),
        ("flannel", "5m", "34Mi", ""),
        ("kube-scheduler", "2m", "34Mi", ""),
        ("kube-proxy", "1m", "33Mi", ""),
        ("redis", "4m", "12Mi", ""),
    ]),
    # master2
    ("k8s-master2", "157m", "5.5Gi", [
        ("kube-apiserver", "37m", "765Mi", ""),
        ("etcd", "32m", "200Mi", ""),
        ("istio-ingressgateway", "7m", "156Mi", ""),
        ("istiod", "3m", "82Mi", ""),
        ("node-exporter", "1m", "46Mi", ""),
        ("volcano-scheduler", "9m", "44Mi", ""),
        ("kube-controller-manager", "1m", "36Mi", ""),
        ("kube-scheduler", "3m", "35Mi", ""),
        ("workflow-controller", "2m", "35Mi", ""),
        ("volcano-controllers", "1m", "27Mi", ""),
        ("kube-proxy", "1m", "26Mi", ""),
        ("flannel", "5m", "21Mi", ""),
    ]),
    # master3
    ("k8s-master3", "119m", "5.4Gi", [
        ("kube-apiserver", "39m", "765Mi", ""),
        ("kube-controller-manager", "11m", "90Mi", ""),
        ("etcd", "28m", "174Mi", ""),
        ("node-exporter", "1m", "45Mi", ""),
        ("coredns", "2m", "41Mi", ""),
        ("kube-scheduler", "2m", "38Mi", ""),
        ("kube-proxy", "1m", "26Mi", ""),
        ("flannel", "5m", "23Mi", ""),
    ]),
    # worker1
    ("k8s-worker1", "57m", "4.5Gi", [
        ("minio", "1m", "112Mi", ""),
        ("node-exporter", "2m", "47Mi", ""),
        ("metrics-server", "4m", "37Mi", ""),
        ("coredns", "2m", "36Mi", ""),
        ("kubernetes-dashboard-cluster", "1m", "32Mi", ""),
        ("kube-proxy", "1m", "30Mi", ""),
        ("dashboard-cluster-metrics-scraper", "1m", "29Mi", ""),
        ("kubernetes-dashboard-user1", "1m", "28Mi", ""),
        ("dashboard-user1-metrics-scraper", "1m", "25Mi", ""),
        ("flannel", "4m", "21Mi", ""),
    ]),
    # worker2
    ("k8s-worker2", "80m", "6.6Gi", [
        ("notebook-spark", "1m", "2720Mi", "长期运行的 Spark Notebook"),
        ("node-exporter", "2m", "43Mi", ""),
        ("kube-proxy", "1m", "26Mi", ""),
        ("flannel", "6m", "22Mi", ""),
    ]),
    # worker3
    ("k8s-worker3", "52m", "4.3Gi", [
        ("node-exporter", "1m", "44Mi", ""),
        ("training-operator", "1m", "41Mi", ""),
        ("server-test", "1m", "37Mi", "长期运行的测试服务"),
        ("kube-proxy", "1m", "30Mi", ""),
        ("flannel", "5m", "21Mi", ""),
        ("batch-test", "0m", "3Mi", ""),
    ]),
]

for node_name, cpu_total, mem_total, pods in pod_data:
    start_row = row
    for i, (pname, pcpu, pmem, pnote) in enumerate(pods):
        ws1.cell(row=row, column=4, value=pname)
        ws1.cell(row=row, column=5, value=pcpu)
        ws1.cell(row=row, column=6, value=pmem)
        ws1.cell(row=row, column=7, value=pnote)
        style_row(ws1, row, len(pod_headers))
        # 高内存 pod 标黄
        mem_val = float(pmem.replace("Mi", "")) if "Mi" in pmem else 0
        if mem_val > 1000:
            for c in range(4, 8):
                ws1.cell(row=row, column=c).fill = warn_fill
        row += 1
    # 合并节点列
    if len(pods) > 1:
        ws1.merge_cells(start_row=start_row, start_column=1, end_row=row - 1, end_column=1)
        ws1.merge_cells(start_row=start_row, start_column=2, end_row=row - 1, end_column=2)
        ws1.merge_cells(start_row=start_row, start_column=3, end_row=row - 1, end_column=3)
    ws1.cell(row=start_row, column=1, value=node_name)
    ws1.cell(row=start_row, column=2, value=cpu_total)
    ws1.cell(row=start_row, column=3, value=mem_total)
    for r in range(start_row, row):
        for c in range(1, 4):
            ws1.cell(row=r, column=c).font = bold_font
            ws1.cell(row=r, column=c).alignment = cell_align
            ws1.cell(row=r, column=c).border = thin_border

# ---- 表3: 汇总对比 ----
row += 2
ws1.merge_cells(f"A{row}:H{row}")
ws1.cell(row=row, column=1, value="三、汇总 & 对比").font = subtitle_font
row += 1

sum_headers = ["节点", "CPU 实际", "内存实际", "系统盘", "数据盘 /bdm", "NFS", "关键负载", ""]
for c, h in enumerate(sum_headers, 1):
    ws1.cell(row=row, column=c, value=h)
style_header(ws1, row, len(sum_headers))
row += 1

summary = [
    ["k8s-master1", "0.23C", "16.2Gi", "/ 15G (57%)", "300G (76%) ⚠", "NFS 服务端", "dashboard + MySQL + Prometheus 共 6.3Gi"],
    ["k8s-master2", "0.16C", "5.5Gi", "/ 15G (48%)", "300G (2%)", "挂载 NFS", "istio + volcano + apiserver"],
    ["k8s-master3", "0.12C", "5.4Gi", "/ 15G (48%)", "300G (2%)", "挂载 NFS", "apiserver + etcd + coredns"],
    ["k8s-worker1", "0.06C", "4.5Gi", "—", "—", "—", "minio + coredns + dashboard-k8s"],
    ["k8s-worker2", "0.08C", "6.6Gi", "—", "—", "—", "notebook-spark 2.7Gi"],
    ["k8s-worker3", "0.05C", "4.3Gi", "—", "—", "—", "training-operator + server-test"],
]
for s in summary:
    for c, v in enumerate(s, 1):
        ws1.cell(row=row, column=c, value=v)
    style_row(ws1, row, len(sum_headers))
    if "76%" in str(s[4]):
        ws1.cell(row=row, column=5).font = warn_font
        ws1.cell(row=row, column=5).fill = warn_fill
    row += 1

# 合计行
row_summary_total = row
ws1.merge_cells(start_row=row, start_column=1, end_row=row, end_column=1)
ws1.cell(row=row, column=1, value="合计")
ws1.cell(row=row, column=2, value="0.69C")
ws1.cell(row=row, column=3, value="42.5Gi")
style_row(ws1, row, len(sum_headers), font=bold_font, fill=sum_fill)
row += 1

# 与开发集群对比表
row += 1
cmp_headers = ["对比维度", "生产集群（6 节点）", "开发集群（5 节点）", "差异说明", "", "", "", ""]
for c, h in enumerate(cmp_headers, 1):
    ws1.cell(row=row, column=c, value=h)
style_header(ws1, row, len(cmp_headers))
row += 1

comparisons = [
    ["总 CPU 实际", "0.69C", "0.45C", "生产多用 ~0.24C"],
    ["总内存实际", "42.5Gi", "12.1Gi", "生产多了 MySQL(955M) + notebook-spark(2.7G) + Prometheus(+500M) + 更多组件"],
    ["最大单节点", "master1 16.2Gi", "master1 6.8Gi", "生产 master1 上堆了 MySQL+Worker+Frontend，开发分散到 master3"],
    ["master1 /bdm", "76% (226/300G) ⚠", "17% (17/100G)", "告警！需清理或扩容"],
    ["QPS (100并发)", "—", "146", "生产未压测"],
    ["p95 延迟", "—", "0.18s", "生产未压测"],
]
for c in comparisons:
    for ci, v in enumerate(c, 1):
        ws1.cell(row=row, column=ci, value=v)
    style_row(ws1, row, len(cmp_headers))
    if "⚠" in str(c[3]):
        ws1.cell(row=row, column=4).font = warn_font
    row += 1

auto_width(ws1)

# ============================================================
# Sheet 2: 开发集群
# ============================================================
ws2 = wb.create_sheet("开发集群")

ws2.merge_cells("A1:G1")
ws2.cell(row=1, column=1, value="Cube Studio 开发集群资源分析（192.168.11.x 网段）").font = title_font
ws2.cell(row=1, column=1).alignment = Alignment(horizontal="center", vertical="center")
ws2.row_dimensions[1].height = 30

ws2.merge_cells("A2:G2")
ws2.cell(row=2, column=1, value="采集时间：2026-07-15  |  5 节点（3 master + 2 worker）  |  数据源：metrics-server").font = Font(name="微软雅黑", size=9, color="666666")
ws2.cell(row=2, column=1).alignment = Alignment(horizontal="center", vertical="center")

# ---- 表1: 节点总览 ----
row2 = 4
ws2.merge_cells(f"A{row2}:G{row2}")
ws2.cell(row=row2, column=1, value="一、节点总览").font = subtitle_font
row2 += 1

dev_node_headers = ["节点", "IP", "角色", "OS", "K8s 版本", "数据盘 /bdm", "备注"]
for c, h in enumerate(dev_node_headers, 1):
    ws2.cell(row=row2, column=c, value=h)
style_header(ws2, row2, len(dev_node_headers))
row2 += 1

dev_nodes = [
    ["k8s-master1", "192.168.11.11", "control-plane", "Kylin V10", "v1.28.2", "100G (17%)", "源码 + NFS 共享导出"],
    ["k8s-master2", "192.168.11.12", "control-plane", "Kylin V10", "v1.28.2", "100G (30%)", "Harbor 镜像仓库 (~30G)"],
    ["k8s-master3", "192.168.11.13", "control-plane", "Kylin V10", "v1.28.2", "100G (7%)", "少量数据"],
    ["k8s-worker1", "192.168.11.14", "worker", "Kylin V10", "v1.28.2", "100G", "PV hostPath 数据"],
    ["k8s-worker2", "192.168.11.15", "worker", "Kylin V10", "v1.28.2", "100G", "MySQL 裸金属 (/bdm/mysql)"],
]
for n in dev_nodes:
    for c, v in enumerate(n, 1):
        ws2.cell(row=row2, column=c, value=v)
    style_row(ws2, row2, len(dev_node_headers))
    row2 += 1

# ---- 表2: 各节点 Pod 明细 ----
row2 += 1
ws2.merge_cells(f"A{row2}:G{row2}")
ws2.cell(row=row2, column=1, value="二、各节点 Pod 明细（实际占用）").font = subtitle_font
row2 += 1

dev_pod_headers = ["节点", "CPU 合计", "内存合计", "Pod 名称", "Pod CPU", "Pod 内存", "说明"]
for c, h in enumerate(dev_pod_headers, 1):
    ws2.cell(row=row2, column=c, value=h)
style_header(ws2, row2, len(dev_pod_headers))
row2 += 1

dev_pod_data = [
    ("k8s-master1", "0.15C", "6.8Gi", [
        ("kubeflow-dashboard", "5m", "4003Mi", "Flask 后端"),
        ("prometheus-k8s", "20m", "1043Mi", "监控 DB"),
        ("kube-apiserver", "67m", "909Mi", ""),
        ("kubeflow-watch", "5m", "394Mi", ""),
        ("etcd", "34m", "243Mi", ""),
        ("dashboard-frontend", "0m", "175Mi", "Nginx"),
        ("node-exporter", "1m", "42Mi", ""),
        ("kube-scheduler", "3m", "33Mi", ""),
        ("kube-controller-manager", "2m", "31Mi", ""),
        ("kube-proxy", "1m", "27Mi", ""),
        ("flannel", "5m", "20Mi", ""),
        ("redis", "5m", "8Mi", ""),
    ]),
    ("k8s-master2", "0.15C", "1.3Gi", [
        ("kube-apiserver", "67m", "692Mi", ""),
        ("etcd", "38m", "242Mi", ""),
        ("kube-controller-manager", "19m", "102Mi", ""),
        ("istio-ingressgateway", "8m", "69Mi", ""),
        ("istiod", "3m", "69Mi", ""),
        ("kube-scheduler", "4m", "51Mi", ""),
        ("node-exporter", "1m", "32Mi", ""),
        ("kube-proxy", "1m", "26Mi", ""),
        ("flannel", "5m", "18Mi", ""),
    ]),
    ("k8s-master3", "0.13C", "3.4Gi", [
        ("dashboard-worker", "2m", "2122Mi", "Celery Worker"),
        ("kube-apiserver", "53m", "678Mi", ""),
        ("dashboard-schedule", "16m", "199Mi", "Celery Beat"),
        ("etcd", "31m", "185Mi", ""),
        ("grafana", "2m", "84Mi", ""),
        ("node-exporter", "1m", "44Mi", ""),
        ("volcano-scheduler", "11m", "36Mi", ""),
        ("kube-scheduler", "3m", "35Mi", ""),
        ("kube-controller-manager", "2m", "32Mi", ""),
        ("prometheus-operator", "2m", "28Mi", ""),
        ("kube-proxy", "1m", "25Mi", ""),
        ("volcano-controllers", "1m", "24Mi", ""),
        ("flannel", "4m", "18Mi", ""),
    ]),
    ("k8s-worker1", "0.02C", "0.4Gi", [
        ("node-exporter", "1m", "45Mi", ""),
        ("kube-proxy", "1m", "27Mi", ""),
        ("flannel", "4m", "20Mi", ""),
    ]),
    ("k8s-worker2", "0.01C", "0.3Gi", [
        ("node-exporter", "1m", "43Mi", ""),
        ("kube-proxy", "1m", "26Mi", ""),
        ("flannel", "5m", "22Mi", ""),
    ]),
]

for node_name, cpu_total, mem_total, pods in dev_pod_data:
    start_row = row2
    for pname, pcpu, pmem, pnote in pods:
        ws2.cell(row=row2, column=4, value=pname)
        ws2.cell(row=row2, column=5, value=pcpu)
        ws2.cell(row=row2, column=6, value=pmem)
        ws2.cell(row=row2, column=7, value=pnote)
        style_row(ws2, row2, len(dev_pod_headers))
        mem_val = float(pmem.replace("Mi", "")) if "Mi" in pmem else 0
        if mem_val > 1000:
            for c in range(4, 8):
                ws2.cell(row=row2, column=c).fill = warn_fill
        row2 += 1
    if len(pods) > 1:
        ws2.merge_cells(start_row=start_row, start_column=1, end_row=row2 - 1, end_column=1)
        ws2.merge_cells(start_row=start_row, start_column=2, end_row=row2 - 1, end_column=2)
        ws2.merge_cells(start_row=start_row, start_column=3, end_row=row2 - 1, end_column=3)
    ws2.cell(row=start_row, column=1, value=node_name)
    ws2.cell(row=start_row, column=2, value=cpu_total)
    ws2.cell(row=start_row, column=3, value=mem_total)
    for r in range(start_row, row2):
        for c in range(1, 4):
            ws2.cell(row=r, column=c).font = bold_font
            ws2.cell(row=r, column=c).alignment = cell_align
            ws2.cell(row=r, column=c).border = thin_border

# ---- 表3: 汇总 ----
row2 += 2
ws2.merge_cells(f"A{row2}:G{row2}")
ws2.cell(row=row2, column=1, value="三、汇总").font = subtitle_font
row2 += 1

dev_sum_headers = ["节点", "CPU 实际", "内存实际", "数据盘 /bdm", "主要占用", "系统盘", ""]
for c, h in enumerate(dev_sum_headers, 1):
    ws2.cell(row=row2, column=c, value=h)
style_header(ws2, row2, len(dev_sum_headers))
row2 += 1

dev_summary = [
    ["k8s-master1", "0.15C", "6.8Gi", "100G (17%)", "dashboard 4Gi + prometheus 1Gi", "/ 50G (20%)"],
    ["k8s-master2", "0.15C", "1.3Gi", "100G (30%)", "Harbor 镜像仓库 30G", "/ 50G (16%)"],
    ["k8s-master3", "0.13C", "3.4Gi", "100G (7%)", "dashboard-worker 2.1Gi", "/ 50G (14%)"],
    ["k8s-worker1", "0.02C", "0.4Gi", "100G", "PV hostPath 数据", "/ 50G"],
    ["k8s-worker2", "0.01C", "0.3Gi", "100G", "MySQL 裸金属数据(/bdm/mysql)", "/ 50G"],
]
for s in dev_summary:
    for c, v in enumerate(s, 1):
        ws2.cell(row=row2, column=c, value=v)
    style_row(ws2, row2, len(dev_sum_headers))
    row2 += 1

# 合计
ws2.merge_cells(start_row=row2, start_column=1, end_row=row2, end_column=1)
ws2.cell(row=row2, column=1, value="合计")
ws2.cell(row=row2, column=2, value="0.45C")
ws2.cell(row=row2, column=3, value="12.1Gi")
style_row(ws2, row2, len(dev_sum_headers), font=bold_font, fill=sum_fill)
row2 += 1

# ---- 表4: 压测结果 ----
row2 += 2
ws2.merge_cells(f"A{row2}:G{row2}")
ws2.cell(row=row2, column=1, value="四、100 并发 API 压测结果").font = subtitle_font
row2 += 1

stress_headers = ["指标", "值", "说明", "", "", "", ""]
for c, h in enumerate(stress_headers, 1):
    ws2.cell(row=row2, column=c, value=h)
style_header(ws2, row2, len(stress_headers))
row2 += 1

stress_data = [
    ["QPS", "146", ""],
    ["p50 延迟", "0.06s", ""],
    ["p95 延迟", "0.18s", ""],
    ["p99 延迟", "0.38s", ""],
    ["CPU 增量", "+~0.5C", "dashboard 进程" ],
    ["内存增量", "几乎无变化", ""],
    ["结论", "4C/16G × 3 master 完全满足", ""],
]
for s in stress_data:
    for c, v in enumerate(s, 1):
        ws2.cell(row=row2, column=c, value=v)
    style_row(ws2, row2, len(stress_headers))
    if "结论" in str(s[0]):
        for c2 in range(1, len(stress_headers) + 1):
            ws2.cell(row=row2, column=c2).font = bold_font
            ws2.cell(row=row2, column=c2).fill = sum_fill
    row2 += 1

auto_width(ws2)

# ============================================================
# 保存
# ============================================================
output = "/bdm/share_bdm/cube-studio-master/files/集群资源分析.xlsx"
wb.save(output)
print(f"✅ 已生成: {output}")
