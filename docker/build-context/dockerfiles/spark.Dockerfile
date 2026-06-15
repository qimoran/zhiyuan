FROM eclipse-temurin:8-jre-jammy

ARG SPARK_VERSION=3.5.1
ARG SPARK_DOWNLOAD_URL=https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop3.tgz
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash curl netcat-openbsd procps python3 python3-pip tini \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fSL "${SPARK_DOWNLOAD_URL}" -o /tmp/spark.tgz \
    && tar -xzf /tmp/spark.tgz -C /opt \
    && ln -s /opt/spark-${SPARK_VERSION}-bin-hadoop3 /opt/spark \
    && rm /tmp/spark.tgz \
    && mkdir -p /spark-events /opt/spark/work-dir

ENV JAVA_HOME=/opt/java/openjdk
ENV SPARK_HOME=/opt/spark
ENV PYSPARK_PYTHON=python3
ENV PATH="${SPARK_HOME}/bin:${SPARK_HOME}/sbin:${PATH}"

COPY config/hadoop/core-site.xml /opt/spark/conf/core-site.xml
COPY config/hadoop/hdfs-site.xml /opt/spark/conf/hdfs-site.xml
COPY config/spark/spark-defaults.conf /opt/spark/conf/spark-defaults.conf
COPY config/spark/hive-site.xml /opt/spark/conf/hive-site.xml
COPY entrypoints/spark-entrypoint.sh /usr/local/bin/spark-entrypoint

RUN chmod +x /usr/local/bin/spark-entrypoint

WORKDIR /opt/spark/work-dir
ENTRYPOINT ["tini", "--", "spark-entrypoint"]
