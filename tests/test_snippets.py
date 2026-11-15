"""docs/snippets: always syntax-checked; imported and exercised (fake guard) only if the library is installed."""

import importlib.util
from pathlib import Path

import pytest

SNIPPETS = Path(__file__).resolve().parents[1] / "docs" / "snippets"
FILES = {"llamaindex_postprocessor.py": "llama_index.core", "langchain_compressor.py": "langchain_core"}


@pytest.mark.parametrize("name", list(FILES))
def test_snippet_compiles_and_is_marked_untested(name):
    src = (SNIPPETS / name).read_text(encoding="utf-8")
    assert src.startswith("# UNTESTED SNIPPET — interface sketch")
    compile(src, name, "exec")
    assert "from planted import guard" in src


def _load(name):
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), SNIPPETS / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_guard(query, results, lang="en"):
    from contracts.schemas import GuardResult

    rs = [{**r, "cluster_id": 0, "guard_score": 1.0} for r in reversed(results)]
    return GuardResult(results=rs, system_note="Answer X: 2 pages / 1 origin", warnings=["DATA_VOID"], hedge_floor=None)


def test_llamaindex_postprocessor():
    pytest.importorskip("llama_index.core")
    from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

    mod = _load("llamaindex_postprocessor.py")
    mod.guard = _fake_guard
    nodes = [NodeWithScore(node=TextNode(text=f"page {i}", metadata={"url": f"https://p{i}.example"}), score=1.0)
             for i in range(2)]
    out = mod.PlantedGuardPostprocessor().postprocess_nodes(nodes, QueryBundle("q"))
    assert [n.node.metadata["url"] for n in out] == ["https://p1.example", "https://p0.example"]
    assert out[0].node.metadata["planted_summary"].startswith("Answer X")


def test_langchain_compressor():
    pytest.importorskip("langchain_core")
    from langchain_core.documents import Document

    mod = _load("langchain_compressor.py")
    mod.guard = _fake_guard
    docs = [Document(page_content=f"page {i}", metadata={"source": f"https://p{i}.example"}) for i in range(2)]
    out = mod.PlantedGuardCompressor().compress_documents(docs, "q")
    assert [d.metadata["source"] for d in out] == ["https://p1.example", "https://p0.example"]
    assert out[0].metadata["planted_warnings"] == ["DATA_VOID"]
