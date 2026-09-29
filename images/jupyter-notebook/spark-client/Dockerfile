FROM 10.240.125.39/cube-studio/notebook:jupyter-ubuntu-py374

# Proxy (build-time only)
ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY}

# Kerberos client (kinit) + JDK (Spark required)
RUN apt-get update && \
    apt-get install -y krb5-user openjdk-8-jdk-headless && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Spark 2.4.8 + Hadoop 2.7 client JARs (YARN/HDFS/Kerberos 必需)
COPY spark-2.4.8-bin-hadoop2.7.tgz /tmp/
RUN tar xzf /tmp/spark-2.4.8-bin-hadoop2.7.tgz -C /opt/ && \
    ln -s /opt/spark-2.4.8-bin-hadoop2.7 /opt/spark && \
    rm /tmp/spark-2.4.8-bin-hadoop2.7.tgz

# CDP cluster configs
COPY conf/core-site.xml \
     conf/hdfs-site.xml \
     conf/yarn-site.xml \
     conf/ssl-client.xml \
     /etc/hadoop/conf/
COPY conf/krb5.conf /etc/krb5.conf

# Kerberos keytab
COPY keytab/ai_general.keytab /home/ai_general/

# Clear proxy
ENV HTTP_PROXY= \
    HTTPS_PROXY=

ENV SPARK_HOME=/opt/spark
ENV HADOOP_CONF_DIR=/etc/hadoop/conf
ENV PATH=$SPARK_HOME/bin:$PATH
ENV PYSPARK_PYTHON=python3
