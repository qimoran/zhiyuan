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

mkdir -p /spark-events /opt/spark/work-dir

case "${1:-}" in
  master)
    exec "${SPARK_HOME}/bin/spark-class" org.apache.spark.deploy.master.Master \
      --host 0.0.0.0 \
      --port 7077 \
      --webui-port 8080
    ;;
  worker)
    wait_for spark-master 7077 "Spark Master"
    exec "${SPARK_HOME}/bin/spark-class" org.apache.spark.deploy.worker.Worker \
      spark://spark-master:7077 \
      --cores "${SPARK_WORKER_CORES:-2}" \
      --memory "${SPARK_WORKER_MEMORY:-2g}" \
      --webui-port 8081
    ;;
  bash|sh)
    exec "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
