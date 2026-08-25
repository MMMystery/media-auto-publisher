# Media Auto Publisher

一个面向个人创作者的低风险、多平台发布编排器。

它不会承诺“绝不封号”——任何非官方自动化都无法作出这种承诺。项目采用以下策略降低误发、重复发布和账号风控概率：

- 官方 API 优先；没有合适 API 时才调用本地浏览器自动化工具。
- 默认不允许真实发布，必须同时打开配置开关并传入 `--live`。
- 内容先入队、再审批；任务内容和媒体路径在审批后保持可审计。
- 每账号每日限量、最小发布间隔、30 天内容去重。
- 检测到验证码、滑块、人脸或风险验证后，立即锁定该账号并停止后续任务。
- 发布命令使用参数数组而不是 Shell 拼接，减少命令注入风险。
- 密钥只从环境变量读取，不写入数据库和日志。

## 当前支持

| 平台 | 发布后端 | 内容类型 | 状态 |
|---|---|---|---|
| 抖音 | `dreammis/social-auto-upload` CLI | 视频、图文 | 已接入 |
| 小红书 | `dreammis/social-auto-upload` CLI | 视频、图文 | 已接入 |
| 闲鱼 | `zhinianboke/xianyu-auto-reply` 本地公开发布 API | 商品 | 已接入 |

本仓库只负责任务编排和风险控制，不复制上游源码。上游服务独立安装、独立升级、独立遵守许可证。详见 [上游说明](docs/UPSTREAMS.md)。

## 快速开始

要求 Python 3.11+。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp config.example.toml config.toml
mapub init
mapub doctor
```

### 小红书图文任务

```bash
mapub enqueue \
  --platform xiaohongshu \
  --account main \
  --kind note \
  --title "上海周末路线" \
  --body-file ./content/note.txt \
  --media ./content/cover.png ./content/page-2.png \
  --tags 旅行,上海
```

新任务默认是 `waiting_approval`。检查后批准：

```bash
mapub list
mapub approve <job-id>
mapub plan
```

### 抖音视频任务

```bash
mapub enqueue \
  --platform douyin \
  --account main \
  --kind video \
  --title "一分钟看懂这个知识点" \
  --body "完整说明" \
  --media ./content/video.mp4 \
  --tags 科普,知识 \
  --schedule "2026-08-26T20:30:00+08:00"
```

### 闲鱼商品任务

先启动并配置 `xianyu-auto-reply`，在其个人设置中取得分销密钥，然后只放到本机环境变量：

```bash
export XIANYU_DISTRIBUTION_SECRET="your-local-secret"

mapub enqueue \
  --platform xianyu \
  --account "xianyu-account-id" \
  --kind listing \
  --title "九成新显示器支架" \
  --body-file ./content/xianyu-description.txt \
  --media ./content/item-1.jpg ./content/item-2.jpg \
  --price 89 \
  --original-price 159 \
  --address "上海市浦东新区"
```

## 真正执行发布

首次使用必须保持：

```toml
[execution]
allow_live_publish = false
```

此时运行只会显示计划，不产生外部操作：

```bash
mapub run-once
```

完成账号登录、测试号验证和内容预览后，把配置改为：

```toml
[execution]
allow_live_publish = true
```

再显式执行：

```bash
mapub run-once --live
```

建议用系统定时器每 5～10 分钟执行一次，而不是让脚本无限循环。若检测到挑战，账号会被锁定；人工完成验证并检查最近发布记录后再解锁：

```bash
mapub unlock-account --platform xiaohongshu --account main
```

## 重要边界

- 不提供验证码、滑块或人脸验证绕过。
- 不提供设备指纹伪造、群控、代理池轮换或批量养号。
- 不建议同一内容短时间跨大量账号发布。
- 发布失败或超时时不要盲目重试，应先去平台后台核对是否已经发布。
- 浏览器 Profile、Cookie、分销密钥和模型 API Key 均不得提交到 Git。

## 开发

```bash
python -m unittest discover -s tests -v
python -m compileall -q src tests
```

架构和后续计划见 [ARCHITECTURE.md](docs/ARCHITECTURE.md)、[OFFICIAL_APIS.md](docs/OFFICIAL_APIS.md) 与 [ROADMAP.md](docs/ROADMAP.md)。
