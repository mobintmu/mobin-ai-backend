import json
import re
from collections import defaultdict

INPUT_PATH = "article_similarities.json"
OUTPUT_PATH = "related_posts.json"
MAX_RECOMMENDATIONS = 4

def clean_slug(node_id: str) -> str:
    """Normalize internal graph identifiers into URL slugs."""
    # Strip common graph prefixes
    slug = re.sub(r'^(post_index_|post_|project_project_1_0_|project_)', '', node_id)
    # Strip trailing hashes/indices if needed, or convert underscores to hyphens
    slug = slug.replace('_', '-').lower()
    return slug

with open(INPUT_PATH, "r", encoding="utf-8") as f:
    relations = json.load(f)

# Group similarities by source and target symmetrically
graph_map = defaultdict(lambda: defaultdict(float))

for item in relations:
    src = clean_slug(item["source"])
    tgt = clean_slug(item["target"])
    score = item.get("weighted_score", item.get("score", 0))

    if src == tgt:
        continue

    # Keep the highest score between pairs
    if score > graph_map[src][tgt]:
        graph_map[src][tgt] = score
    if score > graph_map[tgt][src]:
        graph_map[tgt][src] = score

# Build top-N mapping
final_mapping = {}

for slug, neighbors in graph_map.items():
    # Sort neighbors by score descending
    sorted_neighbors = sorted(neighbors.items(), key=lambda x: x[1], reverse=True)
    final_mapping[slug] = [target for target, _ in sorted_neighbors[:MAX_RECOMMENDATIONS]]

with open(OUTPUT_PATH, "w", encoding="utf-8") as out:
    json.dump(final_mapping, out, ensure_ascii=False, indent=2)

print(f"Generated {len(final_mapping)} article mappings in {OUTPUT_PATH}")