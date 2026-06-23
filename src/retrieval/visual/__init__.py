"""Provider-free, offline-safe ColQwen2.5 visual retrieval tier.

Importing this package requires no GPU and no heavy ML SDK: all heavy SDK
imports (``torch``, ``colpali_engine``, ``qdrant_client``) live inside function
bodies, never at module load. Only counts/run_ids/identifiers/scores cross the
DTO and trace boundaries — never image bytes or page text.
"""
