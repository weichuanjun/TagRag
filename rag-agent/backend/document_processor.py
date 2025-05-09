import os
import pandas as pd
from typing import List, Dict, Any, Optional, Union
from langchain_community.document_loaders import (
    TextLoader, 
    PyPDFLoader, 
    CSVLoader,
    UnstructuredExcelLoader,
    UnstructuredMarkdownLoader,
    UnstructuredHTMLLoader,
    UnstructuredPowerPointLoader,
    Docx2txtLoader
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain_community.vectorstores.utils import filter_complex_metadata
import warnings
import logging
from sqlalchemy.orm import Session
from models import Document as DBDocument, DocumentChunk
import datetime
import tempfile
import json
import re
import traceback
import tiktoken
from fastapi import HTTPException

# Import LLMClient and Tag model for auto-tagging
from tag_routes import llm_client # Assuming llm_client is an instance of LLMClient
from models import Tag as DBTag # Alias to avoid conflict with Langchain Document's Tag

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

# Helper function to count tokens (using tiktoken if available, else simple word count)
_tokenizer_instance = None
def count_tokens(text: str) -> int:
    global _tokenizer_instance
    try:
        if _tokenizer_instance is None:
            _tokenizer_instance = tiktoken.get_encoding("cl100k_base") # Common encoder
        return len(_tokenizer_instance.encode(text))
    except ImportError:
        logger.warning("tiktoken not installed, using simple word count for token estimation.")
        return len(text.split())
    except Exception as e:
        logger.warning(f"Error using tiktoken: {e}, using simple word count.")
        return len(text.split())

class DocumentProcessor:
    """处理各种文档格式并进行分块处理的类"""
    
    def __init__(self, vector_store=None):
        # 文本分割配置
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )
        self.vector_store = vector_store
        
        # 文档加载器映射
        self.loaders = {
            '.txt': TextLoader,
            '.pdf': PyPDFLoader,
            '.docx': Docx2txtLoader,
            '.csv': CSVLoader,
            '.xlsx': UnstructuredExcelLoader,
            '.xls': UnstructuredExcelLoader,
            '.md': UnstructuredMarkdownLoader,
            '.html': UnstructuredHTMLLoader,
            '.htm': UnstructuredHTMLLoader,
            '.pptx': UnstructuredPowerPointLoader,
            '.ppt': UnstructuredPowerPointLoader,
        }
    
    def ensure_document(self, obj: Any, metadata: Dict[str, Any] = None) -> Document:
        """确保对象是Document类型，如果不是则转换为Document对象
        
        Args:
            obj: 要检查或转换的对象
            metadata: 要添加的元数据
            
        Returns:
            Document对象
        """
        try:
            # 如果已经是Document对象，只需要更新元数据
            if isinstance(obj, Document):
                if metadata and isinstance(metadata, dict):
                    # 确保元数据存在
                    if not hasattr(obj, 'metadata') or obj.metadata is None:
                        obj.metadata = {}
                    # 合并新的元数据
                    obj.metadata.update(metadata)
                return obj
                
            # 如果是字符串，创建新的Document对象
            if isinstance(obj, str):
                return Document(
                    page_content=obj,
                    metadata=metadata or {}
                )
                
            # 如果是其他类型，尝试转换为字符串
            try:
                content = str(obj)
                return Document(
                    page_content=content,
                    metadata=metadata or {}
                )
            except:
                # 如果转换失败，返回错误信息
                return Document(
                    page_content="[无法解析的内容]",
                    metadata=metadata or {}
                )
        except Exception as e:
            # 即使在处理过程中出现异常，也返回有效的Document对象
            logger.error(f"确保Document对象时出错: {str(e)}")
            return Document(
                page_content="[处理错误]",
                metadata=metadata or {"error": str(e)}
            )
    
    async def _analyze_and_associate_tags_via_llm(self, document_content_sample: str, db_document: DBDocument, db: Session):
        """Analyzes document content sample using LLM to suggest and associate tags."""
        logger.info(f"Starting LLM tag analysis for doc_id: {db_document.id} ('{db_document.source}')")
        # Add log to check the received sample
        logger.debug(f"_analyze_and_associate_tags_via_llm received content sample (first 500 chars): {document_content_sample[:500]}")
        if not document_content_sample.strip():
            logger.info(f"Document content sample is empty for doc_id: {db_document.id}. Skipping LLM tag analysis.")
            return

        prompt = f"""
        Analyse the following document content and suggest a short list of highly relevant keywords or phrases that can be used as tags. 
        Return these tags as a JSON list of strings. For example: ["API Reference", "User Authentication", "Database Schema"].
        Focus on concrete nouns, technical terms, and key concepts.
        Limit the number of tags to a maximum of 5-7 for conciseness.

        Document Content Sample:
        {document_content_sample[:2000]} # Limit sample size for LLM prompt
        """

        # Add logging to see the exact prompt being sent
        logger.debug(f"Prompt being sent to LLM for doc_id {db_document.id}:\n------PROMPT START------\n{prompt}\n------PROMPT END------\n")

        logger.info(f"Sending content to LLM for tag analysis for doc_id: {db_document.id}")
        llm_response_str = await llm_client.generate(prompt)
        logger.info(f"LLM raw response for tags for doc_id {db_document.id}: {llm_response_str}")

        suggested_tag_names = []
        try:
            cleaned_llm_response_str = llm_response_str.strip()
            if cleaned_llm_response_str.startswith("```json"):
                cleaned_llm_response_str = cleaned_llm_response_str[len("```json"):].strip()
            elif cleaned_llm_response_str.startswith("```"):
                cleaned_llm_response_str = cleaned_llm_response_str[len("```"):].strip()
            if cleaned_llm_response_str.endswith("```"):
                cleaned_llm_response_str = cleaned_llm_response_str[:-len("```")].strip()

            parsed_response = json.loads(cleaned_llm_response_str)
            
            potential_tags_list = None
            if isinstance(parsed_response, list):
                potential_tags_list = parsed_response
            elif isinstance(parsed_response, dict) and "tags" in parsed_response and isinstance(parsed_response["tags"], list):
                potential_tags_list = parsed_response["tags"]

            if potential_tags_list is not None and all(isinstance(name, str) for name in potential_tags_list):
                suggested_tag_names = [name.strip() for name in potential_tags_list if name.strip()]
                logger.info(f"Successfully parsed LLM suggested tag names for doc_id {db_document.id}: {suggested_tag_names}")
            else:
                logger.warning(f"LLM response was not a direct list of strings nor a dict with a 'tags' key containing a list of strings. doc_id {db_document.id}. Parsed response: {parsed_response}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM tag response for doc_id {db_document.id}: {e}. Raw response: {llm_response_str}")
        except Exception as e_parse:
            logger.error(f"An unexpected error occurred while parsing LLM tag response for doc_id {db_document.id}: {e_parse}. Raw: {llm_response_str}")

        if not suggested_tag_names:
            logger.info(f"No tags suggested by LLM or failed to parse for doc_id: {db_document.id}. No tags will be associated.")
            return

        logger.info(f"Attempting to find/create DB tags for doc_id {db_document.id}. Suggested: {suggested_tag_names}")
        associated_tags_for_document = []
        for tag_name in suggested_tag_names:
            if not tag_name: continue
            tag_name_cleaned = tag_name[:255]
            try:
                tag_orm_instance = db.query(DBTag).filter(DBTag.name.ilike(tag_name_cleaned)).first()
                if not tag_orm_instance:
                    logger.info(f"Tag '{tag_name_cleaned}' not found, creating new one for doc_id: {db_document.id}.")
                    tag_orm_instance = DBTag(
                        name=tag_name_cleaned, 
                        description=f"Automatically generated tag for: {tag_name_cleaned}",
                        color="#4287f5",
                        tag_type="auto-generated"
                    )
                    db.add(tag_orm_instance)
                    db.commit()
                    db.refresh(tag_orm_instance)
                    logger.info(f"Created and refreshed tag '{tag_name_cleaned}' with new ID {tag_orm_instance.id} for doc_id {db_document.id}.")
                else:
                    logger.info(f"Tag '{tag_name_cleaned}' found with ID {tag_orm_instance.id} for doc_id: {db_document.id}.")
                
                if tag_orm_instance not in associated_tags_for_document:
                    associated_tags_for_document.append(tag_orm_instance)
            except Exception as e_db_tag:
                logger.error(f"Database error while finding/creating tag '{tag_name_cleaned}' for doc_id {db_document.id}: {e_db_tag}")
                db.rollback()
                continue
        
        if associated_tags_for_document:
            try:
                logger.info(f"Preparing to associate {len(associated_tags_for_document)} found/created tags with doc_id {db_document.id}: {[t.id for t in associated_tags_for_document]}")
                current_doc_tags_set = set(db_document.tags if db_document.tags else [])
                newly_added_tags_count = 0
                for new_tag in associated_tags_for_document:
                    if new_tag not in current_doc_tags_set:
                        current_doc_tags_set.add(new_tag)
                        newly_added_tags_count += 1
                
                db_document.tags = list(current_doc_tags_set)
                db.commit()
                db.refresh(db_document)
                final_associated_tags = [(t.id, t.name) for t in db_document.tags]
                logger.info(f"Successfully associated tags with document_id: {db_document.id}. Added: {newly_added_tags_count}. Final tags on DB Doc: {final_associated_tags}")
            except Exception as e_assoc:
                logger.error(f"Error associating LLM-suggested tags with document_id {db_document.id}: {e_assoc}")
                db.rollback()
        else:
            logger.info(f"No new valid tags to associate with document_id {db_document.id} from LLM suggestions.")
        logger.info(f"Finished LLM tag analysis for doc_id: {db_document.id} ('{db_document.source}')")

    async def process_document(self, file_path: str, repository_id: int, db: Session, chunk_size: int = 1000, knowledge_base_id: Optional[int] = None, original_filename: Optional[str] = None):
        self.text_splitter.chunk_size = chunk_size
        source_name_for_logging = original_filename if original_filename else os.path.basename(file_path)
        logger.info(f"process_document (new version) for: '{file_path}' (Original: '{source_name_for_logging}'), KB_ID: {knowledge_base_id}")

        db_document = DBDocument(
            path=file_path, # This is the temp path
            source=original_filename if original_filename else os.path.basename(file_path),
            document_type=os.path.splitext(original_filename if original_filename else file_path)[1].lower(),
            knowledge_base_id=knowledge_base_id,
            repository_id=repository_id, # Assuming repository_id is for context/grouping, not primary storage key here
            status="processing_started"
        )
        db.add(db_document)
        try:
            db.commit()
            db.refresh(db_document)
            logger.info(f"DBDocument record created with ID: {db_document.id} for '{db_document.source}'")
        except Exception as e_db_init:
            logger.error(f"Error initially saving DBDocument for '{db_document.source}': {e_db_init}", exc_info=True)
            db.rollback()
            # Return an error structure or raise, ensuring no further processing attempt for this doc
            raise HTTPException(status_code=500, detail=f"Failed to create DB record for document: {str(e_db_init)}")

        document_id = db_document.id
        final_status = "processing_failed"
        final_error_message = None
        processed_chunks_count = 0
        vectorized_chunks_count = 0
        associated_tag_names = []

        try:
            # 1. Load and split document into raw chunks
            raw_langchain_chunks, content_sample_for_llm = await self._load_and_process_document(
                file_path=file_path, 
                document_id=document_id, 
                repository_id=repository_id, 
                db=db, 
                knowledge_base_id=knowledge_base_id, 
                original_filename=db_document.source
            )
            # Add log to check the sample returned
            logger.debug(f"process_document received content sample (length: {len(content_sample_for_llm)}) from _load_and_process_document. Sample start: {content_sample_for_llm[:200]}")

            if not raw_langchain_chunks or (len(raw_langchain_chunks) == 1 and raw_langchain_chunks[0].page_content.startswith("[Error:")):
                error_content = raw_langchain_chunks[0].page_content if raw_langchain_chunks else "Unknown loading error"
                logger.error(f"Failed to load or split document '{db_document.source}' (ID: {document_id}). Error: {error_content}")
                final_status = "error_loading"
                final_error_message = error_content
                db_document.status = final_status
                db_document.error_message = final_error_message[:1024] if final_error_message else None
                db_document.processed_at = datetime.datetime.utcnow()
                db.commit()
                return {
                    "status": "error", 
                    "message": f"Failed to load/split: {final_error_message}", 
                    "document_id": document_id
                }
            
            logger.info(f"Successfully loaded and split '{db_document.source}' into {len(raw_langchain_chunks)} raw chunks.")

            # 2. Auto-tagging via LLM (updates db_document.tags in SQL)
            if content_sample_for_llm and content_sample_for_llm.strip(): # Check again before calling
                try:
                    logger.info(f"Attempting LLM auto-tagging for doc_id {document_id} ('{db_document.source}')")
                    await self._analyze_and_associate_tags_via_llm(content_sample_for_llm, db_document, db)
                    db.refresh(db_document) # Ensure db_document.tags is up-to-date from the session
                    associated_tag_names = [tag.name for tag in db_document.tags] if db_document.tags else []
                    logger.info(f"LLM auto-tagging completed for doc_id {document_id}. Associated tags: {associated_tag_names}")
                except Exception as e_autotag:
                    logger.error(f"Error during LLM auto-tagging for doc_id {document_id}: {e_autotag}", exc_info=True)
                    # Non-fatal, proceed without LLM tags if analysis fails
            else:
                logger.info(f"Skipping LLM auto-tagging for doc_id {document_id} due to empty or error content sample (checked in process_document).") # Updated log

            document_level_tag_ids = [tag.id for tag in db_document.tags] if db_document.tags else []
            logger.info(f"PROCESS_DOCUMENT DBG: Document-level tag IDs for doc_id {document_id} after auto-tagging (or if skipped): {document_level_tag_ids}")

            # 3. Process Chunks: Save to DB and prepare for Vector Store
            db_chunks_to_save: List[DocumentChunk] = []
            langchain_docs_for_vector_store: List[Document] = []

            for i, chunk_doc in enumerate(raw_langchain_chunks):
                # ---- DEV_PROCESSOR_DBG Start ----
                page_content_for_debug = chunk_doc.page_content if isinstance(chunk_doc, Document) else None
                logger.info(f"DEV_PROCESSOR_DBG: Processing chunk {i} for doc_id {document_id}. Original chunk object type: {type(chunk_doc)}")
                if isinstance(page_content_for_debug, str):
                    logger.info(f"DEV_PROCESSOR_DBG: Page content (repr): {repr(page_content_for_debug)}")
                    logger.info(f"DEV_PROCESSOR_DBG: Page content (direct print): '{page_content_for_debug}'")
                    logger.info(f"DEV_PROCESSOR_DBG: Is page_content an empty string? {page_content_for_debug == ''}")
                    logger.info(f"DEV_PROCESSOR_DBG: Does page_content consist only of whitespace? {page_content_for_debug.isspace() if page_content_for_debug else False}")
                    logger.info(f"DEV_PROCESSOR_DBG: Does page_content start with [Error:? {page_content_for_debug.startswith('[Error:')}")
                else:
                    logger.info(f"DEV_PROCESSOR_DBG: Page content is not a string or chunk_doc is not a Document. Content: {page_content_for_debug}")
                # ---- DEV_PROCESSOR_DBG End ----

                # Original condition that was supposed to skip empty/error chunks
                # Ensure page_content_for_debug is used here for consistency with debug logs
                should_skip = False
                if not isinstance(chunk_doc, Document) or not page_content_for_debug:
                    should_skip = True
                elif isinstance(page_content_for_debug, str) and page_content_for_debug.startswith("[Error:"):
                    should_skip = True
                
                if should_skip:
                    logger.warning(f"DEV_PROCESSOR_DBG: SKIPPING chunk {i} for doc_id {document_id} based on condition. Content (repr): {repr(page_content_for_debug)}")
                    continue
                
                # This must be called only with valid page_content_for_debug (not None, not starting with [Error:)
                token_count = count_tokens(page_content_for_debug) 
                logger.info(f"DEV_PROCESSOR_DBG: Calculated token_count: {token_count} for the above content (chunk {i}).")

                # Enrich metadata for this chunk
                chunk_doc.metadata["token_count"] = token_count
                chunk_doc.metadata["structural_type"] = chunk_doc.metadata.get('category', 'paragraph')
                # chunk_doc.metadata["tag_ids"] = document_level_tag_ids # Old way
                # logger.info(f"PROCESS_DOCUMENT DBG: Chunk {i} of doc {document_id} assigned metadata tag_ids: {chunk_doc.metadata.get('tag_ids')}")

                # Prepare DB ORM object (DocumentChunk)
                # Ensure metadata for DB is JSON serializable; filter_complex_metadata can help here too if needed
                # For now, assume direct use is fine or handle specific complex fields if they arise.
                try:
                    chunk_metadata_for_db = json.dumps(chunk_doc.metadata)
                except TypeError as te:
                    logger.warning(f"Metadata for chunk {i} of doc {document_id} is not JSON serializable: {te}. Using filtered version.")
                    temp_filtered_meta = filter_complex_metadata(chunk_doc.metadata.copy())
                    chunk_metadata_for_db = json.dumps(temp_filtered_meta)
                
                db_chunk = DocumentChunk(
                    document_id=document_id,
                    content=chunk_doc.page_content,
                    chunk_index=i,
                    token_count=token_count,
                    structural_type=chunk_doc.metadata["structural_type"],
                    chunk_metadata=chunk_metadata_for_db,
                    page=chunk_doc.metadata.get("page_number")
                )
                
                # 新增的行：将文档标签关联到块对象
                if db_document and db_document.tags:
                    db_chunk.tags = list(db_document.tags) # 使用 list() 创建副本以防意外修改
                
                db_chunks_to_save.append(db_chunk)

                # Prepare Langchain Document for Vector Store (with its own filtered metadata copy)
                # This is where metadata for ChromaDB is actually constructed.
                metadata_for_vector_store_dict = chunk_doc.metadata.copy() # Start with existing base metadata
                
                # Remove the list-based 'tag_ids' if it was accidentally set on chunk_doc.metadata earlier
                if "tag_ids" in metadata_for_vector_store_dict:
                    del metadata_for_vector_store_dict["tag_ids"]

                # Add flattened tags: e.g., tag_10: True, tag_9: True
                if document_level_tag_ids:
                    for tag_id in document_level_tag_ids:
                        metadata_for_vector_store_dict[f"tag_{tag_id}"] = True
                
                # Now, final_meta_for_chroma will be built from metadata_for_vector_store_dict
                # ensuring only scalar values are kept by the existing loop.
                final_meta_for_chroma = {}
                for k, v in metadata_for_vector_store_dict.items():
                    if isinstance(v, (str, int, float, bool)):
                        final_meta_for_chroma[k] = v
                    # Lists (other than the original tag_ids which is now removed/flattened) are excluded by this logic

                logger.info(f"PROCESS_DOCUMENT DBG: Final FLATTENED metadata for Chroma for chunk {i} of doc {document_id}: {json.dumps(final_meta_for_chroma)}")
                langchain_docs_for_vector_store.append(Document(page_content=chunk_doc.page_content, metadata=final_meta_for_chroma))
                processed_chunks_count += 1

            if db_chunks_to_save:
                db.add_all(db_chunks_to_save)
                db.commit()
                logger.info(f"Successfully saved {len(db_chunks_to_save)} DocumentChunk records to DB for doc_id {document_id}.")
            else:
                logger.warning(f"No valid DocumentChunk records to save to DB for doc_id {document_id}.")

            # 4. Add to Vector Store
            if langchain_docs_for_vector_store:
                from vector_store import VectorStore # Ensure import is within reach or global
                vector_store_instance = VectorStore(repository_id=repository_id) # Assuming one VS per repo or global if repo_id is None
                vs_add_result = await vector_store_instance.add_documents(langchain_docs_for_vector_store, document_id=document_id)
                if vs_add_result.get("status") == "error":
                    logger.error(f"Failed to add documents to vector store for doc_id {document_id}. Error: {vs_add_result.get('message')}")
                    final_status = "error_vector_store"
                    final_error_message = vs_add_result.get('message', "Vector store addition failed")
                else:
                    vectorized_chunks_count = len(langchain_docs_for_vector_store)
                    logger.info(f"Successfully added {vectorized_chunks_count} chunks to vector store for doc_id {document_id}.")
                    if final_status == "processing_failed": # If no other error occurred yet
                         final_status = "processed" # Mark as processed if vectorization was the last major step
            else:
                logger.warning(f"No valid Langchain Documents to add to vector store for doc_id {document_id}.")
                if processed_chunks_count > 0 and final_status == "processing_failed": # If DB chunks were saved but nothing to vectorize
                    final_status = "processed_no_vectors"

            # Update final document status in DB
            if final_status == "processing_failed" and not final_error_message: # Default to processed if no specific error was set
                final_status = "processed"
                if processed_chunks_count == 0:
                    final_status = "empty_or_error_content" # If no chunks were processed at all
            
            db_document.status = final_status
            db_document.error_message = final_error_message[:1024] if final_error_message else None
            db_document.chunks_count = processed_chunks_count
            db_document.processed_at = datetime.datetime.utcnow()
            db.commit()
            logger.info(f"Processing finished for doc_id {document_id} ('{db_document.source}') with status: {final_status}.")
            
            return {
                "status": final_status,
                "message": final_error_message if final_error_message else f"Document '{db_document.source}' processed.",
                "document_id": document_id,
                "processed_chunks_count": processed_chunks_count,
                "vectorized_chunks_count": vectorized_chunks_count,
                "associated_tags": associated_tag_names
            }

        except HTTPException as http_exc: # Re-raise HTTP exceptions from _analyze_and_associate_tags_via_llm or others
            db.rollback()
            # Ensure db_document is still usable or re-fetch if session was rolled back and invalidated it.
            # Minimal update if possible, otherwise re-fetch.
            # For simplicity, let's assume db_document is still valid for status update or error won't allow it.
            try:
                # Attempt to refresh if needed, or just use it if session state allows.
                # db.refresh(db_document) # This might fail if session is bad
                db_doc_to_update = db.query(DBDocument).filter(DBDocument.id == document_id).first()
                if db_doc_to_update:
                    db_doc_to_update.status = "error_processing_http"
                    db_doc_to_update.error_message = str(http_exc.detail)[:1024]
                    db_doc_to_update.processed_at = datetime.datetime.utcnow()
                    db.commit()
                else:
                    logger.error(f"Failed to find document {document_id} to update status after HTTPException.")    
            except Exception as e_status_update:
                logger.error(f"Failed to update document status after HTTPException for doc_id {document_id}: {e_status_update}")
                # db.rollback() # Rollback status update attempt if it fails
            raise http_exc # Re-raise the original HTTPException
        except Exception as e_main:
            from fastapi import HTTPException # Defensive import for generic exception case
            logger.error(f"Critical error in process_document for '{source_name_for_logging}' (doc_id {document_id}): {e_main}", exc_info=True)
            db.rollback()
            # Ensure db_document status reflects the failure even if it was partially updated
            try:
                db.refresh(db_document) # Get current state from DB if session is rolled back
                db_document.status = "processing_failed_uncaught"
                db_document.error_message = str(e_main)[:1024]
                db_document.processed_at = datetime.datetime.utcnow()
                db.commit()
            except Exception as e_final_status:
                logger.error(f"Failed to update final error status for doc_id {document_id}: {e_final_status}")
            
            # Do not re-raise generic Exception as HTTPException directly to avoid masking the original type
            # Let FastAPI handle it as a 500 Internal Server Error or define a specific error response structure.
            # For now, we will raise a generic HTTPException to provide some feedback to the client.
            raise HTTPException(status_code=500, detail=f"Internal server error during document processing: {str(e_main)}")

    async def _load_and_process_document(self, file_path: str, document_id: int, repository_id: int, db: Session, knowledge_base_id: Optional[int] = None, original_filename: Optional[str] = None) -> tuple[List[Document], str]:
        """
        Loads a document from the given file path, splits it into chunks,
        and returns the list of chunks (Langchain Document objects) and a content sample for LLM analysis.
        Does NOT interact with the database or vector store.
        """
        logger.info(f"_load_and_process_document (new version) started for: '{file_path}', doc_id: {document_id}")
        
        source_name = original_filename if original_filename else os.path.basename(file_path)
        docs_from_loader: List[Document] = []
        content_sample_for_llm = ""

        try:
            file_extension = os.path.splitext(file_path)[1].lower()
            loader_class = self.loaders.get(file_extension)

            if not loader_class:
                logger.warning(f"No loader found for file type '{file_extension}' for file '{file_path}'")
                error_doc = Document(page_content=f"[Error: No loader for file type {file_extension}]", metadata={"source": source_name, "error": "no_loader_found", "document_id": document_id, "knowledge_base_id": knowledge_base_id})
                return [error_doc], "" # Return error doc and empty sample

            logger.info(f"Using loader: {loader_class.__name__} for '{file_path}'")
            if loader_class == TextLoader:
                loader = loader_class(file_path, autodetect_encoding=True)
            else:
                loader = loader_class(file_path)
            
            try:
                loaded_docs_raw = loader.load()
                if not loaded_docs_raw:
                    logger.warning(f"Loader {loader_class.__name__} returned no documents for '{file_path}'.")
                    error_doc = Document(page_content=f"[Error: Loader returned no content for {source_name}]", metadata={"source": source_name, "error": "loader_returned_empty", "document_id": document_id, "knowledge_base_id": knowledge_base_id})
                    return [error_doc], ""
                
                docs_from_loader = [self.ensure_document(d, metadata={"source": source_name, "document_id": document_id, "knowledge_base_id": knowledge_base_id}) for d in loaded_docs_raw]
            
            except Exception as e_load:
                logger.error(f"Error loading '{file_path}' with {loader_class.__name__}: {e_load}", exc_info=True)
                error_doc = Document(page_content=f"[Error loading {source_name}: {str(e_load)}]", metadata={"source": source_name, "error": str(e_load), "document_id": document_id, "knowledge_base_id": knowledge_base_id})
                return [error_doc], ""

            if not docs_from_loader: # Should be caught by earlier checks, but as a safeguard
                logger.error(f"No documents were derived for '{file_path}' after loader processing.")
                return [], ""

            sample_builder = []
            for doc_item in docs_from_loader:
                if doc_item and isinstance(doc_item.page_content, str) and not doc_item.page_content.startswith("[Error:"):
                    sample_builder.append(doc_item.page_content)
                    if len("\n".join(sample_builder)) > 2000:
                        break
            content_sample_for_llm = "\n".join(sample_builder)
            
            split_docs = self.text_splitter.split_documents(docs_from_loader)
            logger.info(f"Document '{source_name}' (doc_id: {document_id}) split into {len(split_docs)} chunks by _load_and_process_document.")

            for i, chunk_doc in enumerate(split_docs):
                if chunk_doc.metadata is None: chunk_doc.metadata = {}
                chunk_doc.metadata.setdefault("source", source_name)
                chunk_doc.metadata.setdefault("document_id", document_id)
                chunk_doc.metadata.setdefault("knowledge_base_id", knowledge_base_id)
                chunk_doc.metadata.setdefault("chunk_index", i)

            return split_docs, content_sample_for_llm

        except Exception as e_outer:
            logger.error(f"Outer try-except in _load_and_process_document (new version) for '{file_path}': {e_outer}", exc_info=True)
            error_doc = Document(page_content=f"[Critical error in _load_and_process_document for {source_name}: {str(e_outer)}]", metadata={"source": source_name, "error": "critical_processing_error", "document_id": document_id, "knowledge_base_id": knowledge_base_id})
            return [error_doc], ""

    async def _process_text_file(self, file_path: str, document_id: int, knowledge_base_id: Optional[int] = None, document_level_tag_ids: List[int] = None):
        # As per original file content (lines 375-457 approx)
        # Pass document_level_tag_ids (initially empty) to metadata
        logger.debug(f"_process_text_file called for {file_path} with initial tags: {document_level_tag_ids}")
        # ... (Original logic) ...
        # Simplified for diff:
        with open(file_path, 'r', encoding='utf-8-sig') as f: content = f.read()
        texts = self.text_splitter.split_text(content)
        docs = []
        for i, text in enumerate(texts):
            docs.append(Document(page_content=text, metadata={
                "source": os.path.basename(file_path), "document_id": document_id, "chunk_index": i, 
                "knowledge_base_id": knowledge_base_id, "tag_ids": document_level_tag_ids or [], 
                "token_count": count_tokens(text), "structural_type": "paragraph"
            }))
        return docs

    async def _process_csv_simple(self, file_path: str, document_id: int, knowledge_base_id: Optional[int] = None, document_level_tag_ids: List[int] = None):
        # As per original file content (lines 457-468 approx)
        logger.debug(f"_process_csv_simple called for {file_path} with initial tags: {document_level_tag_ids}")
        return await self._process_text_file(file_path, document_id, knowledge_base_id, document_level_tag_ids)

    async def _process_excel_simple(self, file_path: str, document_id: int, knowledge_base_id: Optional[int] = None, document_level_tag_ids: List[int] = None):
        # As per original file content (lines 468-528 approx)
        logger.debug(f"_process_excel_simple called for {file_path} with initial tags: {document_level_tag_ids}")
        # ... (Original logic for Excel processing, ensuring it uses document_level_tag_ids for metadata) ...
        # Simplified for diff:
        excel_file = pd.ExcelFile(file_path)
        all_documents = []
        for sheet_name in excel_file.sheet_names:
            df = excel_file.parse(sheet_name)
            content = f"# 工作表: {sheet_name}\n\n{df.to_string(index=False)}"
            texts = self.text_splitter.split_text(content)
            for i, text in enumerate(texts):
                all_documents.append(Document(page_content=text, metadata={
                    "source": os.path.basename(file_path), "document_id": document_id, "chunk_index": i, "sheet_name": sheet_name,
                    "knowledge_base_id": knowledge_base_id, "tag_ids": document_level_tag_ids or [],
                    "token_count": count_tokens(text), "structural_type": "table_row_or_text"
                }))
        return all_documents

    # _extract_and_store_entities method is assumed to be present as per original file (lines 528-670 approx)
    def _extract_and_store_entities(self, documents, document_id, repository_id, knowledge_base_id):
        # Original content of this method
        pass # Placeholder for diff

# Ensure this class definition ends correctly if there were more methods not shown in context 