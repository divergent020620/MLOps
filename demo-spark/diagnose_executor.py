"""
诊断脚本：用 textFile + pipe("bash diagnose.sh") 在 Executor 上跑 shell
Submit:
  kinit -kt /home/ai_general/ai_general.keytab ai_general
  spark-submit \
    --master yarn --deploy-mode client \
    --queue root.ai_general \
    --conf spark.driver.host=10.240.125.39 \
    --conf spark.driver.port=10272 \
    --conf spark.blockManager.port=10273 \
    --conf spark.driver.bindAddress=0.0.0.0 \
    --conf spark.driver.extraJavaOptions=-Djava.net.preferIPv4Stack=true \
    --conf spark.executor.extraJavaOptions=-Djava.net.preferIPv4Stack=true \
    --num-executors 2 --executor-cores 1 --executor-memory 4G \
    --archives pyspark_env.tar.gz#pyspark_env \
    --files diagnose.sh \
    diagnose_executor.py
"""
from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("Executor-Diagnose").getOrCreate()
print(f"Driver: Spark {spark.version}")

# textFile → 纯 JVM HadoopRDD，pipe → JVM ProcessBuilder 跑 shell
rdd = spark.sparkContext.textFile("file:///etc/hosts", minPartitions=2)
result = rdd.pipe("bash diagnose.sh").collect()

for line in result:
    print(line)

spark.stop()
