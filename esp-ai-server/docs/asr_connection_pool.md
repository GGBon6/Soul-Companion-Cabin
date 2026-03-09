# ASR连接池架构文档

## 概述

ASR连接池是ESP-AI-Server的核心组件，为ESP32硬件设备和Web客户端提供高效、可靠的语音识别服务连接管理。

## 设计目标

### 产品化需求
- ✅ **高并发支持**: 支持数百个并发客户端
- ✅ **资源复用**: 减少ASR服务实例创建开销
- ✅ **故障隔离**: ESP32和Web客户端互不影响
- ✅ **负载均衡**: 智能分配连接资源
- ✅ **监控友好**: 完整的指标和健康检查

### 工程化特性
- ✅ **配置驱动**: 通过YAML和环境变量配置
- ✅ **优雅降级**: 连接池满时自动排队等待
- ✅ **自动恢复**: 不健康连接自动清理和重建
- ✅ **可观测性**: 详细的日志和性能指标

## 架构设计

### 核心组件

```
┌─────────────────────────────────────────────────────────┐
│                   ASR Connection Pool                    │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ ESP32 Client │  │  Web Client  │  │ Other Client │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                  │                  │          │
│         └──────────────────┼──────────────────┘          │
│                            │                             │
│                    ┌───────▼────────┐                    │
│                    │  acquire()     │                    │
│                    │  release()     │                    │
│                    └───────┬────────┘                    │
│                            │                             │
│         ┌──────────────────┼──────────────────┐         │
│         │                  │                  │         │
│    ┌────▼────┐       ┌────▼────┐       ┌────▼────┐    │
│    │ Idle    │       │  Busy   │       │Unhealthy│    │
│    │ Queue   │       │  Set    │       │  Set    │    │
│    └─────────┘       └─────────┘       └─────────┘    │
│                                                         │
│  ┌─────────────────────────────────────────────────┐  │
│  │         Background Tasks                        │  │
│  │  • Health Check Loop                            │  │
│  │  • Cleanup Loop                                 │  │
│  │  • Metrics Collection                           │  │
│  └─────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 连接生命周期

```
┌─────────┐
│ Created │
└────┬────┘
     │
     ▼
┌─────────┐     acquire()      ┌──────┐
│  Idle   │ ─────────────────► │ Busy │
└────▲────┘                     └───┬──┘
     │                              │
     │         release()            │
     └──────────────────────────────┘
                  │
                  │ (error_count >= 3)
                  ▼
            ┌───────────┐
            │ Unhealthy │
            └─────┬─────┘
                  │
                  │ (health check)
                  ▼
              ┌────────┐
              │ Closed │
              └────────┘
```

## 使用指南

### 基础用法

```python
from app.shared.services import acquire_asr_service

# 使用上下文管理器（推荐）
async with acquire_asr_service(
    client_type="esp32",
    client_id="device_001",
    timeout=30.0
) as asr_service:
    result = asr_service.transcribe(audio_data)
    print(f"识别结果: {result}")
```

### ESP32设备集成

```python
# app/devices/esp32/adapter.py
async with acquire_asr_service(
    client_type="esp32",
    client_id=device_id,
    timeout=30.0
) as asr_service:
    text = asr_service.transcribe_file(temp_file_path)
```

### Web客户端集成

```python
# app/web/handlers/websocket_handler.py
async with acquire_asr_service(
    client_type="web",
    client_id=user_id,
    timeout=30.0
) as asr_service:
    text = asr_service.transcribe(audio_data, format="webm")
```

## 配置说明

### 环境变量配置

```bash
# .env
ASR_POOL_MIN_CONNECTIONS=2      # 最小连接数
ASR_POOL_MAX_CONNECTIONS=10     # 最大连接数
ASR_POOL_MAX_IDLE_TIME=300      # 最大空闲时间（秒）
ASR_POOL_HEALTH_CHECK_INTERVAL=60  # 健康检查间隔（秒）
ASR_POOL_ACQUIRE_TIMEOUT=30.0   # 获取连接超时（秒）
```

### YAML配置

```yaml
# config/development.yaml
ai:
  asr:
    model: "paraformer-realtime-v2"
    sample_rate: 16000
    pool:
      min_connections: 2
      max_connections: 10
      max_idle_time: 300
      health_check_interval: 60
      acquire_timeout: 30.0
```

## 监控和管理

### 获取连接池状态

```python
from app.api.asr_pool_monitor import get_asr_pool_monitor

monitor = get_asr_pool_monitor()

# 获取状态
status = monitor.get_pool_status()
print(f"总连接数: {status['current_state']['total_connections']}")
print(f"空闲连接: {status['current_state']['idle_connections']}")
print(f"忙碌连接: {status['current_state']['busy_connections']}")

# 获取健康报告
health = monitor.get_health_report()
print(f"健康分数: {health['health_score']}")
print(f"状态: {health['status']}")
print(f"问题: {health['issues']}")
print(f"建议: {health['recommendations']}")
```

### 性能指标

```python
stats = monitor.get_pool_status()
metrics = stats['performance_metrics']

print(f"总请求数: {metrics['total_requests']}")
print(f"成功率: {metrics['success_rate']}%")
print(f"平均处理时间: {metrics['avg_processing_time']}s")
print(f"平均等待时间: {metrics['avg_wait_time']}s")
```

## 性能优化

### 连接数配置建议

| 场景 | 最小连接数 | 最大连接数 | 说明 |
|------|-----------|-----------|------|
| 开发环境 | 2 | 5 | 资源占用小 |
| 测试环境 | 5 | 20 | 模拟生产负载 |
| 生产环境（小规模） | 10 | 50 | 支持100+并发用户 |
| 生产环境（大规模） | 20 | 100 | 支持500+并发用户 |

### 性能调优

1. **连接池大小**
   - 根据并发用户数调整 `max_connections`
   - 保持 `min_connections` 为峰值的20-30%

2. **超时配置**
   - `acquire_timeout`: 建议30-60秒
   - `max_idle_time`: 建议300-600秒

3. **健康检查**
   - `health_check_interval`: 建议60-120秒
   - 避免过于频繁的检查影响性能

## 故障处理

### 常见问题

#### 1. 连接池已满

**现象**: `TimeoutError: 获取ASR连接超时`

**原因**: 
- 并发请求超过 `max_connections`
- 连接释放不及时

**解决方案**:
```python
# 增加最大连接数
ASR_POOL_MAX_CONNECTIONS=20

# 或增加超时时间
ASR_POOL_ACQUIRE_TIMEOUT=60.0
```

#### 2. 连接频繁标记为不健康

**现象**: 日志显示大量 "ASR连接错误次数过多"

**原因**:
- ASR服务不稳定
- 网络问题
- 音频数据质量问题

**解决方案**:
```python
# 检查ASR服务健康状态
# 增加错误容忍度（修改源码）
if conn_info.error_count >= 5:  # 从3改为5
    conn_info.state = ASRConnectionState.UNHEALTHY
```

#### 3. 内存占用过高

**现象**: 服务器内存持续增长

**原因**:
- 连接数过多
- 连接未正确释放

**解决方案**:
```python
# 减少最大连接数
ASR_POOL_MAX_CONNECTIONS=10

# 减少空闲时间
ASR_POOL_MAX_IDLE_TIME=180
```

## 测试

### 运行单元测试

```bash
# 运行所有测试
pytest tests/test_asr_connection_pool.py -v

# 运行特定测试
pytest tests/test_asr_connection_pool.py::TestASRConnectionPool::test_concurrent_acquire -v

# 运行压力测试
pytest tests/test_asr_connection_pool.py::test_pool_stress_test -v
```

### 压力测试结果示例

```
测试场景: 50个并发客户端，每个发送10个请求
总请求数: 500
成功率: 100%
平均处理时间: 0.15s
平均等待时间: 0.02s
连接池峰值: 18/20
```

## 最佳实践

### 1. 始终使用上下文管理器

✅ **推荐**:
```python
async with acquire_asr_service("esp32", "device_001") as asr:
    result = asr.transcribe(audio)
```

❌ **不推荐**:
```python
asr = get_asr_service()  # 不使用连接池
result = asr.transcribe(audio)
```

### 2. 设置合理的超时

```python
# 根据音频长度设置超时
audio_duration = len(audio_data) / sample_rate
timeout = max(30.0, audio_duration * 2)

async with acquire_asr_service("esp32", device_id, timeout=timeout) as asr:
    result = asr.transcribe(audio)
```

### 3. 错误处理

```python
try:
    async with acquire_asr_service("esp32", device_id) as asr:
        result = asr.transcribe(audio)
except TimeoutError:
    logger.error("获取ASR连接超时，连接池可能已满")
    # 降级处理：返回默认回复或重试
except Exception as e:
    logger.error(f"ASR识别失败: {e}")
    # 错误处理
```

### 4. 监控集成

```python
# 定期记录连接池指标
async def log_pool_metrics():
    while True:
        await asyncio.sleep(60)
        monitor = get_asr_pool_monitor()
        status = monitor.get_pool_status()
        logger.info(f"ASR连接池状态: {status['current_state']}")
```

## 未来优化方向

### 短期（1-2个月）
- [ ] 集成Prometheus指标导出
- [ ] 添加连接预热机制
- [ ] 实现动态连接池大小调整

### 中期（3-6个月）
- [ ] 支持多ASR服务提供商
- [ ] 实现智能路由和负载均衡
- [ ] 添加连接池分片支持

### 长期（6-12个月）
- [ ] 分布式连接池支持
- [ ] 跨区域连接池同步
- [ ] AI驱动的自适应调优

## 参考资料

- [DashScope ASR API文档](https://help.aliyun.com/zh/dashscope/developer-reference/api-details-9)
- [连接池设计模式](https://en.wikipedia.org/wiki/Connection_pool)
- [Python asyncio最佳实践](https://docs.python.org/3/library/asyncio.html)

## 贡献指南

欢迎提交Issue和Pull Request！

### 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/your-repo/esp-ai-server.git
cd esp-ai-server

# 安装依赖
pip install -r requirements.txt

# 运行测试
pytest tests/test_asr_connection_pool.py -v
```

## 许可证

MIT License
