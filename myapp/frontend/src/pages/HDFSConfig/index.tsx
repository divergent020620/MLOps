/**
 * HDFS 连接配置页面 — 仅管理员可见
 *
 * 功能:
 *  - 配置 HDFS 连接参数 (URL / keytab / principal / base_path)
 *  - 配置数据集存储路径
 *  - 连接测试
 *  - 保存到服务端持久化
 */
import React, { useState, useEffect } from 'react';
import {
    Form, Input, Button, Card, message, Spin, Alert, Descriptions, Space, Typography
} from 'antd';
import {
    SaveOutlined, LinkOutlined, SettingOutlined, CheckCircleOutlined
} from '@ant-design/icons';
import { getConfigFull, saveConfig, testHDFSConnection } from '../../api/hdfsApi';

const { Title, Text, Paragraph } = Typography;

const HDFSConfigPage: React.FC = () => {
    const [form] = Form.useForm();
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [testing, setTesting] = useState(false);
    const [connectStatus, setConnectStatus] = useState<{
        connected: boolean;
        error?: string;
        base_path?: string;
    } | null>(null);

    // 加载配置
    useEffect(() => {
        loadConfig();
        testConnection();
    }, []);

    const loadConfig = async () => {
        setLoading(true);
        try {
            const res = await getConfigFull();
            if (res.data?.status === 0) {
                const cfg = res.data.result;
                form.setFieldsValue(cfg);
            }
        } catch (e) {
            message.error('加载配置失败');
        } finally {
            setLoading(false);
        }
    };

    const testConnection = async () => {
        setTesting(true);
        try {
            const res = await testHDFSConnection();
            if (res.data?.status === 0) {
                const result = res.data.result;
                setConnectStatus({
                    connected: result.connected,
                    error: result.connect_error,
                    base_path: result.base_path,
                });
            }
        } catch (e) {
            setConnectStatus({ connected: false, error: '无法获取连接状态' });
        } finally {
            setTesting(false);
        }
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            const values = form.getFieldsValue();
            const res = await saveConfig(values);
            if (res.data?.status === 0) {
                const result = res.data.result;
                if (result.connected) {
                    message.success('配置已保存，连接测试成功！');
                } else {
                    message.warning('配置已保存，但连接测试失败: ' + (result.connect_error || '未知错误'));
                }
                // 刷新连接状态
                testConnection();
            } else {
                message.error(res.data?.message || '保存失败');
            }
        } catch (e: any) {
            message.error('保存失败: ' + (e.message || ''));
        } finally {
            setSaving(false);
        }
    };

    return (
        <div style={{ padding: 24, maxWidth: 800, margin: '0 auto' }}>
            <Title level={3}>
                <SettingOutlined /> HDFS 连接配置
            </Title>
            <Paragraph type="secondary">
                配置 HDFS 数据仓库的连接参数。保存后会自动测试连接。配置生效后可在「数仓浏览(HDFS)」中浏览和下载数据。
            </Paragraph>

            {/* 连接状态 */}
            <Card size="small" style={{ marginBottom: 24 }}>
                <Space>
                    <Text strong>当前状态：</Text>
                    {testing ? (
                        <Spin size="small" />
                    ) : connectStatus?.connected ? (
                        <Alert
                            type="success"
                            message={`已连接 — 基础路径: ${connectStatus.base_path || '/'}`}
                            showIcon
                            icon={<CheckCircleOutlined />}
                            style={{ flex: 1 }}
                        />
                    ) : connectStatus?.error ? (
                        <Alert
                            type="warning"
                            message={`未连接 — ${connectStatus.error}`}
                            showIcon
                            style={{ flex: 1 }}
                        />
                    ) : (
                        <Text type="secondary">未知</Text>
                    )}
                    <Button
                        icon={<LinkOutlined />}
                        onClick={testConnection}
                        loading={testing}
                    >
                        刷新状态
                    </Button>
                </Space>
            </Card>

            {/* 配置表单 */}
            <Card title="连接参数" loading={loading}>
                <Form
                    form={form}
                    layout="vertical"
                    onFinish={handleSave}
                >
                    <Form.Item
                        label="HDFS 地址 (WebHDFS URL)"
                        name="url"
                        rules={[{ required: true, message: '请输入 HDFS 地址' }]}
                        extra="例如: http://namenode:50070"
                    >
                        <Input placeholder="http://namenode:50070" />
                    </Form.Item>

                    <Form.Item
                        label="Keytab 文件路径"
                        name="keytab_path"
                        rules={[{ required: true, message: '请输入 Keytab 路径' }]}
                        extra="Kerberos 认证使用的 keytab 文件绝对路径"
                    >
                        <Input placeholder="/etc/security/keytabs/hdfs.keytab" />
                    </Form.Item>

                    <Form.Item
                        label="Kerberos Principal"
                        name="principal"
                        rules={[{ required: true, message: '请输入 Principal' }]}
                        extra="例如: hdfs@REALM.COM"
                    >
                        <Input placeholder="hdfs@REALM.COM" />
                    </Form.Item>

                    <Form.Item
                        label="HDFS 基础路径"
                        name="base_path"
                        rules={[{ required: true, message: '请输入基础路径' }]}
                        extra="HDFS 上数据仓库的根目录，浏览和搜索都从此路径开始"
                    >
                        <Input placeholder="/user/hive/warehouse" />
                    </Form.Item>

                    <Form.Item
                        label="数据集存储路径"
                        name="datasavepath"
                        extra="从 HDFS 下载的数据集存放的本地目录（容器内路径）"
                    >
                        <Input placeholder="/data/k8s/kubeflow/datasets" />
                    </Form.Item>

                    <Form.Item>
                        <Space>
                            <Button
                                type="primary"
                                htmlType="submit"
                                icon={<SaveOutlined />}
                                loading={saving}
                            >
                                保存并测试连接
                            </Button>
                            <Button onClick={loadConfig} disabled={loading}>
                                重置
                            </Button>
                        </Space>
                    </Form.Item>
                </Form>
            </Card>

            {/* 说明 */}
            <Card title="说明" size="small" style={{ marginTop: 24 }}>
                <Descriptions column={1} size="small">
                    <Descriptions.Item label="Kerberos 认证">
                        系统使用 kinit + keytab 方式进行 Kerberos 认证，需要容器内安装 krb5-user 并正确配置 /etc/krb5.conf。
                    </Descriptions.Item>
                    <Descriptions.Item label="数据集存储">
                        从 HDFS 下载的数据集将保存到「数据集存储路径」下，每个数据集一个子目录，包含 data.parquet、header.json、preview.json 三个文件。
                    </Descriptions.Item>
                    <Descriptions.Item label="权限">
                        此配置页面仅管理员可访问。修改配置后立即生效，无需重启服务。
                    </Descriptions.Item>
                </Descriptions>
            </Card>
        </div>
    );
};

export default HDFSConfigPage;
