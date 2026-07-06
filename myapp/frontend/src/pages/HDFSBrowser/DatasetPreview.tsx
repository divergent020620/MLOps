/**
 * 数据集预览 Drawer — 展示表头 + 前10行数据 + Jupyter 加载代码
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
    Drawer, Table, Descriptions, Space, Button, message,
    Typography, Spin, Empty, Tabs, Card, Tooltip
} from 'antd';
import { CopyOutlined, CodeOutlined, TableOutlined } from '@ant-design/icons';
import { getHDFSPreview, getJupyterCode } from '../../api/hdfsApi';

const { Text, Paragraph } = Typography;

interface DatasetPreviewProps {
    visible: boolean;
    datasetId: number | null;
    onClose: () => void;
}

const DatasetPreview: React.FC<DatasetPreviewProps> = ({ visible, datasetId, onClose }) => {
    const [loading, setLoading] = useState(false);
    const [columns, setColumns] = useState<{ name: string; type: string }[]>([]);
    const [rows, setRows] = useState<any[]>([]);
    const [jupyterCode, setJupyterCode] = useState<string>('');
    const [datasetInfo, setDatasetInfo] = useState<any>({});

    const loadData = useCallback(async () => {
        if (!datasetId) return;
        setLoading(true);
        try {
            const [previewRes, codeRes] = await Promise.all([
                getHDFSPreview(datasetId),
                getJupyterCode(datasetId),
            ]);

            if (previewRes.data?.status === 0) {
                const data = previewRes.data.result;
                setColumns(data.columns || []);
                setRows(data.rows || []);
                setDatasetInfo({
                    name: data.dataset_name,
                    label: data.dataset_label,
                    entries_num: data.entries_num,
                    storage_size: data.storage_size,
                });
            }

            if (codeRes.data?.status === 0) {
                setJupyterCode(codeRes.data.result.code || '');
            }
        } catch (err: any) {
            message.error('加载数据集预览失败');
        } finally {
            setLoading(false);
        }
    }, [datasetId]);

    useEffect(() => {
        if (visible && datasetId) {
            loadData();
        }
    }, [visible, datasetId, loadData]);

    // 构建 Ant Table 列定义
    const tableColumns = columns.map((col, i) => ({
        title: (
            <Tooltip title={`类型: ${col.type}`}>
                <span>{col.name}</span>
            </Tooltip>
        ),
        dataIndex: col.name,
        key: col.name,
        width: 150,
        ellipsis: true,
    }));

    const handleCopyCode = useCallback(() => {
        navigator.clipboard.writeText(jupyterCode).then(() => {
            message.success('已复制到剪贴板！在 Jupyter 中粘贴即可使用');
        }).catch(() => {
            message.info('复制失败，请手动选择复制');
        });
    }, [jupyterCode]);

    const tabItems = [
        {
            key: 'preview',
            label: <span><TableOutlined /> 数据预览</span>,
            children: (
                <div>
                    <Descriptions size="small" column={2} style={{ marginBottom: 16 }}>
                        <Descriptions.Item label="数据集名称">
                            {datasetInfo.label || datasetInfo.name}
                        </Descriptions.Item>
                        <Descriptions.Item label="数据量">
                            {datasetInfo.entries_num || '-'} 行
                        </Descriptions.Item>
                        <Descriptions.Item label="存储大小">
                            {datasetInfo.storage_size || '-'}
                        </Descriptions.Item>
                        <Descriptions.Item label="列数">
                            {columns.length}
                        </Descriptions.Item>
                    </Descriptions>

                    {/* 列信息 */}
                    {columns.length > 0 && (
                        <div style={{ marginBottom: 16 }}>
                            <Text strong>表结构 ({columns.length} 列)</Text>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 8 }}>
                                {columns.map(col => (
                                    <span
                                        key={col.name}
                                        style={{
                                            padding: '2px 8px',
                                            background: '#f0f5ff',
                                            border: '1px solid #d6e4ff',
                                            borderRadius: 4,
                                            fontSize: 12,
                                        }}
                                    >
                                        {col.name}
                                        <Text type="secondary" style={{ fontSize: 10, marginLeft: 4 }}>
                                            {col.type}
                                        </Text>
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* 前10行数据 */}
                    {rows.length > 0 && (
                        <div>
                            <Text strong>数据预览 (前 {rows.length} 行)</Text>
                            <Table
                                columns={tableColumns}
                                dataSource={rows.map((row, i) => ({ ...row, _key: i }))}
                                rowKey="_key"
                                size="small"
                                scroll={{ x: 'max-content' }}
                                pagination={false}
                                style={{ marginTop: 8 }}
                                bordered
                            />
                        </div>
                    )}
                </div>
            ),
        },
        {
            key: 'code',
            label: <span><CodeOutlined /> Jupyter 加载代码</span>,
            children: (
                <div>
                    <Card
                        size="small"
                        extra={
                            <Button
                                type="primary"
                                size="small"
                                icon={<CopyOutlined />}
                                onClick={handleCopyCode}
                            >
                                复制代码
                            </Button>
                        }
                        style={{ marginBottom: 16 }}
                    >
                        <pre style={{
                            background: '#1e1e1e',
                            color: '#d4d4d4',
                            padding: 16,
                            borderRadius: 8,
                            fontSize: 13,
                            lineHeight: 1.5,
                            overflow: 'auto',
                            whiteSpace: 'pre-wrap',
                        }}>
                            {jupyterCode || '# 代码加载中...'}
                        </pre>
                    </Card>

                    <Paragraph type="secondary">
                        <Text strong>使用说明:</Text><br />
                        1. 在 Jupyter 中新建 Notebook<br />
                        2. 粘贴上方代码到 Cell 中<br />
                        3. 运行 Cell 即可加载数据集
                    </Paragraph>
                </div>
            ),
        },
    ];

    return (
        <Drawer
            title={datasetInfo.label || datasetInfo.name || '数据集预览'}
            open={visible}
            onClose={onClose}
            width={800}
            destroyOnClose
        >
            <Spin spinning={loading}>
                {rows.length === 0 && columns.length === 0 && !loading ? (
                    <Empty description="暂无数据，数据集可能尚未下载完成" />
                ) : (
                    <Tabs items={tabItems} />
                )}
            </Spin>
        </Drawer>
    );
};

export default DatasetPreview;
