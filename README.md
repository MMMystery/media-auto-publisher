# Media Auto Publisher

一个本地运行的简单发帖工具，支持：

- 抖音：图文、视频
- 小红书：图文、视频
- 闲鱼：图片商品

项目复用了三个 Fork，并固定在 `third_party/`。提供统一网页操作台；不需要 MySQL、Redis，也不需要分别启动三个上游项目。

## 推荐：Docker 一键启动

需要先安装 Docker Desktop。首次拉取项目时带上子模块：

```bash
git clone --recurse-submodules https://github.com/MMMystery/media-auto-publisher.git
cd media-auto-publisher
docker compose up -d --build
```

然后浏览器打开：<http://127.0.0.1:8765>

页面中可以直接：

1. 选择小红书、抖音或闲鱼；
2. 点击“扫码登录”，登录状态会保存在本机 `data/` 目录；
3. 填写标题、正文，拖入图片或视频；
4. 确认右侧预览后点击发布。

日常再次使用只需：

```bash
docker compose up -d
```

查看运行日志和停止服务：

```bash
docker compose logs -f publisher
docker compose down
```

默认只监听本机 `127.0.0.1`，同一局域网的其他设备无法直接访问。

## 不使用 Docker

需要 Python 3.11+：

```bash
git clone --recurse-submodules https://github.com/MMMystery/media-auto-publisher.git
cd media-auto-publisher
scripts/setup
source .venv/bin/activate
mapub web
```

浏览器打开 <http://127.0.0.1:8765>。下面的命令行方式仍然保留，适合脚本调用。

### 第一次登录

每个平台、每个账号只需要先登录一次。`main` 是本地账号别名，可以自行更换：

```bash
mapub login douyin --account main
mapub login xiaohongshu --account main
mapub login xianyu --account main
```

浏览器会打开，正常扫码或登录即可。登录信息只保存在本机的忽略目录里，不会提交到 Git。

### 发布图文

小红书：

```bash
mapub post \
  --platform xiaohongshu \
  --account main \
  --title "上海周末路线" \
  --body "两天一夜路线整理" \
  --media ./content/cover.jpg ./content/page-2.jpg \
  --tags 旅行,上海
```

抖音图文只需把平台改成 `douyin`。上面的命令默认显示预览；确认无误后在末尾加 `--publish` 才会真实发布。

### 发布视频

```bash
mapub post \
  --platform douyin \
  --account main \
  --kind video \
  --title "一分钟看懂这个知识点" \
  --body "补充说明" \
  --media ./content/video.mp4 \
  --tags 科普,知识 \
  --publish
```

小红书视频把平台改成 `xiaohongshu`。

### 发布闲鱼商品

```bash
mapub post \
  --platform xianyu \
  --account main \
  --title "九成新显示器支架" \
  --body "功能正常，同城可自提" \
  --media ./content/item-1.jpg ./content/item-2.jpg \
  --price 89 \
  --original-price 159 \
  --address "上海市浦东新区" \
  --publish
```

闲鱼走 `xianyu-auto-reply` Fork 里的本地 Playwright 发布器，不启动它的整套管理后台。网页改版后可能需要同步 Fork 的修复，更新方法见 [docs/UPDATING_UPSTREAMS.md](docs/UPDATING_UPSTREAMS.md)。

## 检查环境

```bash
mapub doctor
python -m unittest discover -s tests -v
```

验证码、滑块或人脸验证出现时，需要在平台页面人工完成；工具不处理验证绕过。
