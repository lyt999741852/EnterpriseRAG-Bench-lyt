# Server Elasticsearch

This deployment is the isolated Elasticsearch service for EnterpriseRAG-Bench.

- Image: Elasticsearch 8.19.12
- Endpoint on the server: `http://127.0.0.1:9200`
- Persistent data: `/opt/enterprise-rag-es/data`
- Container: `enterprise-rag-es`
- Heap / container cap: 8 GiB / 16 GiB
- CPU cap: 8 cores
- Security: the unauthenticated endpoint is bound to loopback only

Start and initialize:

```sh
docker compose -f /opt/enterprise-rag-es/docker-compose.yml up -d
/opt/enterprise-rag-es/init-indices.sh
```

Check status:

```sh
docker compose -f /opt/enterprise-rag-es/docker-compose.yml ps
curl --fail http://127.0.0.1:9200/_cluster/health?pretty
```

The initial vector index is `enterprise-rag-bge-small-v1`, exposed through the
stable alias `enterprise-rag-bge-small`. Its 384-dimensional vector mapping
matches `BAAI/bge-small-en-v1.5` in `configs/full.yaml`.

For access from another machine, use an SSH tunnel instead of publishing the
unauthenticated port:

```sh
ssh -L 9200:127.0.0.1:9200 root@10.72.100.29
```
