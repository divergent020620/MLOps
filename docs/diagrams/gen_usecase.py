#!/usr/bin/env python3
"""Generate UML Use Case Diagram for Cube Studio Platform - v3"""

import xml.sax.saxutils as saxutils

def esc(s):
    """Escape XML special characters"""
    return saxutils.escape(s)

# ============================================================
# Layout constants
# ============================================================
PAGE_W = 2800
PAGE_H = 1750

# Actor positions (left side)
ACTORS = {
    "admin":  {"id": "2",  "x": 40,  "y": 350, "label": "管理员&#xa;(Admin)"},
    "gamma":  {"id": "3",  "x": 40,  "y": 750, "label": "Gamma用户&#xa;(Gamma User)"},
    "public": {"id": "4",  "x": 40,  "y": 1150, "label": "Public用户&#xa;(Public User)"},
}

# Module containers (right side) - 2-column layout
MODULES = {
    "m1": {"id": "m1", "x": 260, "y": 30,  "w": 1200, "h": 300, "label": "平台底座 (Platform Base)", "color": "#dae8fc", "scolor": "#6c8ebf"},
    "m2": {"id": "m2", "x": 1500, "y": 30, "w": 1240, "h": 300, "label": "系统管理模块 (System Management)", "color": "#e1d5e7", "scolor": "#9673a6"},
    "m3": {"id": "m3", "x": 260, "y": 370, "w": 2480, "h": 400, "label": "用户功能模块 (User Function)", "color": "#d5e8d4", "scolor": "#82b366"},
    "m4": {"id": "m4", "x": 260, "y": 810, "w": 1200, "h": 300, "label": "生产运行模块 (Production Operation)", "color": "#ffe6cc", "scolor": "#d79b00"},
    "m5": {"id": "m5", "x": 1500, "y": 810, "w": 1240, "h": 240, "label": "前端页面 (Frontend)", "color": "#fff2cc", "scolor": "#d6b656"},
}

# Use cases per module: (id, label, rel_x, rel_y)
USE_CASES = {
    "m1": [
        ("11", "K8s集群与容器运行时管理", 30, 50),
        ("12", "CRD自定义资源管理(11种)", 290, 50),
        ("13", "服务网格(Istio VirtualService)", 550, 50),
        ("14", "高可用架构(Redis/多副本)", 810, 50),
        ("15", "存储管理(Ceph块存储/HDFS)", 160, 140),
        ("16", "中间件管理(MySQL/Redis/Kafka)", 420, 140),
        ("17", "信创环境适配", 680, 140),
    ],
    "m2": [
        ("21", "用户与角色权限管理(RBAC)", 30, 50),
        ("22", "项目与团队隔离(多租户Project)", 290, 50),
        ("23", "平台全局配置(DNS/HostAliases)", 550, 50),
        ("24", "日志采集与监控告警(EFK/Prometheus)", 810, 50),
        ("25", "审计日志", 160, 140),
        ("26", "模型资产管理(AI Hub/训练模型)", 420, 140),
        ("27", "镜像仓库管理", 680, 140),
    ],
    "m3": [
        ("31", "数据接入与管理(Dataset/Metadata)", 30, 50),
        ("32", "Jupyter Notebook交互式探索开发", 310, 50),
        ("33", "可视化Pipeline编排(Vision DAG)", 590, 50),
        ("34", "可视化ETL数据管道编排(VisionPlus)", 870, 50),
        ("35", "作业模板管理(Job Template)", 30, 135),
        ("36", "模型训练(TF/PyTorch/MPI/XGB等)", 310, 135),
        ("37", "超参数搜索(NNI自动调参)", 590, 135),
        ("38", "个人项目空间(Project Workspace)", 870, 135),
        ("39", "ChatGPT/RAG知识库对话", 160, 220),
        ("40", "SQL Lab在线查询", 440, 220),
        ("41", "在线镜像构建(Docker Build)", 720, 220),
    ],
    "m4": [
        ("42", "离线批量调度(Argo Workflows)", 30, 50),
        ("43", "定时任务调度(Celery Beat)", 290, 50),
        ("44", "在线推理服务(Inference Service)", 550, 50),
        ("45", "内部服务部署(Service/Deployment)", 810, 50),
        ("46", "服务版本管理与灰度发布(Istio)", 160, 140),
        ("47", "任务监控与运行历史(Run History)", 420, 140),
        ("48", "数据入仓(ETL定时抽取)", 680, 140),
    ],
    "m5": [
        ("51", "主平台Web界面(React+Ant Design)", 30, 50),
        ("52", "Vision Pipeline可视化编辑器", 290, 50),
        ("53", "VisionPlus ETL可视化编辑器", 550, 50),
        ("54", "Flask-AppBuilder管理后台", 810, 50),
    ],
}

# Edge definitions: (edge_id, actor_id, use_case_id, exitY, color)
# Admin: red (#d50000), Gamma: blue (#1a73e8), Public: green (#188038)
EDGES = [
    # Admin -> Module 1 (all): exitY=0.12
    ("100", "2", "11", 0.12, "#d50000"), ("101", "2", "12", 0.12, "#d50000"), ("102", "2", "13", 0.12, "#d50000"),
    ("103", "2", "14", 0.12, "#d50000"), ("104", "2", "15", 0.12, "#d50000"), ("105", "2", "16", 0.12, "#d50000"),
    ("106", "2", "17", 0.12, "#d50000"),
    # Admin -> Module 2 (all): exitY=0.3
    ("107", "2", "21", 0.3, "#d50000"), ("108", "2", "22", 0.3, "#d50000"), ("109", "2", "23", 0.3, "#d50000"),
    ("110", "2", "24", 0.3, "#d50000"), ("111", "2", "25", 0.3, "#d50000"), ("112", "2", "26", 0.3, "#d50000"),
    ("113", "2", "27", 0.3, "#d50000"),
    # Admin -> Module 3 (specific: 作业模板管理): exitY=0.48
    ("114", "2", "35", 0.48, "#d50000"),
    # Admin -> Module 4 (all): exitY=0.66
    ("116", "2", "42", 0.66, "#d50000"), ("117", "2", "43", 0.66, "#d50000"), ("118", "2", "44", 0.66, "#d50000"),
    ("119", "2", "45", 0.66, "#d50000"), ("120", "2", "46", 0.66, "#d50000"), ("121", "2", "47", 0.66, "#d50000"),
    ("122", "2", "48", 0.66, "#d50000"),
    # Admin -> Module 5 (specific: 管理后台): exitY=0.85
    ("123", "2", "54", 0.85, "#d50000"),

    # Gamma -> Module 3 (all): exitY=0.2
    ("200", "3", "31", 0.2, "#1a73e8"), ("201", "3", "32", 0.2, "#1a73e8"), ("202", "3", "33", 0.2, "#1a73e8"),
    ("203", "3", "34", 0.2, "#1a73e8"), ("204", "3", "35", 0.2, "#1a73e8"), ("205", "3", "36", 0.2, "#1a73e8"),
    ("206", "3", "37", 0.2, "#1a73e8"), ("207", "3", "38", 0.2, "#1a73e8"), ("208", "3", "39", 0.2, "#1a73e8"),
    ("209", "3", "40", 0.2, "#1a73e8"), ("210", "3", "41", 0.2, "#1a73e8"),
    # Gamma -> Module 4 (specific): exitY=0.5
    ("211", "3", "42", 0.5, "#1a73e8"), ("212", "3", "44", 0.5, "#1a73e8"), ("213", "3", "45", 0.5, "#1a73e8"),
    ("214", "3", "47", 0.5, "#1a73e8"), ("215", "3", "48", 0.5, "#1a73e8"),
    # Gamma -> Module 5 (specific): exitY=0.8
    ("216", "3", "51", 0.8, "#1a73e8"), ("217", "3", "52", 0.8, "#1a73e8"), ("218", "3", "53", 0.8, "#1a73e8"),

    # Public -> Module 3 (specific): exitY=0.3
    ("300", "4", "31", 0.3, "#188038"), ("301", "4", "33", 0.3, "#188038"), ("302", "4", "26", 0.3, "#188038"),
    # Public -> Module 5 (specific): exitY=0.7
    ("303", "4", "51", 0.7, "#188038"),
]

# ============================================================
# Generate XML
# ============================================================

def make_actor(a):
    return f'''<mxCell id="{a['id']}" value="{esc(a['label'])}" style="shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;outlineConnect=0;fontSize=12;" vertex="1" parent="1">
  <mxGeometry x="{a['x']}" y="{a['y']}" width="30" height="60" as="geometry" />
</mxCell>'''

def make_module_container(m):
    return f'''<mxCell id="{m['id']}" value="{esc(m['label'])}" style="rounded=1;whiteSpace=wrap;html=1;fillColor={m['color']};strokeColor={m['scolor']};strokeWidth=2;verticalAlign=top;align=center;fontStyle=1;fontSize=14;container=1;pointerEvents=0;" vertex="1" parent="1">
  <mxGeometry x="{m['x']}" y="{m['y']}" width="{m['w']}" height="{m['h']}" as="geometry" />
</mxCell>'''

def make_use_case(uid, label, rx, ry, parent_id):
    return f'''<mxCell id="{uid}" value="{esc(label)}" style="ellipse;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=#555555;fontSize=11;fontColor=#333333;" vertex="1" parent="{parent_id}">
  <mxGeometry x="{rx}" y="{ry}" width="260" height="50" as="geometry" />
</mxCell>'''

def make_edge(eid, source, target, exitY, color):
    # Straight diagonal line with arrow, colored per actor
    style = f"edgeStyle=none;exitX=1;exitY={exitY};exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;endArrow=block;endFill=1;html=1;strokeColor={color};strokeWidth=2.5;"
    return f'''<mxCell id="{eid}" value="" style="{style}" edge="1" parent="1" source="{source}" target="{target}">
  <mxGeometry relative="1" as="geometry" />
</mxCell>'''

# Build XML
lines = []
lines.append('<?xml version="1.0" encoding="UTF-8"?>')
lines.append('<mxfile host="drawio" version="26.0.0">')
lines.append('  <diagram name="Cube Studio UML Use Case Diagram">')
lines.append('    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="2800" pageHeight="1750" math="0" shadow="0">')
lines.append('      <root>')
lines.append('        <mxCell id="0" />')
lines.append('        <mxCell id="1" parent="0" />')

# Title
lines.append(f'''        <mxCell id="title" value="Cube Studio 自研平台 UML 用例图" style="text;html=1;align=center;verticalAlign=middle;fontSize=22;fontStyle=1;fontColor=#333333;" vertex="1" parent="1">
          <mxGeometry x="800" y="5" width="1100" height="40" as="geometry" />
        </mxCell>''')

# Actors
for a in ACTORS.values():
    lines.append(f"        {make_actor(a)}")

# Module containers
for m in MODULES.values():
    lines.append(f"        {make_module_container(m)}")

# Use cases
for mkey, ucs in USE_CASES.items():
    for uid, label, rx, ry in ucs:
        lines.append(f"        {make_use_case(uid, label, rx, ry, MODULES[mkey]['id'])}")

# Edges
for eid, src, tgt, exitY, color in EDGES:
    lines.append(f"        {make_edge(eid, src, tgt, exitY, color)}")

# ============================================================
# Legend
# ============================================================
legend_x = 40
legend_y = 1420
legend_w = 280
legend_h = 290
lines.append(f'''        <mxCell id="legend" value="图例 (Legend)" style="rounded=0;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#666666;verticalAlign=top;align=left;spacingLeft=8;fontStyle=1;fontSize=12;" vertex="1" parent="1">
          <mxGeometry x="{legend_x}" y="{legend_y}" width="{legend_w}" height="{legend_h}" as="geometry" />
        </mxCell>''')

# Module color legend
legend_items = [
    ("#dae8fc", "#6c8ebf", "平台底座"),
    ("#e1d5e7", "#9673a6", "系统管理"),
    ("#d5e8d4", "#82b366", "用户功能"),
    ("#ffe6cc", "#d79b00", "生产运行"),
    ("#fff2cc", "#d6b656", "前端页面"),
]
for i, (fc, sc, name) in enumerate(legend_items):
    ly = 32 + i * 24
    lines.append(f'''        <mxCell id="leg_sw_{i}" value="" style="rounded=1;html=1;fillColor={fc};strokeColor={sc};strokeWidth=2;" vertex="1" parent="legend">
          <mxGeometry x="10" y="{ly}" width="24" height="14" as="geometry" />
        </mxCell>''')
    lines.append(f'''        <mxCell id="leg_lb_{i}" value="{name}" style="text;html=1;align=left;verticalAlign=middle;fontSize=10;" vertex="1" parent="legend">
          <mxGeometry x="40" y="{ly-2}" width="160" height="18" as="geometry" />
        </mxCell>''')

# Actor-edge color legend
actor_colors = [
    ("#d50000", "Admin 管理员连线"),
    ("#1a73e8", "Gamma 用户连线"),
    ("#188038", "Public 用户连线"),
]
for i, (color, name) in enumerate(actor_colors):
    ly = 160 + i * 24
    lines.append(f'''        <mxCell id="leg_ac_{i}" value="" style="endArrow=block;endFill=1;html=1;strokeColor={color};strokeWidth=2.5;" edge="1" parent="legend">
          <mxGeometry relative="1" as="geometry">
            <mxPoint x="10" y="{ly+7}" as="sourcePoint" />
            <mxPoint x="34" y="{ly+7}" as="targetPoint" />
          </mxGeometry>
        </mxCell>''')
    lines.append(f'''        <mxCell id="leg_al_{i}" value="{name}" style="text;html=1;align=left;verticalAlign=middle;fontSize=10;fontColor={color};fontStyle=1;" vertex="1" parent="legend">
          <mxGeometry x="40" y="{ly-2}" width="160" height="18" as="geometry" />
        </mxCell>''')

# Note about access
note_x = 350
note_y = 1420
lines.append(f'''        <mxCell id="note" value="注：&#xa;1. Admin(红色): 平台底座/系统管理/生产运行→全部用例; 用户功能→作业模板管理; 前端→管理后台&#xa;2. Gamma(蓝色): 用户功能→全部用例; 生产运行→批量调度、推理服务、服务部署、任务监控、数据入仓; 前端→主平台、Vision、VisionPlus&#xa;3. Public(绿色): 用户功能→查看公开数据/Pipeline/AI Hub模型; 前端→主平台界面(受限)" style="rounded=0;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#999999;fontSize=10;align=left;verticalAlign=top;spacingLeft=8;spacingTop=5;" vertex="1" parent="1">
          <mxGeometry x="{note_x}" y="{note_y}" width="800" height="110" as="geometry" />
        </mxCell>''')

lines.append('      </root>')
lines.append('    </mxGraphModel>')
lines.append('  </diagram>')
lines.append('</mxfile>')

xml_content = '\n'.join(lines)

with open('/bdm/share_bdm/cube-studio-master/docs/diagrams/cube-studio-usecase.drawio', 'w', encoding='utf-8') as f:
    f.write(xml_content)

print("XML generated successfully!")
print(f"File: /bdm/share_bdm/cube-studio-master/docs/diagrams/cube-studio-usecase.drawio")
print(f"Size: {len(xml_content)} bytes")