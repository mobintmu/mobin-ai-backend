import os
import json
import re
import requests
from collections import defaultdict
from typing import List, Dict, Set, Any
from dotenv import load_dotenv

load_dotenv()

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.avalai.ir/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "your-api-key")
MODEL_NAME = os.getenv("OPENAI_MODEL", "deepseek-v4-flash")
GRAPH_JSON_PATH = os.getenv("GRAPH_JSON_PATH", "./md/graphify-out/graph.json")


class GraphRAGRetriever:
    def __init__(self, graph_path: str):
        self.graph_path = graph_path
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.adjacency: Dict[str, Set[str]] = defaultdict(set)
        self.edge_labels: Dict[tuple, str] = {}
        self.hyperedges: List[Dict[str, Any]] = []
        self._load_graph()

    def _load_graph(self):
        """Loads and indexes nodes, binary links, and hyperedges."""
        with open(self.graph_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 1. Index Nodes
        for node in data.get("nodes", []):
            nid = node["id"]
            self.nodes[nid] = {
                "id": nid,
                "label": node.get("label", nid),
                "type": node.get("file_type", "concept"),
                "rationale": node.get("rationale", ""),
                "community": node.get("community_name", ""),
                "source_file": node.get("source_file", "")
            }

        # 2. Index Binary Edges
        for link in data.get("links", []):
            src, tgt = link["source"], link["target"]
            relation = link.get("relation", "RELATES_TO")
            self.adjacency[src].add(tgt)
            self.adjacency[tgt].add(src)
            self.edge_labels[(src, tgt)] = relation
            self.edge_labels[(tgt, src)] = relation

        # 3. Index Hyperedges (Higher-order system patterns)
        self.hyperedges = data.get("graph", {}).get("hyperedges", [])
        for hyper in self.hyperedges:
            members = hyper.get("nodes", [])
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    m1, m2 = members[i], members[j]
                    if m1 in self.nodes and m2 in self.nodes:
                        self.adjacency[m1].add(m2)
                        self.adjacency[m2].add(m1)

    def _find_seed_nodes(self, query: str) -> List[str]:
        """Finds entry-point nodes in the graph matching tokens in the query."""
        query_normalized = query.lower()
        matched = []

        for nid, node in self.nodes.items():
            label = node["label"].lower()
            # Match by exact name or substring presence
            if label in query_normalized or any(w in query_normalized for w in label.split() if len(w) > 3):
                matched.append(nid)

        return matched

    def traverse_subgraph(self, seeds: List[str], depth: int = 2, max_nodes: int = 15) -> Dict[str, Any]:
        """Performs BFS graph expansion from seed entities up to N hops."""
        visited: Set[str] = set(seeds)
        queue: List[tuple] = [(s, 0) for s in seeds]
        collected_edges: List[Dict[str, str]] = []
        collected_hyperedges: List[Dict[str, Any]] = []

        while queue and len(visited) < max_nodes:
            curr, curr_depth = queue.pop(0)
            if curr_depth >= depth:
                continue

            for neighbor in self.adjacency.get(curr, []):
                if neighbor not in self.nodes:
                    continue

                relation = self.edge_labels.get((curr, neighbor), "CONNECTED_TO")
                collected_edges.append({
                    "from": self.nodes[curr]["label"],
                    "relation": relation,
                    "to": self.nodes[neighbor]["label"]
                })

                if neighbor not in visited and len(visited) < max_nodes:
                    visited.add(neighbor)
                    queue.append((neighbor, curr_depth + 1))

        # Capture relevant hyperedges
        for hyper in self.hyperedges:
            members = set(hyper.get("nodes", []))
            if members.intersection(visited):
                collected_hyperedges.append({
                    "pattern": hyper.get("label"),
                    "components": [self.nodes[m]["label"] for m in members if m in self.nodes]
                })

        return {
            "entities": [self.nodes[nid] for nid in visited],
            "relationships": collected_edges[:25],
            "hyperedge_patterns": collected_hyperedges[:5]
        }

    def build_context_prompt(self, query: str, subgraph: Dict[str, Any]) -> str:
        """Formats the extracted graph topology into a structured LLM context prompt."""
        entities_text = "\n".join([
            f"- **{e['label']}** ({e['type']}) [Cluster: {e['community']}]: {e['rationale'] or 'Core domain component'}"
            for e in subgraph["entities"]
        ])

        relations_text = "\n".join([
            f"- ({rel['from']}) --[{rel['relation']}]--> ({rel['to']})"
            for rel in subgraph["relationships"]
        ])

        hyperedges_text = "\n".join([
            f"- **{h['pattern']}**: Connects [{', '.join(h['components'])}]"
            for h in subgraph["hyperedge_patterns"]
        ])

        return f"""You are an expert system architecture AI answering questions using the author's personal knowledge graph.

### Extracted Knowledge Graph Entities:
{entities_text if entities_text else "No specific entity nodes found."}

### Graph Relationships (Triples):
{relations_text if relations_text else "No direct binary links found."}

### Multi-Component Architectural Patterns:
{hyperedges_text if hyperedges_text else "None."}

### User Question:
{query}

Provide a comprehensive, highly technical, and direct answer based on the architecture graphs, patterns, and decisions documented above. Cite the specific components and pipelines where applicable."""


def query_graph_rag(user_query: str) -> str:
    retriever = GraphRAGRetriever(GRAPH_JSON_PATH)

    # 1. Discover seed nodes
    seeds = retriever._find_seed_nodes(user_query)
    if not seeds:
        print("Warning: No direct keyword match found in graph. Expanding to core hub entities.")
        seeds = ["concept_clickhouse", "concept_kafka", "concept_uber_fx", "uber_fx"]

    # 2. Traverse Subgraph
    subgraph = retriever.traverse_subgraph(seeds=seeds, depth=2, max_nodes=12)

    # 3. Build Graph-grounded Context
    prompt = retriever.build_context_prompt(user_query, subgraph)

    # 4. Query LLM Endpoint
    endpoint = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "You are a specialized technical architecture reasoning assistant."},
            {"role": "user", "content": prompt}
        ]
    }

    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=60)
        res_json = response.json()
        if "choices" in res_json and len(res_json["choices"]) > 0:
            return res_json["choices"][0]["message"]["content"]
        else:
            return f"API Error: {res_json}"
    except Exception as e:
        return f"Request failed: {e}"


if __name__ == "__main__":
    print("=== GraphRAG Architecture Assistant (Type 'exit' or Ctrl+C to quit) ===")
    
    while True:
        try:
            question = input("\nAsk a question: ").strip()
            if not question:
                continue
            if question.lower() in ("exit", "quit", "q"):
                print("Goodbye!")
                break

            print(f"\n--- Traversing Graph & Querying {MODEL_NAME} ---")
            answer = query_graph_rag(question)
            print("\n--- Model Response ---\n")
            print(answer)

        except (KeyboardInterrupt, EOFError):
            print("\nSession closed.")
            break