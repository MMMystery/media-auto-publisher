# 同步上游修复

三个运行依赖使用 Git Submodule 固定到 `upstreams.lock.json` 记录的提交。生产环境不自动跟随上游 `main`。

## 查看状态

```bash
scripts/upstream-status
scripts/upstream-status --remote
```

## 将原项目修复同步到自己的 Fork

在对应 Submodule 中添加原项目为 `upstream`，只挑选已确认的修复提交：

```bash
cd third_party/social-auto-upload
git remote add upstream https://github.com/dreammis/social-auto-upload.git
git fetch upstream
git switch -c mapub/fix-<issue> origin/main
git cherry-pick <upstream-fix-sha>
git push origin HEAD
```

闲鱼两个 Fork 使用同样流程，分别把 `upstream` 指向原作者仓库。

## 更新主项目固定版本

在测试分支中将 Submodule 切到你的 Fork 中已经推送的修复提交：

```bash
git -C third_party/social-auto-upload fetch origin
git -C third_party/social-auto-upload checkout <tested-fork-sha>
```

随后同步修改 `upstreams.lock.json` 的 `commit`，依次执行：

```bash
python -m unittest discover -s tests -v
python -m compileall -q src tests
mapub doctor
```

最后使用测试账号逐个平台执行一次真实发布并人工核对回执。只有通过后，才提交主项目中的新 Submodule SHA。出现回归时，把 Submodule checkout 回旧 SHA 即可回退。
