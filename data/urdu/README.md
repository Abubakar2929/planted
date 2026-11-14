# data/urdu

**Owner:** B — see `PLAN.md` §2.

Urdu set: `data/questions/urdu60.jsonl` (60 test questions, parallel to English test questions by qid)
and Urdu pages in both banks (honest, official, filler, syndicated, T1 `wire`/`propaganda`/`neutral`,
and the Urdu halves of every T3 campaign). Written directly in Urdu; numbers in Western digits so answers
match by string; fictional names spelled from syllables with fixed Urdu forms.

**Review status: pending** (`review_status.json`). Workflow:

1. `python -m data.urdu.make_review_packet` writes `review_questions.csv` (60 rows: EN question and answer
   beside the UR ones, plus one honest and one planted UR page sentence) and `review_lexicon.csv` (every UR
   hedge marker and qualifier).
2. The reviewer fills `ok` (y/n), `correction` and `notes` in both files.
3. B applies corrections to `data/templates/main_ur.json`, `data/heldout/templates_ur.json` and
   `data/lexicons/hedge_ur.json`, regenerates, and runs
   `python -m data.urdu.make_review_packet --apply "<name>" --role author` (or `--role external`).

If an author reviews (allowed by PLAN.md), the paper says "checked by an author who is a native Urdu speaker", never "independently reviewed"; `review_status.json` records the role and the exact wording. Until it reads `"approved": true`, the paper describes the Urdu set as checked by the
authors only (PLAN.md kill rule: if no reviewer by Sat 14:00, 30 questions checked by a bilingual teammate,
labelled as such). The reviewer is acknowledged by name only with their consent.
