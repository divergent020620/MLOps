/**
 * HDFS 浏览器 API 客户端
 */
import axios from './index';

const HDFS_BASE = '/hdfs_browser/api';
const DATASET_BASE = '/dataset_modelview/api';

// ─── HDFS 浏览器 ──────────────────────────────────────────

/** 获取 HDFS 配置 (base_path、连接状态等) */
export const getHDFSConfig = () =>
    axios.get(`${HDFS_BASE}/get_config`);

/** 测试 HDFS 连接 (执行 Kerberos 认证，耗时较长) */
export const testHDFSConnection = () =>
    axios.get(`${HDFS_BASE}/test_connection`);

/** 浏览 HDFS 目录 (分页) */
export const listHDFSDir = (params: {
    path?: string;
    page?: number;
    page_size?: number;
}) => axios.get(`${HDFS_BASE}/list_dir`, { params });

/** 模糊搜索 HDFS 路径 */
export const searchHDFSPaths = (params: {
    q: string;
    table?: string;
    limit?: number;
}) => axios.get(`${HDFS_BASE}/search`, { params });

/** 列出 parquet 文件 (支持日期过滤) */
export const listHDFSFile = (params: {
    path: string;
    partition_col?: string;
    date_start?: string;
    date_end?: string;
}) => axios.get(`${HDFS_BASE}/list_files`, { params });

/** 获取 parquet 文件 schema */
export const getHDFSSchema = (params: { path: string }) =>
    axios.get(`${HDFS_BASE}/get_schema`, { params });

// ─── 数据集操作 ────────────────────────────────────────────

/** 触发 HDFS 下载 (返回 Celery task_id) */
export const triggerHDFSDownload = (datasetId: number, data: {
    partition_values: string[];
    partition_col: string;
    hdfs_path: string;
}) => axios.post(`${DATASET_BASE}/download_from_hdfs/${datasetId}`, data);

/** 查询 HDFS 下载状态/进度 */
export const getDownloadStatus = (datasetId: number) =>
    axios.get(`${DATASET_BASE}/download_status/${datasetId}`);

/** 获取 Jupyter 加载代码 */
export const getJupyterCode = (datasetId: number) =>
    axios.get(`${DATASET_BASE}/jupyter_code/${datasetId}`);

/** 获取 HDFS 数据集预览 (header + 前10行) */
export const getHDFSPreview = (datasetId: number) =>
    axios.get(`${DATASET_BASE}/preview_hdfs/${datasetId}`);

/** Jupyter 数据集列表 */
export const getJupyterDatasetList = () =>
    axios.get(`${DATASET_BASE}/jupyter_list`);

// ─── Admin: HDFS 配置管理 ──────────────────────────────────

/** 获取完整 HDFS 配置 (admin only) */
export const getConfigFull = () =>
    axios.get(`${HDFS_BASE}/get_config_full`);

/** 保存 HDFS 配置 (admin only) */
export const saveConfig = (data: {
    url?: string;
    keytab_path?: string;
    principal?: string;
    base_path?: string;
    datasavepath?: string;
}) => axios.post(`${HDFS_BASE}/save_config`, data);
