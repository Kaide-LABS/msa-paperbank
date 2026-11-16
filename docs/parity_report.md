# Embedding parity report

No populated local corpus was available for this build, so no database-backed
measurement is claimed here. The reproducible harness is `app.parity` and the
newly authored query set is `data/parity_queries.json`; it compares the same
cosine-distance top-k ordering used by live retrieval.

Proposed pass threshold: mean Jaccard@10 >= 0.70 and mean rank correlation >=
0.60. This preserves most result overlap while allowing representation-level
variation. An operator must run and append the per-query results and means on a
seeded/local corpus after migration. The authoritative post-migration run is
never performed against GCP production by this phase.
