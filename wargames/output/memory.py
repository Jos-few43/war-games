"""Qdrant vector store for War Games memory.

This module provides vector-based memory storage for rounds, strategies,
and discovered bugs using Qdrant for semantic search.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import AsyncIterator

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, Filter, FieldConditions, MatchValue

from wargames.models import RoundResult, BugReport, Strategy


class MemoryType(Enum):
    """Types of memory stored in the vector database."""

    ROUND = 'round'
    STRATEGY = 'strategy'
    BUG = 'bug'
    INSIGHT = 'insight'


@dataclass
class MemoryEntry:
    """A memory entry stored in the vector database."""

    id: str
    memory_type: MemoryType
    content: str
    round_number: int | None
    phase: str | None
    severity: str | None
    tags: list[str]
    metadata: dict
    created_at: datetime


class WarGamesMemory:
    """Vector-based memory store for War Games using Qdrant."""

    COLLECTIONS = {
        'wargames_rounds': {'description': 'Round results', 'vector_size': 768},
        'wargames_strategies': {'description': 'Strategy patterns', 'vector_size': 768},
        'wargames_bugs': {'description': 'Discovered bugs and exploits', 'vector_size': 768},
        'wargames_insights': {'description': 'Cross-session insights', 'vector_size': 768},
    }

    def __init__(
        self,
        host: str = 'localhost',
        port: int = 6333,
        grpc_port: int = 6334,
    ):
        self.client = QdrantClient(host=host, grpc_port=grpc_port)
        self._ensure_collections()

    def _ensure_collections(self):
        for name, config in self.COLLECTIONS.items():
            exists = self.client.collection_exists(name)
            if not exists:
                self.client.create_collection(
                    name,
                    vectors_config=VectorParams(
                        size=config['vector_size'],
                        distance=Distance.COSINE,
                    ),
                )

    def _generate_id(self, memory_type: MemoryType, round_num: int | None, title: str) -> str:
        ts = datetime.now().strftime('%Y%m%d%H%M%S')
        return f'{memory_type.value}:{round_num or 0}:{title[:20]}:{ts}'

    async def store_round(self, result: RoundResult, embedding: list[float]):
        phase_name = result.phase.name.lower()
        content = f'Round {result.round_number}: {result.outcome.value} - Red scored {result.red_score}/{result.blue_threshold}'

        self.client.upsert(
            'wargames_rounds',
            points=[
                {
                    'id': self._generate_id(MemoryType.ROUND, result.round_number, content),
                    'vector': embedding,
                    'payload': {
                        'memory_type': MemoryType.ROUND.value,
                        'round_number': result.round_number,
                        'phase': phase_name,
                        'outcome': result.outcome.value,
                        'red_score': result.red_score,
                        'blue_threshold': result.blue_threshold,
                        'content': content,
                        'tags': ['wargames', phase_name, 'round'],
                        'created_at': datetime.now().isoformat(),
                    },
                }
            ],
        )

    async def store_strategy(self, strategy: Strategy, embedding: list[float]):
        content = f'[{strategy.strategy_type}] {strategy.content}'
        round_num = getattr(strategy, 'round_number', None) or strategy.created_round

        self.client.upsert(
            'wargames_strategies',
            points=[
                {
                    'id': self._generate_id(MemoryType.STRATEGY, round_num, content),
                    'vector': embedding,
                    'payload': {
                        'memory_type': MemoryType.STRATEGY.value,
                        'round_number': round_num,
                        'strategy_type': strategy.strategy_type,
                        'team': strategy.team,
                        'win_rate': strategy.win_rate,
                        'usage_count': strategy.usage_count,
                        'content': content,
                        'tags': ['wargames', 'strategy'],
                        'created_at': datetime.now().isoformat(),
                    },
                }
            ],
        )

    async def store_bug(self, report: BugReport, embedding: list[float]):
        content = f'Bug Report: {report.title} - {report.severity.value} - {report.domain.value}'

        self.client.upsert(
            'wargames_bugs',
            points=[
                {
                    'id': self._generate_id(MemoryType.BUG, report.round_number, report.title),
                    'vector': embedding,
                    'payload': {
                        'memory_type': MemoryType.BUG.value,
                        'round_number': report.round_number,
                        'severity': report.severity.value,
                        'domain': report.domain.value,
                        'target': report.target,
                        'title': report.title,
                        'content': content,
                        'tags': ['wargames', 'bug', report.severity.value],
                        'created_at': datetime.now().isoformat(),
                    },
                }
            ],
        )

    async def store_insight(self, content: str, tags: list[str], embedding: list[float]):
        self.client.upsert(
            'wargames_insights',
            points=[
                {
                    'id': self._generate_id(MemoryType.INSIGHT, None, content[:30]),
                    'vector': embedding,
                    'payload': {
                        'memory_type': MemoryType.INSIGHT.value,
                        'content': content,
                        'tags': tags,
                        'created_at': datetime.now().isoformat(),
                    },
                }
            ],
        )

    async def search_similar(
        self,
        query_embedding: list[float],
        memory_type: MemoryType | None = None,
        limit: int = 5,
        round_number: int | None = None,
    ) -> list[MemoryEntry]:
        collections = (
            [f'wargames_{memory_type.value}'] if memory_type else list(self.COLLECTIONS.keys())
        )

        results = []
        for collection in collections:
            search_result = self.client.search(
                collection,
                query_vector=query_embedding,
                limit=limit,
            )

            for hit in search_result:
                payload = hit.payload
                results.append(
                    MemoryEntry(
                        id=hit.id,
                        memory_type=MemoryType(payload['memory_type']),
                        content=payload.get('content', ''),
                        round_number=payload.get('round_number'),
                        phase=payload.get('phase'),
                        severity=payload.get('severity'),
                        tags=payload.get('tags', []),
                        metadata=payload,
                        created_at=datetime.fromisoformat(payload['created_at']),
                    )
                )

        return sorted(results, key=lambda x: x.created_at, reverse=True)[:limit]

    async def get_round_context(self, round_number: int) -> list[MemoryEntry]:
        results = []
        for collection in ['wargames_rounds', 'wargames_strategies', 'wargames_bugs']:
            search_result = self.client.search(
                collection,
                query_vector=[0.0] * 768,
                limit=10,
                query_filter=Filter(
                    must=[
                        FieldConditions(
                            key='round_number',
                            match=MatchValue(value=round_number),
                        )
                    ]
                ),
            )
            for hit in search_result:
                payload = hit.payload
                results.append(
                    MemoryEntry(
                        id=hit.id,
                        memory_type=MemoryType(payload['memory_type']),
                        content=payload.get('content', ''),
                        round_number=payload.get('round_number'),
                        phase=payload.get('phase'),
                        severity=payload.get('severity'),
                        tags=payload.get('tags', []),
                        metadata=payload,
                        created_at=datetime.fromisoformat(payload['created_at']),
                    )
                )
        return results

    async def get_cve_intelligence(
        self, domain: str | None = None, limit: int = 20
    ) -> list[MemoryEntry]:
        results = []
        collection = 'wargames_bugs'

        search_result = self.client.search(
            collection,
            query_vector=[0.0] * 768,
            limit=limit,
        )

        for hit in search_result:
            payload = hit.payload
            if domain and payload.get('domain') != domain:
                continue
            results.append(
                MemoryEntry(
                    id=hit.id,
                    memory_type=MemoryType.BUG,
                    content=payload.get('content', ''),
                    round_number=payload.get('round_number'),
                    phase=payload.get('phase'),
                    severity=payload.get('severity'),
                    tags=payload.get('tags', []),
                    metadata=payload,
                    created_at=datetime.fromisoformat(payload['created_at']),
                )
            )
        return results

    def close(self):
        self.client.close()
