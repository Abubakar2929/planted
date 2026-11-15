# UNTESTED SNIPPET — interface sketch (LangChain BaseDocumentCompressor around planted.guard)
from collections.abc import Sequence

from langchain_core.documents import BaseDocumentCompressor, Document

from planted import guard


class PlantedGuardCompressor(BaseDocumentCompressor):
    lang: str = "en"

    def compress_documents(self, documents: Sequence[Document], query: str, callbacks=None) -> Sequence[Document]:
        results = [{"url": d.metadata.get("source", d.metadata.get("url", str(i))), "title": d.metadata.get("title", ""),
                    "snippet": d.page_content[:300], "content": d.page_content, "rank": i + 1}
                   for i, d in enumerate(documents)]
        out = guard(query, results, self.lang)
        reordered = []
        for r in out.results:  # Guard reweights, never deletes: same documents, new order
            d = documents[r["rank"] - 1]
            meta = {**d.metadata, "planted_cluster_id": r.get("cluster_id"), "planted_guard_score": r.get("guard_score"),
                    "planted_summary": out.system_note, "planted_warnings": out.warnings}
            reordered.append(Document(page_content=d.page_content, metadata=meta))
        return reordered
