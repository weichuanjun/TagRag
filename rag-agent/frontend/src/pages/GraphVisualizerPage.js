import React, { useState, useEffect, useRef } from 'react';
import { Card, Select, Button, Spin, Space, Tooltip, Input, Tag, Empty } from 'antd';
import { SearchOutlined, ExpandOutlined, CompressOutlined, InfoCircleOutlined } from '@ant-design/icons';
import ForceGraph2D from 'react-force-graph-2d';
import axios from 'axios';

const { Option } = Select;

const GraphVisualizerPage = () => {
    const [loading, setLoading] = useState(false);
    const [knowledgeBases, setKnowledgeBases] = useState([]);
    const [selectedKnowledgeBase, setSelectedKnowledgeBase] = useState(null);
    const [graphData, setGraphData] = useState({ nodes: [], links: [] });
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedEntity, setSelectedEntity] = useState(null);
    const [fullscreen, setFullscreen] = useState(false);
    const graphRef = useRef();

    // 获取知识库列表
    useEffect(() => {
        fetchKnowledgeBases();
    }, []);

    // 当知识库变更时加载图数据
    useEffect(() => {
        if (selectedKnowledgeBase) {
            fetchGraphData(selectedKnowledgeBase);
        }
    }, [selectedKnowledgeBase]);

    const fetchKnowledgeBases = async () => {
        try {
            const response = await axios.get('/knowledge-bases');
            setKnowledgeBases(response.data || []);
            if (response.data && response.data.length > 0) {
                setSelectedKnowledgeBase(response.data[0].id);
            }
        } catch (error) {
            console.error('获取知识库列表失败:', error);
        }
    };

    const fetchGraphData = async (knowledgeBaseId) => {
        setLoading(true);
        try {
            const response = await axios.get(`/graph/data/${knowledgeBaseId}`);
            setGraphData(response.data);
        } catch (error) {
            console.error('获取图数据失败:', error);
            // 如果没有图数据，设置为空
            setGraphData({ nodes: [], links: [] });
        } finally {
            setLoading(false);
        }
    };

    const handleSearch = async () => {
        if (!searchTerm.trim()) return;

        setLoading(true);
        try {
            const response = await axios.get(`/graph/search`, {
                params: {
                    knowledge_base_id: selectedKnowledgeBase,
                    query: searchTerm
                }
            });
            setGraphData(response.data);
        } catch (error) {
            console.error('搜索图数据失败:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleNodeClick = (node) => {
        setSelectedEntity(node);
        // 可选：高亮显示相关连接
        if (graphRef.current) {
            graphRef.current.centerAt(node.x, node.y, 1000);
            graphRef.current.zoom(2, 1000);
        }
    };

    const toggleFullscreen = () => {
        setFullscreen(!fullscreen);
    };

    // 测试功能：添加示例实体（开发阶段用）
    const addTestEntities = async () => {
        if (!selectedKnowledgeBase) return;

        setLoading(true);
        try {
            const response = await axios.post(`/graph/extract`, {
                text: "这是一个测试文本，用于生成一些示例实体和关系，以便测试知识图谱可视化功能。",
                knowledge_base_id: selectedKnowledgeBase
            });

            // 添加成功后重新加载图数据
            fetchGraphData(selectedKnowledgeBase);
        } catch (error) {
            console.error('添加测试实体失败:', error);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="graph-page" style={{ height: fullscreen ? '100vh' : 'auto' }}>
            <Card
                title="知识图谱可视化"
                style={{
                    width: '100%',
                    position: fullscreen ? 'fixed' : 'relative',
                    top: fullscreen ? 0 : 'auto',
                    left: fullscreen ? 0 : 'auto',
                    zIndex: fullscreen ? 1000 : 1,
                    height: fullscreen ? '100vh' : 'auto',
                }}
                extra={
                    <Button
                        icon={fullscreen ? <CompressOutlined /> : <ExpandOutlined />}
                        onClick={toggleFullscreen}
                    />
                }
            >
                <div style={{ marginBottom: 16 }}>
                    <Space align="center" wrap>
                        <Select
                            style={{ width: 200 }}
                            placeholder="选择知识库"
                            value={selectedKnowledgeBase}
                            onChange={setSelectedKnowledgeBase}
                        >
                            {knowledgeBases.map(kb => (
                                <Option key={kb.id} value={kb.id}>{kb.name}</Option>
                            ))}
                        </Select>

                        <Input
                            placeholder="搜索实体..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            onPressEnter={handleSearch}
                            style={{ width: 200 }}
                            suffix={
                                <Tooltip title="搜索相关实体">
                                    <SearchOutlined
                                        style={{ color: '#1890ff', cursor: 'pointer' }}
                                        onClick={handleSearch}
                                    />
                                </Tooltip>
                            }
                        />

                        <Button onClick={addTestEntities}>添加测试数据</Button>

                        <Tooltip title="图中节点表示文档实体，连线表示它们之间的关系">
                            <InfoCircleOutlined style={{ color: '#1890ff' }} />
                        </Tooltip>
                    </Space>
                </div>

                <div style={{
                    height: fullscreen ? 'calc(100vh - 180px)' : '70vh',
                    position: 'relative',
                    border: '1px solid #f0f0f0',
                    borderRadius: '4px',
                    overflow: 'hidden'
                }}>
                    {loading ? (
                        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
                            <Spin tip="加载图数据中..." />
                        </div>
                    ) : graphData.nodes && graphData.nodes.length > 0 ? (
                        <ForceGraph2D
                            ref={graphRef}
                            graphData={graphData}
                            nodeLabel={node => `${node.label}: ${node.description || ''}`}
                            linkLabel={link => link.type || '关联'}
                            nodeColor={node => selectedEntity && selectedEntity.id === node.id ? '#ff6600' : node.color || '#1890ff'}
                            linkWidth={link => selectedEntity && (link.source.id === selectedEntity.id || link.target.id === selectedEntity.id) ? 3 : 1}
                            linkColor={link => selectedEntity && (link.source.id === selectedEntity.id || link.target.id === selectedEntity.id) ? '#ff6600' : '#999'}
                            onNodeClick={handleNodeClick}
                            cooldownTicks={100}
                        />
                    ) : (
                        <Empty description="暂无图数据或该知识库尚未构建知识图谱" />
                    )}
                </div>

                {selectedEntity && (
                    <div style={{ marginTop: 16, padding: 16, background: '#f9f9f9', borderRadius: 4 }}>
                        <h3>{selectedEntity.label}</h3>
                        <p>{selectedEntity.description}</p>
                        <div>
                            {selectedEntity.tags && selectedEntity.tags.map(tag => (
                                <Tag key={tag} color="blue">{tag}</Tag>
                            ))}
                        </div>
                        {selectedEntity.source && (
                            <p>来源: {selectedEntity.source}</p>
                        )}
                    </div>
                )}
            </Card>
        </div>
    );
};

export default GraphVisualizerPage; 