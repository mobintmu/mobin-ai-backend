import json

import pytest

from scripts.knowledge import stage, validate


def test_manual_stage_validates_hashes_and_graph_references(tmp_path):
    source = tmp_path / "site"
    graph_dir = source / "src/data/kg/md/graphify-out"
    graph_dir.mkdir(parents=True)
    graph = {
        "nodes": [{"id": "kafka", "label": "Kafka"}, {"id": "clickhouse", "label": "ClickHouse"}],
        "links": [{"source": "kafka", "target": "clickhouse"}],
        "graph": {"hyperedges": []},
    }
    (graph_dir / "graph.json").write_text(json.dumps(graph))
    article_dir = source / "src/data/posts"
    article_dir.mkdir(parents=True)
    (article_dir / "kafka.json").write_text(
        json.dumps(
            {
                "slug": "kafka-pipeline",
                "title": "Kafka pipeline",
                "url": "https://mobinshaterian.com/blog/kafka-pipeline",
                "content": [{"type": "paragraph", "html": "<p>Use bounded batches.</p>"}],
            }
        )
    )
    releases = tmp_path / "releases"
    stage(source, releases)
    release = next(releases.iterdir())
    validate(release)
    articles = json.loads((release / "articles.json").read_text())
    assert articles[0]["content"] == "Use bounded batches."
    articles[0]["content"] = "tampered"
    (release / "articles.json").write_text(json.dumps(articles))
    with pytest.raises(ValueError, match="hash mismatch"):
        validate(release)
