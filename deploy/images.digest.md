# 镜像 Digest 清单（deploy/images.digest.md）

> **纪律**：全部 `@sha256` 锁定，无裸 tag（version-lock.md §二.2.1）。
> 镜像沿用本地已拉取，不要求重拉；部署时校验 `docker image ls --digests`。

| # | 镜像 | Tag | Digest (sha256) | 用途 |
|---|---|---|---|---|
| 1 | `quay.io/coreos/etcd` | v3.5.25 | `52f17f7e56e4f7239f0320dbfcbcc24721163d7d78ae710b466af3254ccf6366` | Milvus 元数据存储 |
| 2 | `minio/minio` | RELEASE.2024-12-18T13-15-44Z | `1dce27c494a16bae114774f1cec295493f3613142713130c2d22dd5696be6ad3` | Milvus 对象存储 |
| 3 | `milvusdb/milvus` | v3.0.0 | `49371c30af46b1013e4d3e0b980e691d81376d69cdbe1b372725baf1d7255862` | 向量库 |
| 4 | `paradedb/paradedb` | latest | `188591a0bc317beb2c6d6d3f9ef0cb3e859d09ecc15a71dda5e9a027876686cf` | PG18 + pgvector + pg_search |
| 5 | `redis` | 8 | `298e5b3bc566bade82f46ad5511777a4a07a294097ce16ada2f6a42be5239df5` | 状态库（checkpoint + 限流 + 去重） |
| 6 | `neo4j` | 5-community | `ab3aafb0020e6fed65bb2b59f7db1fabd7ee0568c4da46f3cc3b8fad77801d61` | 图数据库 |
| 7 | `eclipse-mosquitto` | 2 | `38c0da4f2ef84284d47b3b3eeea1cb3bdeabe81ee10caf0cd5c5ff61ee3ea408` | MQTT Broker |
| 8 | `tdengine/tsdb` | 3.3.8.0 | `36e2bf82f151e8013d39a929aadc41bfcd5c46564866635cee1a02693d2256bf` | 时序库（profile: tdengine） |
| 9 | `nginx` | 1.27-alpine | `65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10` | 反向代理（端口 9763） |

> **台账**：详见 `docs/prj-ledger-version-lock.md` §二.2.1 第 1–10 行（含 ParadeDB 等全部镜像）。
