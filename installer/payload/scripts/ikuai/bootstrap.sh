#!/bin/sh
# Open-Box iKuai 引导修复脚本
# 用途：爱快固件升级或根文件系统被重置后（/opt、/lib 链接和 crontab 丢失），
#       SSH 登录后执行一次  sh /etc/log/open-box/ikuai/bootstrap.sh  即可完整恢复。
# /etc/log 是持久数据分区（/dev/nda5），Open-Box 全部文件都在上面，不会因固件升级丢失。
OB=/etc/log/open-box
[ -d "$OB" ] || { echo "ERROR: $OB 不存在，Open-Box 数据分区未挂载？"; exit 1; }

# 1. /opt/open-box 符号链接（脚本内大量硬编码此路径）
mkdir -p /opt
ln -sfn "$OB" /opt/open-box

# 2. musl 动态链接器（iKuai 是 uClibc 系统，musl 版 node 需要 /lib/ld-musl-x86_64.so.1）
ln -sfn "$OB/musl/libc.so" /lib/ld-musl-x86_64.so.1

# 3. 看门狗 cron（主 crontab + cron.d 双写，任一被重建都能存活）
grep -q 'open-box/ikuai/watchdog.sh' /etc/crontabs/root 2>/dev/null || \
	echo '* * * * * /opt/open-box/ikuai/watchdog.sh >/dev/null 2>&1' >> /etc/crontabs/root
mkdir -p /etc/crontabs/cron.d
echo '* * * * * /opt/open-box/ikuai/watchdog.sh >/dev/null 2>&1' > /etc/crontabs/cron.d/openbox
chmod 644 /etc/crontabs/cron.d/openbox

# 4. 权限修正
chmod 755 "$OB"/ikuai/*.sh "$OB"/ikuai/shim/logread "$OB"/debian/bin/openbox-ctl 2>/dev/null
chmod 755 "$OB"/node/bin/node "$OB"/musl/libc.so "$OB"/node/lib/* 2>/dev/null

# 5. 立即拉起面板（以及处于启用状态的内核）
/opt/open-box/ikuai/watchdog.sh

PORT=$(cat "$OB/data/panel-port" 2>/dev/null | tr -dc '0-9')
[ -n "$PORT" ] || PORT=3036
echo "bootstrap done. 面板地址: http://<爱快LAN IP>:$PORT"
