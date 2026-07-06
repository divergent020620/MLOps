/**
 * Cube Studio Dataset — JupyterLab 3.x Sidebar Extension
 *
 * 在左侧边栏创建"数据集"Tab，展示所有已下载的 HDFS 数据集，
 * 支持查看 schema 和一键复制加载代码。
 */
import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin,
} from '@jupyterlab/application';

import { ICommandPalette } from '@jupyterlab/apputils';

import { Widget } from '@lumino/widgets';

import { Message } from '@lumino/messaging';

// ─── API 地址 ──────────────────────────────────────────────
// 优先用全局注入的配置，否则同源请求
function getApiBase(): string {
  const win = window as any;
  if (win._cube_studio_api) {
    return win._cube_studio_api;
  }
  return '/dataset_modelview/api';
}

// ─── 数据接口 ──────────────────────────────────────────────

interface DatasetInfo {
  id: number;
  name: string;
  label: string;
  source_type: string;
  storage_size: string | number;
  entries_num: number;
  columns: Array<{ name: string; type: string }>;
  local_path: string;
  load_code: string;
}

// ─── 工具函数 ──────────────────────────────────────────────

function formatSize(b: any): string {
  if (b === null || b === undefined) return '-';
  const s = parseInt(String(b), 10);
  if (!s) return String(b);
  if (s >= 1073741824) return (s / 1073741824).toFixed(1) + ' GB';
  if (s >= 1048576) return (s / 1048576).toFixed(1) + ' MB';
  if (s >= 1024) return (s / 1024).toFixed(1) + ' KB';
  return s + ' B';
}

function escapeHtml(text: string): string {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function copyToClipboard(text: string): boolean {
  try {
    const el = document.createElement('textarea');
    el.value = text;
    el.style.position = 'fixed';
    el.style.opacity = '0';
    document.body.appendChild(el);
    el.select();
    document.execCommand('copy');
    document.body.removeChild(el);
    return true;
  } catch {
    return false;
  }
}

// ─── Widget ────────────────────────────────────────────────

class DatasetPanel extends Widget {
  private _apiBase: string;

  constructor(apiBase: string) {
    super();
    this._apiBase = apiBase;
    this.id = 'cube-studio-dataset-panel';
    this.title.label = '数据集';
    this.title.closable = true;
    this.title.caption = 'Cube Studio 数据集';
    this.addClass('cs-dataset-panel');

    // 根节点
    this.node.style.padding = '8px';
    this.node.style.overflowY = 'auto';
    this.node.style.height = '100%';
    this.node.style.boxSizing = 'border-box';
  }

  protected onAfterShow(msg: Message): void {
    this._fetchDatasets();
  }

  private _renderLoading(): void {
    this.node.innerHTML =
      '<div style="text-align:center;padding:40px 0;color:#999;">加载中...</div>';
  }

  private _renderEmpty(): void {
    this.node.innerHTML =
      '<div style="text-align:center;padding:40px 0;color:#999;">' +
      '暂无可用的数据集<br>' +
      '<small>请先在 Cube Studio「数仓浏览(HDFS)」中下载数据集</small>' +
      '</div>';
  }

  private _renderError(msg: string): void {
    this.node.innerHTML =
      '<div style="padding:12px;background:#fff2f0;border:1px solid #ffccc7;border-radius:4px;color:#cf1322;font-size:12px;">' +
      escapeHtml(msg) +
      '<br><button onclick="document.getElementById(\'cube-studio-dataset-panel\').dispatchEvent(new Event(\'cs-refresh\'))" ' +
      'style="margin-top:8px;cursor:pointer;padding:2px 12px;border:1px solid #ccc;border-radius:3px;background:#fff;">重试</button>' +
      '</div>';
  }

  private _renderDatasets(datasets: DatasetInfo[]): void {
    let html = '';

    html +=
      '<h3 style="margin:0 0 12px 0;padding-bottom:8px;border-bottom:1px solid #e0e0e0;font-size:14px;">' +
      '数据集 (' +
      datasets.length +
      ')</h3>';

    for (const ds of datasets) {
      const name = escapeHtml(ds.label || ds.name);
      const rows = ds.entries_num ? ds.entries_num.toLocaleString() : '-';
      const sizeStr = formatSize(ds.storage_size) || '-';
      const codeEncoded = encodeURIComponent(ds.load_code || '');

      html +=
        '<div style="margin-bottom:8px;border:1px solid #e0e0e0;border-radius:6px;overflow:hidden;">' +
        // 标题栏
        '<div class="cs-ds-header" style="padding:8px 12px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;user-select:none;"' +
        ' data-cs-toggle="' +
        ds.id +
        '">' +
        '<div>' +
        '<div style="font-weight:600;font-size:13px;">' +
        name +
        '</div>' +
        '<div style="font-size:11px;color:#999;">' +
        rows +
        ' 行 · ' +
        sizeStr +
        '</div>' +
        '</div>' +
        '<button class="cs-copy-btn" style="background:#1976d2;color:white;border:none;border-radius:4px;padding:3px 12px;cursor:pointer;font-size:12px;white-space:nowrap;"' +
        ' data-cs-code="' +
        codeEncoded +
        '">加载</button>' +
        '</div>' +
        // 展开详情
        '<div class="cs-ds-detail" id="cs-detail-' +
        ds.id +
        '" style="display:none;padding:8px 12px;border-top:1px solid #f0f0f0;background:#fafafa;">';

      // Schema 列
      if (ds.columns && ds.columns.length > 0) {
        html +=
          '<div style="font-size:12px;font-weight:600;margin-bottom:4px;">列 (' +
          ds.columns.length +
          '):</div>';
        html +=
          '<div style="display:flex;flex-wrap:wrap;gap:3px;margin-bottom:8px;">';
        for (const col of ds.columns) {
          html +=
            '<span style="padding:1px 6px;background:#fff;border:1px solid #e0e0e0;border-radius:3px;font-size:11px;font-family:monospace;">' +
            escapeHtml(col.name) +
            ':<span style="color:#999;">' +
            escapeHtml(col.type) +
            '</span></span>';
        }
        html += '</div>';
      }

      html +=
        '<div style="font-size:11px;color:#999;word-break:break-all;margin-bottom:4px;">' +
        '路径: ' +
        escapeHtml(ds.local_path || '') +
        '</div>';

      html +=
        '<button class="cs-copy-code-btn" style="margin-top:4px;padding:3px 12px;background:#fff;border:1px solid #e0e0e0;border-radius:4px;cursor:pointer;font-size:12px;"' +
        ' data-cs-code="' +
        codeEncoded +
        '">复制加载代码</button>';

      html += '</div></div>';
    }

    this.node.innerHTML = html;

    // 绑定事件
    this._bindEvents();
  }

  private _bindEvents(): void {
    // 展开/折叠
    const headers = this.node.querySelectorAll('[data-cs-toggle]');
    headers.forEach((el) => {
      el.addEventListener('click', (e) => {
        const target = e.target as HTMLElement;
        // 不拦截按钮点击
        if (target.tagName === 'BUTTON') return;
        const id = el.getAttribute('data-cs-toggle');
        const detail = this.node.querySelector('#cs-detail-' + id) as HTMLElement;
        if (detail) {
          detail.style.display =
            detail.style.display === 'none' ? 'block' : 'none';
        }
      });
    });

    // 复制代码按钮
    const copyBtns = this.node.querySelectorAll(
      '[data-cs-code]'
    ) as NodeListOf<HTMLElement>;
    copyBtns.forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const code = decodeURIComponent(
          btn.getAttribute('data-cs-code') || ''
        );
        if (copyToClipboard(code)) {
          const orig = btn.textContent;
          btn.textContent = '已复制!';
          btn.style.background = '#4caf50';
          btn.style.color = 'white';
          setTimeout(() => {
            btn.textContent = orig;
            btn.style.background = '';
            btn.style.color = '';
          }, 1500);
        }
      });
    });
  }

  private _fetchDatasets(): void {
    this._renderLoading();
    const url = this._apiBase + '/jupyter_list';

    fetch(url, { credentials: 'include' })
      .then((r) => r.json())
      .then((data) => {
        if (data.status === 0) {
          const datasets: DatasetInfo[] = data.result || [];
          if (datasets.length === 0) {
            this._renderEmpty();
          } else {
            this._renderDatasets(datasets);
          }
        } else {
          this._renderError(data.message || '获取数据集列表失败');
        }
      })
      .catch((err) => {
        console.error('[CubeStudio] fetch datasets failed:', err);
        this._renderError('无法连接 Cube Studio API: ' + err.message);
      });
  }
}

// ─── Plugin ────────────────────────────────────────────────

/**
 * JupyterLab 插件: 数据集侧边栏
 */
const plugin: JupyterFrontEndPlugin<void> = {
  id: 'cube-studio-dataset:plugin',
  autoStart: true,
  requires: [ICommandPalette],
  activate: (app: JupyterFrontEnd, palette: ICommandPalette) => {
    console.log('[Cube Studio] JupyterLab extension activated');

    const apiBase = getApiBase();
    console.log('[Cube Studio] API base:', apiBase);

    const panel = new DatasetPanel(apiBase);

    // 添加命令：打开数据集面板
    const commandID = 'cube-studio:open-dataset-panel';
    app.commands.addCommand(commandID, {
      label: 'Cube Studio 数据集',
      caption: '浏览和加载数据集',
      execute: () => {
        if (!panel.isAttached) {
          app.shell.add(panel, 'left', { rank: 900 });
        }
        app.shell.activateById(panel.id);
      },
    });

    // 添加到命令面板
    palette.addItem({ command: commandID, category: 'Cube Studio' });

    // 默认添加到左侧边栏
    app.shell.add(panel, 'left', { rank: 900 });

    // 监听刷新事件 (来自 renderError 中的重试按钮)
    panel.node.addEventListener('cs-refresh', () => {
      panel['_fetchDatasets']();
    });
  },
};

export default plugin;
