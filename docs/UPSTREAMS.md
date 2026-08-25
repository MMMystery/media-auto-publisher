# 上游项目与许可证

## dreammis/social-auto-upload

- 原仓库：https://github.com/dreammis/social-auto-upload
- 项目 Fork：https://github.com/MMMystery/social-auto-upload
- 固定位置：`third_party/social-auto-upload`
- 当前提交：`1c66b7db4b30585bbb40c58eb0aa572ffa3cce97`
- 用途：抖音、小红书及后续视频号/B站等内容平台发布。
- 接入方式：调用 Submodule 中固定版本的 `sau` CLI。
- 仓库标注许可证：MIT。

`scripts/setup-social-auto-upload` 在独立虚拟环境中安装该版本，`scripts/run-social-auto-upload` 是编排器的固定入口。主项目不会自动跟随上游 `main`。

## zhinianboke/xianyu-auto-reply

- 原仓库：https://github.com/zhinianboke/xianyu-auto-reply
- 项目 Fork：https://github.com/MMMystery/xianyu-auto-reply
- 固定位置：`third_party/xianyu-auto-reply`
- 当前提交：`29dc831d4498f3174f0502c989a352ef59815553`
- 用途：闲鱼图片商品发布。
- 接入方式：直接调用 Fork 中的 `XianyuPublisher` 本地浏览器发布器，不启动后台服务。
- `LICENSE` 文件：AGPL-3.0。
- README 另有“禁止商业用途”说明，与标准 AGPL 的商业使用条款存在口径冲突。

如果自媒体项目存在收入、带货、商业推广或对外提供服务，应在正式使用前取得上游作者的书面授权。Fork 并不会自动消除上游义务。

## 23Star/xianyu-super-butler

- 原仓库：https://github.com/23Star/xianyu-super-butler
- 项目 Fork：https://github.com/MMMystery/xianyu-super-butler
- 固定位置：`third_party/xianyu-super-butler`
- 当前提交：`97c4e8a5976c2ed70f898be5bab72b9557ea2b1c`
- 用途：参考多账号、订单、消息、发货、评价、擦亮和后台交互。
- 仓库标注许可证：AGPL-3.0。
- 当前不作为新品发布后端，也不会被默认启动；它作为多账号、订单和后台交互的参考实现。如未来移植代码，需要保留版权和履行 AGPL 义务。

## 更新策略

1. 上游 Fork 使用独立仓库，通过 Submodule 纳入主项目。
2. 在 Gitlink 和 `upstreams.lock.json` 中同时记录验证过的 commit SHA。
3. 平台页面变更时只升级对应发布器。
4. 升级先在测试账号运行预览、单次发布和失败场景，再切换生产账号。

具体操作见 [同步上游修复](UPDATING_UPSTREAMS.md)。
