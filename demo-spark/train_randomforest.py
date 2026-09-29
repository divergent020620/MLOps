"""
Random Forest — Spark MLlib (no venv needed)
Pure Spark SQL + JVM, zero Python workers.

Submit command:
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
    --num-executors 1 --executor-cores 1 --executor-memory 2G \
    train_randomforest.py
"""
from pyspark.sql import SparkSession
from pyspark.sql.functions import rand, when, col
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.classification import RandomForestClassifier
from pyspark.ml.evaluation import MulticlassClassificationEvaluator
import time
import os

spark = SparkSession.builder \
    .appName("RandomForest-Training") \
    .getOrCreate()

print("Generating synthetic data (SQL-only, no Python workers)...")
N = 10000
D = 20

df = spark.range(N)
for i in range(D):
    df = df.withColumn(f"f{i}", rand())
df = df.withColumn("label", when(rand() > 0.5, 1.0).otherwise(0.0))
print(f"Generated: {df.count()} rows, {len(df.columns)} columns")

assembler = VectorAssembler(inputCols=[f"f{i}" for i in range(D)], outputCol="features")
df_vec = assembler.transform(df).select("features", "label")
train_df, test_df = df_vec.randomSplit([0.8, 0.2], seed=42)

t0 = time.time()
rf = RandomForestClassifier(numTrees=50, maxDepth=5, labelCol="label", featuresCol="features")
model = rf.fit(train_df)
print(f"Training: {time.time() - t0:.1f}s")

predictions = model.transform(test_df)
acc = MulticlassClassificationEvaluator(
    labelCol="label", predictionCol="prediction", metricName="accuracy").evaluate(predictions)
print(f"Accuracy: {acc:.4f}")

model_dir = os.path.expanduser("~/models")
os.makedirs(model_dir, exist_ok=True)
save_path = os.path.join(model_dir, f"rf_{time.strftime('%Y%m%d_%H%M%S')}.ml")
model.write().overwrite().save(save_path)
print(f"Model saved: {save_path}")

spark.stop()
print("Done.")