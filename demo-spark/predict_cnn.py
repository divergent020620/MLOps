"""
CNN batch inference — Spark 2.4 + PyTorch, synthetic data.

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
    predict_cnn.py ~/models/cnn_latest.pth
"""
import torch
import torch.nn as nn
import numpy as np
import os
import sys
import time
from pyspark.sql import SparkSession

NUM_CLASSES = 10
NUM_SAMPLES = 1000


class SimpleCNN(nn.Module):
    def __init__(self, num_classes=NUM_CLASSES):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(1, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
        )
        self.fc = nn.Sequential(
            nn.Flatten(),
            nn.Linear(64 * 7 * 7, 128), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(128, num_classes),
        )

    def forward(self, x):
        return self.fc(self.conv(x))


def predict_partition(partition_iter):
    state_dict = {k: torch.from_numpy(v) for k, v in BC_MODEL.value.items()}
    model = SimpleCNN()
    model.load_state_dict(state_dict)
    model.eval()

    rows = list(partition_iter)
    if not rows:
        return iter([])

    X = np.array([r[1:] for r in rows], dtype=np.float32).reshape(-1, 1, 28, 28) / 255.0
    ids = [r[0] for r in rows]

    with torch.no_grad():
        outputs = model(torch.from_numpy(X))
        probs = torch.softmax(outputs, dim=1)
        preds = outputs.argmax(dim=1)

    for i in range(len(rows)):
        yield (int(ids[i]), int(preds[i].item()),
               round(float(probs[i, preds[i]].item()), 6))


def main():
    model_path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/models/cnn_latest.pth")

    spark = SparkSession.builder.appName("CNN-Inference").getOrCreate()

    # Generate synthetic test data
    np.random.seed(123)
    X = np.clip(np.random.randn(NUM_SAMPLES, 784).astype(np.float32) * 40 + 100, 0, 255)
    data = [(i, *row.tolist()) for i, row in enumerate(X)]
    df = spark.createDataFrame(data, ["id"] + [f"f{j}" for j in range(784)])

    state_dict = torch.load(model_path, map_location="cpu")
    state_np = {k: v.numpy() for k, v in state_dict.items()}
    global BC_MODEL
    BC_MODEL = spark.sparkContext.broadcast(state_np)
    print(f"Model broadcast: ~{sum(v.nbytes for v in state_np.values()) / 1024:.0f} KB")

    rdd = df.rdd.map(lambda r: tuple(r)).repartition(10)
    t0 = time.time()
    results = rdd.mapPartitions(predict_partition).collect()
    elapsed = time.time() - t0
    print(f"Inference: {elapsed:.2f}s, {len(results)} records, {len(results) / elapsed:.0f} r/s")

    for r in results[:5]:
        print(f"  id={r[0]} pred={r[1]} conf={r[2]}")

    spark.stop()
    print("Done.")


if __name__ == "__main__":
    main()