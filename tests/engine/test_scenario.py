import pytest
from wargames.engine.scenario import ScenarioGenerator
from wargames.engine.draft import Resource


def test_generate_target_from_cve():
    gen = ScenarioGenerator()
    cve_resources = [
        Resource("CVE-2021-44228", "cve", "Log4Shell: RCE via JNDI lookup in log4j"),
    ]
    target = gen.generate_target(cve_resources)
    assert "CVE-2021-44228" in target
    assert "Log4Shell" in target


def test_generate_target_no_cves_returns_default():
    gen = ScenarioGenerator()
    target = gen.generate_target([])
    assert "web application" in target.lower()


def test_generate_target_multiple_cves():
    gen = ScenarioGenerator()
    cves = [
        Resource("CVE-2021-44228", "cve", "Log4Shell RCE"),
        Resource("CVE-2021-41773", "cve", "Apache path traversal"),
    ]
    target = gen.generate_target(cves)
    assert "CVE-2021-44228" in target
    assert "CVE-2021-41773" in target


def test_generate_target_ignores_non_cve_resources():
    gen = ScenarioGenerator()
    resources = [
        Resource("fuzzer", "offensive", "Sends malformed inputs"),
        Resource("CVE-2021-44228", "cve", "Log4Shell RCE"),
    ]
    target = gen.generate_target(resources)
    assert "CVE-2021-44228" in target
    assert "fuzzer" not in target
