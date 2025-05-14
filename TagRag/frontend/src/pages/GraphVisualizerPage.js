import React, { useState, useEffect, useRef } from 'react';
import { Card, Select, Button, Spin, Space, Tooltip, Input, Tag, Empty, Switch, Divider, Typography, Checkbox, Drawer, Radio, Slider, Table, List, Modal, Row, Col } from 'antd';
import { SearchOutlined, ExpandOutlined, CompressOutlined, InfoCircleOutlined, TagsOutlined, FileTextOutlined, ForceOutlined, ZoomInOutlined, ZoomOutOutlined, ReloadOutlined, EyeOutlined, SettingOutlined } from '@ant-design/icons';
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

    // 新增状态用于显示标签相关文档
    const [relatedDocuments, setRelatedDocuments] = useState([]);
    const [loadingDocuments, setLoadingDocuments] = useState(false);
    // 新增状态用于处理选中文档的分块信息
    const [selectedDocForChunks, setSelectedDocForChunks] = useState(null);
    const [selectedDocChunks, setSelectedDocChunks] = useState([]);
    const [chunksLoading, setChunksLoading] = useState(false);
    const [isChunkModalVisible, setIsChunkModalVisible] = useState(false);

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

    // 当选择新的实体时，如果是TAG类型，获取相关文档
    useEffect(() => {
        if (selectedEntity && selectedEntity.type === 'TAG') {
            fetchTagRelatedDocuments(selectedEntity.id);
        } else {
            setRelatedDocuments([]);
        }
    }, [selectedEntity]);

    // 全局错误处理
    useEffect(() => {
        const handleError = (event) => {
            console.error('全局错误捕获:', event.error);
            // 可以在此添加错误通知或降级策略
        };

        window.addEventListener('error', handleError);

        return () => {
            window.removeEventListener('error', handleError);
        };
    }, []);

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
        // 立即清除当前图数据，确保视觉上看到切换效果
        setGraphData({ nodes: [], links: [] });

        try {
            console.log(`正在获取知识库ID ${knowledgeBaseId} 的图数据，视图模式: ${viewMode}`);

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
                // 将标签类型参数添加到请求中
                if (params.tag_types) {
                    endpoint += `?tag_types=${params.tag_types}`;
                }
            } else {
                // 原有的文档-标签关系视图
                endpoint = onlyShowTags
                    ? `/graph/tag-data/${knowledgeBaseId}`
                    : `/graph/data/${knowledgeBaseId}`;
            }

            console.log(`请求端点: ${endpoint}，参数:`, params);
            const response = await axios.get(endpoint, { params });

            // 数据验证和预处理
            let data = response.data;

            // 检查节点和链接数组是否存在
            if (!data.nodes) data.nodes = [];
            if (!data.links) data.links = [];

            console.log(`获取到 ${data.nodes.length} 个节点和 ${data.links.length} 个链接`);

            // 打印一下看看是否有root标签
            const rootNodes = data.nodes.filter(n => n.hierarchy_level === 'root');
            console.log(`找到 ${rootNodes.length} 个根标签:`, rootNodes);

            // 创建节点ID集合，用于快速查找
            const nodeIds = new Set(data.nodes.map(node => node.id));

            // 过滤掉引用不存在节点的链接
            let validLinks = data.links.filter(link => {
                const sourceExists = nodeIds.has(typeof link.source === 'object' ? link.source.id : link.source);
                const targetExists = nodeIds.has(typeof link.target === 'object' ? link.target.id : link.target);

                if (!sourceExists || !targetExists) {
                    console.warn(`过滤无效链接: source=${typeof link.source === 'object' ? link.source.id : link.source}, target=${typeof link.target === 'object' ? link.target.id : link.target}`);
                    return false;
                }
                return true;
            });

            if (validLinks.length !== data.links.length) {
                console.warn(`过滤了 ${data.links.length - validLinks.length} 个无效链接`);
            }

            // 更新数据
            data.links = validLinks;

            // 当节点数量为0时，显示警告
            if (data.nodes.length === 0) {
                console.warn(`知识库 ${knowledgeBaseId} 没有标签数据`);
            }

            // 用更可靠的方法检测和标记root标签
            if (viewMode === 'tag_hierarchy' && data.nodes.length > 0) {
                // 构建入度映射，记录每个节点被指向的次数
                const inDegreeMap = {};
                data.nodes.forEach(node => {
                    if (node.type === 'TAG') {
                        inDegreeMap[node.id] = 0; // 初始化入度为0
                    }
                });

                // 计算每个节点的入度
                data.links.forEach(link => {
                    const targetId = typeof link.target === 'object' ? link.target.id : link.target;
                    if (inDegreeMap[targetId] !== undefined) {
                        inDegreeMap[targetId]++;
                    }
                });

                // 根据入度标记节点层级
                const rootTagIds = [];
                data.nodes.forEach(node => {
                    if (node.type === 'TAG') {
                        if (inDegreeMap[node.id] === 0) {
                            // 入度为0的是根节点
                            node.hierarchy_level = 'root';
                            node.color = '#FF6A00'; // 橙色
                            rootTagIds.push(node.id);
                        } else {
                            // 检查是否有子节点
                            const hasChildren = data.links.some(link => {
                                const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
                                return sourceId === node.id;
                            });

                            if (hasChildren) {
                                node.hierarchy_level = 'branch';
                                node.color = '#1890FF'; // 蓝色
                            } else {
                                node.hierarchy_level = 'leaf';
                                node.color = '#722ED1'; // 紫色
                            }
                        }
                    }
                });

                console.log(`识别出的根标签IDs:`, rootTagIds);

                // 如果没有找到根标签，强制指定一个
                if (rootTagIds.length === 0) {
                    // 创建一个虚拟根节点
                    const rootNode = {
                        id: 'virtual-root',
                        label: '根标签',
                        type: 'TAG',
                        hierarchy_level: 'root',
                        color: '#FF6A00',
                        size: 15
                    };
                    data.nodes.push(rootNode);

                    // 找出所有入度为0的标签，连接到虚拟根节点
                    const orphanTags = data.nodes.filter(node =>
                        node.type === 'TAG' && inDegreeMap[node.id] === 0 && node.id !== 'virtual-root'
                    );

                    orphanTags.forEach(tag => {
                        data.links.push({
                            source: 'virtual-root',
                            target: tag.id,
                            type: 'PARENT_OF'
                        });
                    });

                    console.log(`创建了虚拟根节点并连接到 ${orphanTags.length} 个孤立标签`);
                }
            }

            setGraphData(data);
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

    // 新增：获取标签相关的文档
    const fetchTagRelatedDocuments = async (tagId) => {
        setLoadingDocuments(true);
        try {
            const response = await axios.get(`/tags/${tagId}/documents`);
            setRelatedDocuments(response.data || []);
        } catch (error) {
            console.error('获取标签关联文档失败:', error);
            setRelatedDocuments([]);
        } finally {
            setLoadingDocuments(false);
        }
    };

    // 新增：获取文档分块信息
    const fetchChunksForSelectedDoc = async (documentId) => {
        if (!documentId) return;
        setChunksLoading(true);
        setSelectedDocChunks([]);
        try {
            const response = await axios.get(`/documents/${documentId}/chunks`);
            setSelectedDocChunks(response.data || []);
        } catch (error) {
            console.error(`获取文档 ${documentId} 的块信息失败:`, error);
        } finally {
            setChunksLoading(false);
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

        // 高亮显示相关连接并居中显示
        if (graphRef.current) {
            graphRef.current.centerAt(node.x, node.y, 800);
            graphRef.current.zoom(1.8, 800); // 增加缩放比例以便查看详情
        }

        // 添加日志以便调试
        console.log("点击节点:", node);
    };

    // 新增：处理查看文档分块
    const handleViewChunks = (document) => {
        setSelectedDocForChunks(document);
        setIsChunkModalVisible(true);
        fetchChunksForSelectedDoc(document.id);
    };

    const handleCancelChunkModal = () => {
        setIsChunkModalVisible(false);
        setSelectedDocForChunks(null);
        setSelectedDocChunks([]);
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

        try {
            // 计算标签节点的平均坐标
            let validNodes = 0;
            let sumX = 0, sumY = 0;

            for (const node of tagNodes) {
                if (node.x !== undefined && node.y !== undefined &&
                    !isNaN(node.x) && !isNaN(node.y)) {
                    sumX += node.x;
                    sumY += node.y;
                    validNodes++;
                }
            }

            // 确保至少有一个有效节点
            if (validNodes === 0) {
                console.warn('没有找到有效的标签节点坐标');
                return;
            }

            const avgX = sumX / validNodes;
            const avgY = sumY / validNodes;

            // 确保坐标是有效数字
            if (isNaN(avgX) || isNaN(avgY)) {
                console.warn('计算的平均坐标无效');
                return;
            }

            // 居中并以适当比例显示
            graphRef.current.centerAt(avgX, avgY, 800);
            graphRef.current.zoom(1.2, 800);
        } catch (error) {
            console.error('居中标签节点时出错:', error);
        }
    };

    // 重新布局图表
    const resetLayout = () => {
        if (!graphRef.current) return;

        console.log('重置图表布局');

        // 设置强制模拟参数
        if (graphRef.current.d3Force) {
            // 设置节点之间的距离
            graphRef.current.d3Force('link').distance(link => {
                // 父子关系的链接距离保持较大
                if (link.type === 'PARENT_OF') {
                    return viewMode === 'tag_hierarchy' ? 60 : 50;
                }
                // 其他类型的链接距离较小，促进聚集
                return viewMode === 'tag_hierarchy' ? 40 : 30;
            });

            // 设置节点间的排斥力
            const forceStrength = viewMode === 'tag_hierarchy' ? -200 : -100;
            graphRef.current.d3Force('charge').strength(forceStrength);

            // 添加聚类力 - 使相同类型的节点靠近
            graphRef.current.d3Force('collide', d3.forceCollide()
                .radius(viewMode === 'tag_hierarchy' ? 8 : 10) // 碰撞半径
                .strength(0.7) // 碰撞强度
            );

            // 添加X、Y向心力，使整个图表向中心聚集
            graphRef.current.d3Force('x', d3.forceX().strength(0.05));
            graphRef.current.d3Force('y', d3.forceY().strength(0.05));

            // 重启模拟
            graphRef.current.d3ReheatSimulation();
        }

        // 稍后居中到标签节点并适应屏幕
        setTimeout(() => {
            if (graphRef.current) {
                centerOnTags();
                graphRef.current.zoomToFit(500, 50);
            }
        }, 800);
    };

    // 获取节点样式
    const getNodeCanvasObject = (node, ctx, globalScale) => {
        const label = node.label || '';
        const fontSize = Math.max(5, node.size ? node.size / 7 : 5); // 减小字体大小

        // 检查坐标是否为有效数值
        const isValidCoordinate = (coord) => typeof coord === 'number' && isFinite(coord) && !isNaN(coord);
        const validX = isValidCoordinate(node.x) ? node.x : 0;
        const validY = isValidCoordinate(node.y) ? node.y : 0;

        // 根据层级和视图模式调整节点大小
        let nodeR;
        if (viewMode === 'tag_hierarchy') {
            // 标签层级视图使用更小的节点，接近文档标签的感觉
            if (node.hierarchy_level === 'root') {
                nodeR = 4; // 根节点
            } else if (node.hierarchy_level === 'branch') {
                nodeR = 3; // 分支节点
            } else {
                nodeR = 3; // 叶节点
            }
        } else {
            // 文档标签视图保持原有大小设置
            if (node.hierarchy_level === 'root') {
                nodeR = 3; // 根节点
            } else if (node.hierarchy_level === 'branch') {
                nodeR = 3; // 分支节点
            } else {
                nodeR = 3; // 叶节点
            }
        }

        // 开始绘制
        ctx.beginPath();

        // 使用扁平化的颜色设计
        if (node.hierarchy_level === 'root') {
            ctx.fillStyle = node.color || '#FF6A00'; // 橙色根节点
        } else if (node.hierarchy_level === 'branch') {
            ctx.fillStyle = node.color || '#1890FF'; // 蓝色分支节点
        } else if (node.type === 'CONTENT') {
            ctx.fillStyle = node.color || '#52C41A'; // 绿色内容节点
        } else {
            ctx.fillStyle = node.color || '#722ED1'; // 紫色叶节点
        }

        // 根据不同层级使用不同形状
        if (node.hierarchy_level === 'root') {
            // 根节点使用菱形
            drawDiamond(ctx, validX, validY, nodeR * 1.2);
        } else if (node.hierarchy_level === 'branch') {
            // 分支节点使用方形
            drawSquare(ctx, validX, validY, nodeR * 0.9);
        } else if (node.type === 'CONTENT') {
            // 内容节点使用文档形状
            drawDocument(ctx, validX, validY, nodeR);
        } else {
            // 叶节点使用圆形
            ctx.arc(validX, validY, nodeR, 0, 2 * Math.PI);
        }

        ctx.fill();

        // 添加边框效果
        ctx.beginPath();
        if (selectedEntity && selectedEntity.id === node.id) {
            // 选中节点有更明显的边框
            ctx.strokeStyle = '#ff6600';
            ctx.lineWidth = 2.5;

            if (node.hierarchy_level === 'root') {
                drawDiamond(ctx, validX, validY, nodeR * 1.2 + 2);
            } else if (node.hierarchy_level === 'branch') {
                drawSquare(ctx, validX, validY, nodeR * 0.9 + 2);
            } else if (node.type === 'CONTENT') {
                drawDocument(ctx, validX, validY, nodeR + 2);
            } else {
                ctx.arc(validX, validY, nodeR + 2, 0, 2 * Math.PI);
            }
        } else {
            // 非选中节点有细微的边框
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 1;

            if (node.hierarchy_level === 'root') {
                drawDiamond(ctx, validX, validY, nodeR * 1.2);
            } else if (node.hierarchy_level === 'branch') {
                drawSquare(ctx, validX, validY, nodeR * 0.9);
            } else if (node.type === 'CONTENT') {
                drawDocument(ctx, validX, validY, nodeR);
            } else {
                ctx.arc(validX, validY, nodeR, 0, 2 * Math.PI);
            }
        }
        ctx.stroke();

        // 只在缩放比例足够大时显示标签，或者节点被选中时，或者全局showLabels开启
        const showLabel = showLabels || globalScale > 1.5 || (selectedEntity && selectedEntity.id === node.id);
        if (showLabel) {
            try {
                // 绘制标签文本
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

                // 半透明背景
                ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
                ctx.fillRect(validX - textWidth / 2 - 4, validY + nodeR + 2, textWidth + 8, fontSize + 6);

                // 白色文字
                ctx.fillStyle = '#fff';
                ctx.fillText(displayLabel, validX, validY + nodeR + fontSize / 2 + 5);

                // 如果是根节点，添加"ROOT"标识
                if (node.hierarchy_level === 'root') {
                    ctx.fillStyle = '#FF6A00';
                    ctx.font = `bold ${fontSize - 2}px Sans-Serif`;
                    ctx.fillText('ROOT', validX, validY - nodeR - 6);
                }
            } catch (error) {
                console.warn('绘制标签失败:', error);
            }
        }
    };

    // 辅助函数：绘制菱形
    const drawDiamond = (ctx, x, y, r) => {
        ctx.beginPath();
        ctx.moveTo(x, y - r); // 上点
        ctx.lineTo(x + r, y); // 右点
        ctx.lineTo(x, y + r); // 下点
        ctx.lineTo(x - r, y); // 左点
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

        ctx.beginPath();
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

    // 文档列表列定义
    const documentColumns = [
        {
            title: 'ID',
            dataIndex: 'id',
            key: 'id',
            width: 60,
        },
        {
            title: '文件名',
            dataIndex: 'source',
            key: 'source',
            width: 240,
            ellipsis: false,
            render: (text) => (
                <div style={{
                    fontSize: '12px',
                    lineHeight: '1.4',
                    wordBreak: 'break-all',
                    wordWrap: 'break-word'
                }}>
                    {text}
                </div>
            )
        },
        {
            title: '操作',
            key: 'actions',
            width: 80,
            align: 'center',
            render: (_, record) => (
                <Button
                    type="text"
                    icon={<EyeOutlined />}
                    onClick={() => handleViewChunks(record)}
                />
            ),
        },
    ];

    return (
        <div className="graph-page" style={{ height: fullscreen ? '100vh' : 'auto' }}>
            <Card
                title={
                    <Space>
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
                <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap' }}>
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
                    </Space>

                    {/* 节点布局调整控件 - 移到顶部工具栏右侧 */}
                    <Space align="center">
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

                        <Tooltip title="节点布局调整">
                            <Space>
                                <Text style={{ fontSize: '12px' }}>间距:</Text>
                                <Slider
                                    min={30}
                                    max={200}
                                    value={linkDistance}
                                    onChange={(value) => setLinkDistance(value)}
                                    onAfterChange={resetLayout}
                                    style={{ width: 80 }}
                                />
                                <Text style={{ fontSize: '12px' }}>排斥力:</Text>
                                <Slider
                                    min={-200}
                                    max={-30}
                                    value={chargeStrength}
                                    onChange={(value) => setChargeStrength(value)}
                                    onAfterChange={resetLayout}
                                    style={{ width: 80 }}
                                />
                            </Space>
                        </Tooltip>

                        <Tooltip title={viewMode === 'tag_hierarchy' ?
                            "图中节点表示标签层级结构和关系" :
                            "图中节点表示文档标签和内容，连线表示它们之间的关系"}>
                            <InfoCircleOutlined style={{ color: '#1890ff' }} />
                        </Tooltip>
                    </Space>
                </div>

                <div style={{
                    height: fullscreen ? 'calc(100vh - 180px)' : '45vh', // 减小图表高度以为底部腾出空间
                    position: 'relative',
                    border: '1px solid #f0f0f0',
                    borderRadius: '4px',
                    overflow: 'hidden',
                    marginBottom: '16px' // 与底部区域保持一致的间距
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
                                    return link.width || 2;
                                }
                                return link.width || 1;
                            }}
                            linkColor={link => {
                                try {
                                    if (selectedEntity && (
                                        (link.source.id === selectedEntity.id || link.target.id === selectedEntity.id) ||
                                        (typeof link.source === 'string' && link.source === selectedEntity.id) ||
                                        (typeof link.target === 'string' && link.target === selectedEntity.id)
                                    )) {
                                        return '#ff6600'; // 高亮选中节点的连接
                                    }

                                    // 根据连接类型设置不同颜色
                                    if (link.type === 'PARENT_OF') {
                                        return 'rgba(24, 144, 255, 0.7)'; // 父子关系使用蓝色
                                    }
                                } catch (error) {
                                    console.warn('链接处理错误:', error);
                                }
                                return link.color || 'rgba(150, 150, 150, 0.5)';
                            }}
                            nodeCanvasObjectMode={() => 'replace'}
                            onNodeClick={handleNodeClick}
                            cooldownTicks={100}
                            nodeCanvasObject={getNodeCanvasObject}
                            linkLineDash={link => link.dashed ? [4, 2] : undefined}
                            linkDirectionalArrowLength={link => link.type === 'PARENT_OF' ? 5 : (link.arrow ? 4 : 0)}
                            linkDirectionalArrowRelPos={0.9}
                            linkCurvature={link => link.type === 'PARENT_OF' ? 0 : 0.2} // 父子链接为直线
                            linkDirectionalParticles={link => link.type === 'PARENT_OF' ? 2 : 0} // 为父子关系添加粒子效果
                            linkDirectionalParticleWidth={2} // 粒子大小
                            linkDirectionalParticleSpeed={0.005} // 粒子速度
                            linkDirectionalParticleColor={() => '#1890ff'} // 粒子颜色
                            d3Force={(name, force) => {
                                // 添加自定义力
                                if (name === 'charge') {
                                    // 调整排斥力 - 标签层级关系和文档标签关系分别配置
                                    const forceValue = viewMode === 'tag_hierarchy' ? -200 : -100;
                                    force.strength(forceValue).distanceMax(200);
                                }

                                if (name === 'link') {
                                    // 调整链接强度和距离
                                    if (viewMode === 'tag_hierarchy') {
                                        // 标签层级视图使用较大的距离，但较低的强度
                                        force.distance(80).strength(0.3);
                                    } else {
                                        // 文档标签视图使用较小的距离，但较高的强度
                                        force.distance(40).strength(0.8);
                                    }
                                }

                                // 为根节点添加额外的中心力
                                if (viewMode === 'tag_hierarchy' && graphData.nodes) {
                                    // 找到所有根节点
                                    const rootNodes = graphData.nodes.filter(n => n.hierarchy_level === 'root');
                                    if (rootNodes.length > 0) {
                                        // 如果有根节点，添加中心力
                                        if (name === 'center' && force) {
                                            force.strength(node => node.hierarchy_level === 'root' ? 1 : 0.1);
                                        }
                                    }
                                }
                            }}
                            linkStrength={link => {
                                // 父子关系的链接强度较低，允许更多的弹性
                                if (link.type === 'PARENT_OF') {
                                    return viewMode === 'tag_hierarchy' ? 0.4 : 0.7;
                                }
                                // 其他类型的链接强度较高，确保紧密连接
                                return link.value || 0.8;
                            }}
                            d3ForceDistance={viewMode === 'tag_hierarchy' ? 80 : 40}
                            warmupTicks={100}
                            onEngineStop={() => {
                                // 在图表停止移动后居中到标签
                                setTimeout(centerOnTags, 300);
                                // 适应视图
                                if (graphRef.current) {
                                    graphRef.current.zoomToFit(400, 40);
                                }
                            }}
                            dagMode={viewMode === 'tag_hierarchy' ? 'radialout' : null} // 放射状布局仅用于标签层级
                            dagLevelDistance={50} // 调整层级间距
                            dagNodeFilter={node => node.type === 'TAG'} // 只有TAG类型节点参与DAG布局
                        />
                    ) : (
                        <Empty description="暂无图数据或该知识库尚未构建知识图谱" />
                    )}
                </div>

                {/* 重新设计的下部区域：左侧显示节点信息，右侧显示相关文档 */}
                <div style={{ marginTop: '0', display: 'flex', gap: '16px', marginBottom: '16px' }}>
                    {/* 左侧：节点信息 */}
                    <div style={{ flex: '1', minWidth: '25%', maxWidth: '25%' }}>
                        {selectedEntity ? (
                            <div style={{ padding: 12, background: '#f9f9f9', borderRadius: 4 }}>
                                <Space align="start">
                                    <Title level={5}>{selectedEntity.label}</Title>
                                    {selectedEntity.tag_type && (
                                        <Tag color={selectedEntity.color}>{selectedEntity.tag_type}</Tag>
                                    )}
                                </Space>
                                <Paragraph ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}>
                                    {selectedEntity.description || '无描述'}
                                </Paragraph>
                            </div>
                        ) : (
                            <Empty description="点击节点查看详情" style={{ marginBottom: '16px' }} />
                        )}
                    </div>

                    {/* 右侧：相关文档列表 */}
                    <div style={{ flex: '2', minWidth: '50%' }}>
                        <Card
                            size="small"
                            title={
                                <Space>
                                    <FileTextOutlined />
                                    {selectedEntity?.type === 'TAG'
                                        ? `标签「${selectedEntity.label}」相关文档`
                                        : "相关文档"}
                                </Space>
                            }
                            bodyStyle={{ padding: '8px', maxHeight: '250px', overflowY: 'auto' }}
                            style={{ height: '100%' }}
                        >
                            {selectedEntity?.type === 'TAG' ? (
                                loadingDocuments ? (
                                    <div style={{ textAlign: 'center', padding: '20px' }}><Spin tip="加载文档..." /></div>
                                ) : relatedDocuments.length > 0 ? (
                                    <Table
                                        columns={documentColumns}
                                        dataSource={relatedDocuments}
                                        rowKey="id"
                                        size="small"
                                        pagination={{ pageSize: 5, size: 'small' }}
                                    />
                                ) : (
                                    <Empty description="暂无相关文档" />
                                )
                            ) : (
                                <Empty description="请选择一个标签节点查看相关文档" />
                            )}
                        </Card>
                    </div>
                </div>

                {/* 分块信息模态框 */}
                <Modal
                    title={`文档分块详情: ${selectedDocForChunks?.source || 'N/A'}`}
                    visible={isChunkModalVisible}
                    onCancel={handleCancelChunkModal}
                    footer={[<Button key="back" onClick={handleCancelChunkModal}>关闭</Button>]}
                    width="80%"
                    destroyOnClose
                    bodyStyle={{ padding: '12px' }}
                >
                    {chunksLoading ? (
                        <div style={{ textAlign: 'center', padding: '50px' }}><Spin tip="加载分块信息..." /></div>
                    ) : (
                        <List
                            itemLayout="vertical"
                            size="small"
                            dataSource={selectedDocChunks}
                            pagination={{ pageSize: 5, size: 'small' }}
                            renderItem={(chunk) => (
                                <List.Item key={chunk.chunk_index} style={{ background: '#f7f9fc', marginBottom: '8px', padding: '12px', borderRadius: '8px' }}>
                                    <List.Item.Meta
                                        title={<Text strong>块 {chunk.chunk_index}</Text>}
                                        description={
                                            <Row gutter={[8, 8]}>
                                                <Col span={24} md={12}>
                                                    <Space>
                                                        <Tag color="cyan">Token: {chunk.token_count || 'N/A'}</Tag>
                                                        <Tag color="purple">类型: {chunk.structural_type || 'N/A'}</Tag>
                                                    </Space>
                                                </Col>
                                            </Row>
                                        }
                                    />
                                    <Paragraph
                                        ellipsis={{ rows: 4, expandable: true, symbol: '展开' }}
                                        style={{
                                            maxHeight: '150px',
                                            overflowY: 'auto',
                                            background: '#fff',
                                            padding: '12px',
                                            border: '1px solid #eee',
                                            borderRadius: '6px',
                                            marginTop: '8px'
                                        }}
                                    >
                                        {chunk.content}
                                    </Paragraph>
                                </List.Item>
                            )}
                        />
                    )}
                </Modal>
            </Card>
        </div>
    );
};

export default GraphVisualizerPage; 