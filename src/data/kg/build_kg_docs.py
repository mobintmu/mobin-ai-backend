import os
import glob
import json

# Current script folder: .../src/data/kg
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# Target output folder: .../src/data/kg/md
OUT_DIR = os.path.join(CURRENT_DIR, "md")
os.makedirs(OUT_DIR, exist_ok=True)

# Source data folder: .../src/data
SRC_DATA_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))

def write_md(filename, title, meta, body):
    filepath = os.path.join(OUT_DIR, f"{filename}.md")
    content = f"# {title}\n\n"
    for k, v in meta.items():
        if v:
            content += f"**{k}:** {v}\n"
    content += f"\n{body}\n"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

print(f"Reading source JSONs from: {SRC_DATA_DIR}")
print(f"Writing Markdown documents to: {OUT_DIR}")

# 1. Process individual articles in posts/
posts_dir = os.path.join(SRC_DATA_DIR, "posts")
if os.path.exists(posts_dir):
    for pf in glob.glob(os.path.join(posts_dir, "*.json")):
        try:
            with open(pf, "r", encoding="utf-8") as f:
                data = json.load(f)
            slug = os.path.splitext(os.path.basename(pf))[0]
            title = data.get("title") or data.get("name") or slug
            tags = ", ".join(data.get("tags", [])) if isinstance(data.get("tags"), list) else str(data.get("tags", ""))
            body = data.get("content") or data.get("markdown") or data.get("body") or data.get("description") or json.dumps(data, ensure_ascii=False, indent=2)
            write_md(f"post_{slug}", title, {"Type": "Article", "Tags": tags, "Category": data.get("category", "")}, body)
        except Exception as e:
            print(f"Skipping {pf}: {e}")

# 2. Process Array-based JSON files
array_files = {
    "github-projects.json": "Project",
    "youtube-videos.json": "YouTube Video",
    "aparat-videos.json": "Aparat Video",
    "virgool-posts.json": "Virgool Article",
    "posts.json": "Post Index"
}

for fname, entity_type in array_files.items():
    fpath = os.path.join(SRC_DATA_DIR, fname)
    if not os.path.exists(fpath):
        continue
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            items = json.load(f)
        if isinstance(items, dict):
            items = [items]
        
        for idx, item in enumerate(items):
            title = item.get("title") or item.get("name") or f"{entity_type} {idx+1}"
            safe_slug = "".join([c if c.isalnum() else "_" for c in title])[:40]
            desc = item.get("description") or item.get("content") or json.dumps(item, ensure_ascii=False, indent=2)
            tags = ", ".join(item.get("topics", []) or item.get("tags", []))
            write_md(f"{entity_type.lower().replace(' ', '_')}_{safe_slug}_{idx}", title, {"Type": entity_type, "Tags": tags, "URL": item.get("url") or item.get("link") or ""}, desc)
    except Exception as e:
        print(f"Skipping {fname}: {e}")

# 3. Process profile.json
profile_path = os.path.join(SRC_DATA_DIR, "profile.json")
if os.path.exists(profile_path):
    with open(profile_path, "r", encoding="utf-8") as f:
        pdata = json.load(f)
    write_md("profile", "Author Profile", {"Type": "Person"}, json.dumps(pdata, ensure_ascii=False, indent=2))

print(f"Done! All Markdown files created inside {OUT_DIR}")