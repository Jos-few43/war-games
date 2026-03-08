from __future__ import annotations
from wargames.engine.draft import Resource


class ScenarioGenerator:
    DEFAULT_TARGET = (
        "A full-stack web application with API, database, authentication, "
        "and file storage. Standard security posture with common misconfigurations."
    )

    def generate_target(self, cve_resources: list[Resource]) -> str:
        """Generate a target description from drafted CVE resources."""
        cves = [r for r in cve_resources if r.category == "cve"]
        if not cves:
            return self.DEFAULT_TARGET

        vuln_list = "\n".join(
            f"- {cve.name}: {cve.description}" for cve in cves
        )
        return (
            f"A web application server with the following known vulnerabilities:\n"
            f"{vuln_list}\n\n"
            f"The server runs outdated software. Exploit the specific CVEs or "
            f"discover additional weaknesses."
        )
