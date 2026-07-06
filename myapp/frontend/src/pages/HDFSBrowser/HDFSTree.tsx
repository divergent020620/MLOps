/**
 * HDFS 目录树 — Ant Design Tree 懒加载
 *
 * 特性:
 *  - 懒加载子节点 (点击展开时才请求)
 *  - 双搜索框：库名 + 表名
 *  - 按钮或回车触发搜索，非递归
 *  - 搜索结果直接替换树展示
 */
import React, { useState, useCallback, useEffect } from 'react';
import { Tree, Input, Spin, Empty, message, Button, Space } from 'antd';
import { SearchOutlined, FolderOutlined, FolderOpenOutlined, ReloadOutlined, CloseCircleOutlined } from '@ant-design/icons';
import type { DataNode, EventDataNode } from 'antd/es/tree';
import { searchHDFSPaths, listHDFSDir } from '../../api/hdfsApi';

interface HDFSTreeProps {
    onSelect: (path: string) => void;
    selectedPath: string;
}

const dirToNode = (dir: { name: string; path: string; mtime?: string }): DataNode => ({
    title: dir.name,
    key: dir.path,
    isLeaf: false,
    icon: <FolderOutlined />,
});

function buildSearchTree(results: { name: string; path: string; depth: number }[]): DataNode[] {
    const rootMap = new Map<string, DataNode>();
    for (const r of results) {
        const parts = r.path.split('/').filter(Boolean);
        if (parts.length === 0) continue;
        const rootKey = '/' + parts[0];
        if (!rootMap.has(rootKey)) {
            rootMap.set(rootKey, {
                title: parts[0], key: rootKey, isLeaf: false,
                icon: <FolderOutlined />, children: [],
            });
        }
        let current = rootMap.get(rootKey)!;
        let accPath = rootKey;
        for (let i = 1; i < parts.length; i++) {
            accPath += '/' + parts[i];
            if (!current.children) current.children = [];
            let child = current.children.find(c => c.key === accPath);
            if (!child) {
                child = {
                    title: parts[i], key: accPath,
                    isLeaf: i === parts.length - 1,
                    icon: <FolderOutlined />,
                };
                current.children.push(child);
            }
            current = child;
        }
    }
    return Array.from(rootMap.values());
}

const HDFSTree: React.FC<HDFSTreeProps> = ({ onSelect, selectedPath }) => {
    const [treeData, setTreeData] = useState<DataNode[]>([]);
    const [loading, setLoading] = useState(false);
    const [searching, setSearching] = useState(false);
    const [searchDb, setSearchDb] = useState('');
    const [searchTable, setSearchTable] = useState('');
    const [expandedKeys, setExpandedKeys] = useState<string[]>([]);
    const [isSearchMode, setIsSearchMode] = useState(false);

    useEffect(() => { loadChildren('/'); }, []);

    const loadChildren = useCallback(async (path: string) => {
        setLoading(true);
        try {
            const res = await listHDFSDir({ path, page: 1, page_size: 200 });
            if (res.data?.status === 0) {
                const dirNodes = (res.data.result.dirs || []).map(dirToNode);
                if (path === '/' || !path) {
                    setTreeData(dirNodes);
                } else {
                    setTreeData(prev => updateTreeNode(prev, path, dirNodes));
                }
            }
        } catch (err: any) {
            message.error('HDFS 连接失败');
        } finally {
            setLoading(false);
        }
    }, []);

    const handleLoadData = useCallback(async (node: EventDataNode<DataNode>) => {
        if (isSearchMode) return;
        const path = node.key as string;
        try {
            const res = await listHDFSDir({ path, page: 1, page_size: 200 });
            if (res.data?.status === 0) {
                const dirNodes = (res.data.result.dirs || []).map(dirToNode);
                setTreeData(prev => updateTreeNode(prev, path, dirNodes));
            }
        } catch (err: any) {
            message.error('加载子目录失败');
        }
    }, [isSearchMode]);

    // 搜索：仅库名 或 库名+表名
    const handleSearch = useCallback(async () => {
        const db = searchDb.trim();
        const tb = searchTable.trim();

        if (!db && tb) {
            message.warning('请先输入库名再搜表名');
            return;
        }
        if (!db) return;

        setSearching(true);
        try {
            const params: any = { q: db, limit: 1000 };
            if (tb) params.table = tb;
            const res = await searchHDFSPaths(params);
            if (res.data?.status === 0) {
                const results = res.data.result || [];
                if (results.length === 0) {
                    message.info('未找到匹配的路径');
                    return;
                }
                setTreeData(buildSearchTree(results));
                setIsSearchMode(true);
                const keys = new Set<string>();
                results.forEach((r: { path: string }) => {
                    const parts = r.path.split('/').filter(Boolean);
                    let acc = '';
                    for (const p of parts) {
                        acc += '/' + p;
                        keys.add(acc);
                    }
                });
                setExpandedKeys(Array.from(keys));
            }
        } catch (err: any) {
            message.error('搜索失败');
        } finally {
            setSearching(false);
        }
    }, [searchDb, searchTable]);

    // 清除搜索，恢复完整树
    const handleClearSearch = useCallback(() => {
        setSearchDb('');
        setSearchTable('');
        setIsSearchMode(false);
        setExpandedKeys([]);
        loadChildren('/');
    }, [loadChildren]);

    const handleSelect = useCallback((keys: React.Key[]) => {
        if (keys.length > 0) onSelect(keys[0] as string);
    }, [onSelect]);

    const handleExpand = useCallback((keys: React.Key[]) => {
        setExpandedKeys(keys as string[]);
    }, []);

    return (
        <div style={{ padding: '0 12px' }}>
            {/* 双搜索框 */}
            <Space direction="vertical" size={4} style={{ width: '100%', marginBottom: 12 }}>
                <Input
                    prefix={<SearchOutlined />}
                    placeholder="库名（如 appalm）"
                    value={searchDb}
                    onChange={(e) => setSearchDb(e.target.value)}
                    onPressEnter={handleSearch}
                    allowClear
                    size="small"
                />
                <Input
                    prefix={<SearchOutlined />}
                    placeholder="表名（可选，如 alm_fx）"
                    value={searchTable}
                    onChange={(e) => setSearchTable(e.target.value)}
                    onPressEnter={handleSearch}
                    allowClear
                    size="small"
                />
                <div style={{ display: 'flex', gap: 8 }}>
                    <Button
                        type="primary"
                        size="small"
                        icon={<SearchOutlined />}
                        onClick={handleSearch}
                        loading={searching}
                    >
                        搜索
                    </Button>
                    {isSearchMode && (
                        <Button
                            size="small"
                            icon={<CloseCircleOutlined />}
                            onClick={handleClearSearch}
                            danger
                        >
                            清除
                        </Button>
                    )}
                    <Button
                        size="small"
                        icon={<ReloadOutlined />}
                        onClick={handleClearSearch}
                    >
                        刷新
                    </Button>
                </div>
            </Space>

            <Spin spinning={loading || searching}>
                {treeData.length === 0 && !loading ? (
                    <Empty description="无法连接 HDFS，请检查配置" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : (
                    <Tree
                        showIcon
                        loadData={handleLoadData}
                        treeData={treeData}
                        expandedKeys={expandedKeys}
                        onExpand={handleExpand}
                        onSelect={handleSelect}
                        selectedKeys={selectedPath ? [selectedPath] : []}
                        switcherIcon={<FolderOpenOutlined />}
                    />
                )}
            </Spin>
        </div>
    );
};

// 递归更新 tree node 的 children
function updateTreeNode(nodes: DataNode[], key: string, children: DataNode[]): DataNode[] {
    return nodes.map(node => {
        if (node.key === key) {
            return { ...node, children };
        }
        if (node.children) {
            return { ...node, children: updateTreeNode(node.children, key, children) };
        }
        return node;
    });
}

export default HDFSTree;
