import argparse
import asyncio
import hashlib
import html
import json
import subprocess
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

import httpx
from sqlalchemy import func, select, text, update

from app.core.config import get_settings
from app.persistence.database import session_factory
from app.persistence.models import ArticleChunk, KnowledgeRelease
from app.providers.embeddings import EmbeddingGateway
from app.rag.retrieval import GraphIndex, allowed_url


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str):
        self.parts.append(data)


def plain_text(value: object) -> str:
    extractor = TextExtractor()
    extractor.feed(str(value))
    return html.unescape(" ".join(extractor.parts)).strip()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stage(source: Path, root: Path):
    graph_path = source / "src/data/kg/md/graphify-out/graph.json"
    graph_bytes = graph_path.read_bytes()
    graph = json.loads(graph_bytes)
    if not graph.get("nodes") or not graph.get("links"):
        raise ValueError("Graph is empty")
    articles = []
    for path in sorted((source / "src/data/posts").glob("*.json")):
        item = json.loads(path.read_text())
        if not all(item.get(field) for field in ("slug", "title", "url", "content")):
            continue
        if not allowed_url(item["url"]):
            continue
        content = "\n".join(
            plain_text(block.get("html", ""))
            for block in item["content"]
            if isinstance(block, dict)
        )
        if not content.strip():
            continue
        article = {
            "id": item["slug"],
            "title": item["title"],
            "url": item["url"],
            "content": content,
        }
        article["sha256"] = digest(json.dumps(article, sort_keys=True).encode())
        articles.append(article)
    if not articles:
        raise ValueError("No eligible articles found in source")
    version = datetime.now(UTC).strftime("%Y%m%d") + "." + digest(graph_bytes)[:12]
    target = root / version
    if target.exists():
        print(f"Existing release: {target}")
        return
    target.mkdir(parents=True)
    (target / "graph.json").write_bytes(graph_bytes)
    (target / "articles.json").write_text(json.dumps(articles, ensure_ascii=False))
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    previous_manifests = [
        json.loads(file.read_text())
        for file in root.glob("*/manifest.json")
        if file.parent.name != version
    ]
    baseline_nodes = max((item.get("node_count", 0) for item in previous_manifests), default=0)
    manifest = {
        "baseline_node_count": baseline_nodes,
        "version": version,
        "source_commit": commit,
        "copied_at": datetime.now(UTC).isoformat(),
        "graph_sha256": digest(graph_bytes),
        "node_count": len(graph["nodes"]),
        "link_count": len(graph["links"]),
        "articles": [
            {"id": row["id"], "url": row["url"], "sha256": row["sha256"]} for row in articles
        ],
    }
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"Staged {len(articles)} articles in {target}; active release unchanged")


def validate(path: Path):
    manifest = json.loads((path / "manifest.json").read_text())
    graph_bytes = (path / "graph.json").read_bytes()
    if digest(graph_bytes) != manifest["graph_sha256"]:
        raise ValueError("Graph hash mismatch")
    graph = GraphIndex.load(path / "graph.json", manifest["version"])
    articles = json.loads((path / "articles.json").read_text())
    if not articles:
        raise ValueError("Release has no articles")
    ids = [row["id"] for row in articles]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate article IDs")
    expected = {row["id"]: row for row in manifest["articles"]}
    if set(ids) != set(expected):
        raise ValueError("Manifest/article mismatch")
    for row in articles:
        if not all(
            row.get(field) for field in ("id", "title", "url", "content")
        ) or not allowed_url(row["url"]):
            raise ValueError("Invalid article metadata")
        check = {key: row[key] for key in ("id", "title", "url", "content")}
        if digest(json.dumps(check, sort_keys=True).encode()) != expected[row["id"]]["sha256"]:
            raise ValueError("Article hash mismatch")
    if len(graph.nodes) < max(1, manifest.get("baseline_node_count", 0) * 0.8):
        raise ValueError("Graph node count regression")
    print(f"Validated {path.name}: {len(graph.nodes)} nodes, {len(articles)} articles")


async def ingest(path: Path):
    validate(path)
    manifest = json.loads((path / "manifest.json").read_text())
    articles = json.loads((path / "articles.json").read_text())
    version = manifest["version"]
    async with session_factory() as session:
        if await session.get(KnowledgeRelease, version):
            print("Release already ingested")
            return
        old_rows = (
            await session.execute(
                select(
                    ArticleChunk.article_id, ArticleChunk.content_hash, ArticleChunk.embedding
                ).where(ArticleChunk.embedding.is_not(None))
            )
        ).all()
    cached = {
        (article_id, content_hash): embedding for article_id, content_hash, embedding in old_rows
    }
    prepared = []
    for article in articles:
        words = article["content"].split()
        for offset in range(0, len(words), 180):
            content = " ".join(words[offset : offset + 180])
            chunk_hash = digest(content.encode())
            chunk_id = digest(f"{version}:{article['id']}:{offset}:{chunk_hash}".encode())
            prepared.append(
                ArticleChunk(
                    id=chunk_id,
                    version=version,
                    article_id=article["id"],
                    title=article["title"],
                    url=article["url"],
                    content=content,
                    content_hash=chunk_hash,
                    embedding=cached.get((article["id"], chunk_hash)),
                )
            )
    changed = [chunk for chunk in prepared if chunk.embedding is None]
    settings = get_settings()
    if all((settings.embedding_base_url, settings.embedding_api_key, settings.embedding_model)):
        async with httpx.AsyncClient() as client:
            gateway = EmbeddingGateway(settings, client)
            for offset in range(0, len(changed), 32):
                batch = changed[offset : offset + 32]
                vectors = await gateway.embed([chunk.content for chunk in batch])
                for chunk, vector in zip(batch, vectors, strict=True):
                    chunk.embedding = vector
    elif settings.app_env == "production":
        raise ValueError("Production ingestion requires embedding configuration")
    async with session_factory() as session:
        async with session.begin():
            await session.execute(text("SELECT pg_advisory_xact_lock(740091)"))
            if await session.get(KnowledgeRelease, version):
                print("Release already ingested")
                return
            session.add(KnowledgeRelease(version=version, manifest=manifest, active=False))
            await session.flush()
            session.add_all(prepared)
            await session.flush()
            await session.execute(
                text(
                    "UPDATE article_chunks SET search_vector = "
                    "to_tsvector('simple', title || ' ' || content) WHERE version = :version"
                ),
                {"version": version},
            )
    print(f"Ingested {version}: {len(prepared)} chunks, {len(changed)} changed")


async def activate(version: str):
    root = get_settings().knowledge_root
    validate(root / version)
    async with session_factory() as session:
        async with session.begin():
            await session.execute(text("SELECT pg_advisory_xact_lock(740091)"))
            if not await session.get(KnowledgeRelease, version):
                raise ValueError("Release must be ingested first")
            chunks = await session.scalar(
                select(func.count(ArticleChunk.id)).where(ArticleChunk.version == version)
            )
            if not chunks:
                raise ValueError("Release has no indexed article chunks")
            if get_settings().app_env == "production":
                embedded = await session.scalar(
                    select(func.count(ArticleChunk.id)).where(
                        ArticleChunk.version == version,
                        ArticleChunk.embedding.is_not(None),
                    )
                )
                if embedded != chunks:
                    raise ValueError("Production release has unembedded article chunks")
            await session.execute(update(KnowledgeRelease).values(active=False))
            await session.execute(
                update(KnowledgeRelease)
                .where(KnowledgeRelease.version == version)
                .values(active=True)
            )
    print(f"Activated {version}; restart API to load immutable graph")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["stage", "validate", "ingest", "activate"])
    parser.add_argument("--source", type=Path)
    parser.add_argument("--version")
    args = parser.parse_args()
    root = get_settings().knowledge_root
    if args.command == "stage":
        if not args.source:
            parser.error("--source is required")
        stage(args.source, root)
    else:
        if not args.version:
            parser.error("--version is required")
        if args.command == "validate":
            validate(root / args.version)
        elif args.command == "ingest":
            asyncio.run(ingest(root / args.version))
        else:
            asyncio.run(activate(args.version))


if __name__ == "__main__":
    main()
