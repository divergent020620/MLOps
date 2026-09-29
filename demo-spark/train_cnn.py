"""
CNN distributed training — Spark 2.4 + PyTorch, synthetic data.

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
    --archives pyspark_env.tar.gz#pyspark_env \
    --conf spark.pyspark.python=./pyspark_env/pyspark_env/bin/python \
    --conf spark.executorEnv.LD_LIBRARY_PATH=./pyspark_env/pyspark_env/lib \
    --conf spark.network.timeout=600s \
    --conf spark.executor.heartbeatInterval=60s \
    train_cnn.py
"""
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import numpy as np
import time
import os
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, DoubleType, IntegerType

NUM_SAMPLES = 5000
NUM_FEATURES = 784
NUM_CLASSES = 10
BATCH_SIZE = 256
LOCAL_EPOCHS = 1
NUM_PARTITIONS = 4


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


def train_on_partition(partition_iter):
    rows = list(partition_iter)
    if len(rows) == 0:
        return iter([])

    X = np.array([r[:-1] for r in rows], dtype=np.float32)
    X = X.reshape(-1, 1, 28, 28) / 255.0
    y = np.array([r[-1] for r in rows], dtype=np.int64)

    dataset = TensorDataset(torch.from_numpy(X), torch.from_numpy(y))
    loader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True)

    model = SimpleCNN()
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)

    model.train()
    for _ in range(LOCAL_EPOCHS):
        for batch_x, batch_y in loader:
            optimizer.zero_grad()
            loss = criterion(model(batch_x), batch_y)
            loss.backward()
            optimizer.step()

    state_np = {k: v.cpu().numpy() for k, v in model.state_dict().items()}
    yield (state_np, len(rows))


def main():
    spark = SparkSession.builder.appName("CNN-Training").getOrCreate()
    print(f"Spark version: {spark.version}")

    np.random.seed(42)
    data = []
    for _ in range(NUM_SAMPLES):
        label = np.random.randint(0, NUM_CLASSES)
        pixels = np.clip(label * 20 + np.random.randn(NUM_FEATURES).astype(np.float32) * 40, 0, 255)
        data.append(tuple(pixels.tolist() + [label]))
    print(f"Generated synthetic data: {len(data)} rows")

    schema = StructType(
        [StructField(f"f{i}", DoubleType()) for i in range(NUM_FEATURES)]
        + [StructField("label", IntegerType())]
    )
    df = spark.createDataFrame(data, schema=schema)

    rdd = df.rdd.map(lambda row: tuple(row)).repartition(NUM_PARTITIONS)
    t0 = time.time()
    results = rdd.mapPartitions(train_on_partition).collect()
    elapsed = time.time() - t0

    total_samples = sum(r[1] for r in results)
    print(f"Training: {elapsed:.1f}s, {len(results)} executors, {total_samples} samples")

    averaged = {}
    for state_dict, n in results:
        w = n / total_samples
        for k, v in state_dict.items():
            averaged.setdefault(k, np.zeros_like(v, dtype=np.float64))
            averaged[k] += v.astype(np.float64) * w

    final_model = SimpleCNN()
    final_model.load_state_dict(
        {k: torch.from_numpy(v.astype(np.float32)) for k, v in averaged.items()}
    )

    model_dir = "file:///root/models"
    save_path = os.path.join(model_dir, f"cnn_{time.strftime('%Y%m%d_%H%M%S')}.pth")
    torch.save(final_model.state_dict(), save_path)
    print(f"Model saved: {save_path}")

    spark.stop()
    print("Done.")


if __name__ == "__main__":
    main()
