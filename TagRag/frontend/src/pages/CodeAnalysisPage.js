import React, { useState, useEffect, useCallback, memo, useMemo } from 'react';
import {
    Table, Card, Tabs, Button, Modal, Spin, Tree, Tag, Space, Input,
    Collapse, message, Progress, Tooltip, Select, Empty, Divider, Row, Col,
    List, Statistic
} from 'antd';
import {
    SearchOutlined, SendOutlined, SplitCellsOutlined, FolderOutlined, FileOutlined, StarOutlined, RobotOutlined, SyncOutlined, LoadingOutlined, FileSearchOutlined, DatabaseOutlined,
    CodeOutlined, BranchesOutlined, RocketOutlined, ArrowRightOutlined, UploadOutlined, InfoCircleTwoTone, PlusOutlined
} from '@ant-design/icons';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import ReactFlow, { Controls, Background } from 'reactflow';
import 'reactflow/dist/style.css';
import axios from 'axios';

// 修改自定义样式，增强美观性
const customStyles = `
.component-list-item:hover {
  background-color: #e6f7ff !important;
  border-left: 3px solid #1890ff;
  transition: all 0.2s;
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

.code-analysis-container {
  padding: 8px;
}

.repo-overview-card {
  margin-bottom: 16px;
  transition: all 0.3s;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}

.repo-overview-card:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.09);
}

.code-navigation-card {
  box-shadow: 0 1px 2px rgba(0,0,0,0.1);
  border-radius: 4px;
  transition: all 0.3s;
}

.code-navigation-card:hover {
  box-shadow: 0 3px 6px rgba(0,0,0,0.1);
}

.code-details-card {
  border-radius: 4px;
  transition: all 0.3s;
}

.code-details-tabs .ant-tabs-nav {
  margin-bottom: 8px;
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

// 修改ImportantComponentsList组件，简化实现
const ImportantComponentsList = memo(({
    repoSummary,
    componentNameSearch,
    setComponentNameSearch,
    loading,
    viewComponentDetails
}) => {
    // 简化状态管理，减少不必要的状态
    const [expandedComponents, setExpandedComponents] = useState({});

    // 只过滤显示组件名称和基本信息，不加载详细内容
    const filteredComponents = useMemo(() => {
        if (!repoSummary?.important_components) {
            return [];
        }

        if (!componentNameSearch) {
            return repoSummary.important_components;
        }

        const searchText = componentNameSearch.toLowerCase();
        return repoSummary.important_components.filter(comp =>
            comp.name.toLowerCase().includes(searchText));
    }, [repoSummary?.important_components, componentNameSearch]);

    // 渲染列表项，简化UI和减少信息
    const renderItem = useCallback((item) => (
        <List.Item
            key={item.id}
            style={{
                cursor: 'pointer',
                background: item._selected ? '#e6f7ff' : 'transparent',
                padding: '6px 10px',
                borderBottom: '1px solid #f0f0f0'
            }}
            className="component-list-item"
            onClick={() => viewComponentDetails(item.id)}
        >
            <div style={{ display: 'flex', alignItems: 'center', width: '100%' }}>
                <div style={{ marginRight: 8 }}>
                    {typeIcons[item.type] || <CodeOutlined />}
                </div>
                <div style={{ flex: 1, overflow: 'hidden' }}>
                    <div style={{ fontWeight: item._selected ? 'bold' : 'normal', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {item.name || '未命名组件'}
                    </div>
                    <div style={{ fontSize: '0.85em', color: '#888', display: 'flex', alignItems: 'center' }}>
                        <Tag color="blue" style={{ fontSize: '0.8em', lineHeight: '1em', padding: '1px 4px', marginRight: 4 }}>
                            {item.type || '未知类型'}
                        </Tag>
                        <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {item.file_path ?
                                (typeof item.file_path === 'string' ?
                                    item.file_path.split('/').pop() :
                                    '未知文件') :
                                '未知文件'}
                        </span>
                    </div>
                </div>
            </div>
        </List.Item>
    ), [viewComponentDetails]);

    return (
        <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '0 12px 8px 12px' }}>
                <Input.Search
                    placeholder="搜索组件名称"
                    onSearch={(value) => setComponentNameSearch(value)}
                    allowClear
                    onChange={(e) => {
                        if (!e.target.value) {
                            setComponentNameSearch('');
                        }
                    }}
                    size="small"
                />
            </div>

            {repoSummary ? (
                loading ? (
                    <div style={{ padding: '20px', textAlign: 'center' }}>
                        <Spin tip="加载组件..." />
                    </div>
                ) : (
                    <div style={{ flex: 1, overflow: 'auto' }}>
                        <List
                            dataSource={filteredComponents}
                            renderItem={renderItem}
                            pagination={{
                                pageSize: 50,
                                size: 'small',
                                simple: true,
                                showTotal: (total) => `${total}个组件`
                            }}
                            style={{ overflowX: 'hidden' }}
                            locale={{ emptyText: '没有匹配的组件' }}
                        />
                    </div>
                )
            ) : (
                <Empty description="暂无代码库数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
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
    // 新增状态
    const [loadingComponent, setLoadingComponent] = useState(false);
    const [loadingStructure, setLoadingStructure] = useState(false);
    const [delayedLoading, setDelayedLoading] = useState(false);
    const [componentListPage, setComponentListPage] = useState(1);
    const [componentListPageSize, setComponentListPageSize] = useState(50);

    // 加载知识库列表
    const fetchKnowledgeBases = useCallback(async () => {
        try {
            setKbLoading(true);
            const response = await axios.get('/knowledge-bases', {
                headers: {
                    'ngrok-skip-browser-warning': 'true'
                }
            });
            // 确保 response.data 是一个数组
            if (Array.isArray(response.data)) {
                setKnowledgeBases(response.data);
                if (response.data.length > 0 && !selectedKnowledgeBase) {
                    setSelectedKnowledgeBase(response.data[0].id);
                }
            } else {
                // 如果不是数组，则视作错误，设置为空数组
                console.error("CodeAnalysisPage: /knowledge-bases did not return an array:", response.data);
                message.error('加载知识库失败: 响应格式不正确');
                setKnowledgeBases([]);
            }
        } catch (error) {
            message.error('加载知识库失败');
            console.error("CodeAnalysisPage: Error fetching knowledge bases:", error);
            setKnowledgeBases([]); // 确保在捕获到错误时设置为空数组
        } finally {
            setKbLoading(false);
        }
    }, [selectedKnowledgeBase]); // 移除了 setSelectedKnowledgeBase 依赖，因为它在 effect 外部

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
        setLoading(true); // 或者一个专门的 repoLoading 状态
        try {
            const response = await axios.get('/code/repositories', { // 假设的端点
                headers: {
                    'ngrok-skip-browser-warning': 'true'
                }
            });
            if (Array.isArray(response.data)) {
                setRepositories(response.data);
                // Optionally select first repo if needed
                // if (response.data.length > 0 && !currentRepo) {
                //     setCurrentRepo(response.data[0].id); 
                // }
            } else {
                console.error("CodeAnalysisPage: /code/repositories did not return an array:", response.data);
                message.error('加载代码仓库失败: 响应格式不正确');
                setRepositories([]);
            }
        } catch (error) {
            console.error("CodeAnalysisPage: Error fetching repositories:", error);
            message.error('加载代码仓库列表失败');
            setRepositories([]);
        } finally {
            setLoading(false);
        }
    }, []); // currentRepo 依赖可能需要根据实际逻辑添加

    useEffect(() => {
        fetchKnowledgeBases();
        fetchRepositories(); // 调用获取代码仓库列表的函数
    }, [fetchKnowledgeBases, fetchRepositories]);

    // 改进的仓库摘要加载函数，拆分为两步：基本信息和详细组件
    const fetchRepoSummary = useCallback(async (repoId) => {
        if (!repoId) return;

        try {
            setLoading(true);
            // 第一步：只加载基本统计信息和目录结构，但不加载组件详情
            const response = await axios.get(`/code/repositories/${repoId}/basic-info`);

            // 设置基本仓库摘要信息
            const basicSummary = {
                ...response.data,
                important_components: [], // 初始化为空数组
                _partiallLoaded: true     // 标记为部分加载
            };

            setRepoSummary(basicSummary);

            // 同时加载目录结构
            setLoadingStructure(true);
            try {
                const structureResponse = await axios.get(`/code/repositories/${repoId}/structure`);
                setDirectoryTree(structureResponse.data);
            } catch (error) {
                console.error('加载目录结构失败:', error);
                message.warning('加载目录结构失败，但基本信息已加载');
            } finally {
                setLoadingStructure(false);
            }

            // 设置基本加载完成的消息
            message.success(`已加载代码库基本信息`);

            // 第二步：延迟加载组件列表，减少初始加载时间
            // 使用setTimeout来避免阻塞UI渲染
            setDelayedLoading(true);
            setTimeout(async () => {
                try {
                    // 分页加载组件列表，一次只加载前50个
                    const componentsResponse = await axios.get(`/code/repositories/${repoId}/components`, {
                        params: {
                            page: 1,
                            page_size: 50
                        }
                    });

                    const components = componentsResponse.data || [];

                    // 确保组件列表是数组
                    if (!Array.isArray(components)) {
                        throw new Error('后端返回的组件列表不是数组');
                    }

                    // 合并新组件到摘要
                    setRepoSummary(prev => ({
                        ...prev,
                        important_components: components,
                        _fullyLoaded: true   // 标记为完全加载
                    }));

                    console.log(`已加载 ${components.length} 个组件`);
                    message.success(`已加载 ${components.length} 个组件`);
                } catch (error) {
                    console.error('加载组件列表失败:', error);
                    message.error('加载组件列表失败');
                    // 即使组件加载失败，也将状态标记为已完成加载
                    setRepoSummary(prev => ({
                        ...prev,
                        _fullyLoaded: true,
                        _loadError: true
                    }));
                } finally {
                    setDelayedLoading(false);
                }
            }, 1000); // 延迟1秒后加载组件列表

        } catch (error) {
            message.error('加载代码库摘要失败');
            console.error(error);
        } finally {
            setLoading(false);
        }
    }, []);

    // 按需加载更多组件
    const loadMoreComponents = async (page) => {
        if (!currentRepo || !currentRepo.id) return;

        try {
            setLoadingComponent(true);
            const componentsResponse = await axios.get(`/code/repositories/${currentRepo.id}/components`, {
                params: {
                    page,
                    page_size: componentListPageSize
                }
            });

            // 确保返回的是数组
            const newComponents = Array.isArray(componentsResponse.data) ?
                componentsResponse.data : [];

            if (newComponents.length === 0) {
                message.info('没有更多组件可加载');
                return;
            }

            // 合并新组件到摘要
            setRepoSummary(prev => {
                if (!prev) return prev;

                // 检查是否有重复组件
                const existingIds = new Set(prev.important_components?.map(c => c.id) || []);
                const uniqueNewComponents = newComponents.filter(c => !existingIds.has(c.id));

                // 移除_loadError标记，如果之前有
                const { _loadError, ...restPrev } = prev;

                return {
                    ...restPrev,
                    important_components: [
                        ...(prev.important_components || []),
                        ...uniqueNewComponents
                    ],
                    _fullyLoaded: true
                };
            });

            setComponentListPage(page);
            message.success(`已加载 ${newComponents.length} 个新组件`);
        } catch (error) {
            console.error('加载更多组件失败:', error);
            message.error('加载更多组件失败');
        } finally {
            setLoadingComponent(false);
        }
    };

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

    // 修改viewComponentDetails函数，实现按需加载详情
    const viewComponentDetails = async (componentId) => {
        // 如果已经选中该组件，不进行任何操作
        if (selectedComponent === componentId) {
            return;
        }

        // 设置选中组件ID，先显示加载状态
        setSelectedComponent(componentId);

        // 立即更新UI中选中状态，不等待数据加载
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

        // 显示一个简单的占位符，表明组件正在加载
        setComponentDetails({
            id: componentId,
            name: "加载中...",
            type: "loading",
            isLoading: true
        });

        // 如果已经有缓存的组件详情，直接使用缓存
        if (componentCache[componentId]) {
            // 延迟一小段时间再显示，让用户感知到状态变化
            setTimeout(() => {
                setComponentDetails(componentCache[componentId]);
            }, 100);
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

            // 尝试懒加载依赖关系和影响分析
            // 不阻塞主线程，使用Promise.all同时请求
            setTimeout(() => {
                Promise.all([
                    fetchComponentDependencies(componentId, false),
                    fetchImpactAnalysis(componentId, false)
                ]).catch(error => {
                    console.error('懒加载组件相关数据失败:', error);
                    // 静默处理错误，不显示错误消息给用户
                });
            }, 300);

        } catch (error) {
            console.error('获取组件详情失败:', error);
            message.error('获取组件详情失败');
            // 设置错误状态
            setComponentDetails({
                id: componentId,
                name: "加载失败",
                error: true,
                message: error.message
            });
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

    // 修改renderCodeDisplay函数，优化加载状态显示
    const renderCodeDisplay = () => {
        if (!componentDetails) {
            return <Empty description="选择一个组件查看详情" />;
        }

        // 处理加载中状态
        if (componentDetails.isLoading) {
            return (
                <div style={{ padding: '40px 0', textAlign: 'center' }}>
                    <Spin tip="加载组件详情..." />
                    <div style={{ marginTop: 16, color: '#888' }}>正在准备代码内容...</div>
                </div>
            );
        }

        // 处理错误状态
        if (componentDetails.error) {
            return (
                <div style={{ padding: '40px 0', textAlign: 'center' }}>
                    <div style={{ fontSize: 32, color: '#ff4d4f', marginBottom: 16 }}>
                        <InfoCircleTwoTone twoToneColor="#ff4d4f" />
                    </div>
                    <div>加载失败: {componentDetails.message || '未知错误'}</div>
                    <Button
                        type="link"
                        onClick={() => viewComponentDetails(componentDetails.id)}
                        style={{ marginTop: 16 }}
                    >
                        重试
                    </Button>
                </div>
            );
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
    const fetchComponentDependencies = async (componentId, showLoading = true) => {
        // 如果缓存中已有依赖数据，直接使用缓存
        if (dependenciesCache[componentId]) {
            setDependencies(dependenciesCache[componentId]);
            return;
        }

        try {
            // 设置加载状态
            if (showLoading) {
                message.loading('加载依赖关系...');
            }

            const response = await axios.get(`/code/components/${componentId}`);
            const data = response.data || {};

            // 检查返回数据结构
            const dependencies = Array.isArray(data.dependencies) ? data.dependencies : [];
            const dependents = Array.isArray(data.dependents) ? data.dependents : [];

            // 构建依赖关系图数据
            const nodes = [];
            const edges = [];

            // 中心节点（当前组件）
            nodes.push({
                id: `component-${data.id}`,
                data: {
                    label: (
                        <div style={{ padding: '5px' }}>
                            {typeIcons[data.type] || <CodeOutlined />}
                            <span style={{ marginLeft: '5px' }}>{data.name}</span>
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
            dependencies.forEach((dep, index) => {
                const angle = (index * (Math.PI * 2)) / (dependencies.length || 1);
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
                    source: `component-${data.id}`,
                    target: `dependency-${dep.id}`,
                    animated: true,
                    style: { stroke: '#52c41a' }
                });
            });

            // 添加被依赖节点
            dependents.forEach((dep, index) => {
                const angle = (index * (Math.PI * 2)) / (dependents.length || 1);
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
                    target: `component-${data.id}`,
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

            if (showLoading && (dependencies.length > 0 || dependents.length > 0)) {
                message.success('依赖关系加载完成');
            } else if (showLoading) {
                message.info('没有发现依赖关系');
            }
        } catch (error) {
            console.error('获取组件依赖关系失败:', error);
            if (showLoading) {
                message.error('获取组件依赖关系失败');
            }
            // 设置空的依赖图，避免UI异常
            setDependencies({ nodes: [], edges: [] });
        }
    };

    // 获取组件影响分析
    const fetchImpactAnalysis = async (componentId, showLoading = true) => {
        // 如果缓存中已有影响分析数据，直接使用缓存
        if (impactAnalysisCache[componentId]) {
            setImpactAnalysis(impactAnalysisCache[componentId]);
            return;
        }

        try {
            if (showLoading) {
                message.loading('加载影响分析数据...');
            }

            const impactResponse = await axios.get(`/code/components/${componentId}/impact`);
            const data = impactResponse.data || {};

            // 规范化数据结构
            const normalizedData = {
                impact_summary: {
                    direct_impact_count: data.impact_summary?.direct_impact_count || 0,
                    indirect_impact_count: data.impact_summary?.indirect_impact_count || 0,
                    affected_tests_count: data.impact_summary?.affected_tests_count || 0
                },
                direct_impact: Array.isArray(data.direct_impact) ? data.direct_impact : [],
                indirect_impact: Array.isArray(data.indirect_impact) ? data.indirect_impact : [],
                affected_tests: Array.isArray(data.affected_tests) ? data.affected_tests : []
            };

            setImpactAnalysis(normalizedData);

            // 更新缓存
            setImpactAnalysisCache(prev => ({
                ...prev,
                [componentId]: normalizedData
            }));

            if (showLoading) {
                message.success('影响分析数据加载完成');
            }
        } catch (error) {
            console.error('获取影响分析失败:', error);
            if (showLoading) {
                message.error('获取影响分析失败');
            }
            // 设置基本的空结构，避免UI异常
            setImpactAnalysis({
                impact_summary: { direct_impact_count: 0, indirect_impact_count: 0, affected_tests_count: 0 },
                direct_impact: [],
                indirect_impact: [],
                affected_tests: []
            });
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

    // 向量化代码库
    const vectorizeRepo = async () => {
        if (!currentRepo) {
            message.error('请先选择一个代码库');
            return;
        }

        setLoading(true);
        try {
            const response = await axios.post(`/code/repositories/${currentRepo.id}/vectorize`, {
                knowledge_base_id: selectedKnowledgeBase
            });

            if (response.data.status === 'success' || response.data.status === 'partial_success') {
                message.success(`代码库向量化成功，已处理 ${response.data.processed_documents} 个组件`);
            } else {
                message.warning(response.data.message || '向量化操作未完全成功');
            }
        } catch (error) {
            console.error('向量化代码库失败:', error);
            message.error(`向量化失败: ${error.response?.data?.detail || error.message}`);
        } finally {
            setLoading(false);
        }
    };

    const repoSelector = (
        <Space style={{ marginBottom: 0 }}>
            <span style={{ fontWeight: 'bold' }}>知识库:</span>
            <Select
                style={{ width: 180 }}
                loading={kbLoading}
                placeholder="选择知识库"
                value={selectedKnowledgeBase}
                onChange={setSelectedKnowledgeBase}
            >
                <Option value={null}>所有代码库</Option>
                {Array.isArray(knowledgeBases) && knowledgeBases.map(kb => (
                    <Option key={kb.id} value={kb.id}>{kb.name}</Option>
                ))}
            </Select>

            <span style={{ fontWeight: 'bold', marginLeft: 8 }}>代码库:</span>
            <Select
                style={{ width: 180 }}
                loading={loading}
                placeholder="选择代码库"
                value={currentRepo?.id}
                onChange={(value) => {
                    const selected = repositories.find(r => r.id === value);
                    setCurrentRepo(selected);
                }}
                disabled={!repositories || repositories.length === 0}
            >
                {Array.isArray(repositories) && repositories.map(repo => (
                    <Option key={repo.id} value={repo.id}>{repo.name}</Option>
                ))}
            </Select>

            <Button
                type="primary"
                size="middle"
                icon={<UploadOutlined />}
                onClick={() => setUploadModalVisible(true)}
            >
                添加
            </Button>
        </Space>
    );

    return (
        <div className="code-analysis-container">
            <style>{customStyles}</style>
            <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                {repoSelector}
            </div>

            {repoSummary && (
                <Card
                    size="small"
                    className="repo-overview-card"
                    style={{ marginBottom: 12 }}
                    bodyStyle={{ padding: '8px 12px' }}
                >
                    <Row gutter={16}>
                        <Col span={18}>
                            <div style={{ fontSize: 16, fontWeight: 'bold', marginBottom: 4 }}>
                                {currentRepo?.name}
                                <span style={{ fontSize: 13, fontWeight: 'normal', marginLeft: 8, color: '#888' }}>
                                    {repoSummary.description && repoSummary.description !== "无描述信息"
                                        ? repoSummary.description
                                        : null
                                    }
                                </span>
                            </div>
                            <Row gutter={24}>
                                <Col span={6}>
                                    <Statistic title="文件" value={repoSummary.statistics.total_files} size="small" />
                                </Col>
                                <Col span={6}>
                                    <Statistic title="组件" value={repoSummary.statistics.total_components} size="small" />
                                </Col>
                                <Col span={6}>
                                    <Statistic title="依赖" value={repoSummary.statistics.total_dependencies} size="small" />
                                </Col>
                            </Row>
                        </Col>
                        <Col span={6}>
                            <div style={{ marginBottom: 4, fontSize: 13 }}>语言分布</div>
                            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                                {Object.entries(repoSummary.file_stats).length > 0 ? (
                                    Object.entries(repoSummary.file_stats).map(([lang, count]) => (
                                        <Tag key={lang} color={
                                            lang === 'python' ? 'blue' :
                                                lang === 'javascript' ? 'green' :
                                                    lang === 'typescript' ? 'geekblue' :
                                                        lang === 'java' ? 'orange' :
                                                            lang === 'c/c++' ? 'purple' : 'default'
                                        }>
                                            {lang}: {count}
                                        </Tag>
                                    ))
                                ) : (
                                    <span style={{ color: '#888', fontSize: 12 }}>无语言统计</span>
                                )}
                            </div>
                        </Col>
                    </Row>
                </Card>
            )}

            {loading && !repoSummary && (
                <div style={{ textAlign: 'center', padding: '12px 0', marginBottom: 12, background: '#f0f8ff', borderRadius: 4 }}>
                    <Spin size="small" style={{ marginRight: 8 }} />
                    <span>正在加载代码库信息...</span>
                </div>
            )}

            {repoSummary && repoSummary._partiallLoaded && !repoSummary._fullyLoaded && (
                <div style={{ textAlign: 'center', padding: '6px 0', marginBottom: 12, background: '#f6ffed', borderRadius: 4 }}>
                    <Spin spinning={delayedLoading} size="small" style={{ marginRight: 8 }} />
                    <span style={{ fontSize: 12, color: '#52c41a' }}>
                        代码库基本信息已加载，组件列表正在后台加载中...
                    </span>
                </div>
            )}

            {repoSummary && repoSummary._loadError && (
                <div style={{ textAlign: 'center', padding: '6px 0', marginBottom: 12, background: '#fff2f0', borderRadius: 4 }}>
                    <span style={{ fontSize: 12, color: '#ff4d4f' }}>
                        组件列表加载失败，但您仍可以浏览目录结构。
                        <Button
                            type="link"
                            size="small"
                            style={{ padding: 0, marginLeft: 4 }}
                            onClick={() => loadMoreComponents(1)}
                        >
                            重试
                        </Button>
                    </span>
                </div>
            )}

            <Row gutter={16}>
                <Col span={7}>
                    <Card
                        title={
                            <div style={{ fontSize: 14 }}>
                                <span>代码导航</span>
                                {repoSummary?.important_components && (
                                    <Tag color="blue" style={{ marginLeft: 8, fontSize: 12 }}>
                                        {repoSummary.important_components.length} 个组件
                                    </Tag>
                                )}
                            </div>
                        }
                        bodyStyle={{ padding: 0, maxHeight: 700, overflow: 'auto', overflowX: 'hidden' }}
                        bordered={true}
                        className="code-navigation-card"
                        size="small"
                        extra={
                            <Tooltip title="刷新组件列表">
                                <Button
                                    type="text"
                                    icon={<SyncOutlined spin={loadingComponent} />}
                                    size="small"
                                    onClick={() => loadMoreComponents(componentListPage + 1)}
                                    disabled={loadingComponent || !repoSummary}
                                />
                            </Tooltip>
                        }
                    >
                        <Tabs
                            activeKey={activeNavTab}
                            onChange={key => setActiveNavTab(key)}
                            type="card"
                            tabBarStyle={{ margin: '0 8px', paddingTop: '8px' }}
                            tabBarGutter={4}
                            size="small"
                        >
                            <TabPane
                                tab={
                                    <span>
                                        结构浏览
                                        {loadingStructure && <LoadingOutlined style={{ marginLeft: 4 }} />}
                                    </span>
                                }
                                key="structure"
                            >
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
                                                    // 从API获取文件内容
                                                    axios.get(`/code/files`, {
                                                        params: {
                                                            path: filePath.replace(currentRepo.path + '/', ''),
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
                                    <Empty description="没有可用的目录结构" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                                )}
                            </TabPane>
                            <TabPane tab="组件列表" key="important">
                                <ImportantComponentsList
                                    repoSummary={repoSummary}
                                    componentNameSearch={componentNameSearch}
                                    setComponentNameSearch={setComponentNameSearch}
                                    loading={loading || delayedLoading}
                                    viewComponentDetails={viewComponentDetails}
                                />
                                {repoSummary?._fullyLoaded && repoSummary.important_components.length >= 50 && (
                                    <div style={{ textAlign: 'center', padding: '8px 0', borderTop: '1px solid #f0f0f0' }}>
                                        <Button
                                            type="link"
                                            loading={loadingComponent}
                                            onClick={() => loadMoreComponents(componentListPage + 1)}
                                        >
                                            加载更多组件
                                        </Button>
                                    </div>
                                )}
                            </TabPane>
                            <TabPane tab="搜索结果" key="search">
                                <div style={{ padding: '12px' }}>
                                    <Search
                                        placeholder="搜索代码..."
                                        onSearch={handleSearch}
                                        enterButton
                                        loading={loading}
                                    />
                                </div>
                                <SearchResultsList
                                    searchResults={searchResults}
                                    viewComponentDetails={viewComponentDetails}
                                />
                            </TabPane>
                        </Tabs>
                    </Card>
                </Col>

                <Col span={17}>
                    <Card
                        className="code-details-card"
                        bodyStyle={{ padding: 8 }}
                        bordered={true}
                        size="small"
                    >
                        <Tabs
                            defaultActiveKey="code"
                            className="code-details-tabs"
                            type="card"
                        >
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
                    </Card>
                </Col>
            </Row>

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

            {loading && !repoSummary && (
                <div style={{ position: 'absolute', left: 0, top: 0, right: 0, bottom: 0, zIndex: 10, background: 'rgba(255,255,255,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Spin tip="加载中..." />
                </div>
            )}
        </div>
    );
};

export default CodeAnalysisPage; 