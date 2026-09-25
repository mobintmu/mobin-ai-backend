## Run Command

cd /home/mobin/Documents/mobinshaterian.com/src/data/kg

# 1. Rebuild Markdown inputs from src/data/*.json and src/data/posts/*.json
python3 build_kg_docs.py

# 2. Load your own API settings from .env, then build the graph
set -a
. ./.env
set +a

echo $OPENAI_BASE_URL
echo $OPENAI_API_KEY
echo $OPENAI_MODEL


graphify extract ./md --backend openai --model "$OPENAI_MODEL"

# 3. Optional: regenerate community labels and the readable graph report
graphify cluster-only ./md --backend openai --model "$OPENAI_MODEL"

# To ask questions through the experimental GraphRAG assistant:

python3 graph_rag.py

# For blog recommendations, there is a separate step:

python3 similarity.py
python3 build_related_posts.py

## All documents

cd /home/mobin/Documents/mobinshaterian.com/src/data/kg

export OPENAI_BASE_URL="https://api.avalai.ir/v1"
export OPENAI_API_BASE="https://api.avalai.ir/v1"
export OPENAI_API_KEY="aa-3mXXXXX"
export OPENAI_MODEL="deepseek-v4.1-flash"

# Load .env into the current subs hell and run graphify
env $(cat .env | xargs) graphify extract ./md --backend openai --model deepseek-v4.1-flash


## Human readable

cd /home/mobin/Documents/mobinshaterian.com/src/data/kg

env $(cat .env | xargs) graphify cluster-only ./md --backend openai --model deepseek-v4.1-flash

## Query 

cd /home/mobin/Documents/mobinshaterian.com/src/data/kg/md

# Find relationships connected to a specific technology
graphify query "ClickHouse"
graphify query "Kafka"


# Find relationships connected to a specific technology and return the results in a human-readable format

python3 graph_rag.py