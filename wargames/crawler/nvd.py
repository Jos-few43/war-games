"""NVD API integration for cross-referencing discovered vulnerabilities.

This module provides NVD API integration to check discovered exploits
against known CVEs.
"""

import os
from dataclasses import dataclass

import httpx

NVD_API_BASE = 'https://services.nvd.nist.gov/rest/json/cves/2.0'


@dataclass
class NVDFinding:
    """NVD CVE match."""

    cve_id: str
    description: str
    severity: str | None
    cvss_score: float | None
    published: str


class NVDClient:
    """Client for NVD API to cross-reference vulnerabilities."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get('NVD_API_KEY', '')
        self.base_url = NVD_API_BASE

    def _headers(self) -> dict:
        headers = {'Accept': 'application/json'}
        if self.api_key:
            headers['apiKey'] = self.api_key
        return headers

    async def search_cve(
        self,
        keyword: str,
        max_results: int = 10,
    ) -> list[NVDFinding]:
        async with httpx.AsyncClient() as client:
            params = {'keywordSearch': keyword, 'resultsPerPage': max_results}
            try:
                resp = await client.get(
                    self.base_url,
                    headers=self._headers(),
                    params=params,
                    timeout=30.0,
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
            except Exception:
                return []

        results = []
        vulnerabilities = data.get('vulnerabilities', [])
        for vuln in vulnerabilities:
            cve_data = vuln.get('cve', {})
            cve_id = cve_data.get('id', 'UNKNOWN')

            descriptions = cve_data.get('descriptions', [])
            description = descriptions[0].get('value', '') if descriptions else ''

            metrics = cve_data.get('metrics', {})
            cvss_data = (
                metrics.get('cvssMetricV31', [])
                or metrics.get('cvssMetricV30', [])
                or metrics.get('cvssMetricV2', [])
            )
            if cvss_data:
                cvss_info = cvss_data[0].get('cvssData', {})
                severity = cvss_info.get('baseSeverity')
                cvss_score = cvss_info.get('baseScore')
            else:
                severity = None
                cvss_score = None

            published = cve_data.get('published', '')

            results.append(
                NVDFinding(
                    cve_id=cve_id,
                    description=description[:200],
                    severity=severity,
                    cvss_score=cvss_score,
                    published=published,
                )
            )

        return results

    async def check_cve_exists(self, cve_id: str) -> NVDFinding | None:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f'{self.base_url}?cveId={cve_id}',
                    headers=self._headers(),
                    timeout=30.0,
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()
            except Exception:
                return None

        vulnerabilities = data.get('vulnerabilities', [])
        if not vulnerabilities:
            return None

        vuln = vulnerabilities[0]
        cve_data = vuln.get('cve', {})
        cve_id = cve_data.get('id', 'UNKNOWN')

        descriptions = cve_data.get('descriptions', [])
        description = descriptions[0].get('value', '') if descriptions else ''

        metrics = cve_data.get('metrics', {})
        cvss_data = (
            metrics.get('cvssMetricV31', [])
            or metrics.get('cvssMetricV30', [])
            or metrics.get('cvssMetricV2', [])
        )
        if cvss_data:
            cvss_info = cvss_data[0].get('cvssData', {})
            severity = cvss_info.get('baseSeverity')
            cvss_score = cvss_info.get('baseScore')
        else:
            severity = None
            cvss_score = None

        published = cve_data.get('published', '')

        return NVDFinding(
            cve_id=cve_id,
            description=description[:200],
            severity=severity,
            cvss_score=cvss_score,
            published=published,
        )

    async def cross_reference_exploit(
        self,
        exploit_description: str,
        target: str,
    ) -> tuple[list[NVDFinding], bool]:
        keywords = [target.split('/')[-1]] if '/' in target else []
        keywords.extend([w for w in exploit_description.split() if len(w) > 5][:3])

        for keyword in keywords[:3]:
            matches = await self.search_cve(keyword, max_results=5)
            if matches:
                return matches, True

        return [], False
