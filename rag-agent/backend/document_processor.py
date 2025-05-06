import os
import pandas as pd
from typing import List, Dict, Any, Optional
from langchain.document_loaders import TextLoader, PyPDFLoader, CSVLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
import warnings
warnings.filterwarnings("ignore")

class DocumentProcessor:
    """处理各种文档格式并进行分块处理的类"""
    
    def __init__(self, vector_store=None):
        # 文本分割配置
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", "。", "，", ".", " ", ""]
        )
        self.vector_store = vector_store
    
    async def process_document(self, file_path: str, chunk_size: int = 1000):
        """处理文档并添加到向量存储"""
        # 更新文本分割器的块大小
        self.text_splitter.chunk_size = chunk_size
        
        # 调用处理文件的方法
        return await self.process_file(file_path, self.vector_store)
    
    async def process_file(self, file_path: str, vector_store):
        """处理文件并添加到向量存储"""
        try:
            # 根据文件扩展名决定使用哪个加载器
            file_extension = os.path.splitext(file_path)[1].lower()
            
            if file_extension == '.txt':
                documents = self._process_text_file(file_path)
            elif file_extension == '.pdf':
                documents = self._process_pdf_file(file_path)
            elif file_extension in ['.csv', '.tsv']:
                documents = self._process_csv_file(file_path)
            elif file_extension in ['.xlsx', '.xls']:
                documents = self._process_excel_file(file_path)
            else:
                raise ValueError(f"不支持的文件格式: {file_extension}")
            
            # 分块处理
            chunks = self.text_splitter.split_documents(documents)
            
            # 添加到向量存储
            await vector_store.add_documents(chunks, file_path)
            
            return {
                "status": "success",
                "message": f"已处理 {file_path} 文件，共 {len(chunks)} 个块",
                "chunks_count": len(chunks)
            }
            
        except Exception as e:
            print(f"处理文件时出错: {str(e)}")
            raise e
    
    def _process_text_file(self, file_path: str) -> List[Document]:
        """处理文本文件"""
        loader = TextLoader(file_path, encoding='utf-8')
        return loader.load()
    
    def _process_pdf_file(self, file_path: str) -> List[Document]:
        """处理PDF文件"""
        loader = PyPDFLoader(file_path)
        return loader.load()
    
    def _process_csv_file(self, file_path: str) -> List[Document]:
        """处理CSV文件"""
        loader = CSVLoader(file_path)
        return loader.load()
    
    def _process_excel_file(self, file_path: str) -> List[Document]:
        """处理Excel文件并转换为Markdown格式"""
        documents = []
        
        # 读取Excel文件的所有工作表
        excel_file = pd.ExcelFile(file_path)
        
        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            
            # 转换为Markdown表格
            markdown_content = f"## 工作表: {sheet_name}\n\n"
            markdown_content += df.to_markdown(index=False) if not df.empty else "空工作表"
            markdown_content += "\n\n========================================\n\n"
            
            # 创建Document对象
            doc = Document(
                page_content=markdown_content,
                metadata={
                    "source": file_path,
                    "sheet_name": sheet_name,
                    "format": "excel_to_markdown"
                }
            )
            
            documents.append(doc)
        
        return documents 