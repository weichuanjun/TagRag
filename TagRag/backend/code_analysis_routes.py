import os
import logging
from typing import List, Dict, Any, Optional
import tempfile
import shutil
from datetime import datetime
import json

from fastapi import APIRouter, HTTPException, Depends, Query, Path, UploadFile, File, Body, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from models import get_db, CodeRepository, CodeFile, CodeComponent, ComponentDependency, KnowledgeBase
from code_analyzer import CodeAnalyzer
from enhanced_code_analyzer import EnhancedCodeAnalyzer
from analysis_service import CodeAnalysisService
from vector_store import VectorStore

# 导入向量化函数
from utils.vectorize_repo import vectorize_repository

router = APIRouter(prefix="/code", tags=["code-analysis"])
logger = logging.getLogger(__name__)

# 模型客户端
class LLMClient:
    """简单的大模型客户端，用于生成代码摘要"""
    
    def __init__(self, config=None):
        self.config = config or get_autogen_config()
        self._results_cache = {}  # 简单的结果缓存
    
    async def generate(self, prompt: str) -> str:
        """生成文本"""
        # 检查缓存
        if prompt in self._results_cache:
            logger.info("使用缓存的生成结果")
            return self._results_cache[prompt]
            
        # 这里简化实现，可以根据实际情况调整
        try:
            # 配置API密钥
            if "config_list" in self.config and len(self.config["config_list"]) > 0:
                first_config = self.config["config_list"][0]
                api_key = first_config.get("api_key")
                api_base = first_config.get("api_base", "https://api.openai.com/v1")
                model = first_config.get("model", "gpt-3.5-turbo")
                temperature = self.config.get("temperature", 0.7)
                
                # 尝试使用新版API
                try:
                    # 新版OpenAI API (>=1.0.0)
                    from openai import OpenAI
                    logger.info("使用OpenAI新版API")
                    
                    client = OpenAI(api_key=api_key, base_url=api_base)
                    response = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": "你是一个代码分析助手，负责分析和总结代码功能。"},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=temperature,
                        max_tokens=500
                    )
                    result = response.choices[0].message.content
                    
                except (ImportError, AttributeError):
                    # 尝试旧版API
                    logger.info("尝试使用OpenAI旧版API")
                    import openai
                    
                    # 配置旧版API
                    openai.api_key = api_key
                    openai.api_base = api_base
                    
                    # 使用旧版ChatCompletion API
                    response = await openai.ChatCompletion.acreate(
                        model=model,
                        messages=[
                            {"role": "system", "content": "你是一个代码分析助手，负责分析和总结代码功能。"},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=temperature,
                        max_tokens=500
                    )
                    result = response.choices[0].message.content
                
                # 缓存结果
                self._results_cache[prompt] = result
                return result
            else:
                return "未配置API密钥，无法生成摘要"
        except Exception as e:
            logger.error(f"调用LLM API失败: {str(e)}")
            return f"摘要生成失败: {str(e)}"

# API端点
@router.post("/repositories")
async def create_repository(
    background_tasks: BackgroundTasks,
    repo_path: str = Body(..., embed=True),
    repo_name: Optional[str] = Body(None, embed=True),
    knowledge_base_id: Optional[int] = Body(None, embed=True),
    auto_vectorize: bool = Body(True, embed=True),  # 默认自动向量化
    db: Session = Depends(get_db)
):
    """创建或更新代码仓库，并在后台分析代码"""
    
    # 验证路径
    if not os.path.exists(repo_path):
        raise HTTPException(status_code=404, detail=f"路径不存在: {repo_path}")
    
    # 如果指定了知识库ID，检查知识库是否存在
    if knowledge_base_id:
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == knowledge_base_id).first()
        if not kb:
            raise HTTPException(status_code=404, detail=f"找不到ID为{knowledge_base_id}的知识库")
    
    # 创建代码分析器
    analyzer = EnhancedCodeAnalyzer(db)
    
    try:
        # 立即开始分析
        repo_id = await analyzer.analyze_repository(repo_path, repo_name, knowledge_base_id)
        
        # 如果设定了自动向量化，则立即开始向量化
        if auto_vectorize:
            # 在后台任务中执行向量化
            background_tasks.add_task(
                _vectorize_repository_background, 
                repo_id=repo_id, 
                knowledge_base_id=knowledge_base_id,
                db_session=db
            )
            
            return {
                "status": "success",
                "repository_id": repo_id,
                "message": "代码库分析已完成，向量化正在后台执行"
            }
        else:
            return {
                "status": "success",
                "repository_id": repo_id,
                "message": "代码库分析已完成"
            }
    except Exception as e:
        logger.error(f"创建代码库时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"分析代码库失败: {str(e)}")

# 后台向量化代码库的辅助函数
async def _vectorize_repository_background(repo_id: int, knowledge_base_id: Optional[int], db_session: Session):
    """在后台执行代码库向量化
    
    Args:
        repo_id: 代码库ID
        knowledge_base_id: 知识库ID
        db_session: 数据库会话
    """
    logger.info(f"开始在后台向量化代码库 ID={repo_id}")
    
    try:
        # 获取代码库信息
        repo = db_session.query(CodeRepository).filter(CodeRepository.id == repo_id).first()
        if not repo:
            logger.error(f"后台向量化: 找不到代码库 ID={repo_id}")
            return
            
        # 确定要使用的知识库ID
        effective_kb_id = knowledge_base_id or repo.knowledge_base_id or repo_id
        
        # 执行向量化
        result = await vectorize_repository(
            repo_id=repo_id,
            knowledge_base_id=effective_kb_id,
            db=db_session
        )
        
        logger.info(f"后台向量化完成: {result.get('message')}")
        
        # 更新代码库的向量化状态和知识库关联
        repo.vectorized = True
        repo.last_vectorized = datetime.utcnow()
        
        # 确保代码库关联了正确的知识库ID
        if effective_kb_id != repo_id and repo.knowledge_base_id != effective_kb_id:
            repo.knowledge_base_id = effective_kb_id
            logger.info(f"更新代码库 {repo_id} 的知识库关联: knowledge_base_id={effective_kb_id}")
        
        db_session.commit()
        
    except Exception as e:
        logger.error(f"后台向量化代码库失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

@router.post("/repositories/upload")
async def upload_repository(
    background_tasks: BackgroundTasks,
    repo_file: UploadFile = File(...),
    repo_name: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """上传代码库压缩文件并分析"""
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    temp_file = os.path.join(temp_dir, repo_file.filename)
    
    try:
        # 保存上传的文件
        with open(temp_file, "wb") as f:
            shutil.copyfileobj(repo_file.file, f)
        
        # 解压缩文件
        import zipfile
        if zipfile.is_zipfile(temp_file):
            with zipfile.ZipFile(temp_file, 'r') as zip_ref:
                extract_dir = os.path.join(temp_dir, "extracted")
                os.makedirs(extract_dir, exist_ok=True)
                zip_ref.extractall(extract_dir)
            
            # 分析解压后的代码
            analyzer = EnhancedCodeAnalyzer(db)
            repo_id = await analyzer.analyze_repository(extract_dir, repo_name or repo_file.filename)
            
            return {
                "status": "success",
                "repository_id": repo_id,
                "message": "代码库上传并分析成功"
            }
        else:
            raise HTTPException(status_code=400, detail="上传的文件不是有效的ZIP压缩文件")
    
    except Exception as e:
        logger.error(f"上传代码库时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理上传文件失败: {str(e)}")
    finally:
        # 清理临时文件
        shutil.rmtree(temp_dir, ignore_errors=True)

@router.get("/repositories")
async def list_repositories(db: Session = Depends(get_db)):
    """列出所有代码仓库"""
    from models import CodeRepository
    
    try:
        repositories = db.query(CodeRepository).all()
        return [
            {
                "id": repo.id,
                "name": repo.name,
                "path": repo.path,
                "last_analyzed": repo.last_analyzed.isoformat() if repo.last_analyzed else None
            }
            for repo in repositories
        ]
    except Exception as e:
        logger.error(f"列出代码库时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取代码库列表失败: {str(e)}")

@router.get("/repositories/{repo_id}")
async def get_repository_summary(repo_id: int, db: Session = Depends(get_db)):
    """获取代码仓库的完整摘要"""
    try:
        repo = db.query(CodeRepository).filter(CodeRepository.id == repo_id).first()
        if not repo:
            raise HTTPException(status_code=404, detail=f"找不到ID为{repo_id}的代码库")
        
        # 获取所有组件和统计信息
        components = db.query(CodeComponent).filter(CodeComponent.repository_id == repo_id).all()
        file_stats = _get_file_stats(repo_id, db)
        dependencies = db.query(ComponentDependency).filter(ComponentDependency.repository_id == repo_id).count()
        
        return {
            "id": repo.id,
            "name": repo.name,
            "path": repo.path,
            "description": repo.description,
            "file_stats": file_stats,
            "important_components": [component.to_dict() for component in components],
            "statistics": {
                "total_files": db.query(CodeFile).filter(CodeFile.repository_id == repo_id).count(),
                "total_components": len(components),
                "total_dependencies": dependencies
            }
        }
    except Exception as e:
        logger.error(f"获取代码库摘要时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取代码库摘要失败: {str(e)}")

@router.get("/repositories/{repo_id}/basic-info")
async def get_repository_basic_info(repo_id: int, db: Session = Depends(get_db)):
    """获取代码仓库的基本信息（不包含组件列表，只有统计数据）"""
    try:
        # 获取仓库基本信息
        repo = db.query(CodeRepository).filter(CodeRepository.id == repo_id).first()
        if not repo:
            raise HTTPException(status_code=404, detail=f"找不到ID为{repo_id}的代码库")
        
        # 简化的统计信息
        file_count = db.query(CodeFile).filter(CodeFile.repository_id == repo_id).count()
        components_count = db.query(CodeComponent).filter(CodeComponent.repository_id == repo_id).count()
        
        # 语言分布统计 - 安全获取
        language_stats = {}
        try:
            files = db.query(CodeFile).filter(CodeFile.repository_id == repo_id).all()
            for file in files:
                # 使用file_path或path，取决于模型定义
                file_path = getattr(file, 'file_path', None) or getattr(file, 'path', '')
                if not file_path:
                    continue
                    
                ext = os.path.splitext(file_path)[-1].lower()
                if ext.startswith('.'):
                    ext = ext[1:]  # 移除点号
                
                # 简化语言分类
                if ext in ['py']:
                    lang = 'python'
                elif ext in ['js', 'jsx']:
                    lang = 'javascript'
                elif ext in ['ts', 'tsx']:
                    lang = 'typescript'
                elif ext in ['java']:
                    lang = 'java'
                elif ext in ['cpp', 'hpp', 'h', 'c']:
                    lang = 'c/c++'
                else:
                    lang = 'other'
                    
                language_stats[lang] = language_stats.get(lang, 0) + 1
        except Exception as e:
            logger.warning(f"获取语言统计失败: {str(e)}")
            # 不中断流程，继续返回其他信息
        
        # 尝试获取依赖关系数量
        dependencies_count = 0
        try:
            # 适应不同的数据模型字段
            if hasattr(ComponentDependency, 'repository_id'):
                dependencies_count = db.query(ComponentDependency).filter(
                    ComponentDependency.repository_id == repo_id
                ).count()
            else:
                # 如果没有repository_id字段，尝试通过组件关联
                dependency_query = db.query(ComponentDependency).join(
                    CodeComponent, 
                    ComponentDependency.source_id == CodeComponent.id
                ).filter(
                    CodeComponent.repository_id == repo_id
                )
                dependencies_count = dependency_query.count()
        except Exception as e:
            logger.warning(f"获取依赖关系统计失败: {str(e)}")
            # 不中断流程，继续返回其他信息
        
        return {
            "id": repo.id,
            "name": repo.name,
            "path": repo.path,
            "description": repo.description or "无描述信息",
            "file_stats": language_stats,
            "statistics": {
                "total_files": file_count,
                "total_components": components_count,
                "total_dependencies": dependencies_count
            }
        }
    except Exception as e:
        logger.error(f"获取代码库基本信息时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取代码库基本信息失败: {str(e)}")

@router.get("/repositories/{repo_id}/components")
async def get_repository_components(
    repo_id: int, 
    page: int = Query(1, ge=1), 
    page_size: int = Query(50, ge=1, le=1000),
    component_type: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """分页获取代码仓库的组件列表"""
    try:
        repo = db.query(CodeRepository).filter(CodeRepository.id == repo_id).first()
        if not repo:
            raise HTTPException(status_code=404, detail=f"找不到ID为{repo_id}的代码库")
        
        # 构建查询
        query = db.query(CodeComponent).filter(CodeComponent.repository_id == repo_id)
        
        # 如果指定了组件类型，进行过滤
        if component_type:
            query = query.filter(CodeComponent.type == component_type)
        
        # 检查模型属性，使用安全的排序字段
        # 尝试不同的可能属性名称
        try:
            if hasattr(CodeComponent, 'importance_score'):
                query = query.order_by(desc(CodeComponent.importance_score))
            elif hasattr(CodeComponent, 'importance'):
                query = query.order_by(desc(CodeComponent.importance))
            else:
                # 如果没有重要性相关字段，则按ID排序
                query = query.order_by(desc(CodeComponent.id))
        except Exception as e:
            logger.warning(f"组件排序出错，使用默认排序: {str(e)}")
            # 默认排序
            query = query.order_by(desc(CodeComponent.id))
        
        # 执行分页
        offset = (page - 1) * page_size
        components = query.offset(offset).limit(page_size).all()
        
        # 转换为字典列表，确保返回字段是安全的
        result = []
        for component in components:
            try:
                # 使用原有to_dict方法，添加异常处理
                result.append(component.to_dict())
            except AttributeError:
                # 如果没有to_dict方法，手动创建简化字典
                comp_dict = {
                    "id": component.id,
                    "name": component.name,
                    "type": component.type,
                    "file_path": getattr(component, 'file_path', None) or f"文件ID: {component.file_id}"
                }
                
                # 添加其他可能存在的字段
                if hasattr(component, 'importance_score'):
                    comp_dict["importance"] = component.importance_score
                elif hasattr(component, 'importance'):
                    comp_dict["importance"] = component.importance
                else:
                    comp_dict["importance"] = 0.5  # 默认中等重要性
                    
                result.append(comp_dict)
                
        return result
    except Exception as e:
        logger.error(f"分页获取代码库组件时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取代码库组件失败: {str(e)}")

def _get_file_stats(repo_id: int, db: Session) -> Dict[str, int]:
    """获取代码库的文件类型统计"""
    try:
        # 按扩展名统计文件数量
        files = db.query(CodeFile).filter(CodeFile.repository_id == repo_id).all()
        stats = {}
        
        for file in files:
            ext = os.path.splitext(file.path)[-1].lower()
            if ext.startswith('.'):
                ext = ext[1:]  # 移除点号
            
            # 扩展名映射到语言
            language = ext
            if ext == 'py':
                language = 'python'
            elif ext in ['js', 'jsx']:
                language = 'javascript'
            elif ext in ['ts', 'tsx']:
                language = 'typescript'
            elif ext in ['java']:
                language = 'java'
            elif ext in ['cpp', 'hpp', 'cc', 'cxx']:
                language = 'cpp'
            elif ext in ['c', 'h']:
                language = 'c'
            
            # 统计语言数量
            if language in stats:
                stats[language] += 1
            else:
                stats[language] = 1
                
        return stats
    except Exception as e:
        logger.warning(f"获取文件统计时出错: {str(e)}")
        return {}

@router.get("/repositories/{repo_id}/structure")
async def get_repository_structure(repo_id: int, db: Session = Depends(get_db)):
    """获取代码库结构"""
    service = CodeAnalysisService(db)
    
    try:
        structure = await service.get_repository_structure(repo_id)
        return structure
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"获取代码库结构时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取代码库结构失败: {str(e)}")

@router.get("/search")
async def search_components(
    repo_id: int,
    query: str,
    component_type: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """搜索代码组件"""
    service = CodeAnalysisService(db)
    
    try:
        logger.info(f"执行搜索: repo_id={repo_id}, query='{query}', component_type={component_type}")
        results = await service.search_components(repo_id, query, component_type, limit)
        logger.info(f"搜索结果数量: {len(results)}")
        return results
    except Exception as e:
        logger.error(f"搜索代码组件时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"搜索代码组件失败: {str(e)}")

@router.get("/components/{component_id}")
async def get_component_details(component_id: int, db: Session = Depends(get_db)):
    """获取组件详情"""
    service = CodeAnalysisService(db)
    
    try:
        details = await service.get_component_details(component_id)
        return details
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"获取组件详情时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取组件详情失败: {str(e)}")

@router.get("/components/{component_id}/impact")
async def analyze_component_impact(component_id: int, db: Session = Depends(get_db)):
    """分析组件影响"""
    service = CodeAnalysisService(db)
    
    try:
        impact = await service.analyze_impact(component_id)
        return impact
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"分析组件影响时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"分析组件影响失败: {str(e)}")

@router.post("/components/{component_id}/generate-summary")
async def generate_component_summary(component_id: int, db: Session = Depends(get_db)):
    """使用大模型生成组件摘要"""
    service = CodeAnalysisService(db)
    llm_client = LLMClient()
    
    try:
        summary = await service.generate_llm_summary(component_id, llm_client)
        return {"summary": summary}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"生成组件摘要时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成组件摘要失败: {str(e)}")

@router.post("/repositories/create-example")
async def create_example_repository(db: Session = Depends(get_db)):
    """创建一个示例代码库用于测试"""
    try:
        from models import CodeRepository, CodeFile, CodeComponent
        import os
        from datetime import datetime
        
        # 创建临时目录
        import tempfile
        temp_dir = tempfile.mkdtemp()
        example_dir = os.path.join(temp_dir, "example-repo")
        os.makedirs(example_dir, exist_ok=True)
        
        # 创建示例仓库
        repo = CodeRepository(
            name="示例代码库",
            path=example_dir,
            last_analyzed=datetime.utcnow()
        )
        db.add(repo)
        db.commit()
        
        # 创建示例文件
        example_file = CodeFile(
            repository_id=repo.id,
            file_path="example.py",
            language="python",
            last_modified=datetime.utcnow(),
            hash="example_hash"
        )
        db.add(example_file)
        db.commit()
        
        # 创建示例组件
        components = [
            CodeComponent(
                repository_id=repo.id,
                file_id=example_file.id,
                name="main",
                type="function",
                start_line=1,
                end_line=10,
                code='def main():\n    """这是主函数"""\n    print("Hello, world!")\n    return 42',
                signature="def main()",
                complexity=1.0,
                component_metadata={"args": [], "returns": ["int"]},
                importance_score=0.8
            ),
            CodeComponent(
                repository_id=repo.id,
                file_id=example_file.id,
                name="Person",
                type="class",
                start_line=12,
                end_line=20,
                code='class Person:\n    """人员类"""\n    def __init__(self, name):\n        self.name = name\n\n    def greet(self):\n        return f"Hello, {self.name}"',
                signature="class Person",
                complexity=1.5,
                component_metadata={"methods": ["__init__", "greet"]},
                importance_score=0.9
            ),
            CodeComponent(
                repository_id=repo.id,
                file_id=example_file.id,
                name="Person.greet",
                type="method",
                start_line=17,
                end_line=20,
                code='    def greet(self):\n        return f"Hello, {self.name}"',
                signature="def greet(self)",
                complexity=1.0,
                component_metadata={"class": "Person", "returns": ["str"]},
                importance_score=0.7
            )
        ]
        
        for comp in components:
            db.add(comp)
        db.commit()
        
        logger.info(f"创建了示例代码库，ID: {repo.id}, 组件数: {len(components)}")
        
        return {
            "status": "success",
            "repository_id": repo.id,
            "message": "示例代码库创建成功",
            "components_count": len(components)
        }
    except Exception as e:
        logger.error(f"创建示例代码库失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"创建示例代码库失败: {str(e)}")

@router.get("/files")
async def get_file_content(
    path: str,
    repo_id: int,
    db: Session = Depends(get_db)
):
    """获取文件内容"""
    service = CodeAnalysisService(db)
    
    try:
        # 验证仓库是否存在
        repo = db.query(CodeRepository).filter(CodeRepository.id == repo_id).first()
        if not repo:
            raise HTTPException(status_code=404, detail=f"找不到ID为{repo_id}的代码库")
        
        # 规范化文件路径 - 确保不以/开头
        path = path.lstrip('/')
        logger.info(f"正在获取文件: 仓库ID={repo_id}, 路径={path}, 仓库路径={repo.path}")
        
        # 组合完整文件路径
        full_path = os.path.join(repo.path, path)
        logger.info(f"完整文件路径: {full_path}")
        
        # 检查文件是否存在
        if not os.path.isfile(full_path):
            # 尝试在数据库中查找文件
            file = db.query(CodeFile).filter(
                CodeFile.repository_id == repo_id,
                CodeFile.file_path == path
            ).first()
            
            if file and os.path.isfile(os.path.join(repo.path, file.file_path)):
                # 使用数据库中的路径
                full_path = os.path.join(repo.path, file.file_path)
                logger.info(f"使用数据库中的路径: {full_path}")
            else:
                # 尝试查找匹配的文件
                matching_files = list(filter(
                    lambda f: f.endswith(path),
                    [os.path.join(dp, f) for dp, dn, filenames in os.walk(repo.path) for f in filenames]
                ))
                
                if matching_files:
                    full_path = matching_files[0]
                    logger.info(f"找到匹配文件: {full_path}")
                else:
                    logger.error(f"文件不存在: {path}")
                    raise HTTPException(status_code=404, detail=f"文件不存在: {path}")
        
        # 读取文件内容
        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        # 获取文件中的组件
        components = await service.get_file_components(repo_id, path)
        
        return {
            "content": content,
            "components": components,
            "path": path,
            "description": f"文件: {path}"
        }
    except Exception as e:
        logger.error(f"获取文件内容时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取文件内容失败: {str(e)}")

@router.post("/repositories/{repo_id}/vectorize")
async def vectorize_repository(
    repo_id: int,
    knowledge_base_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """将已分析的代码库存储到向量数据库，用于后续检索"""
    
    # 获取代码库信息
    repo = db.query(CodeRepository).filter(CodeRepository.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail=f"代码库ID {repo_id} 不存在")
    
    try:
        # 使用的知识库ID：优先使用请求中的，否则使用代码库关联的，再否则使用代码库ID作为知识库ID
        effective_kb_id = knowledge_base_id or repo.knowledge_base_id or repo_id
        logger.info(f"向量化代码库 {repo_id} (名称: {repo.name}) 到知识库 {effective_kb_id}")
        
        # 检查代码库是否已经向量化
        if repo.vectorized:
            logger.info(f"代码库 {repo_id} 已经向量化，将重新处理")
        
        # 初始化代码分析器
        analyzer = EnhancedCodeAnalyzer(db)
        
        # 获取要向量化的文档
        logger.info(f"开始分析代码库 {repo.path}...")
        result = await analyzer.analyze_and_vectorize_repository(
            repo_path=repo.path,
            repo_name=repo.name,
            knowledge_base_id=effective_kb_id
        )
        
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
            
        documents = result.get("documents", [])
        document_count = len(documents)
        logger.info(f"分析完成，获取到 {document_count} 个代码组件文档")
        
        if not documents:
            return {
                "status": "warning",
                "message": "没有找到可向量化的代码组件",
                "document_count": 0,
                "repository_id": repo_id
            }
            
        # 初始化向量存储
        vector_store = VectorStore(knowledge_base_id=effective_kb_id)
        
        # 批量添加文档
        logger.info(f"开始向量化 {document_count} 个代码组件文档...")
        
        # 预处理文档以适应VectorStore.add_documents的要求
        document_batches = []
        batch_size = 50  # 每批处理的文档数
        
        for i in range(0, document_count, batch_size):
            document_batches.append(documents[i:i+batch_size])
        
        # 批量处理文档
        total_added = 0
        failed_batches = 0
        
        for batch_idx, batch in enumerate(document_batches):
            batch_num = batch_idx + 1
            logger.info(f"处理批次 {batch_num}/{len(document_batches)}，包含 {len(batch)} 个文档")
            
            try:
                # 构建文档元数据
                for doc in batch:
                    # 确保文档元数据包含知识库ID
                    if "knowledge_base_id" not in doc.metadata:
                        doc.metadata["knowledge_base_id"] = effective_kb_id
                    
                    # 确保内容类型为代码
                    doc.metadata["content_type"] = "code"
                
                # 添加文档到向量存储
                add_result = await vector_store.add_documents(
                    documents=batch,
                    source_file=f"code_repo_{repo_id}",  # 统一的源文件标记
                    document_id=repo_id  # 使用仓库ID作为文档ID
                )
                
                if add_result.get("status") == "success":
                    added_count = add_result.get("count", 0)
                    total_added += added_count
                    logger.info(f"批次 {batch_num} 成功添加 {added_count} 个文档")
                else:
                    logger.warning(f"批次 {batch_num} 添加异常: {add_result.get('message', '未知错误')}")
                    failed_batches += 1
                    
            except Exception as e:
                logger.error(f"处理批次 {batch_num} 时出错: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                failed_batches += 1
        
        # 更新代码库的向量化状态和知识库关联
        repo.vectorized = True
        repo.last_vectorized = datetime.utcnow()
        
        # 确保代码库关联了正确的知识库ID
        if effective_kb_id != repo_id and repo.knowledge_base_id != effective_kb_id:
            repo.knowledge_base_id = effective_kb_id
            logger.info(f"更新代码库 {repo_id} 的知识库关联: knowledge_base_id={effective_kb_id}")
        
        db.commit()
        
        status = "success" if failed_batches == 0 else "partial_success"
        
        return {
            "status": status,
            "repository_id": repo_id,
            "knowledge_base_id": effective_kb_id,
            "message": f"成功向量化 {total_added}/{document_count} 个代码组件",
            "total_documents": document_count,
            "processed_documents": total_added,
            "failed_batches": failed_batches
        }
        
    except Exception as e:
        logger.error(f"向量化代码库时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        # 如果过程中出错，标记向量化失败
        if repo:
            repo.vectorized = False
            db.commit()
            
        raise HTTPException(status_code=500, detail=f"向量化失败: {str(e)}") 