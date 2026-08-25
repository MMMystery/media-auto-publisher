# 上游项目与许可证

## dreammis/social-auto-upload

- 地址：https://github.com/dreammis/social-auto-upload
- 用途：抖音、小红书及后续视频号/B站等内容平台发布。
- 接入方式：调用 `sau` CLI，不复制其实现。
- 仓库标注许可证：MIT。

建议 Fork 到自己的 GitHub 账号，通过 `social_auto_upload.command` 或 `working_directory` 固定到经过验证的 commit。不要自动跟随上游 `main`。

## zhinianboke/xianyu-auto-reply

- 地址：https://github.com/zhinianboke/xianyu-auto-reply
- 用途：闲鱼媒体上传和单品发布。
- 接入方式：localhost `/api/v1/external/publish/*` API。
- `LICENSE` 文件：AGPL-3.0。
- README 另有“禁止商业用途”说明，与标准 AGPL 的商业使用条款存在口径冲突。

如果自媒体项目存在收入、带货、商业推广或对外提供服务，应在正式使用前取得上游作者的书面授权。Fork 并不会自动消除上游义务。

## 23Star/xianyu-super-butler

- 地址：https://github.com/23Star/xianyu-super-butler
- 用途：参考多账号、订单、消息、发货、评价、擦亮和后台交互。
- 仓库标注许可证：AGPL-3.0。
- 当前不作为新品发布后端；如未来移植代码，需要保留版权和履行 AGPL 义务。

## 更新策略

1. 上游 Fork 使用独立仓库，不把其历史压入本仓库。
2. 记录验证过的 commit SHA。
3. 平台页面变更时只升级对应发布器。
4. 升级先在测试账号运行预览、单次发布和失败场景，再切换生产账号。

