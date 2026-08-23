"""
Tools for Multi-Agent Customer Support Crew.
- kb_search: TF-IDF/bag-of-words retrieval over articles.csv (SAD ADR-13)
- ticket_stub: In-memory stub ticket creation
"""
import os
import csv
import uuid
import re
from typing import List, Dict
from crewai.tools import BaseTool
from pydantic import Field
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np


class KBSearchTool(BaseTool):
    """
    Knowledge Base Search Tool using TF-IDF/bag-of-words cosine similarity.
    Searches backend/kb/articles.csv with similarity floor from KB_SIMILARITY_FLOOR env var.
    """
    name: str = "kb_search"
    description: str = (
        "Search the B-Mobile knowledge base for relevant FAQ articles. "
        "Provide a query string and receive grounded passages with citations. "
        "Returns passages above similarity threshold or gap=true if none found."
    )
    
    # Pydantic fields with defaults
    kb_dir: str = Field(default="backend/kb")
    kb_file: str = Field(default="articles.csv")
    similarity_floor: float = Field(default=0.35)
    
    def __init__(self, **kwargs):
        # Load from env vars or use defaults
        kb_dir = os.getenv("KB_DIR", "backend/kb")
        kb_file = os.getenv("KB_FILE", "articles.csv")
        similarity_floor = float(os.getenv("KB_SIMILARITY_FLOOR", "0.35"))
        
        super().__init__(
            kb_dir=kb_dir,
            kb_file=kb_file,
            similarity_floor=similarity_floor,
            **kwargs
        )
        
        # Non-Pydantic state (not part of the model schema)
        object.__setattr__(self, 'articles', [])
        object.__setattr__(self, 'vectorizer', None)
        object.__setattr__(self, 'tfidf_matrix', None)
        object.__setattr__(self, '_loaded', False)
    
    def _load_kb(self):
        """Load articles.csv and build TF-IDF index."""
        kb_path = os.path.join(self.kb_dir, self.kb_file)
        
        if not os.path.exists(kb_path):
            raise FileNotFoundError(f"KB file not found: {kb_path}")
        
        with open(kb_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            self.articles = list(reader)
        
        if not self.articles:
            raise ValueError(f"No articles found in {kb_path}")
        
        # Build TF-IDF index over title + body
        corpus = [f"{article['title']} {article['body']}" for article in self.articles]
        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words='english',
            max_features=500,
            ngram_range=(1, 2)
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(corpus)
    
    def _run(self, query: str, top_k: int = 3) -> str:
        """
        Search KB and return JSON string with passages, citations, and gap flag.
        
        Args:
            query: Search query string
            top_k: Maximum number of passages to return
            
        Returns:
            JSON string with structure matching RetrieverOutput schema
        """
        # Lazy load KB on first use
        if not self._loaded:
            self._load_kb()
            self._loaded = True
            
        if not query or not query.strip():
            return '{"passages": [], "citations": [], "gap": true}'
        
        # Transform query to TF-IDF vector
        query_vec = self.vectorizer.transform([query])
        
        # Compute cosine similarities
        similarities = cosine_similarity(query_vec, self.tfidf_matrix).flatten()
        
        # Get top k indices above floor
        top_indices = np.argsort(similarities)[::-1][:top_k]
        results = []
        
        for idx in top_indices:
            score = float(similarities[idx])
            if score >= self.similarity_floor:
                article = self.articles[idx]
                # Create snippet from body (first 200 chars)
                body = article['body']
                snippet = body[:200] + "..." if len(body) > 200 else body
                
                results.append({
                    "title": article['title'],
                    "snippet": snippet,
                    "score": round(score, 3)
                })
        
        gap = len(results) == 0
        
        # Build citations list (same as passages but without scores)
        citations = [{"title": r["title"], "snippet": r["snippet"]} for r in results]
        
        # Return JSON matching RetrieverOutput
        output = {
            "passages": results,
            "citations": citations,
            "gap": gap
        }
        
        import json
        return json.dumps(output, indent=2)


class TicketStubTool(BaseTool):
    """
    Stub ticket creation tool for escalations.
    Creates in-memory stub ticket with STUB- prefix.
    """
    name: str = "ticket_stub"
    description: str = (
        "Create a stub support ticket for escalated cases. "
        "Accepts escalation context and returns a stub ticket ID. "
        "This is a no-op stub for MVP - no live ticketing system integration."
    )
    
    def _run(self, context: str = "") -> str:
        """
        Create stub ticket and return ticket ID.
        
        Args:
            context: Escalation context (optional, not persisted in MVP)
            
        Returns:
            Stub ticket ID string (STUB-{uuid})
        """
        ticket_id = f"STUB-{uuid.uuid4().hex[:8].upper()}"
        
        # In MVP, we just return the ID without persistence
        # Future: integrate with Zendesk/Intercom/etc.
        
        return ticket_id


# Tool instances for crew configuration
kb_search_tool = KBSearchTool()
ticket_stub_tool = TicketStubTool()
