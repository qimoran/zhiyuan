#!/usr/bin/env bash
set -euo pipefail

wait_for() {
  local host="$1"
  local port="$2"
  local name="${3:-$host:$port}"
  for _ in $(seq 1 120); do
    if nc -z "$host" "$port" >/dev/null 2>&1; then
      return 0
    fi
    echo "Waiting for ${name}..."
    sleep 2
  done
  echo "Timed out waiting for ${name}" >&2
  return 1
}

render_hive_site() {
  : "${HIVE_DB_USER:=hive}"
  : "${HIVE_DB_PASSWORD:=hive123456}"
  sed \
    -e "s|__HIVE_DB_USER__|${HIVE_DB_USER}|g" \
    -e "s|__HIVE_DB_PASSWORD__|${HIVE_DB_PASSWORD}|g" \
    /opt/hive/conf/hive-site.xml.template > /opt/hive/conf/hive-site.xml
}

prepare_hdfs_dirs() {
  wait_for namenode 9000 "HDFS NameNode"
  hdfs dfs -mkdir -p /tmp /tmp/hive /user/hive/warehouse || true
  hdfs dfs -chmod -R 1777 /tmp || true
  hdfs dfs -chmod -R 1777 /tmp/hive || true
  hdfs dfs -chmod -R 1777 /user/hive/warehouse || true
}

render_hive_site

case "${1:-}" in
  metastore)
    wait_for mysql 3306 "MySQL"
    prepare_hdfs_dirs
    if ! schematool -dbType mysql -info >/tmp/hive-schema-info.log 2>&1; then
      schematool -dbType mysql -initSchema
    fi
    exec hive --service metastore
    ;;
  hiveserver2)
    wait_for hive-metastore 9083 "Hive Metastore"
    exec hive --service hiveserver2
    ;;
  bash|sh)
    exec "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
