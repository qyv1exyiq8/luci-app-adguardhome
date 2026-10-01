# Maintained for xztxy OpenWrt firmware builds
#
# This is free software, licensed under the GNU General Public License v3.
#

include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-autoupdate
LUCI_TITLE:=LuCI Support for AutoUpdate
LUCI_DEPENDS:=+uclient-fetch +wget-ssl +jq +bc
LUCI_PKGARCH:=all


include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
