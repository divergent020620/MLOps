/**
 * HDFS 数仓浏览器 — 主页面
 *
 * 布局: 左侧目录树 + 右侧文件面板
 * 功能: 浏览HDFS → 选择分区 → 下载为数据集
 */
import React, { useState, useCallback } from 'react';
import { Layout, message } from 'antd';
import HDFSTree from './HDFSTree';
import FilePanel from './FilePanel';
import DownloadDialog from './DownloadDialog';
import DatasetPreview from './DatasetPreview';
import './style.less';

const { Sider, Content } = Layout;

const HDFSBrowser: React.FC = () => {
    const [selectedPath, setSelectedPath] = useState<string>('');
    const [downloadVisible, setDownloadVisible] = useState(false);
    const [previewVisible, setPreviewVisible] = useState(false);
    const [previewDatasetId, setPreviewDatasetId] = useState<number | null>(null);
    const [newDatasetId, setNewDatasetId] = useState<number | null>(null);

    const handleSelectPath = useCallback((path: string) => {
        setSelectedPath(path);
    }, []);

    const handleDownload = useCallback(() => {
        if (!selectedPath) {
            message.warning('请先在左侧目录树中选择一个目录');
            return;
        }
        setDownloadVisible(true);
    }, [selectedPath]);

    const handleDownloadSuccess = useCallback((datasetId: number) => {
        message.success('数据集下载任务已提交！');
        setDownloadVisible(false);
        setNewDatasetId(datasetId);
    }, []);

    return (
        <Layout className="hdfs-browser" style={{ height: '100%', background: '#fff' }}>
            <Sider
                width={320}
                style={{
                    background: '#fff',
                    borderRight: '1px solid #f0f0f0',
                    overflow: 'auto',
                    padding: '16px 0',
                }}
            >
                <HDFSTree onSelect={handleSelectPath} selectedPath={selectedPath} />
            </Sider>
            <Content style={{ padding: 16, overflow: 'auto' }}>
                <FilePanel
                    path={selectedPath}
                    onDownload={handleDownload}
                    onPreviewDataset={(id) => {
                        setPreviewDatasetId(id);
                        setPreviewVisible(true);
                    }}
                />
            </Content>

            {/* 下载对话框 */}
            <DownloadDialog
                visible={downloadVisible}
                path={selectedPath}
                onCancel={() => setDownloadVisible(false)}
                onSuccess={handleDownloadSuccess}
            />

            {/* 数据集预览 */}
            <DatasetPreview
                visible={previewVisible}
                datasetId={previewDatasetId}
                onClose={() => setPreviewVisible(false)}
            />
        </Layout>
    );
};

export default HDFSBrowser;
