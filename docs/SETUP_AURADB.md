# AuraDB setup
1. Go to https://console.neo4j.io and create a free AuraDB instance (Free tier is enough for a single subsystem).
2. Save the generated password immediately (it is shown once). Copy the connection URI (`neo4j+s://...`).
3. Put URI, user and password in `.env`.
4. Run `make schema`. In the Aura console run `SHOW INDEXES` and confirm `entity_names`, `decision_text`, `decision_embedding`, `comment_embedding` are ONLINE.
5. Free-tier limits apply (node and relationship caps). Scope to one subsystem and use `--limit` while developing.
6. For deployment, show the graph-native supersession edges, vector + full-text + traversal in one query path, NVL visualisation, and parameterised Cypher templates (no free-form text-to-Cypher).
