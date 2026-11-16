# Local embedding and parity operations

The local provider uses `sentence-transformers/all-mpnet-base-v2` on CPU. It
produces normalized 768-dimensional vectors through the `Embedder` port. For
offline servers, pre-download the model into a local directory and set
`EMBEDDING_MODEL_PATH` to that directory before starting the application.

`python -m app.reembed --batch-size 32` updates both chunk tables in place.
It is disabled for `provider=gcp`; never run it against production. The
optional `--fast-path` drops and recreates the existing HNSW index during the
bulk update.

The fixed queries in `data/parity_queries.json` are evaluated by
`app.parity.run_parity`. The proposed release threshold is mean Jaccard@10
>= 0.70 and mean rank correlation >= 0.60, balancing retrieval stability with
the expected change in model representation.
