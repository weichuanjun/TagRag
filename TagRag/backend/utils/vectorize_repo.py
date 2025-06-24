"""
代码库向量化工具，用于将代码库分析并存储到向量数据库
"""
import os
import sys
import logging
import asyncio
from typing import Optional

# 将项目根目录添加到Python路径，确保可以找到顶级模块
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from sqlalchemy.orm import Session
from ..models import get_db, CodeRepository
from ..enhanced_code_analyzer import EnhancedCodeAnalyzer
from ..vector_store import VectorStore

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def vectorize_repository(repo_id: int, knowledge_base_id: Optional[int] = None, db = None):
    """向量化指定的代码库
    
    Args:
        repo_id: 代码库ID
        knowledge_base_id: 可选的知识库ID，如果提供，则使用此ID作为向量存储的集合名
        db: 可选的数据库会话，如不提供则创建新会话
    """
    if db is None:
        db = next(get_db())  # 获取数据库会话
    
    try:
        # 查找代码库
        repo = db.query(CodeRepository).filter(CodeRepository.id == repo_id).first()
        if not repo:
            logger.error(f"找不到ID为 {repo_id} 的代码库")
            return
        
        # 确定要使用的知识库ID
        effective_kb_id = knowledge_base_id or repo.knowledge_base_id or repo_id
        logger.info(f"准备向量化代码库: {repo.name} (ID={repo_id})，使用知识库ID: {effective_kb_id}")
        
        # 检查代码库路径是否存在
        if not os.path.exists(repo.path):
            logger.error(f"代码库路径不存在: {repo.path}")
            return
        
        # 初始化代码分析器
        analyzer = EnhancedCodeAnalyzer(db)
        
        # 分析代码库并获取文档
        logger.info(f"开始分析代码库: {repo.path}")
        result = await analyzer.analyze_and_vectorize_repository(
            repo_path=repo.path,
            repo_name=repo.name,
            knowledge_base_id=effective_kb_id
        )
        
        if result["status"] == "error":
            logger.error(f"代码库分析失败: {result['message']}")
            return
            
        # 获取文档
        documents = result.get("documents", [])
        document_count = len(documents)
        logger.info(f"代码分析完成，获取到 {document_count} 个组件文档")
        
        if not documents:
            logger.warning("没有找到可向量化的代码组件")
            return
            
        # 初始化向量存储
        vector_store = VectorStore(knowledge_base_id=effective_kb_id)
        
        # 批量添加文档
        logger.info(f"开始向量化 {document_count} 个代码组件文档")
        
        # 预处理文档，添加元数据
        for doc in documents:
            # 确保文档元数据包含知识库ID
            if "knowledge_base_id" not in doc.metadata:
                doc.metadata["knowledge_base_id"] = effective_kb_id
            
            # 确保内容类型为代码
            doc.metadata["content_type"] = "code"
        
        # 按批次处理文档
        batch_size = 50
        total_added = 0
        
        for i in range(0, document_count, batch_size):
            batch = documents[i:i+batch_size]
            batch_num = i // batch_size + 1
            
            logger.info(f"处理批次 {batch_num}/{(document_count + batch_size - 1) // batch_size}，包含 {len(batch)} 个文档")
            
            # 添加文档到向量存储
            add_result = await vector_store.add_documents(
                documents=batch,
                source_file=f"code_repo_{repo_id}",
                document_id=repo_id
            )
            
            if add_result.get("status") == "success":
                added_count = add_result.get("count", 0)
                total_added += added_count
                logger.info(f"批次 {batch_num} 成功添加 {added_count} 个文档")
            else:
                logger.warning(f"批次 {batch_num} 添加异常: {add_result.get('message', '未知错误')}")
        
        # 更新代码库的向量化状态
        if total_added > 0:
            from datetime import datetime
            repo.vectorized = True
            repo.last_vectorized = datetime.utcnow()
            db.commit()
            logger.info(f"已成功向量化 {total_added}/{document_count} 个代码组件")
        else:
            logger.error("向量化失败，没有成功添加任何文档")
        
    except Exception as e:
        logger.error(f"向量化代码库时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

async def main():
    """主函数，处理命令行参数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="代码库向量化工具")
    parser.add_argument("--repo-id", type=int, required=True, help="代码库ID")
    parser.add_argument("--kb-id", type=int, help="知识库ID（可选）")
    
    args = parser.parse_args()
    
    await vectorize_repository(args.repo_id, args.kb_id)

if __name__ == "__main__":
    asyncio.run(main()) 