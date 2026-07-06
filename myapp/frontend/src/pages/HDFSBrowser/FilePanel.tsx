/**
 * HDFS 文件面板
 *
 * 功能:
 *  - 路径面包屑导航
 *  - 文件列表 (名称/大小/修改时间)
 *  - 日期范围过滤 + 分区列选择
 *  - "下载为数据集" 按钮
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
    Table, Button, Select, DatePicker, Space, Breadcrumb, message,
    Tooltip, Typography, Descriptions, Alert, Spin, Empty
} from 'antd';
import {
    DownloadOutlined, FolderOutlined, FileOutlined,
    CalendarOutlined, ReloadOutlined, EyeOutlined
} from '@ant-design/icons';
import { listHDFSFile, getHDFSConfig } from '../../api/hdfsApi';
import type { ColumnsType } from 'antd/es/table';

const { RangePicker } = DatePicker;
const { Text } = Typography;

interface FilePanelProps {
    path: string;
    onDownload: () => void;
    onPreviewDataset: (datasetId: number) => void;
}

interface FileItem {
    name: string;
    path: string;
    size: number;
    mtime: string;
    partition_value: string | null;
}

const FilePanel: React.FC<FilePanelProps> = ({ path, onDownload, onPreviewDataset }) => {
    const [files, setFiles] = useState<FileItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [partitionCols, setPartitionCols] = useState<string[]>(['dt', 'partition_dt', 'date', 'p_date']);
    const [selectedCol, setSelectedCol] = useState<string | undefined>(undefined);
    const [dateRange, setDateRange] = useState<[string, string] | null>(null);
    const [totalSize, setTotalSize] = useState(0);
    const [partitionValues, setPartitionValues] = useState<string[]>([]);
    const [configLoaded, setConfigLoaded] = useState(false);
    const [connectError, setConnectError] = useState<string | null>(null);
    const [truncated, setTruncated] = useState(false);

    // 加载配置
    useEffect(() => {
        getHDFSConfig().then(res => {
            if (res.data?.status === 0) {
                const cfg = res.data.result;
                if (cfg.partition_col_candidates) {
                    setPartitionCols(cfg.partition_col_candidates);
                }
                if (cfg.connect_error) {
                    setConnectError(cfg.connect_error);
                }
                setConfigLoaded(true);
            }
        }).catch(() => {
            setConfigLoaded(true);
        });
    }, []);

    // 稳定化日期范围：数组每次是新引用，用字符串 key 避免不必要的 loadFiles 重建
    const dateRangeKey = dateRange ? dateRange[0] + '_' + dateRange[1] : '_';

    // 路径变化时加载文件列表
    const loadFiles = useCallback(async () => {
        if (!path) return;
        setLoading(true);
        try {
            const params: any = { path };
            if (selectedCol) params.partition_col = selectedCol;
            if (dateRange && dateRange[0]) params.date_start = dateRange[0];
            if (dateRange && dateRange[1]) params.date_end = dateRange[1];

            const res = await listHDFSFile(params);
            if (res.data?.status === 0) {
                const result = res.data.result;
                setFiles(result.files || []);
                setTotalSize(result.total_size || 0);
                setPartitionValues(result.partition_values || []);
                setTruncated(result.truncated || false);
                if (result.detected_partition_col && !selectedCol) {
                    setSelectedCol(result.detected_partition_col);
                }
            }
        } catch (err: any) {
            message.error('加载文件列表失败');
        } finally {
            setLoading(false);
        }
    }, [path, selectedCol, dateRangeKey]);

    useEffect(() => {
        loadFiles();
    }, [loadFiles]);

    // 格式化路径面包屑
    const pathParts = path ? path.split('/').filter(Boolean) : [];
    const breadcrumbItems = [
        { title: <span style={{ cursor: 'pointer' }}>ROOT</span>, key: '/' },
        ...pathParts.map((part, i) => ({
            title: part,
            key: '/' + pathParts.slice(0, i + 1).join('/'),
        })),
    ];

    // 格式化文件大小
    const formatSize = (bytes: number): string => {
        if (!bytes) return '-';
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        let i = 0;
        let size = bytes;
        while (size >= 1024 && i < units.length - 1) {
            size /= 1024;
            i++;
        }
        return `${size.toFixed(2)} ${units[i]}`;
    };

    const columns: ColumnsType<FileItem> = [
        {
            title: '文件名',
            dataIndex: 'name',
            key: 'name',
            render: (name: string, record: FileItem) => (
                <Space>
                    <FileOutlined style={{ color: '#1890ff' }} />
                    <Text copyable={{ text: record.path }}>{name}</Text>
                </Space>
            ),
        },
        {
            title: '分区值',
            dataIndex: 'partition_value',
            key: 'partition_value',
            width: 150,
            render: (val: string | null) => val || '-',
        },
        {
            title: '大小',
            dataIndex: 'size',
            key: 'size',
            width: 120,
            render: (size: number) => formatSize(size),
            sorter: (a, b) => a.size - b.size,
        },
        {
            title: '修改时间',
            dataIndex: 'mtime',
            key: 'mtime',
            width: 180,
        },
    ];

    if (connectError) {
        return (
            <Alert
                type="warning"
                message="HDFS 连接异常"
                description={connectError}
                showIcon
                style={{ marginBottom: 16 }}
            />
        );
    }

    if (!path) {
        return (
            <Empty
                description="请在左侧选择 HDFS 目录"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                style={{ marginTop: 100 }}
            />
        );
    }

    return (
        <div>
            {/* 面包屑 */}
            <Breadcrumb style={{ marginBottom: 16 }}>
                {breadcrumbItems.map((item, i) => (
                    <Breadcrumb.Item key={item.key}>{item.title}</Breadcrumb.Item>
                ))}
            </Breadcrumb>

            {/* 过滤栏 */}
            <Space style={{ marginBottom: 16 }} wrap>
                <span>
                    <CalendarOutlined /> 分区列:
                </span>
                <Select
                    value={selectedCol}
                    onChange={(v) => setSelectedCol(v)}
                    style={{ width: 160 }}
                    allowClear
                    placeholder="自动检测"
                    options={partitionCols.map(c => ({ label: `${c}=`, value: c }))}
                />

                <RangePicker
                    placeholder={['起始日期', '截止日期']}
                    onChange={(dates) => {
                        if (dates && dates[0] && dates[1]) {
                            setDateRange([
                                dates[0].format('YYYYMMDD'),
                                dates[1].format('YYYYMMDD'),
                            ]);
                        } else {
                            setDateRange(null);
                        }
                    }}
                />

                <Button icon={<ReloadOutlined />} onClick={loadFiles}>
                    刷新
                </Button>
            </Space>

            {/* 汇总信息 */}
            {files.length > 0 && (
                <Descriptions size="small" style={{ marginBottom: 16 }} column={3}>
                    <Descriptions.Item label="文件数">{files.length}</Descriptions.Item>
                    <Descriptions.Item label="总大小">{formatSize(totalSize)}</Descriptions.Item>
                    <Descriptions.Item label="分区数">{partitionValues.length}</Descriptions.Item>
                </Descriptions>
            )}

            {/* 截断提示 */}
            {truncated && (
                <Alert
                    type="warning"
                    message="文件过多，仅展示前 2000 个"
                    description="请缩小日期范围以查看更多文件。下载时不受此限制。"
                    showIcon
                    style={{ marginBottom: 16 }}
                />
            )}

            {/* 操作栏 */}
            <Space style={{ marginBottom: 16 }}>
                <Tooltip title="下载所选日期的所有 parquet 文件为数据集">
                    <Button
                        type="primary"
                        icon={<DownloadOutlined />}
                        onClick={onDownload}
                        disabled={files.length === 0}
                    >
                        下载为数据集
                    </Button>
                </Tooltip>
            </Space>

            {/* 文件表格 */}
            <Spin spinning={loading}>
                <Table
                    columns={columns}
                    dataSource={files}
                    rowKey="path"
                    size="small"
                    pagination={{ pageSize: 50, showTotal: (t) => `共 ${t} 个文件` }}
                    locale={{ emptyText: '当前目录下没有 parquet 文件' }}
                />
            </Spin>
        </div>
    );
};

export default FilePanel;
