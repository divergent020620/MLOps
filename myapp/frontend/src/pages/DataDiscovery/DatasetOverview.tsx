/**
 * 数据集概览页面 — 展示字段 + 前10行数据
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Table, Descriptions, Spin, Empty, Typography, message } from 'antd';
import { ArrowLeftOutlined, TableOutlined } from '@ant-design/icons';
import { getHDFSPreview } from '../../api/hdfsApi';

const { Text, Title } = Typography;

export default function DatasetOverview() {
    const [loading, setLoading] = useState(true);
    const [columns, setColumns] = useState<{ name: string; type: string }[]>([]);
    const [rows, setRows] = useState<any[]>([]);
    const [info, setInfo] = useState<any>({});

    const datasetId = new URLSearchParams(window.location.search).get('id');

    const loadData = useCallback(async () => {
        if (!datasetId) return;
        setLoading(true);
        try {
            const res = await getHDFSPreview(Number(datasetId));
            if (res.data?.status === 0) {
                const d = res.data.result;
                setColumns(d.columns || []);
                setRows(d.rows || []);
                setInfo({
                    name: d.dataset_name,
                    label: d.dataset_label,
                    entries_num: d.entries_num,
                    storage_size: d.storage_size,
                });
            } else {
                message.error(res.data?.message || '加载失败');
            }
        } catch (err: any) {
            message.error('加载数据集失败: ' + (err.message || ''));
        } finally {
            setLoading(false);
        }
    }, [datasetId]);

    useEffect(() => {
        loadData();
    }, [loadData]);

    const tableColumns = columns.map(col => ({
        title: (
            <span>
                {col.name}
                <Text type="secondary" style={{ fontSize: 11, marginLeft: 6 }}>{col.type}</Text>
            </span>
        ),
        dataIndex: col.name,
        key: col.name,
        width: 150,
        ellipsis: true,
        render: (val: any) =>
            val === null || val === undefined ? (
                <Text type="secondary" italic>NULL</Text>
            ) : (
                String(val)
            ),
    }));

    return (
        <div style={{ padding: 24, background: '#f5f5f5', minHeight: '100vh' }}>
            <div style={{ maxWidth: 1400, margin: '0 auto' }}>
                <a
                    href="/frontend/data/media_data/dataset"
                    style={{ display: 'inline-block', marginBottom: 16, color: '#1890ff', fontSize: 14 }}
                >
                    <ArrowLeftOutlined /> 返回列表
                </a>

                <Spin spinning={loading}>
                    {!loading && !columns.length && !rows.length ? (
                        <Empty description="数据集尚未下载完成，暂无预览数据" />
                    ) : (
                        <>
                            <div style={{ background: '#fff', padding: '20px 24px', borderRadius: 6, marginBottom: 16 }}>
                                <Title level={4} style={{ marginBottom: 12 }}>
                                    <TableOutlined /> {info.label || info.name || '-'}
                                </Title>
                                <Descriptions size="small" column={4}>
                                    <Descriptions.Item label="数据量">{info.entries_num || '-'} 行</Descriptions.Item>
                                    <Descriptions.Item label="存储大小">{info.storage_size || '-'}</Descriptions.Item>
                                    <Descriptions.Item label="列数">{columns.length}</Descriptions.Item>
                                </Descriptions>
                            </div>

                            <div style={{ background: '#fff', padding: '20px 24px', borderRadius: 6, marginBottom: 16 }}>
                                <Title level={5}>表结构</Title>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                                    {columns.map(col => (
                                        <span
                                            key={col.name}
                                            style={{
                                                padding: '4px 10px',
                                                background: '#f0f5ff',
                                                border: '1px solid #d6e4ff',
                                                borderRadius: 4,
                                                fontSize: 12,
                                            }}
                                        >
                                            {col.name}
                                            <Text type="secondary" style={{ fontSize: 11, marginLeft: 4 }}>{col.type}</Text>
                                        </span>
                                    ))}
                                </div>
                            </div>

                            <div style={{ background: '#fff', padding: '20px 24px', borderRadius: 6 }}>
                                <Title level={5}>数据预览 (前 {rows.length} 行)</Title>
                                <Table
                                    columns={tableColumns}
                                    dataSource={rows.map((row, i) => ({ ...row, _key: i }))}
                                    rowKey="_key"
                                    size="small"
                                    scroll={{ x: 'max-content' }}
                                    pagination={false}
                                    bordered
                                />
                            </div>
                        </>
                    )}
                </Spin>
            </div>
        </div>
    );
}
