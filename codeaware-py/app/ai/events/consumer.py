"""Kafka Consumer — 事件消费端。

独立进程运行（kafka_consumer 容器），负责：
1. 审计事件 → 归档到日志文件（按日期分片）
2. 指标事件 → 汇总到结构化日志
3. 异常事件 → 实时告警日志

投递语义：
- audit.* / ops.* → 至少一次（手动提交 offset，失败不提交 → 重启后重消费）
- metrics.* → 至多一次（先提交 offset 再处理，丢几条指标可接受）
- 审计事件按 event_id 去重（幂等消费者）
"""

import json
import logging
import os
from datetime import date

from kafka import KafkaConsumer

logger = logging.getLogger(__name__)

AUDIT_LOG_DIR = os.getenv("AUDIT_LOG_DIR", "/var/log/codeaware/audit")


def _get_audit_logger(topic: str) -> logging.Logger:
    log_name = topic.replace(".", "_")
    audit_logger = logging.getLogger(f"audit.{log_name}")
    if not audit_logger.handlers:
        os.makedirs(AUDIT_LOG_DIR, exist_ok=True)
        handler = logging.FileHandler(
            f"{AUDIT_LOG_DIR}/{log_name}_{date.today().isoformat()}.log"
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"
        ))
        audit_logger.addHandler(handler)
        audit_logger.setLevel(logging.INFO)
        audit_logger.propagate = False
    return audit_logger


def run_consumer(bootstrap_servers: str = "localhost:9093",
                 group_id: str = "codeaware-consumer") -> None:
    consumer = KafkaConsumer(
        bootstrap_servers=bootstrap_servers,
        group_id=group_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        key_deserializer=lambda k: k.decode("utf-8") if k else None,
    )
    consumer.subscribe(pattern="codeaware\\..*")

    _seen_ids: set[str] = set()

    logger.info("Kafka consumer started servers=%s group=%s", bootstrap_servers, group_id)
    try:
        for msg in consumer:
            topic = msg.topic.replace("codeaware.", "", 1)
            value = msg.value or {}
            is_metrics = topic.startswith("metrics.")

            if not is_metrics:
                # 至少一次：先处理，再提交
                event_id = value.get("event_id", "")
                if event_id:
                    if event_id in _seen_ids:
                        consumer.commit()
                        continue
                    _seen_ids.add(event_id)
                    if len(_seen_ids) > 1000:
                        _seen_ids.clear()

                audit_logger = _get_audit_logger(topic)
                audit_logger.info(
                    "topic=%s key=%s value=%s",
                    topic, msg.key, json.dumps(value, ensure_ascii=False),
                )
                consumer.commit()
            else:
                # 至多一次：先提交 offset，再处理
                consumer.commit()
                audit_logger = _get_audit_logger(topic)
                audit_logger.info(
                    "topic=%s key=%s value=%s",
                    topic, msg.key, json.dumps(value, ensure_ascii=False),
                )
    except KeyboardInterrupt:
        logger.info("Kafka consumer shutting down")
    finally:
        consumer.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_consumer()