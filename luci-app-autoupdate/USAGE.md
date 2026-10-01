# luci-app-autoupdate 使用说明

## 功能介绍

这是一个用于 OpenWrt 路由器的自动固件更新插件，支持自定义更新仓库，不再依赖特定的固件编译环境。

## 主要特性

1. **自定义仓库支持** - 可以配置任意 GitHub 仓库作为固件更新源
2. **GitHub API 模式** - 支持直接使用 GitHub API 获取固件信息，无需 zzz_api 文件
3. **完整配置选项** - 可配置固件版本、设备型号、目标平台等参数
4. **自动更新** - 支持定时自动更新
5. **手动升级** - 支持手动选择固件版本进行升级

## 配置说明

### LuCI 界面配置

在 OpenWrt 的 LuCI 界面中，进入 **系统 -> AutoUpdate** 进行配置：

#### 基本设置

- **启用 AutoUpdate** - 开启自动更新功能
- **星期** - 设置自动更新的星期（可选择每天或特定星期）
- **小时** - 设置自动更新的小时（0-23）
- **分钟** - 设置自动更新的分钟（0-59）

#### 仓库设置

- **GitHub URL** - 你的 GitHub 仓库地址，格式：`https://github.com/username/repo`
- **使用 GitHub API** - 勾选后直接使用 GitHub API，不依赖 zzz_api 文件（推荐自定义仓库使用）
- **GitHub Proxy** - GitHub 代理地址，用于加速访问（默认：https://ghproxy.com）
- **Release Download Path** - 固件下载路径（默认：releases/download）

#### 固件信息设置

- **Source** - 固件源名称（默认：openwrt）
- **LuCI Edition** - LuCI 版本（默认：luci）
- **Firmware Version** - 当前固件版本号
- **Target Board** - 目标平台（如：x86、ramips、qualcommipq等）
- **Device Model** - 设备型号（如：generic、x86-64等）
- **Firmware Suffix** - 固件文件后缀（如：.img.gz、.bin等）

#### 更新选项

- **不保留配置更新** - 勾选后更新时不保留配置

## 使用 GitHub API 模式

### 优势

1. **无需 zzz_api 文件** - 不需要在仓库中放置 zzz_api 文件
2. **标准 GitHub API** - 使用 GitHub 官方 API，兼容性更好
3. **自动获取最新版本** - 自动获取仓库的最新 release 信息

### 配置步骤

1. 在 LuCI 界面中勾选 **"使用 GitHub API"**
2. 填写你的 **GitHub URL**
3. 配置其他固件信息（Source、LuCI Edition、Target Board 等）
4. 点击 **"保存并应用"**

### 固件命名规则

使用 GitHub API 模式时，固件文件名需要符合以下命名规则：

```
{LUCI_EDITION}-{SOURCE}-{DEVICE_MODEL}-{VERSION}-{BOOT_TYPE}{FIRMWARE_SUFFIX}
```

示例：
```
luci-openwrt-x86-64-20250101000000-sysupgrade.img.gz
luci-openwrt-generic-20250101000000-uefi.img.gz
```

### BOOT_TYPE 说明

- **sysupgrade** - 适用于 OpenWrt 标准升级方式
- **uefi** - 适用于 x86 UEFI 引导
- **legacy** - 适用于 x86 Legacy BIOS 引导

## 使用 zzz_api 模式

如果你的仓库已经包含 zzz_api 文件，可以不勾选 **"使用 GitHub API"**，系统将使用原有的 zzz_api 模式。

### zzz_api 文件要求

zzz_api 文件应包含 GitHub Releases API 的 JSON 数据，通常放在仓库的 releases 目录下。

## 手动升级

### 一键升级到最新版本

在 LuCI 界面点击 **"开始升级"** 按钮，系统将自动：
1. 检测云端最新版本
2. 下载固件
3. 校验固件完整性
4. 执行升级

### 选择特定版本升级

使用 SSH 登录路由器，执行：

```bash
AutoUpgrade -u
```

然后按照提示选择要安装的固件版本。

## 命令行工具

### AutoUpdate

```bash
# 检查更新（保留配置）
AutoUpdate -u

# 检查更新（不保留配置）
AutoUpdate -k

# 仅检查版本
AutoUpdate -c
```

### AutoUpgrade

```bash
# 交互式选择固件升级
AutoUpgrade -u
```

## 配置文件

### /etc/openwrt_update

系统自动生成的配置文件，包含以下内容：

```bash
GITHUB_LINK="https://github.com/username/repo"
GITHUB_PROXY="https://ghproxy.com"
RELEASE_DOWNLOAD="releases/download"
SOURCE="openwrt"
LUCI_EDITION="luci"
FIRMWARE_VERSION="1.0.0"
TARGET_BOARD="x86"
DEVICE_MODEL="generic"
FIRMWARE_SUFFIX=".img.gz"
```

### UCI 配置

```bash
# 查看配置
uci show autoupdate

# 修改配置
uci set autoupdate.@login[0].github="https://github.com/username/repo"
uci set autoupdate.@login[0].use_github_api="1"
uci commit autoupdate

# 重启服务
/etc/init.d/autoupdate restart
```

## 故障排除

### 获取 API 数据失败

1. 检查 GitHub URL 是否正确
2. 检查网络连接
3. 尝试更换 GitHub Proxy
4. 确认仓库为公开仓库（非私有仓库）

### 固件下载失败

1. 检查 /tmp 空间是否足够
2. 检查网络连接
3. 尝试使用 GitHub API 模式

### 找不到匹配的固件

1. 检查固件命名规则是否正确
2. 检查 Target Board、Device Model 等参数配置
3. 查看日志文件 `/tmp/autoupdate.log`

## 注意事项

1. **备份配置** - 升级前建议备份重要配置
2. **网络稳定** - 升级过程中请保持网络稳定
3. **电源稳定** - 升级过程中请勿断开电源
4. **版本兼容** - 确保新版本固件与你的硬件兼容
5. **测试固件** - 建议先在测试环境验证新固件

## 编译说明

### 添加到 OpenWrt 编译环境

1. 将此项目复制到 OpenWrt 源码的 `feeds/luci/applications/` 目录
2. 更新 feeds：
   ```bash
   ./scripts/feeds update packages luci
   ./scripts/feeds install -a
   ```
3. 在 `make menuconfig` 中选择：
   ```
   LuCI -> 3. Applications -> luci-app-autoupdate
   ```
4. 编译固件：
   ```bash
   make package/luci/applications/luci-app-autoupdate/compile
   ```

## 许可证

GNU General Public License v3

## 更新日志

### v2.0

- 添加自定义仓库支持
- 添加 GitHub API 模式
- 添加完整的配置选项
- 优化固件检测和下载逻辑
- 支持从 UCI 配置生成 openwrt_update 文件