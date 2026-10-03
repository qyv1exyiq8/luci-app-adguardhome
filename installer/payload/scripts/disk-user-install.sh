#!/bin/sh
# Open-Box 开机自启脚本（iKuai 固件 patch-9 钩子调用）
# 固件 /usr/ikuai/script/rc 的 start_ikuai_services() 每次开机执行本脚本：
#   [ -e /etc/log/disk_user/openbox/install.sh ] && sh .../install.sh >/tmp/iktmp/bootlog/openbox_install 2>&1 &
# 本脚本位于持久分区 /etc/log，重启不丢。实际工作由 watchdog v3 完成：
# 重建 /opt、/lib 符号链接 → 补 crontab → 拉起面板 → 内核启用则拉起内核。
# 开机早期时序不确定（tun 设备、网络就绪时间），分三次调用兜底。
sh /etc/log/open-box/ikuai/watchdog.sh
( sleep 20; sh /etc/log/open-box/ikuai/watchdog.sh ) &
( sleep 60; sh /etc/log/open-box/ikuai/watchdog.sh ) &
exit 0
