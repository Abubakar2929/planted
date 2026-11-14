import importlib

import pytest

MODULES = [
    "contracts", "contracts.schemas",
    "planted", "planted.engine", "planted.engine.mock_engine",
    "planted.agent", "planted.agent.loop", "planted.agent.cache", "planted.agent.logger",
    "planted.providers", "planted.providers.gemini", "planted.providers.groq",
    "planted.guard", "planted.guard.core", "planted.guard.normalize", "planted.guard.cluster",
    "planted.guard.vote", "planted.guard.hedge",
    "planted.baselines", "planted.inspect_task", "planted.serve", "planted.cli",
    "data.generator", "data.generator.generate",
    "analysis", "analysis.score", "analysis.stats", "analysis.figures", "analysis.analyze",
    "run", "scripts.smoke_keys", "scripts.realweb_check",
]


@pytest.mark.parametrize("name", MODULES)
def test_import(name):
    importlib.import_module(name)
