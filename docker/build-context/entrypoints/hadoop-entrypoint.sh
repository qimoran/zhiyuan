#!/usr/bin/env bash
set -euo pipefail

wait_for() {
  local host="$1"
  local port="$2"
  local name="${3:-$host:$port}"
  for _ in $(seq 1 90); do
    if nc -z "$host" "$port" >/dev/null 2>&1; then
      return 0
    fi
    echo "Waiting for ${name}..."
    sleep 2
  done
  echo "Timed out waiting for ${name}" >&2
  return 1
}

case "${1:-}" in
  namenode)
    mkdir -p /hadoop/dfs/name /hadoop/tmp
    if [ ! -d /hadoop/dfs/name/current ]; then
      hdfs namenode -format -force -nonInteractive
    fi
    exec hdfs namenode
    ;;
  datanode)
    mkdir -p /hadoop/dfs/data /hadoop/tmp
    wait_for namenode 9000 "HDFS NameNode"
    exec hdfs datanode
    ;;
  resourcemanager)
    exec yarn resourcemanager
    ;;
  nodemanager)
    wait_for resourcemanager 8032 "YARN ResourceManager"
    exec yarn nodemanager
    ;;
  bash|sh)
    exec "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
