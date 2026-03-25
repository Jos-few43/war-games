import asyncio
from typing import Any

import httpx


class CVSSData:
    """CVSS scoring data for a vulnerability.

    Attributes:
        base_score: CVSS base score (0.0-10.0)
        base_severity: Severity level (low, medium, high, critical)
        temporal_score: Temporal score if available
        exploitability_score: Exploitability subscore
        impact_score: Impact subscore
        vector_string: CVSS vector string
    """

    def __init__(
        self,
        base_score: float = 0.0,
        base_severity: str = 'unknown',
        temporal_score: float | None = None,
        exploitability_score: float = 0.0,
        impact_score: float = 0.0,
        vector_string: str = '',
    ):
        self.base_score = base_score
        self.base_severity = base_severity
        self.temporal_score = temporal_score
        self.exploitability_score = exploitability_score
        self.impact_score = impact_score
        self.vector_string = vector_string

    def to_dict(self) -> dict[str, Any]:
        return {
            'cvss_base_score': self.base_score,
            'cvss_base_severity': self.base_severity,
            'cvss_temporal_score': self.temporal_score,
            'cvss_exploitability_score': self.exploitability_score,
            'cvss_impact_score': self.impact_score,
            'cvss_vector_string': self.vector_string,
        }


class NVDCrawler:
    """Crawl NIST NVD API for CVE data with CVSS scoring."""

    BASE_URL = 'https://services.nvd.nist.gov/rest/json/cves/2.0'
    MAX_RETRIES = 3
    RETRY_BACKOFF = 2.0

    # Keywords for vulnerability categorization
    DOMAIN_KEYWORDS = {
        'prompt-injection': ['prompt injection', 'llm', 'language model', 'chatbot'],
        'code-vuln': ['buffer overflow', 'sql injection', 'xss', 'rce', 'remote code'],
        'config': ['misconfiguration', 'default password', 'weak config'],
        'social-engineering': ['phishing', 'social engineering', 'pretexting'],
    }

    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._http = http_client or httpx.AsyncClient(timeout=30.0)

    def _categorize_vulnerability(self, description: str) -> str:
        """Categorize vulnerability by domain based on description keywords."""
        desc_lower = description.lower()
        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            for keyword in keywords:
                if keyword in desc_lower:
                    return domain
        return 'code-vuln'  # Default category

    def _extract_cvss_data(self, cve: dict[str, Any]) -> CVSSData:
        """Extract CVSS scoring data from CVE metrics."""
        metrics = cve.get('metrics', {})

        for metric_key in ['cvssMetricV31', 'cvssMetricV30']:
            metric_list = metrics.get(metric_key, [])
            if metric_list:
                metric = metric_list[0]
                cvss_data = metric.get('cvssData', {})

                base_score = float(cvss_data.get('baseScore', 0.0))
                base_severity = cvss_data.get('baseSeverity', 'UNKNOWN').lower()
                temporal_score = metric.get('temporalScore')
                if temporal_score is not None:
                    temporal_score = float(temporal_score)
                exploitability_score = float(metric.get('exploitabilityScore', 0.0))
                impact_score = float(metric.get('impactScore', 0.0))
                vector_string = cvss_data.get('vectorString', '')

                return CVSSData(
                    base_score=base_score,
                    base_severity=base_severity,
                    temporal_score=temporal_score,
                    exploitability_score=exploitability_score,
                    impact_score=impact_score,
                    vector_string=vector_string,
                )

        return CVSSData()

    def _check_exploit_availability(self, cve: dict[str, Any]) -> dict[str, Any]:
        """Check if exploits are available for this CVE."""
        references = cve.get('references', [])

        exploit_indicators = {
            'exploit_available': False,
            'exploit_in_metasploit': False,
            'exploit_in_exploitdb': False,
            'poc_available': False,
        }

        for ref in references:
            url = ref.get('url', '').lower()
            tags = [t.lower() for t in ref.get('tags', [])]

            if 'exploit' in tags or 'proof-of-concept' in tags:
                exploit_indicators['exploit_available'] = True

            if 'metasploit' in url:
                exploit_indicators['exploit_in_metasploit'] = True

            if 'exploit-db' in url:
                exploit_indicators['exploit_in_exploitdb'] = True

            if 'poc' in url or 'proof' in url:
                exploit_indicators['poc_available'] = True

        return exploit_indicators

    async def fetch(self, keyword: str = '', max_results: int = 20) -> list[dict[str, Any]]:
        params = {'resultsPerPage': max_results}
        if keyword:
            params['keywordSearch'] = keyword  # type: ignore[assignment]

        for attempt in range(self.MAX_RETRIES):
            try:
                response = await self._http.get(self.BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()
                return self._parse(data)
            except (httpx.TimeoutException, httpx.ConnectError):
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_BACKOFF * (attempt + 1))
            except httpx.HTTPStatusError:
                return []
        return []

    def _parse(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        results = []
        for vuln in data.get('vulnerabilities', []):
            cve = vuln.get('cve', {})
            cve_id = cve.get('id', '')
            desc = ''
            for d in cve.get('descriptions', []):
                if d.get('lang') == 'en':
                    desc = d.get('value', '')
                    break

            cvss_data = self._extract_cvss_data(cve)
            domain = self._categorize_vulnerability(desc)
            exploit_info = self._check_exploit_availability(cve)

            results.append(
                {
                    'cve_id': cve_id,
                    'source': 'nvd',
                    'severity': cvss_data.base_severity,
                    'domain': domain,
                    'description': desc,
                    'exploit_code': '',
                    'fix_hint': '',
                    **cvss_data.to_dict(),
                    **exploit_info,
                }
            )
        return results

    async def store(self, db: Any, results: list[dict[str, Any]]) -> None:
        for r in results:
            await db.save_cve(r)
