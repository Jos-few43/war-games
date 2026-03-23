"""Benchmark tests for performance testing."""

import pytest
import time
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock


class TestEnginePerformance:
    """Performance benchmarks for game engine."""

    @pytest.mark.benchmark
    def test_elo_calculation_performance(self):
        """Benchmark ELO rating calculations."""
        from wargames.engine.elo import calculate_elo

        start = time.perf_counter()
        for _ in range(10000):
            calculate_elo(1500, 1500, 1, 1)
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f'ELO calculation too slow: {elapsed:.3f}s'

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_strategy_retrieval_performance(self):
        """Benchmark strategy retrieval from database."""
        mock_db = AsyncMock()
        mock_db.get_strategies = AsyncMock(return_value=[])

        start = time.perf_counter()
        for _ in range(1000):
            await mock_db.get_strategies(team='red', phase=1, limit=5)
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f'Strategy retrieval too slow: {elapsed:.3f}s'


class TestLLMPerformance:
    """Performance benchmarks for LLM client."""

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_client_initialization(self):
        """Benchmark LLM client initialization."""
        from wargames.llm.client import LLMClient

        start = time.perf_counter()
        for _ in range(100):
            client = LLMClient(model='test', api_base='http://localhost:4000', api_key='test')
        elapsed = time.perf_counter() - start

        assert elapsed < 2.0, f'Client init too slow: {elapsed:.3f}s'


class TestDatabasePerformance:
    """Performance benchmarks for database operations."""

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_database_write_performance(self):
        """Benchmark database write operations."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        start = time.perf_counter()
        for i in range(1000):
            await mock_conn.execute(
                'INSERT INTO strategies VALUES (?, ?, ?, ?)', (i, 'red', 'attack', 'test')
            )
        elapsed = time.perf_counter() - start

        assert elapsed < 2.0, f'DB write too slow: {elapsed:.3f}s'
