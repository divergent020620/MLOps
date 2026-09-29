import time

i = 0
while True:
    i += 1
    result = f"{time.strftime('%Y-%m-%d %H:%M:%S')} | 第{i}次 | 1+{i}={1+i}"
    with open("/tmp/add.log", "a") as f:
        f.write(result + "\n")
    print(result)
    time.sleep(60)
