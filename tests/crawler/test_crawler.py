import pytest
from unittest.mock import AsyncMock, MagicMock
from wargames.crawler.cve import NVDCrawler
from wargames.crawler.exploitdb import ExploitDBCrawler

@pytest.mark.asyncio
async def test_nvd_crawler_parses_response():
    mock_http = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "vulnerabilities": [{
            "cve": {
                "id": "CVE-2024-1234",
                "descriptions": [{"lang": "en", "value": "SQL injection in login form"}],
                "metrics": {"cvssMetricV31": [{"cvssData": {"baseScore": 8.5, "baseSeverity": "HIGH"}}]},
            }
        }]
    }
    mock_response.raise_for_status = MagicMock()
    mock_http.get.return_value = mock_response

    crawler = NVDCrawler(mock_http)
    results = await crawler.fetch(keyword="sql injection", max_results=1)
    assert len(results) == 1
    assert results[0]["cve_id"] == "CVE-2024-1234"
    assert results[0]["severity"] == "high"
    assert "sql injection" in results[0]["description"].lower()

@pytest.mark.asyncio
async def test_exploitdb_crawler_parses_csv():
    mock_http = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = (
        "id,file,description,date_published,author,platform,type,port\n"
        "12345,exploits/php/webapps/12345.txt,WordPress Plugin SQLi,2024-01-15,researcher,php,webapps,80\n"
    )
    mock_response.raise_for_status = MagicMock()
    mock_http.get.return_value = mock_response

    crawler = ExploitDBCrawler(mock_http)
    results = await crawler.fetch(max_results=1)
    assert len(results) == 1
    assert results[0]["cve_id"] == "EDB-12345"
    assert "WordPress" in results[0]["description"]
    assert results[0]["source"] == "exploitdb"

@pytest.mark.asyncio
async def test_nvd_crawler_stores_to_db():
    mock_http = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"vulnerabilities": [{
        "cve": {
            "id": "CVE-2024-5678",
            "descriptions": [{"lang": "en", "value": "XSS in admin panel"}],
            "metrics": {"cvssMetricV31": [{"cvssData": {"baseScore": 6.1, "baseSeverity": "MEDIUM"}}]},
        }
    }]}
    mock_response.raise_for_status = MagicMock()
    mock_http.get.return_value = mock_response

    mock_db = AsyncMock()
    crawler = NVDCrawler(mock_http)
    results = await crawler.fetch(keyword="xss", max_results=1)
    await crawler.store(mock_db, results)
    mock_db.save_cve.assert_called_once()

@pytest.mark.asyncio
async def test_nvd_crawler_retries_on_timeout():
    mock_http = AsyncMock()
    import httpx
    mock_success = MagicMock()
    mock_success.status_code = 200
    mock_success.json.return_value = {
        "vulnerabilities": [{
            "cve": {
                "id": "CVE-2024-9999",
                "descriptions": [{"lang": "en", "value": "Test"}],
                "metrics": {},
            }
        }]
    }
    mock_success.raise_for_status = MagicMock()
    mock_http.get.side_effect = [httpx.ReadTimeout("timeout"), mock_success]

    crawler = NVDCrawler(mock_http)
    results = await crawler.fetch(keyword="test", max_results=1)
    assert len(results) == 1
    assert results[0]["cve_id"] == "CVE-2024-9999"

@pytest.mark.asyncio
async def test_nvd_crawler_returns_empty_on_persistent_failure():
    mock_http = AsyncMock()
    import httpx
    mock_http.get.side_effect = httpx.ConnectError("down")

    crawler = NVDCrawler(mock_http)
    results = await crawler.fetch(keyword="test", max_results=1)
    assert results == []
