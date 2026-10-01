#
# luci-app-openbox —— 把 Open-Box(sing-box 一体化透明代理 + 管理面板)
# 直接编进 OpenWrt 固件,替代 SSH 里跑 install.sh 的安装方式。
#
# 用法:
#   1. 把本目录整个复制到 OpenWrt 源码树: package/luci-app-openbox/
#      (或放进自定义 feeds 的 packages 目录)
#   2. ./scripts/feeds update -a && ./scripts/feeds install -a
#      make menuconfig  →  LuCI → 3. Applications → luci-app-openbox 选 <*> 或 <M>
#   3. make -j$(nproc)  (或先 make package/luci-app-openbox/compile V=s 单独验证)
#
# 下载策略:每次编译都拉上游最新发布包
#   - 直接用 GitHub 的稳定资产名 open-box-linux-<arch>.tar.gz
#     (releases/latest/download/ 指向,上游发新版即自动跟上,无需改本文件)。
#   - 下载在 Build/Prepare 里现场完成,刻意绕过 OpenWrt 的 dl/ 下载缓存——
#     缓存按文件名判重,稳定资产名永远同名,走缓存的话"最新"就是假的。
#   - 因此每次 make package/luci-app-openbox/{clean,compile} 都是当时上游的最新版;
#     编译日志里会打印实际编入的版本号(从 meta.json 读),事后也可在路由器上
#     查 /opt/open-box/meta.json 或面板「设置 → 后端设置」确认。
#   - 代价(可接受则无需理会):
#     a) 没有 SHA256 钉版校验,完整性依赖到 github.com 的 HTTPS(与 install.sh
#        同级;上游发布页本来也没上传 .sha256 文件);
#     b) 构建不可复现:不同时间编出的固件内嵌版本可能不同;
#     c) 每次编译都要联网重新下载约 80MB。
#   - 想回到钉版可复现模式:把下方 Build/Prepare 换成默认解包,并设
#     PKG_VERSION / PKG_SOURCE:=open-box-v$(PKG_VERSION)-linux-$(OPENBOX_ARCH).tar.gz /
#     PKG_SOURCE_URL:=.../releases/download/v$(PKG_VERSION) / 按架构的 PKG_HASH。
#
# 工作原理:
#   编译时从上游 GitHub Releases 下载对应架构的官方发布包(与 install.sh
#   下载的是同一个 tarball,含 node 运行时、sing-box 内核、面板前端/后端),
#   解包后按 install.sh 的铺装逻辑装进固件:
#     /opt/open-box/          程序本体(node/panel/bin/meta.json/update.sh/uninstall.sh)
#     /etc/init.d/openbox{,-panel}  procd 服务(内核 + 面板)
#     /www/luci-static/resources/view/openbox/status.js   LuCI 兜底页
#     /usr/share/luci/menu.d/luci-app-openbox.json        LuCI 菜单(服务 → Open-Box)
#     /usr/share/rpcd/acl.d/luci-app-openbox.json         LuCI ACL
#   首次开机由 /etc/uci-defaults/ 启用面板自启(与 install.sh 一致:只启面板,
#   不启内核——内核等你在面板里配好订阅后再启动)。
#
# 注意:
#   - 仅支持 x86_64 与 aarch64(上游只发布这两种架构,install.sh 同样限制)。
#   - 发布包解压后约 150MB+,squashfs 压缩后固件体积约增加 80~90MB,
#     请确认设备 Flash 够大(eMMC/大容量 NAND,或 extroot)。
#
# 这是预览包,以官方安装脚本 scripts/install.sh 为权威参考。
#

include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-openbox
# 追最新模式下版本号不对应具体上游版本,取构建日期代替,仅用于构建目录
# 命名与包版本;实际编入的上游版本以编译日志 / meta.json 为准。
# 注意:必须是合法 apk 版本号(以数字开头),OpenWrt master 已改用 apk 打包,
# "latest" 这类纯字符串会被 apk 拒绝:
#   ERROR: info field 'version' has invalid value: package version is invalid
PKG_VERSION:=$(shell date +%Y.%m.%d)
PKG_RELEASE:=1

PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=bin/sing-box.LICENSE node/LICENSE
PKG_MAINTAINER:=liandu2024

# 发布包按架构分发,映射 OpenWrt ARCH → 上游资产名后缀
ifeq ($(ARCH),x86_64)
  OPENBOX_ARCH:=x64
else ifeq ($(ARCH),aarch64)
  OPENBOX_ARCH:=arm64
endif

# 稳定资产名:GitHub 把 releases/latest/download/<资产名> 302 到最新 release 的
# 同名资产,常见加速站也普遍代理这条路径(与 install.sh 同源)
OPENBOX_LATEST_URL:=https://github.com/liandu2024/Open-Box/releases/latest/download/open-box-linux-$(OPENBOX_ARCH).tar.gz

# tarball 顶层没有包裹目录(node/ panel/ bin/ ... 直接在根)

PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)-$(PKG_VERSION)

include $(INCLUDE_DIR)/package.mk

define Package/luci-app-openbox
  SECTION:=luci
  CATEGORY:=LuCI
  SUBMENU:=3. Applications
  TITLE:=Open-Box - sing-box transparent proxy with web panel
  URL:=https://github.com/liandu2024/Open-Box
  # +libc: 声明运行时依赖(内置 node/sing-box 是 musl 动态链接的预编译
  #        二进制)。注意它无法单独通过打包期的库依赖检查——见下方
  #        extra_provides 的说明。
  DEPENDS:=@(TARGET_x86_64||TARGET_aarch64) \
    +libc \
    +luci-base \
    +kmod-tun \
    +kmod-nft-tproxy \
    +ca-bundle
  # kmod-tun: 内核 tun 入站;kmod-nft-tproxy: tproxy/共享网络;
  # ca-bundle: 面板内自更新 / update.sh 走 https 下载需要根证书
endef

# 打包期库依赖检查(gen-dependencies.sh)会扫描装入固件的 ELF 的 DT_NEEDED,
# 要求每个库名出现在本包的 .provides(= 自带 lib*.so* + 各 DEPENDS 包的
# provides + 下面的 extra_provides)里。
# node/sing-box 是 Alpine/musl 环境预编译的,NEEDED 记的是 musl 的 SONAME
# "libc.musl-$(ARCH).so.1";而 OpenWrt 的 libc 包只装 ld-musl-$(ARCH).so.1
# 和 libc.so*,provides 里没有这个名字——所以只写 +libc 仍会报
# "missing dependencies for the following libraries: libc.musl-x86_64.so.1"。
# 运行时并无问题(musl ldso 把自身 SONAME 视为已加载,这也是 install.sh
# 方式一直能跑的原因),这里只是向检查器声明该 soname 已满足。
define Package/luci-app-openbox/extra_provides
	echo "libc.musl-$(ARCH).so.1";
endef

define Package/luci-app-openbox/description
 Open-Box is an all-in-one transparent proxy on OpenWrt: sing-box core plus
 a web management panel (subscriptions, routing policies, DNS takeover,
 per-device routing, traffic stats). This package bundles the official
 release payload into the firmware image — no SSH install script needed.
endef

# 不设 PKG_SOURCE / PKG_HASH,下载不走 download.pl 与 dl/ 缓存(见文件头说明)
define Build/Download
endef

define Build/Prepare
	@[ -n "$(OPENBOX_ARCH)" ] || { echo >&2 "luci-app-openbox: 不支持的架构 $(ARCH),仅支持 x86_64 / aarch64"; exit 1; }
	@command -v curl >/dev/null 2>&1 || { echo >&2 "luci-app-openbox: 编译机上需要 curl"; exit 1; }
	rm -rf $(PKG_BUILD_DIR)
	mkdir -p $(PKG_BUILD_DIR)
	echo "luci-app-openbox: 正在拉取上游最新发布包 open-box-linux-$(OPENBOX_ARCH).tar.gz ..."
	curl -fsSL --retry 3 "$(OPENBOX_LATEST_URL)" | tar -xz -C $(PKG_BUILD_DIR)
	@test -f $(PKG_BUILD_DIR)/meta.json || { echo >&2 "luci-app-openbox: 解包结果异常(缺少 meta.json)"; exit 1; }
	@sed -n 's/.*"version" *: *"\([^"]*\)".*/luci-app-openbox: 本次编入的上游版本 \1/p' $(PKG_BUILD_DIR)/meta.json
endef

define Build/Compile
	# 发布包已是编译好的产物(node/sing-box 二进制 + 面板构建结果),无需编译
endef

define Package/luci-app-openbox/install
	# ---- 程序本体 → /opt/open-box/(与 install.sh 的铺装目标一致)----
	$(INSTALL_DIR) $(1)/opt/open-box
	$(CP) $(PKG_BUILD_DIR)/node $(1)/opt/open-box/
	$(CP) $(PKG_BUILD_DIR)/panel $(1)/opt/open-box/
	$(CP) $(PKG_BUILD_DIR)/bin $(1)/opt/open-box/
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/meta.json $(1)/opt/open-box/
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/update.sh $(1)/opt/open-box/
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/uninstall.sh $(1)/opt/open-box/

	# data/:运行期数据(订阅、规则、面板密码)。预置 channel=direct,
	# 与 install.sh 直连安装的行为一致,供面板自更新/update.sh 判断下载通道。
	$(INSTALL_DIR) $(1)/opt/open-box/data
	printf 'direct\n' > $(1)/opt/open-box/data/channel

	# ---- procd 服务 ----
	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/openwrt/initd/openbox $(1)/etc/init.d/openbox
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/openwrt/initd/openbox-panel $(1)/etc/init.d/openbox-panel

	# ---- LuCI 三件套(兜底页,装到标准路径,无需 install.sh 的 rpcd 重启/清缓存)----
	$(INSTALL_DIR) $(1)/www/luci-static/resources/view/openbox
	# 按目录拷,不写死文件名:上游 v0.1.216+ 把 status.js 改名 main.js
	# (绕浏览器对 luci-static 的缓存),以后还可能再改;用 *.js 通配,
	# 与 install.sh 同策略,避免新包配旧 Makefile 在这里硬失败
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/openwrt/luci/htdocs/luci-static/resources/view/openbox/*.js \
		$(1)/www/luci-static/resources/view/openbox/
	$(INSTALL_DIR) $(1)/usr/share/luci/menu.d
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/openwrt/luci/root/usr/share/luci/menu.d/luci-app-openbox.json \
		$(1)/usr/share/luci/menu.d/
	$(INSTALL_DIR) $(1)/usr/share/rpcd/acl.d
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/openwrt/luci/root/usr/share/rpcd/acl.d/luci-app-openbox.json \
		$(1)/usr/share/rpcd/acl.d/

	# ---- 首次开机启用面板自启 ----
	$(INSTALL_DIR) $(1)/etc/uci-defaults
	$(INSTALL_BIN) ./files/etc/uci-defaults/99-luci-app-openbox $(1)/etc/uci-defaults/
endef

# opkg 方式安装(编译为 <M> 后 opkg install)时等价于 install.sh 的收尾动作
define Package/luci-app-openbox/postinst
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] && exit 0
rm -rf /tmp/luci-*cache* 2>/dev/null
/etc/init.d/openbox-panel enable
/etc/init.d/openbox-panel start
exit 0
endef

define Package/luci-app-openbox/prerm
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] && exit 0
/etc/init.d/openbox stop >/dev/null 2>&1
/etc/init.d/openbox-panel stop >/dev/null 2>&1
/etc/init.d/openbox disable >/dev/null 2>&1
/etc/init.d/openbox-panel disable >/dev/null 2>&1
exit 0
endef

$(eval $(call BuildPackage,luci-app-openbox))
