# UNTESTED SNIPPET — interface sketch (LlamaIndex BaseNodePostprocessor around planted.guard)
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.schema import NodeWithScore, QueryBundle

from planted import guard


class PlantedGuardPostprocessor(BaseNodePostprocessor):
    lang: str = "en"

    def _postprocess_nodes(self, nodes: list[NodeWithScore], query_bundle: QueryBundle | None = None):
        results = [{"url": n.node.metadata.get("url", n.node.node_id), "title": n.node.metadata.get("title", ""),
                    "snippet": n.node.get_content()[:300], "content": n.node.get_content(), "rank": i + 1}
                   for i, n in enumerate(nodes)]
        out = guard(query_bundle.query_str if query_bundle else "", results, self.lang)
        reordered = []
        for r in out.results:  # Guard reweights, never deletes: same items, new order
            n = nodes[r["rank"] - 1]
            n.node.metadata.update(planted_cluster_id=r.get("cluster_id"), planted_guard_score=r.get("guard_score"),
                                   planted_summary=out.system_note, planted_warnings=out.warnings)
            reordered.append(n)
        return reordered
