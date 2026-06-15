FROM eclipse-temurin:8-jre-jammy

ARG HADOOP_VERSION=3.3.6
ARG HADOOP_DOWNLOAD_URL=https://archive.apache.org/dist/hadoop/common/hadoop-${HADOOP_VERSION}/hadoop-${HADOOP_VERSION}.tar.gz
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash curl netcat-openbsd procps tini \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fSL "${HADOOP_DOWNLOAD_URL}" -o /tmp/hadoop.tar.gz \
    && tar -xzf /tmp/hadoop.tar.gz -C /opt \
    && ln -s /opt/hadoop-${HADOOP_VERSION} /opt/hadoop \
    && rm /tmp/hadoop.tar.gz \
    && mkdir -p /hadoop/dfs/name /hadoop/dfs/data /hadoop/tmp /opt/hadoop/logs

ENV JAVA_HOME=/opt/java/openjdk
ENV HADOOP_HOME=/opt/hadoop
ENV HADOOP_CONF_DIR=/opt/hadoop/etc/hadoop
ENV PATH="${HADOOP_HOME}/bin:${HADOOP_HOME}/sbin:${PATH}"

COPY config/hadoop/ /opt/hadoop/etc/hadoop/
COPY entrypoints/hadoop-entrypoint.sh /usr/local/bin/hadoop-entrypoint

RUN chmod +x /usr/local/bin/hadoop-entrypoint

WORKDIR /opt/hadoop
ENTRYPOINT ["tini", "--", "hadoop-entrypoint"]
