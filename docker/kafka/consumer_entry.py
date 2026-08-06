"""Kafka 消费者容器入口。"""
import os
from app.ai.events.consumer import run_consumer

if __name__ == "__main__":
    run_consumer(
        bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9093"),
        group_id="codeaware-consumer",
    )