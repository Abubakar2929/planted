# OWNER: C — see PLAN.md §2 (written by A; A never opened data/generator or data/heldout)
"""Guard thresholds. Tuned on dev20 only (scripts/eval_guard.py --tune) and frozen before any test or
held-out evaluation; see docs/guard_thresholds.md. Do not change after the prereg-v2 tag (AGENTS.md §8)."""

from __future__ import annotations

import hashlib
import json

TAU_CONTENT = 0.4        # MinHash Jaccard on answer-masked shingles -> content edge
TAU_EMBED = 0.92         # embedding cosine on answer-masked text -> edge, only with a weak provenance signal
TAU_PARA = None          # variant P (embedding edge with no provenance requirement); None = OFF
GATE_MARGIN = 1          # CONTESTED when the top two answers' origin counts differ by <= this
MIN_ORIGINS = 2          # DATA_VOID when the top answer has fewer independent origins
NUM_PERM = 128           # MinHash permutations
MINHASH_SEED = 1         # datasketch MinHash seed
EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

FROZEN = True


def values() -> dict:
    return {"TAU_CONTENT": TAU_CONTENT, "TAU_EMBED": TAU_EMBED, "TAU_PARA": TAU_PARA,
            "GATE_MARGIN": GATE_MARGIN, "TIE_BREAK": "rank",
            "MIN_ORIGINS": MIN_ORIGINS, "NUM_PERM": NUM_PERM, "MINHASH_SEED": MINHASH_SEED,
            "EMBED_MODEL": EMBED_MODEL}


CONFIG_HASH = hashlib.sha256(json.dumps(values(), sort_keys=True).encode("utf-8")).hexdigest()
