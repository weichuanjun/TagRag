import React, { useState, useEffect, useRef } from 'react';
import { Card, Select, Button, Spin, Space, Tooltip, Input, Tag, Empty, Switch, Divider, Typography, Checkbox, Drawer, Radio, Slider } from 'antd';
import { SearchOutlined, ExpandOutlined, CompressOutlined, InfoCircleOutlined, TagsOutlined, FileTextOutlined, ForceOutlined, ZoomInOutlined, ZoomOutOutlined, ReloadOutlined } from '@ant-design/icons';
import ForceGraph2D from 'react-force-graph-2d';
import axios from 'axios';

const { Option } = Select;
const { Title, Paragraph, Text } = Typography;
const { CheckboxGroup } = Checkbox;

const GraphVisualizerPage = () => {
    const [loading, setLoading] = useState(false);
    const [knowledgeBases, setKnowledgeBases] = useState([]);
    const [selectedKnowledgeBase, setSelectedKnowledgeBase] = useState(null);
    const [graphData, setGraphData] = useState({ nodes: [], links: [] });
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedEntity, setSelectedEntity] = useState(null);
    const [fullscreen, setFullscreen] = useState(false);
    const [onlyShowTags, setOnlyShowTags] = useState(true); // 默认仅显示标签
    const [tagTypes, setTagTypes] = useState([]);
    const [selectedTagTypes, setSelectedTagTypes] = useState([]);
    const [contentDrawerVisible, setContentDrawerVisible] = useState(false);
    const [contentText, setContentText] = useState('');
    const [showLabels, setShowLabels] = useState(true); // 是否显示标签文字
    const [linkDistance, setLinkDistance] = useState(120); // 连接线距离
    const [chargeStrength, setChargeStrength] = useState(-80); // 节点排斥力
    const graphRef = useRef();

    // 获取知识库列表
    useEffect(() => {
        fetchKnowledgeBases();
    }, []);

    // 当知识库变更时加载图数据和标签类型
    useEffect(() => {
        if (selectedKnowledgeBase) {
            fetchGraphData(selectedKnowledgeBase);
            fetchTagTypes(selectedKnowledgeBase);
        }
    }, [selectedKnowledgeBase]);

    // 标签类型筛选或只显示标签模式变更时重新加载图数据
    useEffect(() => {
        if (selectedKnowledgeBase) {
            fetchGraphData(selectedKnowledgeBase);
        }
    }, [onlyShowTags, selectedTagTypes]);

    // 设置图表中心点为TAG节点
    useEffect(() => {
        if (graphRef.current && graphData.nodes && graphData.nodes.length > 0) {
            // 找到TAG类型的节点
            const tagNodes = graphData.nodes.filter(node => node.type === 'TAG');
            if (tagNodes.length > 0) {
                // 计算标签节点的中心点
                setTimeout(() => {
                    centerOnTags();
                }, 500);
            }
        }
    }, [graphData]);

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
            // 构建查询参数
            const params = {};
            if (selectedTagTypes.length > 0) {
                params.tag_types = selectedTagTypes.join(',');
            }

            // 选择合适的API端点
            const endpoint = onlyShowTags
                ? `/graph/tag-data/${knowledgeBaseId}`
                : `/graph/data/${knowledgeBaseId}`;

            const response = await axios.get(endpoint, { params });
            setGraphData(response.data);
        } catch (error) {
            console.error('获取图数据失败:', error);
            // 如果没有图数据，设置为空
            setGraphData({ nodes: [], links: [] });
        } finally {
            setLoading(false);
        }
    };

    const fetchTagTypes = async (knowledgeBaseId) => {
        try {
            const response = await axios.get(`/graph/tag-types/${knowledgeBaseId}`);
            setTagTypes(response.data.tag_types || []);
            // 默认选择所有标签类型
            setSelectedTagTypes(response.data.tag_types || []);
        } catch (error) {
            console.error('获取标签类型失败:', error);
            setTagTypes([]);
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

        // 如果有相关内容，可以显示在抽屉中
        if (node.related_content) {
            setContentText(node.related_content);
            setContentDrawerVisible(true);
        }

        // 可选：高亮显示相关连接并居中显示
        if (graphRef.current) {
            graphRef.current.centerAt(node.x, node.y, 1000);
            graphRef.current.zoom(2, 1000);
        }
    };

    const toggleFullscreen = () => {
        setFullscreen(!fullscreen);
    };

    const handleTagTypeChange = (checkedValues) => {
        setSelectedTagTypes(checkedValues);
    };

    // 将视图居中到标签节点
    const centerOnTags = () => {
        if (!graphRef.current) return;

        // 找到所有TAG类型节点
        const tagNodes = graphData.nodes.filter(node => node.type === 'TAG');
        if (tagNodes.length === 0) return;

        // 计算标签节点的平均坐标
        let sumX = 0, sumY = 0;
        for (const node of tagNodes) {
            if (node.x !== undefined && node.y !== undefined) {
                sumX += node.x;
                sumY += node.y;
            }
        }

        const avgX = sumX / tagNodes.length;
        const avgY = sumY / tagNodes.length;

        // 居中并稍微缩小视图
        graphRef.current.centerAt(avgX, avgY, 1000);
        graphRef.current.zoom(1.5, 1000);
    };

    // 重新布局图表
    const resetLayout = () => {
        if (!graphRef.current) return;

        // 设置强制模拟参数
        if (graphRef.current.d3Force) {
            // 设置节点之间的距离
            graphRef.current.d3Force('link').distance(linkDistance);

            // 设置节点间的排斥力
            graphRef.current.d3Force('charge').strength(chargeStrength);

            // 重启模拟
            graphRef.current.d3ReheatSimulation();
        }

        // 稍后居中到标签节点
        setTimeout(() => {
            centerOnTags();
        }, 500);
    };

    // 获取节点样式
    const getNodeCanvasObject = (node, ctx, globalScale) => {
        const label = node.label || '';
        const fontSize = Math.max(8, node.size ? node.size / 5 : 8); // 更小的字体
        const nodeR = node.size || 5;

        // 绘制不同形状的节点
        ctx.beginPath();
        ctx.fillStyle = node.color || '#1890ff';

        // 高亮选中的节点
        if (selectedEntity && selectedEntity.id === node.id) {
            ctx.strokeStyle = '#ff6600';
            ctx.lineWidth = 2;
        } else {
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 1;
        }

        // 根据节点形状绘制不同样式
        switch (node.shape) {
            case 'triangle':
                drawTriangle(ctx, node.x, node.y, nodeR);
                break;
            case 'square':
                drawSquare(ctx, node.x, node.y, nodeR);
                break;
            case 'diamond':
                drawDiamond(ctx, node.x, node.y, nodeR);
                break;
            case 'star':
                drawStar(ctx, node.x, node.y, nodeR);
                break;
            case 'document':
                drawDocument(ctx, node.x, node.y, nodeR);
                break;
            default:
                ctx.arc(node.x, node.y, nodeR, 0, 2 * Math.PI);
        }

        ctx.fill();
        ctx.stroke();

        // 只在缩放比例足够大时显示标签，或者节点被选中时，或者全局showLabels开启
        const showLabel = showLabels || globalScale > 1.5 || (selectedEntity && selectedEntity.id === node.id);
        if (showLabel) {
            // 绘制标签文本
            ctx.fillStyle = 'black';
            ctx.font = `${fontSize}px Sans-Serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';

            let displayLabel = label;
            // 如果标签过长，截断
            if (displayLabel.length > 15) {
                displayLabel = displayLabel.substring(0, 12) + '...';
            }

            // 如果是内容节点，添加图标
            if (node.type === 'CONTENT') {
                displayLabel = '📄';
            }

            // 绘制带背景的文本
            const textWidth = ctx.measureText(displayLabel).width;
            ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
            ctx.fillRect(node.x - textWidth / 2 - 2, node.y + nodeR + 2, textWidth + 4, fontSize + 4);

            ctx.fillStyle = '#333';
            ctx.fillText(displayLabel, node.x, node.y + nodeR + fontSize / 2 + 4);
        }
    };

    // 辅助函数：绘制三角形
    const drawTriangle = (ctx, x, y, r) => {
        ctx.moveTo(x, y - r);
        ctx.lineTo(x - r, y + r);
        ctx.lineTo(x + r, y + r);
        ctx.closePath();
    };

    // 辅助函数：绘制方形
    const drawSquare = (ctx, x, y, r) => {
        ctx.rect(x - r, y - r, r * 2, r * 2);
    };

    // 辅助函数：绘制菱形
    const drawDiamond = (ctx, x, y, r) => {
        ctx.moveTo(x, y - r);
        ctx.lineTo(x + r, y);
        ctx.lineTo(x, y + r);
        ctx.lineTo(x - r, y);
        ctx.closePath();
    };

    // 辅助函数：绘制星形
    const drawStar = (ctx, x, y, r) => {
        const spikes = 5;
        const outerRadius = r;
        const innerRadius = r * 0.4;

        let rot = Math.PI / 2 * 3;
        let step = Math.PI / spikes;

        ctx.moveTo(x, y - outerRadius);
        for (let i = 0; i < spikes; i++) {
            ctx.lineTo(x + Math.cos(rot) * outerRadius, y + Math.sin(rot) * outerRadius);
            rot += step;
            ctx.lineTo(x + Math.cos(rot) * innerRadius, y + Math.sin(rot) * innerRadius);
            rot += step;
        }
        ctx.closePath();
    };

    // 辅助函数：绘制文档形状
    const drawDocument = (ctx, x, y, r) => {
        const width = r * 1.6;
        const height = r * 2;
        const foldSize = r * 0.3;

        ctx.moveTo(x - width / 2, y - height / 2);
        ctx.lineTo(x + width / 2 - foldSize, y - height / 2);
        ctx.lineTo(x + width / 2, y - height / 2 + foldSize);
        ctx.lineTo(x + width / 2, y + height / 2);
        ctx.lineTo(x - width / 2, y + height / 2);
        ctx.closePath();

        // 折角
        ctx.moveTo(x + width / 2 - foldSize, y - height / 2);
        ctx.lineTo(x + width / 2 - foldSize, y - height / 2 + foldSize);
        ctx.lineTo(x + width / 2, y - height / 2 + foldSize);
    };

    return (
        <div className="graph-page" style={{ height: fullscreen ? '100vh' : 'auto' }}>
            <Card
                title={
                    <Space>
                        <span>知识图谱可视化</span>
                        {selectedKnowledgeBase && (
                            <Tag color="blue">
                                {knowledgeBases.find(kb => kb.id === selectedKnowledgeBase)?.name || ''}
                            </Tag>
                        )}
                    </Space>
                }
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

                        <Tooltip title="仅显示标签节点">
                            <Switch
                                checkedChildren="仅标签"
                                unCheckedChildren="全部"
                                checked={onlyShowTags}
                                onChange={setOnlyShowTags}
                                style={{ marginRight: 8 }}
                            />
                        </Tooltip>

                        <Tooltip title="标签类型筛选">
                            <Select
                                mode="multiple"
                                style={{ minWidth: 200 }}
                                placeholder="筛选标签类型"
                                value={selectedTagTypes}
                                onChange={setSelectedTagTypes}
                                allowClear
                                disabled={tagTypes.length === 0}
                            >
                                {tagTypes.map(type => (
                                    <Option key={type} value={type}>{type}</Option>
                                ))}
                            </Select>
                        </Tooltip>

                        <Space>
                            <Tooltip title="总是显示标签文字">
                                <Switch
                                    checkedChildren="标签"
                                    unCheckedChildren="标签"
                                    checked={showLabels}
                                    onChange={setShowLabels}
                                    size="small"
                                />
                            </Tooltip>

                            <Tooltip title="居中显示标签">
                                <Button
                                    icon={<ZoomInOutlined />}
                                    size="small"
                                    onClick={centerOnTags}
                                />
                            </Tooltip>

                            <Tooltip title="重置图表布局">
                                <Button
                                    icon={<ReloadOutlined />}
                                    size="small"
                                    onClick={resetLayout}
                                />
                            </Tooltip>
                        </Space>

                        <Tooltip title="图中节点表示文档标签和内容，连线表示它们之间的关系">
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
                            linkWidth={link => link.width || (selectedEntity && (link.source.id === selectedEntity.id || link.target.id === selectedEntity.id) ? 3 : 1)}
                            linkColor={link => link.color || (selectedEntity && (link.source.id === selectedEntity.id || link.target.id === selectedEntity.id) ? '#ff6600' : '#999')}
                            onNodeClick={handleNodeClick}
                            cooldownTicks={100}
                            nodeCanvasObject={getNodeCanvasObject}
                            linkLineDash={link => link.dashed ? [5, 3] : undefined}
                            linkDirectionalArrowLength={link => link.arrow ? 6 : 0}
                            d3Force="charge"
                            d3ForceChargeStrength={chargeStrength}
                            d3ForceDistance={linkDistance}
                            warmupTicks={100}
                            onEngineStop={() => {
                                // 在图表停止移动后居中到标签
                                setTimeout(centerOnTags, 300);
                            }}
                        />
                    ) : (
                        <Empty description="暂无图数据或该知识库尚未构建知识图谱" />
                    )}
                </div>

                <div style={{ marginTop: 16, display: 'flex', justifyContent: 'space-between' }}>
                    {/* 图表参数调整 */}
                    <div style={{ width: '100%', maxWidth: '600px' }}>
                        <Space direction="vertical" size="small" style={{ width: '100%' }}>
                            <div>
                                <Text>节点间距调整:</Text>
                                <Slider
                                    min={50}
                                    max={300}
                                    value={linkDistance}
                                    onChange={(value) => setLinkDistance(value)}
                                    onAfterChange={resetLayout}
                                    style={{ width: 200, marginLeft: 16 }}
                                />
                            </div>
                            <div>
                                <Text>节点排斥力:</Text>
                                <Slider
                                    min={-200}
                                    max={-30}
                                    value={chargeStrength}
                                    onChange={(value) => setChargeStrength(value)}
                                    onAfterChange={resetLayout}
                                    style={{ width: 200, marginLeft: 16 }}
                                />
                            </div>
                        </Space>
                    </div>

                    {/* 选中节点信息 */}
                    {selectedEntity && (
                        <div style={{ padding: 16, background: '#f9f9f9', borderRadius: 4, minWidth: '400px' }}>
                            <Space align="start">
                                <Title level={4}>{selectedEntity.label}</Title>
                                {selectedEntity.tag_type && (
                                    <Tag color={selectedEntity.color}>{selectedEntity.tag_type}</Tag>
                                )}
                            </Space>

                            <Paragraph>{selectedEntity.description}</Paragraph>

                            {selectedEntity.related_content && (
                                <Button
                                    type="primary"
                                    icon={<FileTextOutlined />}
                                    onClick={() => {
                                        setContentText(selectedEntity.related_content);
                                        setContentDrawerVisible(true);
                                    }}
                                >
                                    查看相关内容
                                </Button>
                            )}

                            {selectedEntity.type === "TAG" && (
                                <div style={{ marginTop: 8 }}>
                                    <Text strong>重要性: </Text>
                                    <Text>{(selectedEntity.importance * 100).toFixed(0)}%</Text>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </Card>

            <Drawer
                title="原始内容"
                placement="right"
                onClose={() => setContentDrawerVisible(false)}
                open={contentDrawerVisible}
                width={500}
            >
                <div style={{ whiteSpace: 'pre-wrap' }}>
                    {contentText}
                </div>
            </Drawer>
        </div>
    );
};

export default GraphVisualizerPage; 