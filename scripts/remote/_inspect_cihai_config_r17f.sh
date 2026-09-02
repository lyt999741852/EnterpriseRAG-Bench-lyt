set -u
sed -n '140,165p' /data01/cihai/cihai-embedding-v3/deployment.yaml
echo '=== model mounts ==='
find /data01/k8s-pv/models /data04/xuepeng/models /data07/yangrx/cihai_deploy_models -maxdepth 3 -type f -name config.json 2>/dev/null | head -40 || true
