set -u
env | grep -E '^(DPV4_API_KEY|EMBEDDING_API_KEY|LARK_API_KEY)=' | sed 's/=.*$/=<set>/' || true
