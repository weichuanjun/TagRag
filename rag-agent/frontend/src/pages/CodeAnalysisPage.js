import React, { useState, useEffect, useCallback } from 'react';
import {
    Table, Card, Tabs, Button, Modal, Spin, Tree, Tag, Space, Input,
    Collapse, message, Progress, Tooltip, Select, Empty, Divider, Row, Col,
    List, Statistic
} from 'antd';
import {
    SearchOutlined, CodeOutlined, BranchesOutlined,
    RocketOutlined, FileOutlined, RobotOutlined, FolderOutlined,
    ArrowRightOutlined, UploadOutlined, LoadingOutlined
} from '@ant-design/icons';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import ReactFlow, { Controls, Background } from 'reactflow';
import 'reactflow/dist/style.css';
import axios from 'axios';

const { TabPane } = Tabs;
const { Panel } = Collapse;
const { Search } = Input;
const { DirectoryTree } = Tree;
const { Option } = Select;

// 语言到文件扩展名的映射
const languageExtensions = {
    "python": "py",
    "javascript": "js",
    "typescript": "ts",
    "java": "java",
    "cpp": "cpp",
    "c": "c"
};

// 组件图标映射
const typeIcons = {
    "function": <CodeOutlined />,
    "class": <BranchesOutlined />,
    "method": <ArrowRightOutlined />,
    "react_component": <RocketOutlined />
};

const CodeAnalysisPage = () => {
    // 状态管理
    const [repositories, setRepositories] = useState([]);
    const [currentRepo, setCurrentRepo] = useState(null);
    const [repoSummary, setRepoSummary] = useState(null);
    const [loading, setLoading] = useState(false);
    const [searchResults, setSearchResults] = useState([]);
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedComponent, setSelectedComponent] = useState(null);
    const [componentDetails, setComponentDetails] = useState(null);
    const [impactAnalysis, setImpactAnalysis] = useState(null);
    const [directoryTree, setDirectoryTree] = useState(null);
    const [dependencies, setDependencies] = useState([]);
    const [llmModalVisible, setLlmModalVisible] = useState(false);
    const [llmSummary, setLlmSummary] = useState('');
    const [llmLoading, setLlmLoading] = useState(false);
    const [uploadModalVisible, setUploadModalVisible] = useState(false);
    const [localRepoPath, setLocalRepoPath] = useState('');
    const [componentType, setComponentType] = useState(null);

    // 加载仓库列表
    const fetchRepositories = useCallback(async () => {
        try {
            setLoading(true);
            const response = await axios.get('/code/repositories');
            setRepositories(response.data);
            if (response.data.length > 0 && !currentRepo) {
                setCurrentRepo(response.data[0]);
            }
        } catch (error) {
            message.error('加载代码库失败');
            console.error(error);
        } finally {
            setLoading(false);
        }
    }, [currentRepo]);

    // 加载仓库摘要
    const fetchRepoSummary = useCallback(async (repoId) => {
        if (!repoId) return;

        try {
            setLoading(true);
            const response = await axios.get(`/code/repositories/${repoId}`);
            setRepoSummary(response.data);

            // 同时加载目录结构
            const structureResponse = await axios.get(`/code/repositories/${repoId}/structure`);
            setDirectoryTree(structureResponse.data);
        } catch (error) {
            message.error('加载代码库摘要失败');
            console.error(error);
        } finally {
            setLoading(false);
        }
    }, []);

    // 首次加载和仓库切换时
    useEffect(() => {
        fetchRepositories();
    }, [fetchRepositories]);

    useEffect(() => {
        if (currentRepo) {
            fetchRepoSummary(currentRepo.id);
        }
    }, [currentRepo, fetchRepoSummary]);

    // 搜索代码
    const handleSearch = async (query) => {
        if (!query.trim() || !currentRepo) {
            if (!currentRepo) {
                message.error('请先选择一个代码库');
            }
            return;
        }

        setSearchQuery(query);
        setLoading(true);
        setSearchResults([]);

        console.log(`执行搜索: repo_id=${currentRepo.id}, query=${query}, type=${componentType || '所有类型'}`);

        try {
            const response = await axios.get('/code/search', {
                params: {
                    repo_id: currentRepo.id,
                    query: query,
                    component_type: componentType
                }
            });
            console.log('搜索结果:', response.data);

            if (Array.isArray(response.data)) {
                setSearchResults(response.data);
                if (response.data.length === 0) {
                    message.info('没有找到匹配的结果');
                }
            } else {
                console.error('返回的搜索结果不是数组:', response.data);
                message.error('搜索结果格式异常');
            }
        } catch (error) {
            console.error('搜索错误:', error);
            if (error.response) {
                console.error('错误响应:', error.response.data);
                message.error(`搜索失败: ${error.response.data.detail || error.message}`);
            } else {
                message.error(`搜索失败: ${error.message}`);
            }
        } finally {
            setLoading(false);
        }
    };

    // 查看组件详情
    const viewComponentDetails = async (componentId) => {
        setLoading(true);
        try {
            const response = await axios.get(`/code/components/${componentId}`);
            setSelectedComponent(componentId);
            setComponentDetails(response.data);

            // 构建依赖关系图数据
            const nodes = [];
            const edges = [];

            // 中心节点（当前组件）
            nodes.push({
                id: `component-${response.data.id}`,
                data: {
                    label: (
                        <div style={{ padding: '5px' }}>
                            {typeIcons[response.data.type] || <CodeOutlined />}
                            <span style={{ marginLeft: '5px' }}>{response.data.name}</span>
                        </div>
                    )
                },
                position: { x: 250, y: 100 },
                style: {
                    background: '#1890ff',
                    color: 'white',
                    border: '1px solid #096dd9',
                    borderRadius: '3px'
                }
            });

            // 添加依赖节点
            response.data.dependencies.forEach((dep, index) => {
                const angle = (index * (Math.PI * 2)) / response.data.dependencies.length;
                const x = 250 + Math.cos(angle) * 150;
                const y = 100 + Math.sin(angle) * 150;

                nodes.push({
                    id: `dependency-${dep.id}`,
                    data: {
                        label: (
                            <div style={{ padding: '3px' }}>
                                {typeIcons[dep.type] || <CodeOutlined />}
                                <span style={{ marginLeft: '5px', fontSize: '0.85em' }}>{dep.name}</span>
                            </div>
                        )
                    },
                    position: { x, y },
                    style: {
                        background: '#52c41a',
                        color: 'white',
                        border: '1px solid #389e0d',
                        borderRadius: '3px',
                        fontSize: '0.9em'
                    }
                });

                edges.push({
                    id: `edge-to-${dep.id}`,
                    source: `component-${response.data.id}`,
                    target: `dependency-${dep.id}`,
                    animated: true,
                    style: { stroke: '#52c41a' }
                });
            });

            // 添加被依赖节点
            response.data.dependents.forEach((dep, index) => {
                const angle = (index * (Math.PI * 2)) / response.data.dependents.length;
                const x = 250 + Math.cos(angle) * 150;
                const y = 250 + Math.sin(angle) * 150;

                nodes.push({
                    id: `dependent-${dep.id}`,
                    data: {
                        label: (
                            <div style={{ padding: '3px' }}>
                                {typeIcons[dep.type] || <CodeOutlined />}
                                <span style={{ marginLeft: '5px', fontSize: '0.85em' }}>{dep.name}</span>
                            </div>
                        )
                    },
                    position: { x, y },
                    style: {
                        background: '#f5222d',
                        color: 'white',
                        border: '1px solid #cf1322',
                        borderRadius: '3px',
                        fontSize: '0.9em'
                    }
                });

                edges.push({
                    id: `edge-from-${dep.id}`,
                    source: `dependent-${dep.id}`,
                    target: `component-${response.data.id}`,
                    animated: true,
                    style: { stroke: '#f5222d' }
                });
            });

            setDependencies({ nodes, edges });

            // 分析影响
            const impactResponse = await axios.get(`/code/components/${componentId}/impact`);
            setImpactAnalysis(impactResponse.data);

        } catch (error) {
            message.error('获取组件详情失败');
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    // 生成组件摘要
    const generateSummary = async (componentId) => {
        setLlmLoading(true);
        setLlmModalVisible(true);
        try {
            const response = await axios.post(`/code/components/${componentId}/generate-summary`);
            setLlmSummary(response.data.summary);
        } catch (error) {
            message.error('生成摘要失败');
            console.error(error);
            setLlmSummary('生成摘要失败，请重试。');
        } finally {
            setLlmLoading(false);
        }
    };

    // 添加本地代码仓库
    const addLocalRepo = async () => {
        if (!localRepoPath.trim()) {
            message.error('请输入有效的代码库路径');
            return;
        }

        setLoading(true);
        try {
            const response = await axios.post('/code/repositories', {
                repo_path: localRepoPath
            });

            message.success('代码库添加成功');
            setUploadModalVisible(false);
            setLocalRepoPath('');

            // 刷新仓库列表
            fetchRepositories();
        } catch (error) {
            message.error('添加代码库失败');
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    // 创建示例代码库
    const createExampleRepo = async () => {
        setLoading(true);
        try {
            const response = await axios.post('/code/repositories/create-example');
            message.success('示例代码库创建成功');

            // 刷新仓库列表
            fetchRepositories();
        } catch (error) {
            console.error('创建示例代码库失败:', error);
            message.error('创建示例代码库失败');
        } finally {
            setLoading(false);
        }
    };

    // 构建目录树数据
    const buildTreeData = (directoryNode) => {
        if (!directoryNode) return [];

        return [
            {
                title: directoryNode.name,
                key: directoryNode.name,
                isLeaf: directoryNode.type === 'file',
                icon: directoryNode.type === 'directory' ? <FolderOutlined /> : <FileOutlined />,
                selectable: directoryNode.type === 'file',
                children: directoryNode.children ?
                    directoryNode.children.map(child => buildTreeData(child)[0]) :
                    undefined
            }
        ];
    };

    // 渲染代码展示
    const renderCodeDisplay = () => {
        if (!componentDetails) {
            return <Empty description="选择一个组件查看详情" />;
        }

        const language = languageExtensions[componentDetails.file_path.split('.').pop()] || 'text';

        return (
            <Card
                title={
                    <Space>
                        {typeIcons[componentDetails.type] || <CodeOutlined />}
                        <span>{componentDetails.name}</span>
                        <Tag color="blue">{componentDetails.type}</Tag>
                        <Tag color="green">{componentDetails.file_path}</Tag>
                    </Space>
                }
                extra={
                    <Button
                        type="primary"
                        icon={<RobotOutlined />}
                        onClick={() => generateSummary(componentDetails.id)}
                    >
                        AI分析
                    </Button>
                }
            >
                {componentDetails.llm_summary && (
                    <div style={{ marginBottom: 16, padding: 12, background: '#f0f9ff', borderRadius: 4 }}>
                        <div style={{ fontWeight: 'bold', marginBottom: 4 }}>AI分析摘要:</div>
                        {componentDetails.llm_summary}
                    </div>
                )}

                <SyntaxHighlighter
                    language={language}
                    style={vscDarkPlus}
                    showLineNumbers
                    customStyle={{ fontSize: '14px' }}
                >
                    {componentDetails.code || '// 无可用代码'}
                </SyntaxHighlighter>

                {componentDetails.signature && (
                    <div style={{ marginTop: 12 }}>
                        <strong>签名:</strong> <code>{componentDetails.signature}</code>
                    </div>
                )}

                {componentDetails.metadata && (
                    <Collapse ghost style={{ marginTop: 12 }}>
                        <Panel header="元数据">
                            <pre style={{ background: '#f5f5f5', padding: 8, borderRadius: 4 }}>
                                {JSON.stringify(componentDetails.metadata, null, 2)}
                            </pre>
                        </Panel>
                    </Collapse>
                )}
            </Card>
        );
    };

    // 渲染依赖关系图
    const renderDependencyGraph = () => {
        if (!dependencies || !dependencies.nodes || dependencies.nodes.length === 0) {
            return <Empty description="没有依赖关系数据" />;
        }

        return (
            <div style={{ height: 400 }}>
                <ReactFlow
                    nodes={dependencies.nodes}
                    edges={dependencies.edges}
                    draggable={true}
                    zoomOnScroll={true}
                    zoomOnPinch={true}
                    snapToGrid={true}
                    snapGrid={[15, 15]}
                    defaultZoom={1}
                >
                    <Controls />
                    <Background color="#aaa" gap={16} />
                </ReactFlow>
            </div>
        );
    };

    // 渲染影响分析
    const renderImpactAnalysis = () => {
        if (!impactAnalysis) {
            return <Empty description="选择一个组件进行影响分析" />;
        }

        return (
            <div>
                <Card title="影响分析总结">
                    <Row gutter={16}>
                        <Col span={8}>
                            <Statistic
                                title="直接影响组件"
                                value={impactAnalysis.impact_summary.direct_impact_count}
                                suffix="个"
                                valueStyle={{ color: '#1890ff' }}
                            />
                        </Col>
                        <Col span={8}>
                            <Statistic
                                title="间接影响组件"
                                value={impactAnalysis.impact_summary.indirect_impact_count}
                                suffix="个"
                                valueStyle={{ color: '#52c41a' }}
                            />
                        </Col>
                        <Col span={8}>
                            <Statistic
                                title="影响测试"
                                value={impactAnalysis.impact_summary.affected_tests_count}
                                suffix="个"
                                valueStyle={{ color: '#faad14' }}
                            />
                        </Col>
                    </Row>
                </Card>

                <Tabs defaultActiveKey="direct" style={{ marginTop: 16 }}>
                    <TabPane tab="直接影响" key="direct">
                        <Table
                            dataSource={impactAnalysis.direct_impact}
                            rowKey="id"
                            columns={[
                                {
                                    title: '组件名称',
                                    dataIndex: 'name',
                                    key: 'name',
                                    render: (text, record) => (
                                        <Button
                                            type="link"
                                            onClick={() => viewComponentDetails(record.id)}
                                        >
                                            {text}
                                        </Button>
                                    )
                                },
                                {
                                    title: '类型',
                                    dataIndex: 'type',
                                    key: 'type',
                                    render: type => <Tag color="blue">{type}</Tag>
                                },
                                {
                                    title: '文件',
                                    dataIndex: 'file_path',
                                    key: 'file_path'
                                },
                                {
                                    title: '重要性',
                                    dataIndex: 'importance',
                                    key: 'importance',
                                    render: value => (
                                        <Tooltip title={value.toFixed(2)}>
                                            <Progress
                                                percent={Math.min(value * 20, 100)}
                                                size="small"
                                                showInfo={false}
                                            />
                                        </Tooltip>
                                    )
                                }
                            ]}
                            size="small"
                            pagination={{ pageSize: 5 }}
                        />
                    </TabPane>
                    <TabPane tab="间接影响" key="indirect">
                        <Table
                            dataSource={impactAnalysis.indirect_impact}
                            rowKey="id"
                            columns={[
                                {
                                    title: '组件名称',
                                    dataIndex: 'name',
                                    key: 'name',
                                    render: (text, record) => (
                                        <Button
                                            type="link"
                                            onClick={() => viewComponentDetails(record.id)}
                                        >
                                            {text}
                                        </Button>
                                    )
                                },
                                {
                                    title: '类型',
                                    dataIndex: 'type',
                                    key: 'type',
                                    render: type => <Tag color="blue">{type}</Tag>
                                },
                                {
                                    title: '文件',
                                    dataIndex: 'file_path',
                                    key: 'file_path'
                                }
                            ]}
                            size="small"
                            pagination={{ pageSize: 5 }}
                        />
                    </TabPane>
                    <TabPane tab="影响的测试" key="tests">
                        <Table
                            dataSource={impactAnalysis.affected_tests}
                            rowKey="id"
                            columns={[
                                {
                                    title: '测试名称',
                                    dataIndex: 'name',
                                    key: 'name',
                                    render: (text, record) => (
                                        <Button
                                            type="link"
                                            onClick={() => viewComponentDetails(record.id)}
                                        >
                                            {text}
                                        </Button>
                                    )
                                },
                                {
                                    title: '文件',
                                    dataIndex: 'file_path',
                                    key: 'file_path'
                                }
                            ]}
                            size="small"
                            pagination={{ pageSize: 5 }}
                        />
                    </TabPane>
                </Tabs>
            </div>
        );
    };

    return (
        <div className="code-analysis-container">
            <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Space>
                    <Select
                        style={{ width: 240 }}
                        placeholder="选择代码库"
                        loading={loading}
                        value={currentRepo ? currentRepo.id : undefined}
                        onChange={value => {
                            const repo = repositories.find(r => r.id === value);
                            setCurrentRepo(repo);
                        }}
                    >
                        {repositories.map(repo => (
                            <Option key={repo.id} value={repo.id}>{repo.name}</Option>
                        ))}
                    </Select>

                    <Button
                        type="primary"
                        icon={<UploadOutlined />}
                        onClick={() => setUploadModalVisible(true)}
                    >
                        添加代码库
                    </Button>

                    <Button
                        icon={<CodeOutlined />}
                        onClick={createExampleRepo}
                    >
                        创建示例库
                    </Button>
                </Space>

                <Space>
                    <Select
                        style={{ width: 120 }}
                        placeholder="组件类型"
                        allowClear
                        value={componentType}
                        onChange={value => setComponentType(value)}
                    >
                        <Option value="function">函数</Option>
                        <Option value="class">类</Option>
                        <Option value="method">方法</Option>
                        <Option value="react_component">React组件</Option>
                    </Select>

                    <Search
                        placeholder="搜索代码..."
                        onSearch={handleSearch}
                        style={{ width: 300 }}
                        enterButton
                        loading={loading}
                    />
                </Space>
            </div>

            {repoSummary && (
                <Card
                    title={`仓库概览: ${currentRepo?.name}`}
                    style={{ marginBottom: 20 }}
                    size="small"
                >
                    <div style={{ display: 'flex', justifyContent: 'space-around', textAlign: 'center' }}>
                        <div>
                            <div style={{ fontSize: 20, fontWeight: 'bold' }}>{repoSummary.statistics.total_files}</div>
                            <div>文件数</div>
                        </div>
                        <div>
                            <div style={{ fontSize: 20, fontWeight: 'bold' }}>{repoSummary.statistics.total_components}</div>
                            <div>组件数</div>
                        </div>
                        <div>
                            <div style={{ fontSize: 20, fontWeight: 'bold' }}>{repoSummary.statistics.total_dependencies}</div>
                            <div>依赖关系</div>
                        </div>
                    </div>

                    <Divider style={{ margin: '12px 0' }}>语言分布</Divider>

                    <div style={{ display: 'flex', justifyContent: 'center', gap: 8 }}>
                        {Object.entries(repoSummary.file_stats).map(([lang, count]) => (
                            <Tag key={lang} color={lang === 'python' ? 'blue' : lang === 'javascript' ? 'green' : 'orange'}>
                                {lang}: {count}
                            </Tag>
                        ))}
                    </div>
                </Card>
            )}

            <Row gutter={16}>
                <Col span={8}>
                    <Card title="代码导航" bodyStyle={{ padding: 0, maxHeight: 600, overflow: 'auto' }}>
                        <Tabs defaultActiveKey="search">
                            <TabPane tab="搜索结果" key="search">
                                {searchResults.length > 0 ? (
                                    <div style={{ padding: '0 12px' }}>
                                        <div style={{ marginBottom: 8, color: '#888' }}>
                                            找到 {searchResults.length} 个匹配项
                                        </div>
                                        <List
                                            dataSource={searchResults}
                                            renderItem={item => (
                                                <List.Item
                                                    key={item.id}
                                                    onClick={() => viewComponentDetails(item.id)}
                                                    style={{
                                                        cursor: 'pointer',
                                                        background: selectedComponent === item.id ? '#e6f7ff' : 'transparent'
                                                    }}
                                                >
                                                    <List.Item.Meta
                                                        avatar={typeIcons[item.type] || <CodeOutlined />}
                                                        title={item.name}
                                                        description={
                                                            <div>
                                                                <Space size={0}>
                                                                    <Tag color="blue">{item.type}</Tag>
                                                                    <span style={{ fontSize: '0.85em' }}>{item.file_path}</span>
                                                                </Space>
                                                                {item.code_preview && (
                                                                    <div style={{
                                                                        marginTop: 5,
                                                                        padding: '8px',
                                                                        background: '#f6f8fa',
                                                                        borderRadius: '4px',
                                                                        fontSize: '12px',
                                                                        fontFamily: 'monospace',
                                                                        whiteSpace: 'pre-wrap',
                                                                        overflow: 'hidden',
                                                                        maxHeight: '80px'
                                                                    }}>
                                                                        {item.code_preview}
                                                                    </div>
                                                                )}
                                                            </div>
                                                        }
                                                    />
                                                </List.Item>
                                            )}
                                        />
                                    </div>
                                ) : searchQuery ? (
                                    <Empty description="没有找到匹配项" />
                                ) : (
                                    <Empty description="请输入搜索关键词" />
                                )}
                            </TabPane>
                            <TabPane tab="结构浏览" key="structure">
                                {directoryTree ? (
                                    <DirectoryTree
                                        showIcon
                                        defaultExpandAll={false}
                                        treeData={buildTreeData(directoryTree)}
                                    />
                                ) : (
                                    <Empty description="没有可用的目录结构" />
                                )}
                            </TabPane>
                            <TabPane tab="重要组件" key="important">
                                {repoSummary?.important_components?.length > 0 ? (
                                    <List
                                        dataSource={repoSummary.important_components}
                                        renderItem={item => (
                                            <List.Item
                                                key={item.id}
                                                onClick={() => viewComponentDetails(item.id)}
                                                style={{
                                                    cursor: 'pointer',
                                                    background: selectedComponent === item.id ? '#e6f7ff' : 'transparent'
                                                }}
                                            >
                                                <List.Item.Meta
                                                    avatar={typeIcons[item.type] || <CodeOutlined />}
                                                    title={
                                                        <Space>
                                                            <span>{item.name}</span>
                                                            <Tooltip title={`重要性: ${item.importance.toFixed(2)}`}>
                                                                <Progress
                                                                    percent={Math.min(item.importance * 20, 100)}
                                                                    size="small"
                                                                    showInfo={false}
                                                                    style={{ width: 60 }}
                                                                />
                                                            </Tooltip>
                                                        </Space>
                                                    }
                                                    description={<Tag color="blue">{item.type}</Tag>}
                                                />
                                            </List.Item>
                                        )}
                                    />
                                ) : (
                                    <Empty description="没有重要组件数据" />
                                )}
                            </TabPane>
                        </Tabs>
                    </Card>
                </Col>

                <Col span={16}>
                    <Tabs defaultActiveKey="code">
                        <TabPane tab="代码" key="code">
                            {renderCodeDisplay()}
                        </TabPane>
                        <TabPane tab="依赖关系" key="dependencies">
                            {renderDependencyGraph()}
                        </TabPane>
                        <TabPane tab="影响分析" key="impact">
                            {renderImpactAnalysis()}
                        </TabPane>
                    </Tabs>
                </Col>
            </Row>

            {/* 添加代码库模态框 */}
            <Modal
                title="添加代码库"
                visible={uploadModalVisible}
                onOk={addLocalRepo}
                onCancel={() => setUploadModalVisible(false)}
                okText="添加"
                cancelText="取消"
            >
                <Input
                    placeholder="输入本地代码库路径"
                    value={localRepoPath}
                    onChange={e => setLocalRepoPath(e.target.value)}
                    style={{ marginBottom: 16 }}
                />
                <p>请输入您计算机上代码库的完整路径，系统将分析并索引代码结构。</p>
            </Modal>

            {/* LLM摘要模态框 */}
            <Modal
                title="AI代码分析"
                visible={llmModalVisible}
                onCancel={() => setLlmModalVisible(false)}
                footer={[
                    <Button key="close" onClick={() => setLlmModalVisible(false)}>
                        关闭
                    </Button>
                ]}
                width={600}
            >
                {llmLoading ? (
                    <div style={{ textAlign: 'center', padding: '30px 0' }}>
                        <Spin indicator={<LoadingOutlined style={{ fontSize: 24 }} spin />} />
                        <div style={{ marginTop: 12 }}>分析代码中，请稍候...</div>
                    </div>
                ) : (
                    <div>
                        <div style={{ marginBottom: 8, fontWeight: 'bold' }}>代码功能分析:</div>
                        <div style={{ whiteSpace: 'pre-line' }}>{llmSummary}</div>
                    </div>
                )}
            </Modal>
        </div>
    );
};

export default CodeAnalysisPage; 