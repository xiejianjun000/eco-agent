# 定时维护配置

## 方式一：Cron（推荐）

### 安装

```bash
# 1. 给脚本添加执行权限
chmod +x /path/to/dsh-eia-review-plugin/scripts/maintenance.sh

# 2. 编辑 crontab
crontab -e

# 3. 添加以下行（每天凌晨 3:00 执行）
0 3 * * * /path/to/dsh-eia-review-plugin/scripts/maintenance.sh >> /path/to/dsh-eia-review-plugin/logs/cron.log 2>&1

# 4. 确保环境变量可用
# 在 crontab 顶部添加：
EHS_KB_API_KEY=your-api-key
PATH=/usr/local/bin:/usr/bin:/bin
```

### 验证

```bash
# 查看 cron 任务
crontab -l

# 手动测试运行
/path/to/dsh-eia-review-plugin/scripts/maintenance.sh

# 查看日志
tail -f /path/to/dsh-eia-review-plugin/logs/maintenance-$(date +%Y%m%d).log
```

## 方式二：Systemd Timer（Linux 服务器推荐）

### 1. 创建 Service 文件

```ini
# /etc/systemd/system/dsh-eia-review-maintenance.service
[Unit]
Description=DSH EIA Review Plugin Daily Maintenance
After=network.target

[Service]
Type=oneshot
ExecStart=/path/to/dsh-eia-review-plugin/scripts/maintenance.sh
Environment=EHS_KB_API_KEY=your-api-key
Environment=PATH=/usr/local/bin:/usr/bin:/bin
StandardOutput=append:/var/log/dsh-eia-review-maintenance.log
StandardError=append:/var/log/dsh-eia-review-maintenance.log
```

### 2. 创建 Timer 文件

```ini
# /etc/systemd/system/dsh-eia-review-maintenance.timer
[Unit]
Description=Run DSH EIA Review Plugin Maintenance daily at 3:00 AM

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

### 3. 启用并启动

```bash
sudo systemctl daemon-reload
sudo systemctl enable dsh-eia-review-maintenance.timer
sudo systemctl start dsh-eia-review-maintenance.timer

# 查看状态
sudo systemctl status dsh-eia-review-maintenance.timer
sudo systemctl list-timers --all
```

## 方式三：Docker（容器化部署）

```dockerfile
# Dockerfile.maintenance
FROM node:22-alpine
RUN apk add --no-cache bash curl
COPY scripts/maintenance.sh /app/maintenance.sh
RUN chmod +x /app/maintenance.sh
ENV EHS_KB_API_KEY=${EHS_KB_API_KEY}
CMD ["/app/maintenance.sh"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  maintenance:
    build:
      context: .
      dockerfile: Dockerfile.maintenance
    environment:
      - EHS_KB_API_KEY=${EHS_KB_API_KEY}
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped
```

## 维护内容

每天凌晨 3:00 自动执行：

| 步骤 | 内容 | 耗时 |
|------|------|------|
| 1 | 环境检查（Node.js、pnpm、API Key） | ~1s |
| 2 | 依赖更新检查（outdated、audit） | ~10s |
| 3 | EHS 知识库同步 | ~30-120s |
| 4 | 规则库更新检查 | ~2s |
| 5 | 日志清理（保留30天） | ~1s |
| 6 | 健康检查（编译、文件完整性、磁盘） | ~5s |
| 7 | 生成维护报告（JSON） | ~1s |

**总耗时**: 约 1-3 分钟

## 日志查看

```bash
# 查看最新维护日志
tail -f logs/maintenance-$(date +%Y%m%d).log

# 查看维护报告
cat logs/maintenance-report-$(date +%Y%m%d).json

# 查看所有历史日志
ls -lt logs/maintenance-*.log | head -10
```
