"""
Spark SQL 测试 — 用自定义 Python 3.7 venv
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
    --conf spark.pyspark.python=./pyspark_env/pyspark_env/bin/python \
    --conf spark.executorEnv.LD_LIBRARY_PATH=./pyspark_env/pyspark_env/lib \
    --conf spark.network.timeout=600s \
    --conf spark.hadoop.hive.metastore.uris=thrift://zjdsjt10.shbankpp.com:9083 \
    --conf spark.hadoop.hive.metastore.sasl.enabled=true \
    --conf spark.hadoop.hive.metastore.kerberos.principal=hive/_HOST@SHBANKPP.COM \
    test_sql.py
"""
from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName("SQL-Test") \
    .enableHiveSupport() \
    .getOrCreate()

print(f"Spark version: {spark.version}")

# 1. 测试简单 SQL
print("\n=== 测试1: show databases ===")
spark.sql("show databases").show()

# 2. 测试聚合
print("\n=== 测试2: SELECT 聚合 ===")
spark.sql("SELECT 1+1 as result, 'hello' as msg").show()

# 3. 测试 DataFrame + RDD 混合操作（之前在 Executor 上会炸）
print("\n=== 测试3: DataFrame → RDD ===")
df = spark.sql("SELECT 1 as id UNION ALL SELECT 2 UNION ALL SELECT 3")
print(f"Count: {df.count()}")
result = df.rdd.map(lambda row: row.id * 10).collect()
print(f"RDD map result: {result}")

spark.stop()
print("\nDone. SQL 测试通过!")