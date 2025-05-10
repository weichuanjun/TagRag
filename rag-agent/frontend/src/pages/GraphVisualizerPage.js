import React, { useState, useEffect, useRef } from 'react';
import { Card, Select, Button, Spin, Space, Tooltip, Input, Tag, Empty, Switch, Divider, Typography, Checkbox, Drawer, Radio, Slider } from 'antd';
import { SearchOutlined, ExpandOutlined, CompressOutlined, InfoCircleOutlined, TagsOutlined, FileTextOutlined, ForceOutlined, ZoomInOutlined, ZoomOutOutlined, ReloadOutlined } from '@ant-design/icons';
import ForceGraph2D from 'react-force-graph-2d';
import axios from 'axios';
import * as d3 from 'd3';

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
    const [linkDistance, setLinkDistance] = useState(150); // 增加父子节点间的距离
    const [chargeStrength, setChargeStrength] = useState(-350); // 大幅增强节点间排斥力使独立群组更紧凑
    const [viewMode, setViewMode] = useState('tag_hierarchy'); // 新增视图模式: tag_hierarchy 或 document_tags
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
    }, [selectedKnowledgeBase, viewMode]);

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

            // 根据视图模式选择合适的API端点
            let endpoint;
            if (viewMode === 'tag_hierarchy') {
                // 标签层级关系视图
                endpoint = `/graph/tag-relations/${knowledgeBaseId}`;
            } else {
                // 原有的文档-标签关系视图
                endpoint = onlyShowTags
                    ? `/graph/tag-data/${knowledgeBaseId}`
                    : `/graph/data/${knowledgeBaseId}`;
            }

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

        // 确保有相关内容时显示抽屉
        if (node.related_content) {
            setContentText(node.related_content);
            setContentDrawerVisible(true);
        } else if (node.description) {
            // 如果没有related_content但有description，也显示在抽屉中
            setContentText(node.description);
            setContentDrawerVisible(true);
        }

        // 高亮显示相关连接并居中显示
        if (graphRef.current) {
            graphRef.current.centerAt(node.x, node.y, 800);
            graphRef.current.zoom(1.8, 800); // 增加缩放比例以便查看详情
        }

        // 添加日志以便调试
        console.log("点击节点:", node);
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

        // 居中并以适当比例显示
        graphRef.current.centerAt(avgX, avgY, 800);
        graphRef.current.zoom(1.2, 800);
    };

    // 重新布局图表
    const resetLayout = () => {
        if (!graphRef.current) return;

        // 设置强制模拟参数
        if (graphRef.current.d3Force) {
            // 设置节点之间的距离
            graphRef.current.d3Force('link').distance(link => {
                // 父子关系的链接距离保持较大
                if (link.type === 'PARENT_OF') {
                    return linkDistance;
                }
                // 其他类型的链接距离较小，促进聚集
                return linkDistance * 0.6;
            });

            // 设置节点间的排斥力
            graphRef.current.d3Force('charge').strength(chargeStrength);

            // 添加聚类力 - 使相同类型的节点靠近
            graphRef.current.d3Force('collide', d3.forceCollide()
                .radius(10) // 碰撞半径
                .strength(0.8) // 碰撞强度
            );

            // 添加X、Y向心力，使整个图表向中心聚集
            graphRef.current.d3Force('x', d3.forceX().strength(0.05));
            graphRef.current.d3Force('y', d3.forceY().strength(0.05));

            // 重启模拟
            graphRef.current.d3ReheatSimulation();

            // 打印当前力学参数
            console.log("力学参数:", {
                linkDistance,
                chargeStrength,
                forceCollide: 0.8,
                forceX: 0.05,
                forceY: 0.05
            });
        }

        // 稍后居中到标签节点
        setTimeout(() => {
            centerOnTags();
        }, 800);
    };

    // 获取节点样式
    const getNodeCanvasObject = (node, ctx, globalScale) => {
        const label = node.label || '';
        const fontSize = Math.max(6, node.size ? node.size / 6 : 6); // 减小字体大小

        // 根据层级简化节点大小
        let nodeR;
        if (node.hierarchy_level === 'root') {
            nodeR = 8; // 根节点稍大
        } else if (node.hierarchy_level === 'branch') {
            nodeR = 6; // 分支节点中等
        } else {
            nodeR = 4; // 叶节点最小
        }

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

        // 简化形状：只用三种形状区分层级
        if (node.hierarchy_level === 'root') {
            // 根节点使用方形
            drawSquare(ctx, node.x, node.y, nodeR);
        } else if (node.hierarchy_level === 'branch') {
            // 分支节点使用三角形
            drawTriangle(ctx, node.x, node.y, nodeR);
        } else if (node.type === 'CONTENT') {
            // 内容节点使用文档形状
            drawDocument(ctx, node.x, node.y, nodeR);
        } else {
            // 叶节点和其他节点使用圆形
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

                        <Radio.Group
                            value={viewMode}
                            onChange={(e) => setViewMode(e.target.value)}
                            optionType="button"
                            buttonStyle="solid"
                        >
                            <Radio.Button value="tag_hierarchy">标签层级关系</Radio.Button>
                            <Radio.Button value="document_tags">文档标签关系</Radio.Button>
                        </Radio.Group>

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

                        {viewMode === 'document_tags' && (
                            <Tooltip title="仅显示标签节点">
                                <Switch
                                    checkedChildren="仅标签"
                                    unCheckedChildren="全部"
                                    checked={onlyShowTags}
                                    onChange={setOnlyShowTags}
                                    style={{ marginRight: 8 }}
                                />
                            </Tooltip>
                        )}

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

                        <Tooltip title={viewMode === 'tag_hierarchy' ?
                            "图中节点表示标签层级结构和关系" :
                            "图中节点表示文档标签和内容，连线表示它们之间的关系"}>
                            <InfoCircleOutlined style={{ color: '#1890ff' }} />
                        </Tooltip>
                    </Space>
                </div>

                <div style={{
                    height: fullscreen ? 'calc(100vh - 180px)' : '55vh', // 图表高度从70vh减小到55vh
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
                            linkWidth={link => {
                                // 增强父子链接的显示
                                if (link.type === 'PARENT_OF') {
                                    return link.width || 1.5;
                                }
                                return link.width || 0.8;
                            }}
                            linkColor={link => {
                                if (selectedEntity && (link.source.id === selectedEntity.id || link.target.id === selectedEntity.id)) {
                                    return '#ff6600'; // 高亮选中节点的连接
                                }
                                return link.color || '#999';
                            }}
                            onNodeClick={handleNodeClick}
                            cooldownTicks={100}
                            nodeCanvasObject={getNodeCanvasObject}
                            linkLineDash={link => link.dashed ? [4, 2] : undefined}
                            linkDirectionalArrowLength={link => link.type === 'PARENT_OF' ? 5 : (link.arrow ? 4 : 0)}
                            linkDirectionalArrowRelPos={0.9}
                            linkCurvature={link => link.type === 'PARENT_OF' ? 0 : 0.2} // 父子链接为直线
                            d3Force={(name, force) => {
                                // 添加自定义力
                                if (name === 'charge') {
                                    // 强化排斥力
                                    force.strength(chargeStrength).distanceMax(300);
                                }
                            }}
                            linkStrength={link => {
                                // 父子关系的链接强度较低，允许更多的弹性
                                if (link.type === 'PARENT_OF') {
                                    return 0.3;
                                }
                                // 其他类型的链接强度较高，确保紧密连接
                                return link.value || 0.9;
                            }}
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

                <div style={{ marginTop: 12, display: 'flex', justifyContent: 'space-between' }}>
                    {/* 图表参数调整 */}
                    <div style={{ width: '100%', maxWidth: '600px' }}>
                        <Space direction="vertical" size="small" style={{ width: '100%' }}>
                            <div>
                                <Text>节点间距调整:</Text>
                                <Slider
                                    min={30} // 最小值从50减小到30
                                    max={200} // 最大值从300减小到200
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

                    {/* 选中节点信息 - 简化显示 */}
                    {selectedEntity && (
                        <div style={{ padding: 12, background: '#f9f9f9', borderRadius: 4, maxWidth: '400px', minWidth: '300px' }}>
                            <Space align="start">
                                <Title level={5}>{selectedEntity.label}</Title> {/* 从level 4改为level 5，减小标题大小 */}
                                {selectedEntity.tag_type && (
                                    <Tag color={selectedEntity.color}>{selectedEntity.tag_type}</Tag>
                                )}
                            </Space>

                            <Paragraph ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}>{selectedEntity.description}</Paragraph> {/* 添加ellipsis让描述可折叠 */}

                            {selectedEntity.related_content && (
                                <Button
                                    type="primary"
                                    size="small" // 减小按钮大小
                                    icon={<FileTextOutlined />}
                                    onClick={() => {
                                        setContentText(selectedEntity.related_content);
                                        setContentDrawerVisible(true);
                                    }}
                                >
                                    查看文档
                                </Button>
                            )}
                        </div>
                    )}
                </div>
            </Card>

            <Drawer
                title={selectedEntity ? `${selectedEntity.label}的详细信息` : "详细信息"}
                placement="right"
                onClose={() => setContentDrawerVisible(false)}
                open={contentDrawerVisible}
                width={500}
            >
                <div style={{ whiteSpace: 'pre-wrap' }}>
                    {contentText || "没有可显示的内容"}
                </div>

                {selectedEntity && selectedEntity.type === 'TAG' && (
                    <div style={{ marginTop: 16 }}>
                        <Button type="primary" onClick={() => {
                            // 这里可以添加查询标签相关文档的API调用
                            console.log("查询相关文档:", selectedEntity.id);
                            // 示例：fetchTagDocuments(selectedEntity.id);
                        }}>
                            查看相关文档
                        </Button>
                    </div>
                )}
            </Drawer>
        </div>
    );
};

export default GraphVisualizerPage; 