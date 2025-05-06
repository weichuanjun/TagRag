from typing import Dict, List, Any, Optional
import asyncio
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_
import numpy as np
from sentence_transformers import SentenceTransformer
import logging

from models import CodeRepository, CodeFile, CodeComponent, ComponentDependency, UserQuery

logger = logging.getLogger(__name__)

class CodeAnalysisService:
    """代码分析查询服务，用于查询代码结构和分析代码关系"""
    
    def __init__(self, db_session: Session, embedding_model: Optional[str] = None):
        """初始化代码分析服务
        
        Args:
            db_session: 数据库会话
            embedding_model: 嵌入模型名称（用于语义搜索）
        """
        self.db_session = db_session
        # 初始化语义搜索模型
        self.embedding_model = None
        try:
            if embedding_model:
                self.embedding_model = SentenceTransformer(embedding_model)
                logger.info(f"已加载嵌入模型: {embedding_model}")
            else:
                try:
                    self.embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
                    logger.info("已加载默认嵌入模型")
                except Exception as e:
                    # 备选模型
                    try:
                        logger.warning(f"加载默认模型失败，尝试备选模型: {str(e)}")
                        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
                        logger.info("已加载备选嵌入模型")
                    except Exception as e2:
                        logger.warning(f"加载备选模型也失败: {str(e2)}，将使用基于文本的搜索")
                        self.embedding_model = None
        except Exception as e:
            logger.warning(f"加载嵌入模型失败: {str(e)}，将使用基于文本的搜索")
            self.embedding_model = None
    
    async def get_repository_summary(self, repo_id: int) -> Dict[str, Any]:
        """获取代码库概要信息
        
        Args:
            repo_id: 仓库ID
            
        Returns:
            Dict: 仓库摘要信息
            
        Raises:
            ValueError: 如果找不到仓库
        """
        repo = self.db_session.query(CodeRepository).get(repo_id)
        if not repo:
            raise ValueError(f"找不到ID为{repo_id}的代码库")
            
        # 文件统计
        file_stats = self.db_session.query(
            func.count(CodeFile.id).label("count"),
            CodeFile.language
        ).filter(
            CodeFile.repository_id == repo_id
        ).group_by(
            CodeFile.language
        ).all()
        
        # 组件统计
        component_stats = self.db_session.query(
            func.count(CodeComponent.id).label("count"),
            CodeComponent.type
        ).filter(
            CodeComponent.repository_id == repo_id
        ).group_by(
            CodeComponent.type
        ).all()
        
        # 获取重要组件
        important_components = self.db_session.query(CodeComponent).filter(
            CodeComponent.repository_id == repo_id
        ).order_by(
            desc(CodeComponent.importance_score)
        ).limit(10).all()
        
        # 统计依赖信息
        dependency_count = self.db_session.query(func.count(ComponentDependency.id)).scalar() or 0
        
        return {
            "repository": {
                "id": repo.id,
                "name": repo.name,
                "path": repo.path,
                "last_analyzed": repo.last_analyzed.isoformat() if repo.last_analyzed else None
            },
            "statistics": {
                "total_files": sum(count for count, _ in file_stats),
                "total_components": sum(count for count, _ in component_stats),
                "total_dependencies": dependency_count
            },
            "file_stats": {
                lang: count for count, lang in file_stats if lang
            },
            "component_stats": {
                comp_type: count for count, comp_type in component_stats if comp_type
            },
            "important_components": [
                {
                    "id": comp.id,
                    "name": comp.name,
                    "type": comp.type,
                    "file": comp.file.file_path if comp.file else "未知",
                    "importance": comp.importance_score
                }
                for comp in important_components
            ]
        }
    
    async def search_components(self, 
                               repo_id: int, 
                               query: str, 
                               component_type: Optional[str] = None,
                               limit: int = 20) -> List[Dict[str, Any]]:
        """搜索代码组件
        
        Args:
            repo_id: 仓库ID
            query: 搜索查询字符串
            component_type: 可选的组件类型过滤
            limit: 结果数量限制
            
        Returns:
            List[Dict]: 搜索结果列表
        """
        logger.info(f"开始搜索: repo_id={repo_id}, query='{query}', component_type={component_type}")
        
        # 记录查询
        try:
            user_query = UserQuery(
                query_text=query,
                repository_id=repo_id
            )
            self.db_session.add(user_query)
            self.db_session.commit()
            logger.debug("已记录用户查询")
        except Exception as e:
            logger.warning(f"记录用户查询时出错（非关键错误）: {str(e)}")
            # 继续执行，不影响搜索功能
        
        # 基本过滤条件
        filter_conditions = [CodeComponent.repository_id == repo_id]
        if component_type:
            filter_conditions.append(CodeComponent.type == component_type)
        
        # 处理查询，使用子字符串分词提高匹配率
        search_terms = query.lower().split()
        
        # 使用更精确的文本匹配
        try:
            match_conditions = []
            for term in search_terms:
                if len(term) > 2:  # 忽略太短的词
                    match_conditions.append(or_(
                        CodeComponent.name.ilike(f"%{term}%"),
                        CodeComponent.code.ilike(f"%{term}%"),
                        CodeComponent.signature.ilike(f"%{term}%")
                    ))
            
            if match_conditions:
                # 组合匹配条件 (至少匹配一个词条)
                components = self.db_session.query(CodeComponent).filter(
                    *filter_conditions,
                    or_(*match_conditions)
                ).order_by(
                    desc(CodeComponent.importance_score)
                ).limit(limit).all()
            else:
                # 回退到简单匹配
                components = self.db_session.query(CodeComponent).filter(
                    *filter_conditions,
                    or_(
                        CodeComponent.name.ilike(f"%{query}%"),
                        CodeComponent.code.ilike(f"%{query}%")
                    )
                ).order_by(
                    desc(CodeComponent.importance_score)
                ).limit(limit).all()
                
            logger.info(f"文本搜索找到 {len(components)} 个结果")
                
        except Exception as e:
            logger.error(f"文本搜索出错: {str(e)}")
            # 如果文本搜索失败，返回空结果
            return []
        
        # 如果文本匹配结果不足，进行语义搜索
        if len(components) < limit and self.embedding_model:
            try:
                logger.info("开始语义搜索")
                # 获取所有组件
                all_components = self.db_session.query(CodeComponent).filter(
                    *filter_conditions
                ).all()
                
                # 不在已找到结果中的组件
                remaining = [c for c in all_components if c not in components]
                
                if remaining:
                    # 计算查询的嵌入向量
                    query_embedding = self.embedding_model.encode(query)
                    
                    # 为所有组件构建更丰富的文本表示
                    remaining_texts = []
                    for c in remaining:
                        # 增强组件表示，添加更多上下文
                        component_text = f"{c.name} {c.signature or ''}"
                        
                        # 添加代码摘要（只取前200个字符，避免过长）
                        if c.code:
                            code_sample = c.code[:200].replace('\n', ' ')
                            component_text += f" {code_sample}"
                            
                        # 添加组件类型
                        component_text += f" {c.type}"
                        
                        # 添加元数据信息
                        if c.component_metadata:
                            try:
                                for k, v in c.component_metadata.items():
                                    if isinstance(v, (str, int, float, bool)):
                                        component_text += f" {k}:{v}"
                            except Exception as e:
                                logger.warning(f"处理组件元数据时出错: {str(e)}")
                        
                        remaining_texts.append(component_text)
                    
                    # 为组件计算嵌入向量
                    embeddings = self.embedding_model.encode(remaining_texts)
                    
                    # 计算余弦相似度
                    similarities = np.dot(embeddings, query_embedding) / (
                        np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_embedding)
                    )
                    
                    # 按相似度排序
                    semantic_matches = sorted(
                        zip(remaining, similarities),
                        key=lambda x: x[1], 
                        reverse=True
                    )[:limit - len(components)]
                    
                    # 添加语义搜索结果
                    semantic_results = [comp for comp, sim in semantic_matches if sim > 0.3]  # 只添加相似度较高的结果
                    components.extend(semantic_results)
                    logger.info(f"语义搜索额外找到 {len(semantic_results)} 个结果")
            except Exception as e:
                logger.error(f"语义搜索出错: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                # 语义搜索失败也没关系，继续使用文本搜索的结果
        elif self.embedding_model is None:
            logger.info("跳过语义搜索，嵌入模型不可用")
        
        # 关联查询和组件
        try:
            for component in components:
                user_query.components.append(component)
            self.db_session.commit()
        except Exception as e:
            logger.warning(f"关联查询和组件时出错（非关键错误）: {str(e)}")
        
        # 格式化结果并添加代码预览
        results = []
        for comp in components:
            try:
                # 构建结果，包含代码预览
                code_preview = ""
                if comp.code:
                    # 提取代码前几行作为预览
                    code_lines = comp.code.split('\n')[:3]
                    code_preview = '\n'.join(code_lines)
                    if len(code_lines) < len(comp.code.split('\n')):
                        code_preview += "\n..."
                
                results.append({
                    "id": comp.id,
                    "name": comp.name,
                    "type": comp.type,
                    "file_path": comp.file.file_path if comp.file else "未知",
                    "start_line": comp.start_line,
                    "end_line": comp.end_line,
                    "signature": comp.signature,
                    "code_preview": code_preview,
                    "importance": comp.importance_score,
                    "llm_summary": comp.llm_summary
                })
            except Exception as e:
                logger.warning(f"格式化组件 {comp.id} 时出错: {str(e)}")
                # 跳过有问题的组件
        
        logger.info(f"搜索结束，返回 {len(results)} 个结果")
        return results
    
    async def get_component_details(self, component_id: int) -> Dict[str, Any]:
        """获取组件详细信息
        
        Args:
            component_id: 组件ID
            
        Returns:
            Dict: 组件详情
            
        Raises:
            ValueError: 如果找不到组件
        """
        component = self.db_session.query(CodeComponent).get(component_id)
        if not component:
            raise ValueError(f"找不到ID为{component_id}的组件")
            
        # 获取依赖和被依赖
        dependencies = (
            self.db_session.query(CodeComponent)
            .join(ComponentDependency, ComponentDependency.target_id == CodeComponent.id)
            .filter(ComponentDependency.source_id == component_id)
            .all()
        )
        
        dependents = (
            self.db_session.query(CodeComponent)
            .join(ComponentDependency, ComponentDependency.source_id == CodeComponent.id)
            .filter(ComponentDependency.target_id == component_id)
            .all()
        )
        
        return {
            "id": component.id,
            "name": component.name,
            "type": component.type,
            "file_path": component.file.file_path if component.file else "未知",
            "start_line": component.start_line,
            "end_line": component.end_line,
            "code": component.code,
            "signature": component.signature,
            "metadata": component.component_metadata,
            "importance": component.importance_score,
            "llm_summary": component.llm_summary,
            "dependencies": [
                {
                    "id": dep.id,
                    "name": dep.name,
                    "type": dep.type,
                    "file_path": dep.file.file_path if dep.file else "未知"
                }
                for dep in dependencies
            ],
            "dependents": [
                {
                    "id": dep.id, 
                    "name": dep.name,
                    "type": dep.type,
                    "file_path": dep.file.file_path if dep.file else "未知"
                }
                for dep in dependents
            ]
        }
    
    async def analyze_impact(self, component_id: int) -> Dict[str, Any]:
        """分析修改组件的影响范围
        
        Args:
            component_id: 组件ID
            
        Returns:
            Dict: 影响分析结果
            
        Raises:
            ValueError: 如果找不到组件
        """
        component = self.db_session.query(CodeComponent).get(component_id)
        if not component:
            raise ValueError(f"找不到ID为{component_id}的组件")
            
        # 递归获取所有依赖此组件的组件
        impacted_components = await self._get_all_dependents(component_id)
        
        # 按影响程度分类（直接/间接）
        direct_impact = []
        indirect_impact = []
        
        for impact_depth, comp_id in impacted_components:
            comp = self.db_session.query(CodeComponent).get(comp_id)
            if not comp:
                continue
                
            impact_info = {
                "id": comp.id,
                "name": comp.name,
                "type": comp.type,
                "file_path": comp.file.file_path if comp.file else "未知",
                "importance": comp.importance_score
            }
            
            if impact_depth == 1:  # 直接依赖
                direct_impact.append(impact_info)
            else:  # 间接依赖
                indirect_impact.append(impact_info)
                
        # 查找相关测试
        # 这里用简单规则：查找名称中包含"test"且直接/间接依赖的组件
        test_components = self.db_session.query(CodeComponent).filter(
            CodeComponent.repository_id == component.repository_id,
            or_(
                CodeComponent.name.ilike("%test%"),
                CodeComponent.file.has(CodeFile.file_path.ilike("%test%"))
            )
        ).all()
        
        affected_tests = []
        for test in test_components:
            # 查找测试是否引用了受影响的组件
            for imp_comp in direct_impact + indirect_impact:
                if test.code and imp_comp["name"] in test.code:
                    affected_tests.append({
                        "id": test.id,
                        "name": test.name,
                        "file_path": test.file.file_path if test.file else "未知"
                    })
                    break
        
        return {
            "component": {
                "id": component.id,
                "name": component.name,
                "type": component.type,
                "file_path": component.file.file_path if component.file else "未知"
            },
            "impact_summary": {
                "direct_impact_count": len(direct_impact),
                "indirect_impact_count": len(indirect_impact),
                "affected_tests_count": len(affected_tests)
            },
            "direct_impact": direct_impact,
            "indirect_impact": indirect_impact,
            "affected_tests": affected_tests
        }
    
    async def _get_all_dependents(self, component_id, depth=1, max_depth=5, visited=None):
        """递归获取所有依赖组件（带深度信息）
        
        Args:
            component_id: 组件ID
            depth: 当前深度
            max_depth: 最大深度
            visited: 已访问组件集合
            
        Returns:
            List[Tuple[int, int]]: 依赖深度和组件ID列表
        """
        if visited is None:
            visited = set()
            
        if component_id in visited or depth > max_depth:
            return []
            
        visited.add(component_id)
        
        # 获取直接依赖
        direct_deps = (
            self.db_session.query(ComponentDependency.source_id)
            .filter(ComponentDependency.target_id == component_id)
            .all()
        )
        
        results = [(depth, dep.source_id) for dep in direct_deps]
        
        # 递归获取间接依赖
        for dep in direct_deps:
            indirect_deps = await self._get_all_dependents(
                dep.source_id, 
                depth + 1, 
                max_depth, 
                visited
            )
            results.extend(indirect_deps)
            
        return results
    
    async def generate_llm_summary(self, component_id: int, llm_client) -> str:
        """使用大模型生成组件摘要（需用户同意）
        
        Args:
            component_id: 组件ID
            llm_client: 大模型客户端
            
        Returns:
            str: 生成的摘要
            
        Raises:
            ValueError: 如果找不到组件
        """
        component = self.db_session.query(CodeComponent).get(component_id)
        if not component:
            raise ValueError(f"找不到ID为{component_id}的组件")
            
        # 准备上下文
        context = f"""组件名称: {component.name}
类型: {component.type}
文件: {component.file.file_path if component.file else "未知"}
代码:
```
{component.code}
```
"""
        
        # 生成提示
        prompt = f"""请简明扼要地总结这段代码的功能和用途，包括：
1. 主要功能是什么
2. 关键参数和返回值
3. 与其他组件的交互方式
4. 可能的边界情况和注意事项

{context}
"""
        
        # 调用大模型
        try:
            summary = await llm_client.generate(prompt)
            
            # 更新数据库
            component.llm_summary = summary
            self.db_session.commit()
            
            return summary
        except Exception as e:
            logger.error(f"生成摘要时发生错误: {str(e)}")
            return f"生成摘要失败: {str(e)}"
    
    async def get_repository_structure(self, repo_id: int) -> Dict[str, Any]:
        """获取代码库的目录结构
        
        Args:
            repo_id: 仓库ID
            
        Returns:
            Dict: 目录结构树
        """
        repo = self.db_session.query(CodeRepository).get(repo_id)
        if not repo:
            raise ValueError(f"找不到ID为{repo_id}的代码库")
            
        # 获取所有文件
        files = self.db_session.query(CodeFile).filter(
            CodeFile.repository_id == repo_id
        ).all()
        
        # 构建目录树
        dir_tree = {"name": repo.name, "children": [], "type": "directory"}
        
        for file in files:
            path_parts = file.file_path.split('/')
            current = dir_tree
            
            # 遍历路径部分，构建树
            for i, part in enumerate(path_parts):
                if i == len(path_parts) - 1:  # 文件
                    current["children"].append({
                        "name": part,
                        "type": "file",
                        "language": file.language,
                        "id": file.id
                    })
                else:  # 目录
                    # 查找是否已存在此目录
                    dir_exists = False
                    for child in current["children"]:
                        if child["name"] == part and child["type"] == "directory":
                            current = child
                            dir_exists = True
                            break
                    
                    if not dir_exists:
                        new_dir = {"name": part, "children": [], "type": "directory"}
                        current["children"].append(new_dir)
                        current = new_dir
        
        return dir_tree
    
    async def get_all_fields(self, repo_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取代码库中的所有字段
        
        Args:
            repo_id: 可选的仓库ID，如果不提供则返回所有仓库的字段
            
        Returns:
            List[Dict]: 字段列表，包含字段名称、类型、所属组件等信息
        """
        logger.info(f"获取{'仓库 ' + str(repo_id) if repo_id else '所有'}代码字段")
        
        try:
            # 构建查询条件
            query = self.db_session.query(CodeComponent).filter(
                CodeComponent.type.in_(["field", "property", "variable", "attribute"])
            )
            
            # 如果指定了仓库ID，添加过滤条件
            if repo_id:
                query = query.filter(CodeComponent.repository_id == repo_id)
            
            # 执行查询
            components = query.all()
            
            # 格式化结果
            fields = []
            for component in components:
                field_info = {
                    "id": component.id,
                    "name": component.name,
                    "type": component.type,
                    "data_type": None,  # 数据类型，默认为None
                    "belongs_to": None,  # 所属类/组件
                    "file_path": None,  # 文件路径
                    "is_public": True,  # 默认为公开
                    "is_static": False,  # 默认为非静态
                    "description": None  # 描述
                }
                
                # 从元数据中提取更多信息
                if component.component_metadata:
                    try:
                        metadata = component.component_metadata
                        if isinstance(metadata, dict):
                            # 提取数据类型
                            field_info["data_type"] = metadata.get("data_type") or metadata.get("type")
                            
                            # 提取可见性信息
                            visibility = metadata.get("visibility", "").lower()
                            field_info["is_public"] = visibility != "private" and visibility != "protected"
                            
                            # 提取静态标志
                            field_info["is_static"] = metadata.get("is_static", False) or metadata.get("static", False)
                            
                            # 提取描述
                            field_info["description"] = metadata.get("description", "")
                    except Exception as e:
                        logger.warning(f"处理字段元数据时出错: {str(e)}")
                
                # 获取所属组件信息
                if component.parent_id:
                    parent = self.db_session.query(CodeComponent).get(component.parent_id)
                    if parent:
                        field_info["belongs_to"] = parent.name
                
                # 获取文件路径
                if component.file:
                    field_info["file_path"] = component.file.file_path
                
                fields.append(field_info)
            
            logger.info(f"找到 {len(fields)} 个字段")
            return fields
            
        except Exception as e:
            logger.error(f"获取字段列表时出错: {str(e)}")
            raise e
    
    async def get_field_impact(self, field_name: str, repo_id: Optional[int] = None) -> Dict[str, Any]:
        """获取字段影响分析
        
        Args:
            field_name: 字段名称
            repo_id: 可选的仓库ID
            
        Returns:
            Dict: 字段影响信息，包括使用该字段的组件列表
        """
        logger.info(f"分析字段 {field_name} 的影响")
        
        try:
            # 查找匹配的字段
            query = self.db_session.query(CodeComponent).filter(
                CodeComponent.name == field_name,
                CodeComponent.type.in_(["field", "property", "variable", "attribute"])
            )
            
            # 如果指定了仓库ID，添加过滤条件
            if repo_id:
                query = query.filter(CodeComponent.repository_id == repo_id)
            
            # 获取匹配的字段
            field = query.first()
            if not field:
                return {"error": f"未找到字段: {field_name}"}
            
            # 获取依赖关系
            dependent_components = self.db_session.query(
                CodeComponent
            ).join(
                ComponentDependency,
                CodeComponent.id == ComponentDependency.source_id
            ).filter(
                ComponentDependency.target_id == field.id
            ).all()
            
            # 格式化结果
            impact_info = {
                "field": {
                    "id": field.id,
                    "name": field.name,
                    "type": field.type,
                    "file_path": field.file.file_path if field.file else None
                },
                "used_by": [
                    {
                        "id": comp.id,
                        "name": comp.name,
                        "type": comp.type,
                        "file_path": comp.file.file_path if comp.file else None
                    }
                    for comp in dependent_components
                ],
                "usage_count": len(dependent_components)
            }
            
            logger.info(f"字段 {field_name} 被 {len(dependent_components)} 个组件使用")
            return impact_info
            
        except Exception as e:
            logger.error(f"分析字段影响时出错: {str(e)}")
            raise e 