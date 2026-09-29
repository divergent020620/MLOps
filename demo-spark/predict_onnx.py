"""
ONNX batch inference — Spark 2.4 + onnxruntime, synthetic data.

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
    --num-executors 2 --executor-cores 1 --executor-memory 4G \
    --archives pyspark_env.tar.gz#venv \
    --conf spark.executorEnv.PYSPARK_PYTHON=./venv/bin/python \
    --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON=./venv/bin/python \
    predict_onnx.py ~/models/model.onnx
"""
import numpy as np
import os
import sys
import time
from pyspark.sql import SparkSession

NUM_SAMPLES = 1000


def predict_onnx_partition(partition_iter):
    import onnxruntime as ort
    sess = ort.InferenceSession(BC_MODEL.value)

    rows = list(partition_iter)
    if not rows:
        return iter([])

    X = np.array([r[1:] for r in rows], dtype=np.float32).reshape(-1, 1, 28, 28) / 255.0
    ids = [r[0] for r in rows]

    outputs = sess.run(None, {"input": X})
    logits = outputs[0]
    preds = logits.argmax(axis=1)
    probs = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)

    for i in range(len(rows)):
        yield (int(ids[i]), int(preds[i]), round(float(probs[i, preds[i]]), 6))


def main():
    model_path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/models/model.onnx")

    spark = SparkSession.builder.appName("ONNX-Inference").getOrCreate()

    # Generate synthetic test data
    np.random.seed(123)
    X = np.clip(np.random.randn(NUM_SAMPLES, 784).astype(np.float32) * 40 + 100, 0, 255)
    data = [(i, *row.tolist()) for i, row in enumerate(X)]
    df = spark.createDataFrame(data, ["id"] + [f"f{j}" for j in range(784)])

    with open(model_path, "rb") as f:
        model_bytes = f.read()
    global BC_MODEL
    BC_MODEL = spark.sparkContext.broadcast(model_bytes)
    print(f"Model broadcast: {len(model_bytes) / 1024:.0f} KB")

    rdd = df.rdd.map(lambda r: tuple(r)).repartition(10)
    t0 = time.time()
    results = rdd.mapPartitions(predict_onnx_partition).collect()
    elapsed = time.time() - t0
    print(f"Inference: {elapsed:.2f}s, {len(results)} records, {len(results) / elapsed:.0f} r/s")

    for r in results[:5]:
        print(f"  id={r[0]} pred={r[1]} conf={r[2]}")

    spark.stop()
    print("Done.")


if __name__ == "__main__":
    main()