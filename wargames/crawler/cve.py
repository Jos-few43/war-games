import httpx

class NVDCrawler:
    """Crawl NIST NVD API for CVE data."""
    BASE_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"

    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._http = http_client or httpx.AsyncClient(timeout=30.0)

    async def fetch(self, keyword: str = "", max_results: int = 20) -> list[dict]:
        params = {"resultsPerPage": max_results}
        if keyword:
            params["keywordSearch"] = keyword

        response = await self._http.get(self.BASE_URL, params=params)
        response.raise_for_status()
        data = response.json()

        results = []
        for vuln in data.get("vulnerabilities", []):
            cve = vuln.get("cve", {})
            cve_id = cve.get("id", "")
            desc = ""
            for d in cve.get("descriptions", []):
                if d.get("lang") == "en":
                    desc = d.get("value", "")
                    break

            severity = "unknown"
            metrics = cve.get("metrics", {})
            for metric_key in ["cvssMetricV31", "cvssMetricV30", "cvssMetricV2"]:
                metric_list = metrics.get(metric_key, [])
                if metric_list:
                    base_severity = metric_list[0].get("cvssData", {}).get("baseSeverity", "")
                    if base_severity:
                        severity = base_severity.lower()
                    break

            results.append({
                "cve_id": cve_id,
                "source": "nvd",
                "severity": severity,
                "domain": "code-vuln",
                "description": desc,
                "exploit_code": "",
                "fix_hint": "",
            })
        return results

    async def store(self, db, results: list[dict]):
        for r in results:
            await db.save_cve(r)
