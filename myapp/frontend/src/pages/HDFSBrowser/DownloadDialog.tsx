/**
 * 下载对话框 — 选择分区列 + 日期范围 + 数据集名称
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
    Modal, Form, Input, Select, DatePicker, Steps, Space,
    Button, message, Alert, Spin, Descriptions, Progress, Result
} from 'antd';
import {
    CalendarOutlined, InfoCircleOutlined, CheckCircleOutlined,
    LoadingOutlined, ExclamationCircleOutlined
} from '@ant-design/icons';
import {
    listHDFSFile, triggerHDFSDownload, getDownloadStatus, getHDFSConfig
} from '../../api/hdfsApi';

const { RangePicker } = DatePicker;
const { TextArea } = Input;

interface DownloadDialogProps {
    visible: boolean;
    path: string;
    onCancel: () => void;
    onSuccess: (datasetId: number) => void;
}

const DownloadDialog: React.FC<DownloadDialogProps> = ({ visible, path, onCancel, onSuccess }) => {
    const [form] = Form.useForm();
    const [currentStep, setCurrentStep] = useState(0);
    const [loading, setLoading] = useState(false);
    const [fileSummary, setFileSummary] = useState<{
        total_files: number;
        total_size: number;
        partition_values: string[];
    } | null>(null);
    const [partitionCols, setPartitionCols] = useState<string[]>(['dt', 'partition_dt']);
    const [datasetId, setDatasetId] = useState<number | null>(null);
    const [downloadProgress, setDownloadProgress] = useState(0);
    const [downloadStatus, setDownloadStatus] = useState<string>('pending');
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const [pollTimer, setPollTimer] = useState<ReturnType<typeof setInterval> | null>(null);

    // 加载配置
    useEffect(() => {
        if (visible) {
            getHDFSConfig().then(res => {
                if (res.data?.status === 0 && res.data.result.partition_col_candidates) {
                    setPartitionCols(res.data.result.partition_col_candidates);
                }
            }).catch(() => {});
        }
    }, [visible]);

    // 重置状态
    const resetState = useCallback(() => {
        setCurrentStep(0);
        setFileSummary(null);
        setDatasetId(null);
        setDownloadProgress(0);
        setDownloadStatus('pending');
        setErrorMessage(null);
        form.resetFields();
        if (pollTimer) {
            clearInterval(pollTimer);
            setPollTimer(null);
        }
    }, [form, pollTimer]);

    // 组件卸载时清理定时器
    useEffect(() => {
        return () => {
            if (pollTimer) {
                clearInterval(pollTimer);
            }
        };
    }, [pollTimer]);

    // 关闭时重置
    const handleCancel = useCallback(() => {
        resetState();
        onCancel();
    }, [resetState, onCancel]);

    // Step 1: 预览要下载的文件
    const handlePreviewFiles = useCallback(async () => {
        if (!path) return;
        setLoading(true);
        try {
            const partitionCol = form.getFieldValue('partition_col');
            const dateRange = form.getFieldValue('date_range');

            const params: any = { path };
            if (partitionCol) params.partition_col = partitionCol;
            if (dateRange && dateRange[0]) {
                params.date_start = dateRange[0].format('YYYYMMDD');
                params.date_end = dateRange[1].format('YYYYMMDD');
            }

            const res = await listHDFSFile(params);
            if (res.data?.status === 0) {
                const result = res.data.result;
                setFileSummary({
                    total_files: result.total_count,
                    total_size: result.total_size,
                    partition_values: result.partition_values,
                });
                setCurrentStep(1);
            } else {
                message.error(res.data?.message || '获取文件列表失败');
            }
        } catch (err: any) {
            message.error('获取文件列表失败: ' + (err.message || ''));
        } finally {
            setLoading(false);
        }
    }, [path, form]);

    // Step 2: 创建数据集 + 触发下载
    const handleCreateAndDownload = useCallback(async () => {
        setLoading(true);
        try {
            // 用 getFieldValue 而非 validateFields（step 1 时表单字段已卸载，validateFields 拿不到值）
            const partitionCol = form.getFieldValue('partition_col') || 'dt';
            const dateRange = form.getFieldValue('date_range');
            const datasetName = form.getFieldValue('dataset_name');
            const datasetLabel = form.getFieldValue('dataset_label');
            const datasetDesc = form.getFieldValue('describe');

            if (!dateRange || !dateRange[0]) {
                message.error('请选择日期范围');
                return;
            }
            if (!datasetName) {
                message.error('请输入数据集名称');
                return;
            }
            const dateStart = dateRange[0].format('YYYYMMDD');
            const dateEnd = dateRange[1].format('YYYYMMDD');

            // 生成分区间列表
            const partitionValues = fileSummary?.partition_values || [];
            const filteredValues = partitionValues.filter(pv => {
                const d = pv.replace(/[^0-9]/g, '').slice(0, 8);
                return d >= dateStart && d <= dateEnd;
            });

            if (filteredValues.length === 0) {
                message.warning('所选日期范围内没有分区数据');
                return;
            }

            // 先创建数据集记录 (通过 API)
            // 使用现有的数据集 API 创建一个以 hdfs 为 source 的数据集
            const safeDatasetName = datasetName || path.split('/').pop() || `hdfs_${Date.now()}`;

            // 创建数据集
            const createRes = await fetch('/dataset_modelview/api/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: safeDatasetName.replace(/[^a-z0-9_-]/gi, '_').toLowerCase(),
                    label: datasetLabel || safeDatasetName,
                    describe: datasetDesc || `HDFS: ${path}`,
                    source_type: 'hdfs',
                    source: path,
                    file_type: 'parquet',
                    hdfs_path: path,
                }),
            }).then(r => r.json());

            let dsId: number;
            if (createRes.status === 0 && createRes.result?.id) {
                dsId = createRes.result.id;
            } else {
                // 如果前端创建失败，尝试通过后端直接
                throw new Error('创建数据集记录失败: ' + (createRes.message || ''));
            }

            setDatasetId(dsId);

            // 触发下载
            const downloadRes = await triggerHDFSDownload(dsId, {
                partition_values: filteredValues,
                partition_col: partitionCol,
                hdfs_path: path,
            });

            if (downloadRes.data?.status === 0) {
                const celeryTaskId = downloadRes.data.result?.celery_task_id;
                setCurrentStep(2);
                setDownloadStatus('downloading');

                // 轮询进度
                const timer = setInterval(async () => {
                    try {
                        const statusRes = await getDownloadStatus(dsId);
                        if (statusRes.data?.status === 0) {
                            const s = statusRes.data.result;
                            setDownloadProgress(s.download_progress || 0);
                            setDownloadStatus(s.download_status);
                            if (s.error_message) setErrorMessage(s.error_message);
                            if (s.download_status === 'completed') {
                                clearInterval(timer);
                                setCurrentStep(3);
                                onSuccess(dsId);
                            } else if (s.download_status === 'failed') {
                                clearInterval(timer);
                                setCurrentStep(3);
                                setErrorMessage(s.error_message || '下载失败');
                            }
                        }
                    } catch (e) {
                        // 忽略轮询错误
                    }
                }, 2000);
                setPollTimer(timer);
            } else {
                message.error(downloadRes.data?.message || '提交下载任务失败');
                setCurrentStep(1);
            }
        } catch (err: any) {
            message.error(err.message || '操作失败');
        } finally {
            setLoading(false);
        }
    }, [form, path, fileSummary, onSuccess]);

    // 格式化大小
    const formatSize = (bytes: number) => {
        if (!bytes) return '-';
        if (bytes >= 1073741824) return `${(bytes / 1073741824).toFixed(2)} GB`;
        if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(2)} MB`;
        if (bytes >= 1024) return `${(bytes / 1024).toFixed(2)} KB`;
        return `${bytes} B`;
    };

    // ── 渲染 ──

    const steps = [
        { title: '选择参数', icon: loading ? <LoadingOutlined /> : <CalendarOutlined /> },
        { title: '确认文件', icon: <InfoCircleOutlined /> },
        { title: '下载中', icon: <LoadingOutlined /> },
        { title: '完成', icon: <CheckCircleOutlined /> },
    ];

    return (
        <Modal
            title="下载 HDFS 数据为数据集"
            open={visible}
            onCancel={handleCancel}
            width={640}
            footer={null}
            destroyOnClose
            maskClosable={false}
        >
            <Steps current={currentStep} size="small" style={{ marginBottom: 24 }}>
                {steps.map((s, i) => (
                    <Steps.Step key={i} title={s.title} icon={s.icon} />
                ))}
            </Steps>

            {currentStep === 0 && (
                <Form form={form} layout="vertical">
                    <Alert
                        message={`选择路径: ${path}`}
                        type="info"
                        showIcon
                        style={{ marginBottom: 16 }}
                    />

                    <Form.Item label="分区列名" name="partition_col" initialValue="dt">
                        <Select
                            options={partitionCols.map(c => ({
                                label: `${c}=YYYYMMDD`,
                                value: c,
                            }))}
                        />
                    </Form.Item>

                    <Form.Item
                        label="日期范围"
                        name="date_range"
                        rules={[{ required: true, message: '请选择日期范围' }]}
                    >
                        <RangePicker style={{ width: '100%' }} />
                    </Form.Item>

                    <Form.Item
                        label="数据集名称(英文)"
                        name="dataset_name"
                        rules={[{ required: true, message: '请输入数据集名称' }]}
                    >
                        <Input placeholder="如: mlm_tab_popup_feature" />
                    </Form.Item>

                    <Form.Item label="数据集中文名" name="dataset_label">
                        <Input placeholder="如: 弹窗预测特征" />
                    </Form.Item>

                    <Form.Item label="描述" name="describe">
                        <TextArea rows={3} placeholder="数据集描述信息..." />
                    </Form.Item>

                    <Form.Item>
                        <Space>
                            <Button type="primary" onClick={handlePreviewFiles} loading={loading}>
                                预览文件
                            </Button>
                            <Button onClick={handleCancel}>取消</Button>
                        </Space>
                    </Form.Item>
                </Form>
            )}

            {currentStep === 1 && fileSummary && (
                <div>
                    <Descriptions bordered size="small" column={2}>
                        <Descriptions.Item label="文件总数">
                            {fileSummary.total_files}
                        </Descriptions.Item>
                        <Descriptions.Item label="总大小">
                            {formatSize(fileSummary.total_size)}
                        </Descriptions.Item>
                        <Descriptions.Item label="分区数">
                            {fileSummary.partition_values.length}
                        </Descriptions.Item>
                        <Descriptions.Item label="分区列">
                            {form.getFieldValue('partition_col') || 'dt'}
                        </Descriptions.Item>
                    </Descriptions>

                    {fileSummary.partition_values.length > 0 && (
                        <div style={{ marginTop: 16 }}>
                            <Alert
                                type="success"
                                message={`将下载 ${fileSummary.partition_values.length} 个分区的数据`}
                                description={`分区值: ${fileSummary.partition_values.join(', ')}`}
                                showIcon
                                style={{ maxHeight: 120, overflow: 'auto' }}
                            />
                        </div>
                    )}

                    <div style={{ marginTop: 24, textAlign: 'right' }}>
                        <Space>
                            <Button onClick={() => setCurrentStep(0)}>上一步</Button>
                            <Button type="primary" onClick={handleCreateAndDownload} loading={loading}>
                                确认下载
                            </Button>
                        </Space>
                    </div>
                </div>
            )}

            {currentStep === 2 && (
                <div style={{ textAlign: 'center', padding: '40px 0' }}>
                    <Spin spinning={true} size="large" />
                    <div style={{ marginTop: 24 }}>
                        <Progress percent={downloadProgress} status="active" />
                        <p style={{ marginTop: 16, color: '#666' }}>
                            正在下载数据集，请勿关闭页面...
                        </p>
                        <p style={{ color: '#999', fontSize: 12 }}>
                            下载完成后会自动创建数据集的 header.json 和 preview.json
                        </p>
                    </div>
                </div>
            )}

            {currentStep === 3 && (
                <div style={{ textAlign: 'center', padding: '40px 0' }}>
                    {downloadStatus === 'completed' ? (
                        <Result
                            status="success"
                            title="数据集下载完成！"
                            subTitle="数据集已保存到本地，包含 data.parquet / header.json / preview.json 三个文件"
                            extra={[
                                <Button type="primary" key="close" onClick={handleCancel}>
                                    关闭
                                </Button>,
                            ]}
                        />
                    ) : (
                        <Result
                            status="error"
                            title="下载失败"
                            subTitle={errorMessage || '未知错误'}
                            extra={[
                                <Button key="retry" onClick={() => {
                                    setCurrentStep(1);
                                    setErrorMessage(null);
                                }}>
                                    重试
                                </Button>,
                                <Button key="close" onClick={handleCancel}>
                                    关闭
                                </Button>,
                            ]}
                        />
                    )}
                </div>
            )}
        </Modal>
    );
};

export default DownloadDialog;
