import React, { useState, useEffect, useCallback, memo } from 'react';
import {
    Table, Card, Tabs, Button, Modal, Spin, Tree, Tag, Space, Input,
    Collapse, message, Progress, Tooltip, Select, Empty, Divider, Row, Col,
    List, Statistic
} from 'antd';
import {
    SearchOutlined, CodeOutlined, BranchesOutlined,
    RocketOutlined, FileOutlined, RobotOutlined, FolderOutlined,
    ArrowRightOutlined, UploadOutlined, LoadingOutlined, DatabaseOutlined,
    StarOutlined, InfoCircleTwoTone
} from '@ant-design/icons';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import ReactFlow, { Controls, Background } from 'reactflow';
import 'reactflow/dist/style.css';
import axios from 'axios';

// 自定义样式
const customStyles = `
.component-list-item:hover {
  background-color: #e6f7ff !important;
  border-left: 3px solid #1890ff;
}

.file-node {
  transition: all 0.3s;
}

.file-node:hover {
  color: #1890ff;
}

.ant-tabs-tab {
  padding: 6px 16px !important;
}
`;

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

// 使用React.memo包装的重要组件列表，避免不必要的重新渲染
const ImportantComponentsList = memo(({
    repoSummary,
    componentNameSearch,
    setComponentNameSearch,
    loading,
    viewComponentDetails
}) => {
    const filteredComponents = componentNameSearch && repoSummary?.important_components
        ? repoSummary.important_components.filter(comp =>
            comp.name.toLowerCase().includes(componentNameSearch.toLowerCase()))
        : (repoSummary?.important_components || []);

    return (
        <div style={{ padding: '8px 0' }}>
            <div style={{ padding: '0 12px', marginBottom: 10 }}>
                <Input.Search
                    placeholder="搜索组件名称"
                    onSearch={(value) => setComponentNameSearch(value)}
                    allowClear
                    onChange={(e) => {
                        if (!e.target.value) {
                            setComponentNameSearch('');
                        }
                    }}
                />
            </div>
            {repoSummary ? (
                <>
                    {loading ? (
                        <div style={{ padding: '20px', textAlign: 'center' }}>
                            <Spin tip="加载组件..." />
                        </div>
                    ) : (
                        <List
                            dataSource={filteredComponents}
                            renderItem={item => (
                                <List.Item
                                    key={item.id}
                                    onClick={() => viewComponentDetails(item.id)}
                                    style={{
                                        cursor: 'pointer',
                                        background: item._selected ? '#e6f7ff' : 'transparent',
                                        padding: '8px 12px'
                                    }}
                                    className="component-list-item"
                                >
                                    <List.Item.Meta
                                        avatar={typeIcons[item.type] || <CodeOutlined />}
                                        title={
                                            <Space>
                                                <span>{item.name}</span>
                                                <Tooltip title={`重要性: ${item.importance?.toFixed(2) || 0}`}>
                                                    <Progress
                                                        percent={Math.min((item.importance || 0) * 20, 100)}
                                                        size="small"
                                                        showInfo={false}
                                                        style={{ width: 60 }}
                                                    />
                                                </Tooltip>
                                            </Space>
                                        }
                                        description={
                                            <>
                                                <Tag color="blue">{item.type}</Tag>
                                                <span style={{ fontSize: '0.85em', marginLeft: '8px', color: '#888', wordBreak: 'break-all' }}>{item.file_path || '未知文件'}</span>
                                            </>
                                        }
                                    />
                                </List.Item>
                            )}
                            pagination={{
                                pageSize: 50,
                                size: 'small',
                                showSizeChanger: true,
                                pageSizeOptions: ['50', '100', '200', '500', '1000'],
                                showTotal: (total) => `共 ${total} 个组件`
                            }}
                            style={{ padding: '0 0 12px 0', overflowX: 'hidden' }}
                        />
                    )}
                </>
            ) : (
                <Empty description="暂无代码库数据" />
            )}
        </div>
    );
});

const CodeAnalysisPage = () => {
    // 状态管理
    const [repositories, setRepositories] = useState([]);
    const [knowledgeBases, setKnowledgeBases] = useState([]);
    const [selectedKnowledgeBase, setSelectedKnowledgeBase] = useState(null);
    const [currentRepo, setCurrentRepo] = useState(null);
    const [repoSummary, setRepoSummary] = useState(null);
    const [loading, setLoading] = useState(false);
    const [kbLoading, setKbLoading] = useState(false);
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
    const [componentFilters, setComponentFilters] = useState(['all']);
    const [componentNameSearch, setComponentNameSearch] = useState('');
    const [activeNavTab, setActiveNavTab] = useState('structure'); // 当前激活的导航标签页
    const [expandedKeys, setExpandedKeys] = useState([]); // 目录树已展开的节点
    const [componentCache, setComponentCache] = useState({});
    const [dependenciesCache, setDependenciesCache] = useState({});
    const [impactAnalysisCache, setImpactAnalysisCache] = useState({});
    const [fileContentCache, setFileContentCache] = useState({});

    // 加载知识库列表
    const fetchKnowledgeBases = useCallback(async () => {
        try {
            setKbLoading(true);
            const response = await axios.get('/knowledge-bases');
            setKnowledgeBases(response.data);
            if (response.data.length > 0 && !selectedKnowledgeBase) {
                setSelectedKnowledgeBase(response.data[0].id);
            }
        } catch (error) {
            message.error('加载知识库失败');
            console.error(error);
        } finally {
            setKbLoading(false);
        }
    }, []);

    // 加载特定知识库中的代码库
    const fetchRepositoriesByKnowledgeBase = useCallback(async (kbId) => {
        if (!kbId) return;

        try {
            setLoading(true);
            const response = await axios.get(`/knowledge-bases/${kbId}/repositories`);
            setRepositories(response.data);
            if (response.data.length > 0) {
                setCurrentRepo(response.data[0]);
            } else {
                setCurrentRepo(null);
                setRepoSummary(null);
                setDirectoryTree(null);
            }
        } catch (error) {
            message.error('加载知识库代码库失败');
            console.error(error);
        } finally {
            setLoading(false);
        }
    }, []);

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
    }, []);

    // 加载仓库摘要
    const fetchRepoSummary = useCallback(async (repoId) => {
        if (!repoId) return;

        try {
            setLoading(true);
            const response = await axios.get(`/code/repositories/${repoId}`);

            // 不再创建模拟数据，直接使用API返回的数据
            setRepoSummary(response.data);

            // 同时加载目录结构
            const structureResponse = await axios.get(`/code/repositories/${repoId}/structure`);
            setDirectoryTree(structureResponse.data);

            // 设置加载状态
            message.success(`已加载代码库，包含 ${response.data?.important_components?.length || 0} 个组件`);

            // 直接在控制台输出组件数量，以便验证
            console.log(`代码库包含 ${response.data?.important_components?.length || 0} 个组件`);
        } catch (error) {
            message.error('加载代码库摘要失败');
            console.error(error);
        } finally {
            setLoading(false);
        }
    }, []);

    // 使用Effect监听repoSummary变化，显示加载完成的组件数量
    useEffect(() => {
        if (repoSummary && repoSummary.important_components) {
            console.log(`已加载 ${repoSummary.important_components.length} 个组件`);
        }
    }, [repoSummary]);

    // 首次加载
    useEffect(() => {
        fetchKnowledgeBases();
    }, []);

    // 当选择的知识库变化时
    useEffect(() => {
        if (selectedKnowledgeBase) {
            fetchRepositoriesByKnowledgeBase(selectedKnowledgeBase);
        } else {
            fetchRepositories();
        }
    }, [selectedKnowledgeBase]);

    // 当代码库变化时
    useEffect(() => {
        if (currentRepo) {
            fetchRepoSummary(currentRepo.id);
        }
    }, [currentRepo]);

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
        // 如果已经选中该组件，不进行任何操作
        if (selectedComponent === componentId) {
            return;
        }

        setSelectedComponent(componentId);

        // 如果已经有缓存的组件详情，直接使用缓存
        if (componentCache[componentId]) {
            setComponentDetails(componentCache[componentId]);

            // 仅更新选中状态，不重新加载整个组件列表
            if (repoSummary && repoSummary.important_components) {
                const updatedComponents = repoSummary.important_components.map(comp => ({
                    ...comp,
                    _selected: comp.id === componentId
                }));
                setRepoSummary(prev => ({
                    ...prev,
                    important_components: updatedComponents
                }));
            }
            return;
        }

        setLoading(true);

        try {
            // 获取组件详情
            const response = await axios.get(`/code/components/${componentId}`);
            const componentData = response.data;

            // 更新组件缓存
            setComponentCache(prev => ({
                ...prev,
                [componentId]: componentData
            }));

            setComponentDetails(componentData);

            // 更新组件选择状态
            if (repoSummary && repoSummary.important_components) {
                const updatedComponents = repoSummary.important_components.map(comp => ({
                    ...comp,
                    _selected: comp.id === componentId
                }));
                setRepoSummary(prev => ({
                    ...prev,
                    important_components: updatedComponents
                }));
            }

            // 尝试加载依赖关系
            await fetchComponentDependencies(componentId);

            // 尝试加载影响分析
            await fetchImpactAnalysis(componentId);

        } catch (error) {
            console.error('获取组件详情失败:', error);
            message.error('获取组件详情失败');
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

    // 添加本地代码库
    const addLocalRepo = async () => {
        if (!localRepoPath.trim()) {
            message.error('请输入有效的代码库路径');
            return;
        }

        setLoading(true);
        try {
            const response = await axios.post('/code/repositories', {
                repo_path: localRepoPath,
                knowledge_base_id: selectedKnowledgeBase
            });

            message.success('代码库添加成功，正在分析中...');
            setUploadModalVisible(false);

            // 刷新代码库列表
            if (selectedKnowledgeBase) {
                fetchRepositoriesByKnowledgeBase(selectedKnowledgeBase);
            } else {
                fetchRepositories();
            }
        } catch (error) {
            message.error(`添加代码库失败: ${error.response?.data?.detail || error.message}`);
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

        const buildNode = (node, parentPath = '') => {
            // 构建当前节点的路径
            const nodePath = parentPath ? `${parentPath}/${node.name}` : node.name;

            return {
                title: <span className={node.type === 'file' ? 'file-node' : ''}>{node.name}</span>,
                key: nodePath,
                isLeaf: node.type === 'file',
                icon: node.type === 'directory' ? <FolderOutlined /> : <FileOutlined />,
                selectable: node.type === 'file',
                children: node.children ? node.children.map(child => buildNode(child, nodePath)) : undefined
            };
        };

        return [buildNode(directoryNode)];
    };

    // 渲染代码展示
    const renderCodeDisplay = () => {
        if (!componentDetails) {
            return <Empty description="选择一个组件查看详情" />;
        }

        const language = languageExtensions[componentDetails.file_path.split('.').pop()] || 'text';
        const isFile = componentDetails.type === 'file';
        const hasFileBackup = componentDetails._fileBackup !== undefined;

        return (
            <Card
                title={
                    <Space wrap>
                        {isFile ? <FileOutlined /> : (typeIcons[componentDetails.type] || <CodeOutlined />)}
                        <span style={{ fontWeight: 'bold' }}>{componentDetails.name}</span>
                        <Tag color="blue">{componentDetails.type}</Tag>
                        <Tooltip title={componentDetails.file_path}>
                            <Tag color="green" style={{ maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                {componentDetails.file_path}
                            </Tag>
                        </Tooltip>
                        {hasFileBackup && (
                            <Button
                                size="small"
                                icon={<ArrowRightOutlined />}
                                onClick={() => {
                                    // 返回到文件视图
                                    setComponentDetails(componentDetails._fileBackup.file_details);
                                    setSelectedComponent(null);
                                }}
                            >
                                返回文件
                            </Button>
                        )}
                    </Space>
                }
                extra={
                    <Space>
                        <Button
                            type="primary"
                            icon={<RobotOutlined />}
                            onClick={() => generateSummary(componentDetails.id)}
                            disabled={isFile}
                        >
                            AI分析
                        </Button>
                        <Tooltip title="将组件标记为重要业务组件">
                            <Button
                                icon={<StarOutlined />}
                                onClick={() => message.success('已标记为重要业务组件')}
                                disabled={isFile}
                            >
                                标记为重要
                            </Button>
                        </Tooltip>
                    </Space>
                }
                bodyStyle={{ maxHeight: '70vh', overflow: 'auto' }}
                bordered
            >
                {componentDetails.llm_summary && !isFile && (
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

                {isFile && componentDetails.components && componentDetails.components.length > 0 && (
                    <div style={{ marginTop: 20 }}>
                        <Divider orientation="left">文件内组件 ({componentDetails.components.length})</Divider>
                        <List
                            size="small"
                            bordered
                            dataSource={componentDetails.components}
                            renderItem={item => (
                                <List.Item
                                    key={item.id}
                                    onClick={() => {
                                        // 使用真实API获取组件详情，保持在当前视图
                                        const originalFileDetails = { ...componentDetails };
                                        setLoading(true);

                                        // 获取组件详情
                                        axios.get(`/code/components/${item.id}`)
                                            .then(response => {
                                                // 保存原始文件备份
                                                const fileBackup = {
                                                    id: originalFileDetails.id,
                                                    file_details: originalFileDetails,
                                                    file_path: originalFileDetails.file_path
                                                };

                                                // 设置组件详情并保留文件信息
                                                setComponentDetails({
                                                    ...response.data,
                                                    _fileBackup: fileBackup
                                                });

                                                setSelectedComponent(item.id);
                                            })
                                            .catch(error => {
                                                console.error('获取组件详情失败:', error);
                                                message.error('获取组件详情失败');
                                            })
                                            .finally(() => {
                                                setLoading(false);
                                            });
                                    }}
                                    style={{
                                        cursor: 'pointer',
                                        padding: '8px 16px',
                                        backgroundColor: 'rgba(245, 245, 245, 0.5)',
                                        marginBottom: '4px',
                                        borderRadius: '4px',
                                        transition: 'all 0.3s'
                                    }}
                                    className="component-list-item"
                                >
                                    <List.Item.Meta
                                        avatar={typeIcons[item.type] || <CodeOutlined />}
                                        title={item.name}
                                        description={
                                            <Space>
                                                <Tag color="blue">{item.type}</Tag>
                                                <span>行: {item.start_line}-{item.end_line}</span>
                                            </Space>
                                        }
                                    />
                                </List.Item>
                            )}
                        />
                    </div>
                )}

                {isFile && (!componentDetails.components || componentDetails.components.length === 0) && (
                    <div style={{ marginTop: 16, padding: 16, background: '#fffbe6', borderRadius: 4 }}>
                        <InfoCircleTwoTone twoToneColor="#faad14" style={{ marginRight: 8 }} />
                        该文件内未检测到组件，可能需要后端实现相关功能或添加组件分析
                    </div>
                )}

                {!isFile && componentDetails.signature && (
                    <div style={{ marginTop: 12 }}>
                        <strong>签名:</strong> <code>{componentDetails.signature}</code>
                    </div>
                )}

                {!isFile && componentDetails.metadata && (
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

    // 过滤重要组件
    const getFilteredComponents = useCallback(() => {
        if (!repoSummary?.important_components) return [];

        let filteredComponents = repoSummary.important_components;

        // 首先应用名称搜索过滤
        if (componentNameSearch) {
            filteredComponents = filteredComponents.filter(comp =>
                comp.name.toLowerCase().includes(componentNameSearch.toLowerCase()));
        }

        // 如果包含'all'，返回当前筛选的组件列表，不进行进一步类型过滤
        if (componentFilters.includes('all')) {
            return filteredComponents;
        }

        // 如果没有选择任何过滤器，也返回所有组件
        if (componentFilters.length === 0) {
            return filteredComponents;
        }

        // 应用过滤器逻辑
        return filteredComponents.filter(comp => {
            // 业务组件: 通常包含业务领域词汇，不含有通用工具功能词
            if (componentFilters.includes('business')) {
                const businessTerms = ['Service', 'Controller', 'Repository', 'Manager', 'Handler', 'Process', 'Execute', 'Create', 'Update', 'Delete', 'Account', 'User', 'Admin', 'Client', 'Order', 'Payment'];
                const utilityTerms = ['Util', 'Helper', 'Error', 'Config', 'Log', 'Format', 'Convert', 'Parse'];

                // 简单启发式：如果包含业务术语且不是工具函数
                const hasBusiness = businessTerms.some(term => comp.name.includes(term));
                const isUtility = utilityTerms.some(term => comp.name.includes(term));

                if (hasBusiness && !isUtility) return true;

                // 长名称的函数/组件通常是业务逻辑而不是工具函数
                if (comp.name.length > 15 && !isUtility) return true;
            }

            // 控制器：处理请求的组件
            if (componentFilters.includes('controller') &&
                (comp.name.includes('Controller') || comp.name.includes('Handler') ||
                    comp.name.includes('Router') || comp.name.includes('Endpoint'))) {
                return true;
            }

            // 服务：包含业务逻辑的组件
            if (componentFilters.includes('service') &&
                (comp.name.includes('Service') || comp.name.includes('Manager') ||
                    comp.name.includes('Provider') || comp.name.includes('Processor'))) {
                return true;
            }

            // 工具函数：通用辅助功能
            if (componentFilters.includes('utility') &&
                (comp.name.includes('Util') || comp.name.includes('Helper') ||
                    comp.name.startsWith('get') || comp.name.startsWith('set') ||
                    comp.name.startsWith('is') || comp.name.startsWith('has') ||
                    comp.name.startsWith('parse') || comp.name.startsWith('format') ||
                    ['Error', 'Errorf', 'Fatalf', 'Unmarshal', 'Marshal'].includes(comp.name))) {
                return true;
            }

            // 数据模型
            if (componentFilters.includes('model') &&
                (comp.type === 'struct' || comp.type === 'interface' ||
                    comp.name.includes('Model') || comp.name.includes('Entity') ||
                    comp.name.includes('DTO') || comp.name.includes('VO'))) {
                return true;
            }

            return false;
        });
    }, [repoSummary, componentFilters, componentNameSearch]);

    // 获取组件依赖关系
    const fetchComponentDependencies = async (componentId) => {
        // 如果缓存中已有依赖数据，直接使用缓存
        if (dependenciesCache[componentId]) {
            setDependencies(dependenciesCache[componentId]);
            return;
        }

        try {
            const response = await axios.get(`/code/components/${componentId}`);

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

            const dependencyData = { nodes, edges };
            setDependencies(dependencyData);

            // 更新缓存
            setDependenciesCache(prev => ({
                ...prev,
                [componentId]: dependencyData
            }));
        } catch (error) {
            console.error('获取组件依赖关系失败:', error);
        }
    };

    // 获取组件影响分析
    const fetchImpactAnalysis = async (componentId) => {
        // 如果缓存中已有影响分析数据，直接使用缓存
        if (impactAnalysisCache[componentId]) {
            setImpactAnalysis(impactAnalysisCache[componentId]);
            return;
        }

        try {
            const impactResponse = await axios.get(`/code/components/${componentId}/impact`);
            setImpactAnalysis(impactResponse.data);

            // 更新缓存
            setImpactAnalysisCache(prev => ({
                ...prev,
                [componentId]: impactResponse.data
            }));
        } catch (error) {
            console.error('获取影响分析失败:', error);
        }
    };

    // 搜索结果列表组件
    const SearchResultsList = memo(({
        searchResults,
        viewComponentDetails
    }) => {
        return (
            <List
                dataSource={searchResults}
                renderItem={item => (
                    <List.Item
                        key={item.id}
                        onClick={() => viewComponentDetails(item.id)}
                        style={{
                            cursor: 'pointer',
                            padding: '12px 16px',
                            borderBottom: '1px solid #f0f0f0'
                        }}
                        className="component-list-item"
                    >
                        <List.Item.Meta
                            avatar={typeIcons[item.type] || <CodeOutlined />}
                            title={item.name}
                            description={
                                <Space>
                                    <Tag color="blue">{item.type}</Tag>
                                    <span>{item.file}</span>
                                </Space>
                            }
                        />
                    </List.Item>
                )}
                locale={{ emptyText: '无搜索结果' }}
            />
        );
    });

    const repoSelector = (
        <Space style={{ marginBottom: 16 }}>
            <span style={{ fontWeight: 'bold' }}>知识库:</span>
            <Select
                style={{ width: 200 }}
                loading={kbLoading}
                placeholder="选择知识库"
                value={selectedKnowledgeBase}
                onChange={setSelectedKnowledgeBase}
            >
                <Option value={null}>所有代码库</Option>
                {knowledgeBases.map(kb => (
                    <Option key={kb.id} value={kb.id}>{kb.name}</Option>
                ))}
            </Select>

            <span style={{ fontWeight: 'bold', marginLeft: 16 }}>代码库:</span>
            <Select
                style={{ width: 220 }}
                loading={loading}
                placeholder="选择代码库"
                value={currentRepo?.id}
                onChange={(value) => {
                    const selected = repositories.find(r => r.id === value);
                    setCurrentRepo(selected);
                }}
                disabled={!repositories || repositories.length === 0}
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
        </Space>
    );

    return (
        <div className="code-analysis-container">
            <style>{customStyles}</style>
            <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                {repoSelector}

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
                    bordered={true}
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
                <Col span={7}>
                    <Card
                        title={
                            <Space>
                                <span>代码导航</span>
                                {repoSummary?.important_components && (
                                    <Tag color="blue">
                                        {repoSummary.important_components.length} 个组件
                                    </Tag>
                                )}
                            </Space>
                        }
                        bodyStyle={{ padding: 0, maxHeight: 600, overflow: 'auto', overflowX: 'hidden' }}
                        bordered={true}
                        style={{ boxShadow: '0 1px 2px rgba(0,0,0,0.1)' }}
                    >
                        <Tabs
                            activeKey={activeNavTab}
                            onChange={key => setActiveNavTab(key)}
                            type="card"
                            tabBarStyle={{ margin: '0 8px', paddingTop: '8px' }}
                            tabBarGutter={4}
                            size="small"
                        >
                            <TabPane tab="结构浏览" key="structure">
                                {directoryTree ? (
                                    <DirectoryTree
                                        showIcon
                                        defaultExpandAll={false}
                                        expandedKeys={expandedKeys}
                                        onExpand={(keys) => setExpandedKeys(keys)}
                                        treeData={buildTreeData(directoryTree)}
                                        onSelect={(keys, info) => {
                                            if (info.node.isLeaf) {
                                                const filePath = info.node.key;

                                                // 检查缓存中是否已有文件内容
                                                if (fileContentCache[filePath]) {
                                                    setComponentDetails(fileContentCache[filePath]);
                                                    setSelectedComponent(null);
                                                    return;
                                                }

                                                setLoading(true);
                                                try {
                                                    // 从API获取真实文件内容而不是创建模拟数据
                                                    axios.get(`/code/files`, {
                                                        params: {
                                                            path: filePath.replace(currentRepo.path + '/', ''), // 只使用相对路径
                                                            repo_id: currentRepo.id
                                                        }
                                                    })
                                                        .then(response => {
                                                            const fileDetails = {
                                                                id: `file-${filePath}`,
                                                                name: info.node.title,
                                                                type: 'file',
                                                                file_path: filePath,
                                                                code: response.data.content || '// 无内容',
                                                                components: response.data.components || [],
                                                                description: response.data.description || '文件内容'
                                                            };

                                                            // 更新缓存
                                                            setFileContentCache(prev => ({
                                                                ...prev,
                                                                [filePath]: fileDetails
                                                            }));

                                                            setComponentDetails(fileDetails);
                                                            setSelectedComponent(null);
                                                            message.success(`已加载 ${info.node.title} 文件内容`);
                                                        })
                                                        .catch(error => {
                                                            console.error('获取文件内容失败:', error);
                                                            message.error('获取文件内容失败');
                                                            const errorDetails = {
                                                                id: `file-${filePath}`,
                                                                name: info.node.title,
                                                                type: 'file',
                                                                file_path: filePath,
                                                                code: '// 无法加载文件内容',
                                                                components: [],
                                                                description: '无法加载文件内容'
                                                            };
                                                            setComponentDetails(errorDetails);

                                                            // 错误时也缓存，避免重复请求失败的文件
                                                            setFileContentCache(prev => ({
                                                                ...prev,
                                                                [filePath]: errorDetails
                                                            }));
                                                        })
                                                        .finally(() => {
                                                            setLoading(false);
                                                        });
                                                } catch (error) {
                                                    console.error('处理文件内容时出错:', error);
                                                    message.error('处理文件内容时出错');
                                                    setLoading(false);
                                                }
                                            }
                                        }}
                                        style={{ padding: '8px', overflowX: 'hidden' }}
                                    />
                                ) : (
                                    <Empty description="没有可用的目录结构" />
                                )}
                            </TabPane>
                            <TabPane tab="重要组件" key="important">
                                {/* 使用React.memo包装的组件来避免不必要的重新渲染 */}
                                <ImportantComponentsList
                                    repoSummary={repoSummary}
                                    componentNameSearch={componentNameSearch}
                                    setComponentNameSearch={setComponentNameSearch}
                                    loading={loading}
                                    viewComponentDetails={viewComponentDetails}
                                />
                            </TabPane>
                            <TabPane tab="搜索结果" key="search">
                                <SearchResultsList
                                    searchResults={searchResults}
                                    viewComponentDetails={viewComponentDetails}
                                />
                            </TabPane>
                        </Tabs>
                    </Card>
                </Col>

                <Col span={17}>
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

            {/* 页面首次加载时，导航区域显示全局loading遮罩 */}
            {loading && !repoSummary && (
                <div style={{ position: 'absolute', left: 0, top: 0, right: 0, bottom: 0, zIndex: 10, background: 'rgba(255,255,255,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Spin tip="加载中..." />
                </div>
            )}
        </div>
    );
};

export default CodeAnalysisPage; 