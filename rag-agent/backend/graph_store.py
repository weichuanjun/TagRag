from typing import List, Dict, Any, Optional
import logging
import networkx as nx  
import os
import json
import time
from sqlalchemy.orm import Session

# 导入配置
from config import VECTOR_DB_DIR
from models import Tag, Document, DocumentChunk, get_db

logger = logging.getLogger(__name__)

class GraphStore:
    """图存储管理类，处理实体关系图的构建和查询"""
    
    def __init__(self, repository_id: Optional[int] = None, knowledge_base_id: Optional[int] = None, db: Optional[Session] = None):
        """初始化图存储
        
        Args:
            repository_id: 代码库ID
            knowledge_base_id: 知识库ID
            db: 数据库会话
        """
        # 确定存储标识
        self.repository_id = repository_id
        self.knowledge_base_id = knowledge_base_id
        self.db = db
        
        # 为每个知识库创建独立的图存储目录
        if knowledge_base_id:
            self.graph_directory = os.path.join(VECTOR_DB_DIR, f"graph_kb_{knowledge_base_id}")
        elif repository_id:
            self.graph_directory = os.path.join(VECTOR_DB_DIR, f"graph_repo_{repository_id}")
        else:
            self.graph_directory = os.path.join(VECTOR_DB_DIR, "graph_default")
            
        os.makedirs(self.graph_directory, exist_ok=True)
        logger.info(f"图存储目录: {self.graph_directory}")
        
        # 初始化图数据结构 (使用NetworkX作为简单实现)
        self.graph = nx.DiGraph()
        
        # 初始化图元数据存储
        self.metadata_path = os.path.join(self.graph_directory, "graph_metadata.json")
        self.entity_path = os.path.join(self.graph_directory, "entities.json")
        self.relation_path = os.path.join(self.graph_directory, "relations.json")
        
        # 加载已有图数据
        self._load_graph()
    
    def _load_graph(self):
        """加载图数据，包括从文件加载和从数据库标签加载"""
        # 从文件加载实体
        if os.path.exists(self.entity_path):
            try:
                with open(self.entity_path, 'r', encoding='utf-8') as f:
                    entities = json.load(f)
                    for entity in entities:
                        self.graph.add_node(
                            entity["id"],
                            **{k: v for k, v in entity.items() if k != "id"}
                        )
                logger.info(f"已加载 {len(entities)} 个实体")
            except Exception as e:
                logger.error(f"加载实体数据失败: {str(e)}")
        
        # 从文件加载关系
        if os.path.exists(self.relation_path):
            try:
                with open(self.relation_path, 'r', encoding='utf-8') as f:
                    relations = json.load(f)
                    for relation in relations:
                        self.graph.add_edge(
                            relation["source"],
                            relation["target"],
                            **{k: v for k, v in relation.items() if k not in ["source", "target"]}
                        )
                logger.info(f"已加载 {len(relations)} 个关系")
            except Exception as e:
                logger.error(f"加载关系数据失败: {str(e)}")
        
        # 从数据库加载标签和文档
        self._load_tags_as_graph()
    
    def _load_tags_as_graph(self):
        """从数据库中加载标签作为图节点"""
        if not self.db:
            # 创建新的数据库会话
            for db in get_db():
                self.db = db
                break
        
        if not self.db:
            logger.error("无法创建数据库会话，跳过从标签加载图数据")
            return
        
        try:
            # 加载标签
            query = self.db.query(Tag)
            
            # 如果指定了知识库，加载该知识库下的标签
            if self.knowledge_base_id:
                # 通过文档过滤标签
                tags = []
                doc_query = self.db.query(Document).filter(Document.knowledge_base_id == self.knowledge_base_id)
                for doc in doc_query:
                    for tag in doc.tags:
                        if tag not in tags:
                            tags.append(tag)
            else:
                # 否则加载所有标签
                tags = query.all()
            
            # 添加标签作为节点
            for tag in tags:
                # 标签ID格式为 tag_{id}
                tag_id = f"tag_{tag.id}"
                importance = tag.importance or 0.5
                tag_color = self._get_color_by_importance(importance)
                
                # 根据标签类型选择节点形状
                node_shape = self._get_shape_by_type(tag.tag_type)
                
                self.graph.add_node(
                    tag_id,
                    id=tag_id,
                    label=tag.name,
                    description=tag.description or "",
                    type="TAG",
                    tag_type=tag.tag_type,
                    importance=importance,
                    related_content=tag.related_content or "",
                    color=tag_color,
                    shape=node_shape
                )
            
            # 同一类型的标签之间建立关系
            type_groups = {}
            for tag in tags:
                tag_type = tag.tag_type or "general"
                if tag_type not in type_groups:
                    type_groups[tag_type] = []
                type_groups[tag_type].append(f"tag_{tag.id}")
            
            # 为每个类型组创建关系
            for tag_type, tag_ids in type_groups.items():
                if len(tag_ids) > 1:
                    # 对每对同类型标签创建关系
                    for i in range(len(tag_ids)):
                        for j in range(i+1, len(tag_ids)):
                            self.graph.add_edge(
                                tag_ids[i],
                                tag_ids[j],
                                type=f"SAME_TYPE_{tag_type}",
                                strength=0.5
                            )
            
            # 查找父子关系的标签，建立层级关系
            for tag in tags:
                if tag.parent_id:
                    self.graph.add_edge(
                        f"tag_{tag.parent_id}",
                        f"tag_{tag.id}",
                        type="PARENT_OF",
                        strength=0.8
                    )
            
            # 从文档内容创建原文节点，连接到相关标签
            for tag in tags:
                if tag.related_content and len(tag.related_content.strip()) > 0:
                    # 为原始内容创建节点
                    content_id = f"content_{tag.id}"
                    
                    # 截取内容以避免过长
                    content_text = tag.related_content
                    if len(content_text) > 200:
                        content_text = content_text[:197] + "..."
                    
                    self.graph.add_node(
                        content_id,
                        id=content_id,
                        label="原始内容",
                        description=content_text,
                        type="CONTENT",
                        color="#722ed1",
                        shape="document"
                    )
                    
                    # 连接标签到原始内容
                    self.graph.add_edge(
                        f"tag_{tag.id}",
                        content_id,
                        type="HAS_CONTENT",
                        strength=1.0
                    )
            
            logger.info(f"已从数据库加载 {len(tags)} 个标签到图")
        except Exception as e:
            logger.error(f"从数据库加载标签失败: {str(e)}")
    
    def _get_color_by_importance(self, importance):
        """根据重要性获取颜色"""
        if importance >= 0.8:
            return "#f5222d"  # 红色 - 非常重要
        elif importance >= 0.6:
            return "#fa8c16"  # 橙色 - 重要
        elif importance >= 0.4:
            return "#1890ff"  # 蓝色 - 一般重要
        else:
            return "#52c41a"  # 绿色 - 次要
    
    def _get_shape_by_type(self, tag_type):
        """根据标签类型获取节点形状"""
        type_shapes = {
            "API": "triangle",
            "字段": "square",
            "功能": "diamond",
            "技术": "star",
            "文档类型": "circle"
        }
        return type_shapes.get(tag_type, "circle")
    
    def _save_graph(self):
        """保存图数据"""
        # 保存实体
        try:
            entities = []
            for node_id, attrs in self.graph.nodes(data=True):
                entity = {"id": node_id, **attrs}
                entities.append(entity)
                
            with open(self.entity_path, 'w', encoding='utf-8') as f:
                json.dump(entities, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存实体数据失败: {str(e)}")
        
        # 保存关系
        try:
            relations = []
            for source, target, attrs in self.graph.edges(data=True):
                relation = {"source": source, "target": target, **attrs}
                relations.append(relation)
                
            with open(self.relation_path, 'w', encoding='utf-8') as f:
                json.dump(relations, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存关系数据失败: {str(e)}")
    
    async def add_entities(self, entities: List[Dict[str, Any]], document_id: Optional[int] = None):
        """添加实体到图
        
        Args:
            entities: 实体列表，每个实体包含id、label、type等属性
            document_id: 文档ID
        """
        try:
            for entity in entities:
                # 确保实体ID存在
                if "id" not in entity:
                    entity["id"] = f"entity_{len(self.graph.nodes) + 1}"
                
                # 添加文档ID和知识库ID
                if document_id:
                    entity["document_id"] = document_id
                if self.knowledge_base_id:
                    entity["knowledge_base_id"] = self.knowledge_base_id
                if self.repository_id:
                    entity["repository_id"] = self.repository_id
                
                # 添加或更新节点
                self.graph.add_node(entity["id"], **{k: v for k, v in entity.items() if k != "id"})
            
            logger.info(f"已添加 {len(entities)} 个实体到图")
            self._save_graph()
            return {"added_entities": len(entities)}
        except Exception as e:
            logger.error(f"添加实体时出错: {str(e)}")
            raise e
    
    async def add_relations(self, relations: List[Dict[str, Any]]):
        """添加关系到图
        
        Args:
            relations: 关系列表，每个关系包含source、target、type等属性
        """
        try:
            for relation in relations:
                if "source" not in relation or "target" not in relation:
                    continue
                
                # 添加知识库ID
                if self.knowledge_base_id:
                    relation["knowledge_base_id"] = self.knowledge_base_id
                if self.repository_id:
                    relation["repository_id"] = self.repository_id
                
                # 添加或更新边
                self.graph.add_edge(
                    relation["source"],
                    relation["target"],
                    **{k: v for k, v in relation.items() if k not in ["source", "target"]}
                )
            
            logger.info(f"已添加 {len(relations)} 个关系到图")
            self._save_graph()
            return {"added_relations": len(relations)}
        except Exception as e:
            logger.error(f"添加关系时出错: {str(e)}")
            raise e
    
    async def search_entities(self, query: str, max_depth: int = 2):
        """搜索实体并返回相关子图
        
        Args:
            query: 搜索查询
            max_depth: 最大搜索深度
            
        Returns:
            nodes, links: 节点和边列表，用于可视化
        """
        try:
            # 简单实现：匹配实体标签或描述
            matched_nodes = []
            for node_id, attrs in self.graph.nodes(data=True):
                label = attrs.get("label", "")
                description = attrs.get("description", "")
                if query.lower() in label.lower() or query.lower() in description.lower():
                    matched_nodes.append(node_id)
            
            # 获取连接到匹配节点的子图
            subgraph_nodes = set(matched_nodes)
            frontier = set(matched_nodes)
            
            # BFS扩展子图
            for _ in range(max_depth):
                new_frontier = set()
                for node in frontier:
                    # 获取所有邻居
                    neighbors = set(self.graph.predecessors(node)) | set(self.graph.successors(node))
                    new_nodes = neighbors - subgraph_nodes
                    subgraph_nodes.update(new_nodes)
                    new_frontier.update(new_nodes)
                
                frontier = new_frontier
                if not frontier:
                    break
            
            # 构建子图
            subgraph = self.graph.subgraph(subgraph_nodes)
            
            # 转换为可视化格式
            nodes = []
            for node_id, attrs in subgraph.nodes(data=True):
                nodes.append({
                    "id": node_id,
                    "label": attrs.get("label", str(node_id)),
                    "description": attrs.get("description", ""),
                    "type": attrs.get("type", "entity"),
                    "color": attrs.get("color", "#1890ff"),
                    "source": attrs.get("source", ""),
                    "tags": attrs.get("tags", [])
                })
            
            links = []
            for source, target, attrs in subgraph.edges(data=True):
                links.append({
                    "source": source,
                    "target": target,
                    "type": attrs.get("type", "related"),
                    "strength": attrs.get("strength", 1)
                })
            
            return nodes, links
        except Exception as e:
            logger.error(f"搜索实体时出错: {str(e)}")
            raise e
    
    async def get_visualization_data(self, tag_types=None, only_tags=False):
        """获取可视化数据
        
        Args:
            tag_types: 要筛选的标签类型列表，如果为None则显示所有
            only_tags: 是否只显示标签节点和内容节点
        
        Returns:
            nodes, links: 节点和边列表，用于可视化
        """
        try:
            # 创建新图而不是复制现有图，避免frozen graph错误
            filtered_nodes = []
            filtered_edges = []
            
            # 筛选节点
            for node_id, attrs in self.graph.nodes(data=True):
                # 如果是标签节点，检查类型
                if attrs.get("type") == "TAG":
                    # 如果指定了类型筛选，检查是否匹配
                    if tag_types and attrs.get("tag_type") not in tag_types:
                        continue
                    filtered_nodes.append((node_id, attrs))
                # 如果是内容节点，只有在显示原始内容时才包含
                elif attrs.get("type") == "CONTENT":
                    if not only_tags:
                        filtered_nodes.append((node_id, attrs))
                # 其他类型节点，只在不限制为标签节点时保留
                elif not only_tags:
                    filtered_nodes.append((node_id, attrs))
            
            # 筛选边
            for source, target, attrs in self.graph.edges(data=True):
                source_attrs = self.graph.nodes.get(source, {})
                target_attrs = self.graph.nodes.get(target, {})
                
                # 检查源节点和目标节点是否都在筛选后的节点列表中
                source_included = False
                target_included = False
                
                for node_id, _ in filtered_nodes:
                    if node_id == source:
                        source_included = True
                    if node_id == target:
                        target_included = True
                
                if source_included and target_included:
                    filtered_edges.append((source, target, attrs))
            
            # 限制节点数量，避免过大图形影响性能
            MAX_NODES = 100  # 减少节点数量以减少拥挤
            
            # 如果节点太多，优先选择标签节点和重要节点
            if len(filtered_nodes) > MAX_NODES:
                # 首先保留所有标签节点
                tag_nodes = [(node_id, attrs) for node_id, attrs in filtered_nodes if attrs.get("type") == "TAG"]
                
                # 如果标签节点已经超过最大数量，根据重要性筛选
                if len(tag_nodes) > MAX_NODES:
                    tag_nodes.sort(key=lambda x: x[1].get("importance", 0.5), reverse=True)
                    filtered_nodes = tag_nodes[:MAX_NODES]
                else:
                    # 计算剩余可用节点数
                    remaining_slots = MAX_NODES - len(tag_nodes)
                    
                    # 筛选非标签节点
                    non_tag_nodes = [(node_id, attrs) for node_id, attrs in filtered_nodes if attrs.get("type") != "TAG"]
                    
                    # 内容节点优先
                    content_nodes = [(node_id, attrs) for node_id, attrs in non_tag_nodes if attrs.get("type") == "CONTENT"]
                    other_nodes = [(node_id, attrs) for node_id, attrs in non_tag_nodes if attrs.get("type") != "CONTENT"]
                    
                    if len(content_nodes) > remaining_slots:
                        filtered_nodes = tag_nodes + content_nodes[:remaining_slots]
                    else:
                        filtered_nodes = tag_nodes + content_nodes + other_nodes[:remaining_slots - len(content_nodes)]
            
            # 再次筛选边，确保只包含选中的节点
            node_ids = [node_id for node_id, _ in filtered_nodes]
            filtered_edges = [(source, target, attrs) for source, target, attrs in filtered_edges 
                             if source in node_ids and target in node_ids]
            
            # 转换为可视化格式
            nodes = []
            for node_id, attrs in filtered_nodes:
                # 构建基本节点信息
                node_data = {
                    "id": node_id,
                    "label": attrs.get("label", str(node_id)),
                    "description": attrs.get("description", ""),
                    "type": attrs.get("type", "entity"),
                    "color": attrs.get("color", "#1890ff"),
                    "shape": attrs.get("shape", "circle"),
                    "size": 15  # 默认大小改小
                }
                
                # 为不同类型的节点设置不同的大小和样式
                if attrs.get("type") == "TAG":
                    # 根据重要性调整大小
                    importance = attrs.get("importance", 0.5)
                    node_data["size"] = 15 + importance * 10  # 重要性越高，节点越大，但整体缩小
                    
                    # 添加标签类型
                    node_data["tag_type"] = attrs.get("tag_type", "general")
                    
                    # 添加相关内容摘要
                    if attrs.get("related_content"):
                        content = attrs.get("related_content")
                        node_data["tooltip"] = content[:100] + "..." if len(content) > 100 else content
                        node_data["related_content"] = content
                
                elif attrs.get("type") == "CONTENT":
                    # 内容节点略小一些
                    node_data["size"] = 12
                    node_data["shape"] = "document"
                
                # 添加其他属性
                for key, value in attrs.items():
                    if key not in node_data and key != "id":
                        node_data[key] = value
                
                nodes.append(node_data)
            
            links = []
            for source, target, attrs in filtered_edges:
                # 构建基本连接信息
                link_data = {
                    "source": source,
                    "target": target,
                    "type": attrs.get("type", "related"),
                    "strength": attrs.get("strength", 1)
                }
                
                # 根据关系类型设置不同样式
                if "SAME_TYPE" in attrs.get("type", ""):
                    link_data["dashed"] = True
                    link_data["width"] = 1
                elif attrs.get("type") == "PARENT_OF":
                    link_data["width"] = 2
                    link_data["arrow"] = True
                elif attrs.get("type") == "HAS_CONTENT":
                    link_data["color"] = "#722ed1"
                    link_data["width"] = 2
                
                # 添加其他属性
                for key, value in attrs.items():
                    if key not in link_data and key not in ["source", "target"]:
                        link_data[key] = value
                
                links.append(link_data)
            
            return nodes, links
        except Exception as e:
            logger.error(f"获取可视化数据时出错: {str(e)}")
            raise e 