import logging
import math
from typing import List, Dict, Any, Optional, Tuple
from langchain_community.embeddings import HuggingFaceEmbeddings

from .config import (
    T_CUS_ALPHA,
    T_CUS_BETA,
    T_CUS_GAMMA,
    STRUCTURAL_WEIGHTS,
    TAG_SIMILARITY_CONFIG,
    CONTEXT_TOKEN_LIMIT,
    T_CUS_EMBEDDING_MODEL
)
# from models import Tag # Avoid direct import if models.py might import this, handle via accessor

logger = logging.getLogger(__name__)

# Define the new weights with higher emphasis on tag score (beta)
NEW_T_CUS_ALPHA = 0.3  # Weight for semantic similarity
NEW_T_CUS_BETA = 0.6   # Increased weight for tag similarity/match
NEW_T_CUS_GAMMA = 0.1  # Weight for structural importance

# Ensure weights sum to 1 (or handle normalization if they don't)
assert abs(NEW_T_CUS_ALPHA + NEW_T_CUS_BETA + NEW_T_CUS_GAMMA - 1.0) < 1e-6, "T-CUS weights must sum to 1.0"

class TagGraphAccessor:
    def __init__(self, db_session=None, graph_store_instance=None):
        self.db = db_session
        self.graph_store = graph_store_instance

    def get_tag_by_id(self, tag_id: int) -> Optional[Dict]:
        if self.db:
            from models import Tag as TagModel # Local import
            tag_obj = self.db.query(TagModel).filter(TagModel.id == tag_id).first()
            if tag_obj:
                return {
                    "id": tag_obj.id,
                    "name": tag_obj.name,
                    "tag_type": tag_obj.tag_type,
                    "parent_id": tag_obj.parent_id
                }
        return None

    def get_parent_child_relationship(self, tag_id1: int, tag_id2: int) -> Optional[str]:
        tag1_obj = self.get_tag_by_id(tag_id1)
        tag2_obj = self.get_tag_by_id(tag_id2)
        if not tag1_obj or not tag2_obj: return None
        if tag1_obj.get("parent_id") == tag2_obj.get("id"): return "child_of"
        if tag2_obj.get("parent_id") == tag1_obj.get("id"): return "parent_of"
        return None

    def get_dependency_relationship(self, tag_id1: int, tag_id2: int) -> Optional[str]:
        # Placeholder for querying TagDependency model
        return None

def _calculate_tag_similarity_v2(
    query_tag_ids: List[int],
    chunk_tag_ids: List[int],
    tag_graph_accessor: Optional[TagGraphAccessor] = None,
    config: Dict = TAG_SIMILARITY_CONFIG
) -> float:
    """
    Calculates tag similarity score.
    Prioritizes direct matches (returns 1.0).
    If no direct match, uses Jaccard similarity and potentially graph relations.
    """
    if not query_tag_ids or not chunk_tag_ids:
        return 0.0
    
    query_tags_set = set(query_tag_ids)
    chunk_tags_set = set(chunk_tag_ids)
    intersection = query_tags_set.intersection(chunk_tags_set)

    # --- Key Change: Prioritize direct match ---
    if intersection:
        # logger.debug(f"Direct tag match found: Query={query_tags_set}, Chunk={chunk_tags_set}")
        return 1.0
    # --- End Key Change ---

    # If no direct match, calculate Jaccard and potentially add bonus for related tags
    union = query_tags_set.union(chunk_tags_set)
    jaccard_sim = len(intersection) / len(union) if union > 0 else 0.0 # Will be 0 if no intersection
    similarity_score = config.get("jaccard_weight", 0.5) * jaccard_sim # Lower default weight for Jaccard if direct match is prioritized

    bonus = 0.0
    if tag_graph_accessor:
        for qt_id in query_tags_set:
            for ct_id in chunk_tags_set:
                relation = tag_graph_accessor.get_parent_child_relationship(qt_id, ct_id)
                if relation:
                    bonus += config.get("parent_child_bonus", 0.1) # Lower bonus if direct match is primary goal
                    # Limit total bonus?
                # Add check for dependency relationships if implemented
                # dep_relation = tag_graph_accessor.get_dependency_relationship(qt_id, ct_id)
                # if dep_relation: bonus += config.get("dependency_bonus", 0.05)

    final_score = similarity_score + bonus
    return min(final_score, 1.0) # Ensure score doesn't exceed 1.0

async def calculate_t_cus_score( 
    chunk_content: str,
    chunk_metadata: Dict[str, Any],
    semantic_similarity_score: float, # Score from initial vector search (0-1, higher is better)
    query_embedding: Optional[List[float]], # Precomputed query embedding - Can be removed if not used
    chunk_embedding: Optional[List[float]], # Optional precomputed chunk embedding - Can be removed if not used
    tag_graph_accessor: Optional[TagGraphAccessor],
    embedding_model_instance: Optional[Any], # Can be removed if not used
    query_tags_tq_ids: Optional[List[int]] = None, # NEW parameter
    alpha: float = NEW_T_CUS_ALPHA, # Use new weight
    beta: float = NEW_T_CUS_BETA,   # Use new weight
    gamma: float = NEW_T_CUS_GAMMA, # Use new weight
    structural_weights_map: Dict = STRUCTURAL_WEIGHTS,
    tag_sim_config: Dict = TAG_SIMILARITY_CONFIG
) -> float:
    """
    Calculates the Tag-aware Context Utility Score (T-CUS) for a given chunk.
    Version 2: Prioritizes direct tag matches from query_tags_tq_ids.
    """
    # --- Score Tag (Using New Logic based on query_tags_tq_ids) ---
    score_tag = 0.0
    chunk_tag_ids = chunk_metadata.get('tag_ids', [])
    if not isinstance(chunk_tag_ids, list): chunk_tag_ids = []

    if query_tags_tq_ids is not None:
        # Use the new similarity function which prioritizes direct match with T(q)
        score_tag = _calculate_tag_similarity_v2(query_tags_tq_ids, chunk_tag_ids, tag_graph_accessor, tag_sim_config)
    else:
        logger.warning("calculate_t_cus_score called without query_tags_tq_ids.")
        score_tag = 0.0 # Default if T(q) is missing

    # --- Score Semantic (Passed in) ---
    score_sem = max(0.0, min(1.0, semantic_similarity_score))

    # --- Score Structural ---
    structural_type = chunk_metadata.get('structural_type', 'unknown')
    score_struct = structural_weights_map.get(structural_type, structural_weights_map.get('unknown', 0.1))

    # --- Calculate Final T-CUS (Corrected Weights) ---
    # beta (tag score) is now weighted higher
    total_t_cus_score = (alpha * score_sem) + (beta * score_tag) + (gamma * score_struct)
    
    # logger.debug(f"T-CUS Calc: ChunkIdx={chunk_metadata.get('chunk_index')}, Sem={score_sem:.2f}(w={alpha}), Tag={score_tag:.2f}(w={beta}), Struct={score_struct:.2f}(w={gamma}) -> T-CUS={total_t_cus_score:.3f}")
    
    return total_t_cus_score

def greedy_token_constrained_selection(
    candidate_chunks: List[Dict[str, Any]],
    token_limit: int = CONTEXT_TOKEN_LIMIT
) -> Tuple[str, List[Dict[str, Any]]]:
    scored_chunks_with_density = []
    for chunk_data in candidate_chunks:
        token_count = chunk_data.get('metadata', {}).get('token_count', 1)
        if token_count <= 0: token_count = 1
        density = chunk_data.get('t_cus_score', 0.0) / token_count
        scored_chunks_with_density.append({**chunk_data, "density": density})

    sorted_chunks = sorted(scored_chunks_with_density, key=lambda x: x["density"], reverse=True)
    selected_chunks_content = []
    selected_chunks_data = []
    current_token_count = 0
    for chunk_data in sorted_chunks:
        chunk_token_count = chunk_data.get('metadata', {}).get('token_count', 0)
        if chunk_token_count <= 0: continue
        if current_token_count + chunk_token_count <= token_limit:
            selected_chunks_content.append(chunk_data['content'])
            selected_chunks_data.append(chunk_data)
            current_token_count += chunk_token_count
    final_context_str = "\n\n".join(selected_chunks_content)
    logger.info(f"Greedy selection: {len(selected_chunks_data)} chunks selected, total tokens: {current_token_count}/{token_limit}")
    return final_context_str, selected_chunks_data

async def _illustrative_usage():
    logger.info("Starting illustrative usage of scoring_service...")
    query = "How to use feature X with module Y?"
    query_tag_ids_from_llm = [1, 5]
    candidate_chunks_from_vector_store = [
        {"content": "Feature X is a new component... associated with Tag 1, Tag 3.", "metadata": {"document_id": 101, "chunk_index":0, "tag_ids": [1, 3], "token_count": 50, "structural_type": "paragraph", "search_score": 0.85}},
        {"content": "Module Y documentation details... associated with Tag 5, Tag 6.", "metadata": {"document_id": 102, "chunk_index":0, "tag_ids": [5, 6], "token_count": 70, "structural_type": "title_l2", "search_score": 0.90}},
        {"content": "To use X with Y, first initialize Y... associated with Tag 1, Tag 5, Tag 7.", "metadata": {"document_id": 103, "chunk_index":0, "tag_ids": [1, 5, 7], "token_count": 120, "structural_type": "code_block", "search_score": 0.78}},
        {"content": "Old feature Z details... associated with Tag 99.", "metadata": {"document_id": 104, "chunk_index":0, "tag_ids": [99], "token_count": 80, "structural_type": "paragraph", "search_score": 0.30 }},
    ]
    mock_embedding_model = HuggingFaceEmbeddings(model_name=T_CUS_EMBEDDING_MODEL)
    tag_accessor = TagGraphAccessor() # No DB for this example
    scored_candidate_chunks = []
    for chunk_data in candidate_chunks_from_vector_store:
        t_cus = calculate_t_cus_score(
            chunk_content=chunk_data['content'], chunk_metadata=chunk_data['metadata'],
            semantic_similarity_score=chunk_data['metadata'].get('search_score', 0.0),
            query_embedding=None, chunk_embedding=None,
            tag_graph_accessor=tag_accessor, embedding_model_instance=mock_embedding_model,
            query_tags_tq_ids=query_tag_ids_from_llm
        )
        scored_candidate_chunks.append({**chunk_data, "t_cus_score": t_cus})
    for sc in scored_candidate_chunks:
        logger.info(f"Doc {sc['metadata']['document_id']} Chunk {sc['metadata']['chunk_index']} - T-CUS: {sc['t_cus_score']:.3f}")
    final_prompt_context, selected_chunks_info = greedy_token_constrained_selection(scored_candidate_chunks, token_limit=150)
    logger.info("\nSelected Context for LLM:")
    logger.info(final_prompt_context)
    logger.info("\nDetails of selected chunks:")
    for sc_info in selected_chunks_info:
        logger.info(f"  DocID: {sc_info['metadata']['document_id']}, ChunkIdx: {sc_info['metadata']['chunk_index']}, Score: {sc_info['t_cus_score']:.3f}, Density: {sc_info.get('density',0):.3f}")

if __name__ == '__main__':
    import asyncio
    logging.basicConfig(level=logging.INFO)
    # asyncio.run(_illustrative_usage())
    pass 