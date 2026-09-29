/**
 * Cube Studio Dataset — JupyterLab 4.x Sidebar Extension
 * ------------------------------------------------------------------
 * 在左侧边栏创建「数据集」Tab，列出 Cube Studio 中已下载的 HDFS 数据集，
 * 支持展开看 schema、一键复制加载代码。
 *
 * 与 JL3 旧版的差异（这是本文件存在的全部理由）：
 *   1. 依赖 @jupyterlab/* ^4、@lumino/widgets ^2（旧版是 ^3.4 / ^1.31）
 *   2. 不再依赖 `window.jupyterlab` 全局（JL4 已不暴露）
 *      —— 改用 JupyterFrontEndPlugin 的 activate(app) 注入，这是 JL4 正路
 *   3. 不再用 Tornado OutputTransform 注入页面（JL4 上会抛异常）
 *      —— 面板由 labextension 自己挂载
 *   4. 构建产物走 prebuilt：scoped 到 cube_studio_dataset/labextension
 *
 * 数据来源：Cube Studio 后端 /dataset_modelview/api/jupyter_list
 * （见 myapp/views/view_dataset.py:683 Dataset_ModelView_base.jupyter_list）
 */

import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';

import { ICommandPalette } from '@jupyterlab/apputils';

import { ISettingRegistry } from '@jupyterlab/settingregistry';

import { Message } from '@lumino/messaging';

import { Widget } from '@lumino/widgets';

// ─── 常量 ──────────────────────────────────────────────────────

const PLUGIN_ID = 'cube-studio-dataset:plugin';
const PANEL_ID = 'cube-studio-dataset-panel';
const COMMAND_OPEN = 'cube-studio:open-dataset-panel';
const COMMAND_REFRESH = 'cube-studio:refresh-dataset-panel';

/** 默认 API 前缀：与 JupyterLab 同源（行内 istio 按 path 分流，无需绝对地址） */
const DEFAULT_API_BASE = '/dataset_modelview/api';

// ─── 数据接口 ──────────────────────────────────────────────────

interface DatasetColumn {
  name: string;
  type: string;
}

/**
 * 与后端 jupyter_list 返回结构对齐。
 *
 * ★ 注意 entries_num / storage_size 都是**字符串**，不是数字 ——
 *   后端 model_dataset.py:47-48 这两个字段是 Column(String(200))，
 *   且 hdfs_tasks.py:356-357 用 str() 赋值。
 *   所以绝不能直接 .toLocaleString()（String 没这方法，会抛 TypeError 导致面板空白）。
 */
interface DatasetInfo {
  id: number;
  name: string;
  label?: string;
  source_type?: string;
  storage_size?: string | number;
  entries_num?: string | number;
  columns?: DatasetColumn[];
  local_path?: string;
  load_code?: string;
  describe?: string;
}

/** 后端统一响应包络 */
interface CubeResponse<T> {
  status?: number;
  message?: string;
  result?: T;
}

// ─── 工具函数 ──────────────────────────────────────────────────

function formatSize(b: unknown): string {
  if (b === null || b === undefined || b === '') return '-';
  const s = parseInt(String(b), 10);
  if (!s || Number.isNaN(s)) return String(b);
  if (s >= 1073741824) return (s / 1073741824).toFixed(1) + ' GB';
  if (s >= 1048576) return (s / 1048576).toFixed(1) + ' MB';
  if (s >= 1024) return (s / 1024).toFixed(1) + ' KB';
  return s + ' B';
}

/**
 * 记录条数格式化。
 * 后端给的是 String（可能是 '1000'、'' 或 '1,000'），
 * 也可能直接给数字 —— 统一转成数字再本地化，转不动就原样显示。
 */
function formatCount(v: unknown): string {
  if (v === null || v === undefined || v === '') return '-';
  const n = Number(String(v).replace(/,/g, '').trim());
  return Number.isFinite(n) ? n.toLocaleString() : String(v);
}

function escapeHtml(text: unknown): string {
  const div = document.createElement('div');
  div.textContent = text === null || text === undefined ? '' : String(text);
  return div.innerHTML;
}

/**
 * 复制到剪贴板。
 * 优先用异步 Clipboard API（JL4 页面通常是安全上下文），失败回退 execCommand。
 */
async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* 落到下面的回退 */
  }
  try {
    const el = document.createElement('textarea');
    el.value = text;
    el.style.position = 'fixed';
    el.style.top = '-1000px';
    el.style.opacity = '0';
    document.body.appendChild(el);
    el.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(el);
    return ok;
  } catch {
    return false;
  }
}

// ─── 面板 Widget ───────────────────────────────────────────────

class DatasetPanel extends Widget {
  private _apiBase: string;
  private _loading = false;

  constructor(apiBase: string) {
    super();
    this._apiBase = apiBase;

    this.id = PANEL_ID;
    this.title.label = '数据集';
    this.title.caption = 'Cube Studio 数据集';
    this.title.closable = true;
    this.addClass('cs-dataset-panel');

    this.node.style.padding = '8px';
    this.node.style.overflowY = 'auto';
    this.node.style.height = '100%';
    this.node.style.boxSizing = 'border-box';
  }

  get apiBase(): string {
    return this._apiBase;
  }

  set apiBase(v: string) {
    this._apiBase = v;
  }

  /** 首次挂载时拉一次数据 */
  protected onAfterShow(msg: Message): void {
    super.onAfterShow(msg);
    if (!this._loaded) {
      this._loaded = true;
      void this.refresh();
    }
  }

  private _loaded = false;

  /** 公开的刷新入口（命令 / 按钮都用它） */
  async refresh(): Promise<void> {
    if (this._loading) return;
    this._loading = true;
    try {
      await this._fetchDatasets();
    } finally {
      this._loading = false;
    }
  }

  // ── 渲染 ──────────────────────────────────────────────────

  private _shell(titleText: string, bodyHtml: string): void {
    this.node.innerHTML =
      '<div class="cs-ds-shell">' +
      '<div class="cs-ds-titlebar">' +
      '<span class="cs-ds-title">' +
      escapeHtml(titleText) +
      '</span>' +
      '<button class="cs-ds-refresh" title="刷新">刷新</button>' +
      '</div>' +
      bodyHtml +
      '</div>';
    const btn = this.node.querySelector('.cs-ds-refresh');
    if (btn) {
      btn.addEventListener('click', () => {
        void this.refresh();
      });
    }
  }

  private _renderLoading(): void {
    this._shell('数据集', '<div class="cs-ds-hint">加载中…</div>');
  }

  private _renderEmpty(): void {
    this._shell(
      '数据集',
      '<div class="cs-ds-hint">暂无可用数据集<br>' +
        '<small>请先在 Cube Studio「数仓浏览(HDFS)」中下载数据集</small></div>'
    );
  }

  private _renderError(msg: string): void {
    this._shell(
      '数据集',
      '<div class="cs-ds-error">' +
        escapeHtml(msg) +
        '<div class="cs-ds-error-hint">' +
        ' 请确认：① 笔记本与 Cube Studio 同源；② 数据集已下载；③ 登录态未过期' +
        '</div></div>'
    );
  }

  private _renderDatasets(datasets: DatasetInfo[]): void {
    let body = '<div class="cs-ds-count">共 ' + datasets.length + ' 个</div>';

    for (const ds of datasets) {
      const label = escapeHtml(ds.label || ds.name);
      const rows = formatCount(ds.entries_num);
      const sizeStr = formatSize(ds.storage_size);
      const code = ds.load_code || '';
      const codeAttr = escapeHtml(encodeURIComponent(code));
      const cols = ds.columns || [];

      body +=
        '<div class="cs-ds-item">' +
        '<div class="cs-ds-head" data-cs-toggle="' +
        ds.id +
        '">' +
        '<div class="cs-ds-head-main">' +
        '<div class="cs-ds-name">' +
        label +
        '</div>' +
        '<div class="cs-ds-meta">' +
        rows +
        ' 行 · ' +
        sizeStr +
        '</div>' +
        '</div>' +
        '<button class="cs-ds-copy cs-ds-copy-primary" data-cs-code="' +
        codeAttr +
        '">加载</button>' +
        '</div>' +
        '<div class="cs-ds-detail" data-cs-detail="' +
        ds.id +
        '">';

      if (cols.length > 0) {
        body +=
          '<div class="cs-ds-detail-label">列 (' + cols.length + ')</div>' +
          '<div class="cs-ds-cols">';
        for (const col of cols) {
          body +=
            '<span class="cs-ds-col">' +
            escapeHtml(col.name) +
            '<span class="cs-ds-col-type">:' +
            escapeHtml(col.type) +
            '</span></span>';
        }
        body += '</div>';
      }

      if (ds.local_path) {
        body +=
          '<div class="cs-ds-path">路径: ' + escapeHtml(ds.local_path) + '</div>';
      }

      body +=
        '<button class="cs-ds-copy" data-cs-code="' +
        codeAttr +
        '">复制加载代码</button>' +
        '</div></div>';
    }

    this._shell('数据集', body);
    this._bindEvents();
  }

  // ── 事件绑定 ──────────────────────────────────────────────

  private _bindEvents(): void {
    // 展开 / 收起
    this.node.querySelectorAll('[data-cs-toggle]').forEach(el => {
      el.addEventListener('click', (ev: Event) => {
        const target = ev.target as HTMLElement;
        if (target && target.tagName === 'BUTTON') return;
        const id = (el as HTMLElement).getAttribute('data-cs-toggle');
        const detail = this.node.querySelector(
          '[data-cs-detail="' + id + '"]'
        ) as HTMLElement | null;
        if (detail) {
          detail.classList.toggle('cs-ds-open');
        }
      });
    });

    // 复制按钮
    this.node.querySelectorAll('[data-cs-code]').forEach(el => {
      el.addEventListener('click', (ev: Event) => {
        ev.stopPropagation();
        const btn = el as HTMLElement;
        const code = decodeURIComponent(btn.getAttribute('data-cs-code') || '');
        void copyToClipboard(code).then(ok => {
          const orig = btn.textContent || '';
          btn.textContent = ok ? '已复制' : '复制失败';
          btn.classList.add(ok ? 'cs-ds-copied' : 'cs-ds-copyfail');
          window.setTimeout(() => {
            btn.textContent = orig;
            btn.classList.remove('cs-ds-copied', 'cs-ds-copyfail');
          }, 1500);
        });
      });
    });
  }

  // ── 取数 ──────────────────────────────────────────────────

  private async _fetchDatasets(): Promise<void> {
    this._renderLoading();
    const url = this._apiBase.replace(/\/+$/, '') + '/jupyter_list';
    try {
      const resp = await fetch(url, {
        credentials: 'include',
        headers: { Accept: 'application/json' }
      });

      if (resp.status === 401 || resp.status === 403) {
        this._renderError('未登录或登录已过期（HTTP ' + resp.status + '）');
        return;
      }
      if (!resp.ok) {
        this._renderError('接口返回 HTTP ' + resp.status);
        return;
      }

      const data = (await resp.json()) as CubeResponse<DatasetInfo[]>;
      if (data.status === 0) {
        const datasets = data.result || [];
        if (datasets.length === 0) {
          this._renderEmpty();
        } else {
          this._renderDatasets(datasets);
        }
      } else {
        this._renderError(data.message || '获取数据集列表失败');
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error('[CubeStudio] fetch datasets failed:', err);
      this._renderError('无法连接 Cube Studio API：' + msg);
    }
  }
}

// ─── 插件入口 ──────────────────────────────────────────────────

/**
 * JupyterLab 4 插件：数据集侧边栏。
 *
 * 注意 `optional: [ICommandPalette]` —— 用 optional 而非 requires，
 * 命令面板缺失时面板本身仍能正常挂载。
 */
const plugin: JupyterFrontEndPlugin<void> = {
  id: PLUGIN_ID,
  description: 'Cube Studio 数据集面板',
  autoStart: true,
  optional: [ICommandPalette, ISettingRegistry],
  activate: async (
    app: JupyterFrontEnd,
    palette: ICommandPalette | null,
    settingRegistry: ISettingRegistry | null
  ) => {
    console.log('[CubeStudio] JupyterLab extension 已激活');

    // 读用户设置（可选）
    let apiBase = DEFAULT_API_BASE;
    let autoOpen = true;
    if (settingRegistry) {
      try {
        const settings = await settingRegistry.load(PLUGIN_ID);
        const custom = settings.get('apiBase').composite as string | undefined;
        if (custom && custom.trim()) {
          apiBase = custom.trim();
        }
        autoOpen = (settings.get('autoOpen').composite as boolean) ?? true;
      } catch (err) {
        console.warn('[CubeStudio] 读取设置失败，使用默认值:', err);
      }
    }

    // 兜底：允许运维在页面上覆盖 API 前缀
    const injected = (window as unknown as { _cube_studio_api?: string })
      ._cube_studio_api;
    if (injected) {
      apiBase = injected;
    }
    console.log('[CubeStudio] API base =', apiBase);

    const panel = new DatasetPanel(apiBase);

    const reveal = (): void => {
      if (!panel.isAttached) {
        app.shell.add(panel, 'left', { rank: 900 });
      }
      app.shell.activateById(panel.id);
    };

    app.commands.addCommand(COMMAND_OPEN, {
      label: 'Cube Studio 数据集',
      caption: '浏览和加载数据集',
      execute: () => {
        reveal();
      }
    });

    app.commands.addCommand(COMMAND_REFRESH, {
      label: '刷新数据集列表',
      caption: '重新拉取 Cube Studio 数据集列表',
      isEnabled: () => panel.isAttached,
      execute: () => {
        void panel.refresh();
      }
    });

    if (palette) {
      palette.addItem({ command: COMMAND_OPEN, category: 'Cube Studio' });
      palette.addItem({ command: COMMAND_REFRESH, category: 'Cube Studio' });
    }

    if (autoOpen) {
      app.shell.add(panel, 'left', { rank: 900 });
    }

    console.log('[CubeStudio] 数据集面板已挂载');
  }
};

export default plugin;
