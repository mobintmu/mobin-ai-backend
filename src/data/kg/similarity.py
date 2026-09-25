import json
import math
from collections import defaultdict

GRAPH_PATH = "./md/graphify-out/graph.json"

with open(GRAPH_PATH, "r", encoding="utf-8") as f:
    graph_data = json.load(f)

# 1. Build adjacency and calculate degree of all concept nodes
adjacency = defaultdict(set)
node_communities = {}
article_nodes = []

for node in graph_data.get("nodes", []):
    nid = node["id"]
    ftype = node.get("file_type", "")
    node_communities[nid] = node.get("community")
    if ftype in ["document", "code", "paper"] or nid.startswith("post_"):
        article_nodes.append(nid)

for edge in graph_data.get("links", []):
    s, t = edge["source"], edge["target"]
    adjacency[s].add(t)
    adjacency[t].add(s)

for hyper in graph_data.get("graph", {}).get("hyperedges", []):
    members = hyper.get("nodes", [])
    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            adjacency[members[i]].add(members[j])
            adjacency[members[j]].add(members[i])

# 2. Weighted similarity (Adamic-Adar metric)
cleaned_relations = []

for i, src in enumerate(article_nodes):
    for dst in article_nodes[i + 1:]:
        shared = adjacency[src].intersection(adjacency[dst])
        if not shared:
            continue
        
        # Calculate Adamic-Adar score: sum of 1 / log(degree(common_neighbor))
        score = 0.0
        for neighbor in shared:
            deg = len(adjacency[neighbor])
            if deg > 1:
                score += 1.0 / math.log(deg)
        
        # Boost if sharing the exact community cluster
        if node_communities.get(src) is not None and node_communities.get(src) == node_communities.get(dst):
            score *= 1.35
        
        # Filter out noisy scores
        if score >= 0.4:
            cleaned_relations.append({
                "source": src,
                "target": dst,
                "weighted_score": round(score, 4),
                "shared_concepts": list(shared)
            })

cleaned_relations.sort(key=lambda x: x["weighted_score"], reverse=True)

with open("cleaned_article_relations.json", "w", encoding="utf-8") as out:
    json.dump(cleaned_relations, out, ensure_ascii=False, indent=2)

print(f"Generated {len(cleaned_relations)} high-confidence related pairs.")