from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Query, Body, UploadFile, File
from sqlalchemy.orm import Session
from typing import Dict, List, Any, Optional
import os
import shutil
import tempfile
import logging

from models import get_db, KnowledgeBase, CodeRepository  # 添加CodeRepository导入
from enhanced_code_analyzer import EnhancedCodeAnalyzer
from analysis_service import CodeAnalysisService
from config import get_autogen_config  # 使用现有配置管理

router = APIRouter(prefix="/code", tags=["code-analysis"])

logger = logging.getLogger(__name__)

# 模型客户端
class LLMClient:
    """简单的大模型客户端，用于生成代码摘要"""
    
    def __init__(self, config=None):
        self.config = config or get_autogen_config()
    
    async def generate(self, prompt: str) -> str:
        """生成文本"""
        # 这里简化实现，可以根据实际情况调整
        import openai
        
        # 配置API密钥
        if "config_list" in self.config and len(self.config["config_list"]) > 0:
            first_config = self.config["config_list"][0]
            openai.api_key = first_config.get("api_key")
            openai.api_base = first_config.get("api_base", "https://api.openai.com/v1")
            
            # 使用ChatCompletion API
            try:
                response = await openai.ChatCompletion.acreate(
                    model=first_config.get("model", "gpt-3.5-turbo"),
                    messages=[
                        {"role": "system", "content": "你是一个代码分析助手，负责分析和总结代码功能。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=self.config.get("temperature", 0.7),
                    max_tokens=500
                )
                return response.choices[0].message.content
            except Exception as e:
                logger.error(f"调用OpenAI API失败: {str(e)}")
                return f"摘要生成失败: {str(e)}"
        else:
            return "未配置API密钥，无法生成摘要"

# API端点
@router.post("/repositories")
async def create_repository(
    background_tasks: BackgroundTasks,
    repo_path: str = Body(..., embed=True),
    repo_name: Optional[str] = Body(None, embed=True),
    knowledge_base_id: Optional[int] = Body(None, embed=True),
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
        
        return {
            "status": "success",
            "repository_id": repo_id,
            "message": "代码库分析已开始"
        }
    except Exception as e:
        logger.error(f"创建代码库时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"分析代码库失败: {str(e)}")

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
    """获取代码库摘要信息"""
    service = CodeAnalysisService(db)
    
    try:
        summary = await service.get_repository_summary(repo_id)
        return summary
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"获取代码库摘要时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取代码库摘要失败: {str(e)}")

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