"""
Cube Studio Dataset — Jupyter Server Extension

在 JupyterLab 侧边栏添加 "数据集" 面板。
纯 Python 实现，无需 TypeScript 编译，兼容 JupyterLab 3.x。

用法:
    pip install cube_studio_dataset/
    jupyter serverextension enable --py cube_studio_dataset --sys-prefix
"""

import json
import os
from pathlib import Path

HERE = Path(__file__).parent

# ─── 前端 JS (内联，无需编译) ──────────────────────────────────
# 这段 JS 在 JupyterLab 加载后执行，向左侧边栏添加数据集面板

PANEL_JS = r"""
<script>
(function() {
    // 等待 JupyterLab 加载完成
    function waitForJupyterLab(callback) {
        if (window.jupyterlab && window.jupyterlab.shell) {
            callback();
        } else {
            setTimeout(function() { waitForJupyterLab(callback); }, 500);
        }
    }

    function initDatasetPanel() {
        try {
            // 获取 JupyterLab 的 shell 和命令注册中心
            var lab = window.jupyterlab;
            var shell = lab.shell;
            var commands = lab.commands;
            var app = window._jupyterlab_app || lab;

            // 从页面获取 API 基础 URL
            var apiBase = window.location.origin + '/dataset_modelview/api';

            // 创建侧边栏 Widget
            var Panel = document.createElement('div');
            Panel.id = 'cs-dataset-panel';
            Panel.style.cssText = 'padding:12px;overflow-y:auto;height:100%;font-size:13px;';

            function renderLoading() {
                Panel.innerHTML = '<div style="text-align:center;padding:40px 0;color:#999;">加载中...</div>';
            }

            function renderError(msg) {
                Panel.innerHTML = '<div style="padding:12px;background:#fff2f0;border:1px solid #ffccc7;border-radius:4px;color:#cf1322;font-size:12px;">' +
                    msg + '<br><button onclick="location.reload()" style="margin-top:8px;cursor:pointer;">重试</button></div>';
            }

            function renderEmpty() {
                Panel.innerHTML = '<div style="text-align:center;padding:40px 0;color:#999;">' +
                    '暂无可用的数据集<br><small>请先在 Cube Studio 中下载 HDFS 数据集</small></div>';
            }

            function formatSize(b) {
                if (!b) return '-';
                var s = parseInt(b);
                if (!s) return b;
                if (s >= 1073741824) return (s/1073741824).toFixed(1)+' GB';
                if (s >= 1048576) return (s/1048576).toFixed(1)+' MB';
                if (s >= 1024) return (s/1024).toFixed(1)+' KB';
                return s+' B';
            }

            function renderDatasets(datasets) {
                var html = '<h3 style="margin:0 0 12px 0;padding-bottom:8px;border-bottom:1px solid #e0e0e0;font-size:14px;">' +
                    '数据集 (' + datasets.length + ')</h3>';

                datasets.forEach(function(ds) {
                    html += '<div style="margin-bottom:8px;border:1px solid #e0e0e0;border-radius:6px;overflow:hidden;">' +
                        '<div style="padding:8px 12px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;"' +
                        ' onclick="var d=this.nextElementSibling;d.style.display=d.style.display==\'none\'?\'block\':\'none\'">' +
                        '<div>' +
                        '<div style="font-weight:600;">' + (ds.label || ds.name) + '</div>' +
                        '<div style="font-size:11px;color:#999;">' + (ds.entries_num||'') + ' 行 · ' + formatSize(ds.storage_size) + '</div>' +
                        '</div>' +
                        '<button style="background:#1976d2;color:white;border:none;border-radius:4px;padding:3px 10px;cursor:pointer;font-size:12px;"' +
                        ' onclick="event.stopPropagation();' +
                        'var el=document.createElement(\'textarea\');el.value=decodeURIComponent(\'' + encodeURIComponent(ds.load_code) + '\');' +
                        'document.body.appendChild(el);el.select();document.execCommand(\'copy\');document.body.removeChild(el);' +
                        'this.textContent=\'已复制!\';var t=this;setTimeout(function(){t.textContent=\'加载\'},1500);' +
                        '">加载</button>' +
                        '</div>' +
                        '<div style="display:none;padding:8px 12px;border-top:1px solid #f0f0f0;background:#fafafa;">';

                    if (ds.columns && ds.columns.length > 0) {
                        html += '<div style="font-size:12px;font-weight:600;margin-bottom:4px;">列 (' + ds.columns.length + '):</div>';
                        html += '<div style="display:flex;flex-wrap:wrap;gap:3px;margin-bottom:8px;">';
                        ds.columns.forEach(function(c) {
                            html += '<span style="padding:1px 6px;background:#fff;border:1px solid #e0e0e0;border-radius:3px;font-size:11px;font-family:monospace;">' +
                                c.name + ':<span style="color:#999;">' + c.type + '</span></span>';
                        });
                        html += '</div>';
                    }

                    html += '<div style="font-size:11px;color:#999;word-break:break-all;margin-bottom:4px;">' +
                        '路径: ' + (ds.local_path || '') + '</div>';

                    html += '<button style="margin-top:4px;padding:3px 10px;background:#fff;border:1px solid #e0e0e0;border-radius:4px;cursor:pointer;font-size:12px;"' +
                        ' onclick="var el=document.createElement(\'textarea\');el.value=decodeURIComponent(\'' + encodeURIComponent(ds.load_code) + '\');' +
                        'document.body.appendChild(el);el.select();document.execCommand(\'copy\');document.body.removeChild(el);' +
                        'this.textContent=\'已复制!\';var t=this;setTimeout(function(){t.textContent=\'复制加载代码\'},1500);' +
                        '">复制加载代码</button>';

                    html += '</div></div>';
                });

                Panel.innerHTML = html;
            }

            function fetchDatasets() {
                renderLoading();
                fetch(apiBase + '/jupyter_list', { credentials: 'include' })
                    .then(function(r) { return r.json(); })
                    .then(function(data) {
                        if (data.status === 0) {
                            var datasets = data.result || [];
                            if (datasets.length === 0) {
                                renderEmpty();
                            } else {
                                renderDatasets(datasets);
                            }
                        } else {
                            renderError(data.message || '获取数据集列表失败');
                        }
                    })
                    .catch(function(err) {
                        renderError('无法连接 Cube Studio API: ' + err.message);
                    });
            }

            // 注册命令
            commands.addCommand('cube-studio:datasets', {
                label: 'Cube Studio 数据集',
                caption: '浏览和加载数据集',
                execute: function() {
                    fetchDatasets();
                }
            });

            // 初始加载
            fetchDatasets();

            // 将 Panel 添加到 JupyterLab 左侧区域
            // JupyterLab 3.x 的布局区域: 'left', 'main', 'right'
            // 使用 shell.add() 添加 widget
            try {
                var widget = {
                    id: 'cube-studio-dataset-panel',
                    node: Panel,
                    title: { label: '数据集', icon: 'jp-FolderIcon' },
                    revealed: true
                };
                // JL3.x 需要用 Lumino Widget 包装
                // 简化方案: 直接插入 DOM
                var leftArea = document.getElementById('jp-left-stack');
                if (leftArea) {
                    leftArea.appendChild(Panel);
                } else {
                    // fallback: 添加到 main area 的左侧
                    var mainArea = document.getElementById('main');
                    if (mainArea) {
                        Panel.style.width = '280px';
                        Panel.style.borderRight = '1px solid #e0e0e0';
                        Panel.style.float = 'left';
                        mainArea.parentNode.insertBefore(Panel, mainArea);
                    }
                }
            } catch(e) {
                console.warn('[CubeStudio] 无法添加到侧边栏:', e);
            }

            console.log('[Cube Studio] 数据集面板已加载');
        } catch(e) {
            console.error('[Cube Studio] 初始化失败:', e);
        }
    }

    waitForJupyterLab(initDatasetPanel);
})();
</script>
"""


# ─── Server Extension ─────────────────────────────────────────

def _jupyter_server_extension_paths():
    """Jupyter Server 扩展入口点注册。"""
    return [{
        "module": "cube_studio_dataset"
    }]


def _jupyter_labextension_paths():
    """JupyterLab 扩展路径注册 (用于前端资源)。"""
    return []


def _load_jupyter_server_extension(lab_app):
    """
    JupyterLab 启动时调用。
    使用 Tornado OutputTransform 向页面注入数据集面板 JS。
    """
    extra_js = PANEL_JS
    extra_js_bytes = extra_js.encode('utf-8')

    # 方式1: Tornado OutputTransform (兼容 Jupyter Server 1.x / 2.x)
    if hasattr(lab_app, 'web_app'):
        from tornado.web import OutputTransform
        js_bytes = extra_js_bytes

        class _InjectPanelJS(OutputTransform):
            def transform_first_chunk(self, status_code, headers, chunk, finishing):
                ctype = headers.get('Content-Type', '')
                if 'text/html' in ctype and b'</body>' in chunk and b'cs-dataset-panel' not in chunk:
                    chunk = chunk.replace(b'</body>', js_bytes + b'\n</body>')
                return status_code, headers, chunk

        try:
            lab_app.web_app.add_transform(_InjectPanelJS())
            lab_app.log.info('[Cube Studio] 数据集面板扩展已加载 (OutputTransform)')
        except Exception as e:
            lab_app.log.warning(f'[Cube Studio] OutputTransform 注入失败: {e}')

    # 方式2: 通过 extra_template_vars (某些 JupyterHub 版本)
    if hasattr(lab_app, 'settings'):
        settings = lab_app.settings
        if isinstance(settings, dict) and 'extra_template_vars' in settings:
            settings['extra_template_vars'].setdefault('extra_js', '')
            settings['extra_template_vars']['extra_js'] += extra_js
