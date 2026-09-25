# Manual knowledge releases

Run `make knowledge-stage SOURCE_SITE=/path/to/mobinshaterian.com` after reviewing the website source. This copies only the accepted graph and article text/metadata to a new immutable release. Review its `manifest.json`, run `make knowledge-validate VERSION=...`, then `make knowledge-ingest VERSION=...` and `make knowledge-activate VERSION=...`. Restart the API to load the active graph. Re-activate the previous ingested version to roll back. Never copy Graphify caches, `.env`, `.git`, or raw contact lists.
