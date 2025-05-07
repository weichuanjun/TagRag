from typing import List, Dict, Any, Optional
import logging
import networkx as nx  
import os
import json
import time

# 导入配置
from config import VECTOR_DB_DIR

logger = logging.getLogger(__name__)

class GraphStore:
    """图存储管理类，处理实体关系图的构建和查询"""
    
    def __init__(self, repository_id: Optional[int] = None, knowledge_base_id: Optional[int] = None):
        """初始化图存储
        
        Args:
            repository_id: 代码库ID
            knowledge_base_id: 知识库ID
        """
        # 确定存储标识
        self.repository_id = repository_id
        self.knowledge_base_id = knowledge_base_id
        
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
        """加载图数据"""
        # 加载实体
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
        
        # 加载关系
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
    
    async def get_visualization_data(self):
        """获取可视化数据
        
        Returns:
            nodes, links: 节点和边列表，用于可视化
        """
        try:
            # 限制节点数量，避免过大图形影响性能
            MAX_NODES = 200
            
            # 如果图太大，选择重要节点
            if len(self.graph.nodes) > MAX_NODES:
                # 使用度中心性选择重要节点
                centrality = nx.degree_centrality(self.graph)
                important_nodes = sorted(centrality.keys(), key=lambda x: centrality[x], reverse=True)[:MAX_NODES]
                subgraph = self.graph.subgraph(important_nodes)
            else:
                subgraph = self.graph
            
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
            logger.error(f"获取可视化数据时出错: {str(e)}")
            raise e 