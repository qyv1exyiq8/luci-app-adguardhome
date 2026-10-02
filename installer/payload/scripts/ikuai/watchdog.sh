#!/bin/sh
# Open-Box 看门狗（iKuai 专用）v2 —— 自愈合版本
# 由 crond 每分钟调用（推荐：爱快 Web「计划任务」填  sh /etc/log/open-box/ikuai/watchdog.sh）
#
# iKuai 重启后根文件系统会被重建，/opt、/lib 里的符号链接和 crontab 全部丢失，
# 只有 /etc/log（sda5 持久分区）还在。本脚本每次运行先自愈环境，再检查服务：
#   1. 重建 /opt/open-box 与 /lib/ld-musl-x86_64.so.1 符号链接
#   2. 补写 crontab（当前启动周期内双写保险）
#   3. 面板进程死了就拉起（等效 systemd Restart=always）
#   4. 内核处于启用状态而守护循环死了就拉起
#   5. 日志文件超过 2MB 截断保留尾部 1MB
OB=/etc/log/open-box
ROOT=/opt/open-box
DATA="$OB/data"

# 1) 符号链接自愈（根文件系统重启后被重建，/opt 和 /lib 里的链接会丢）
if [ ! -e "$ROOT/meta.json" ]; then
	mkdir -p /opt
	ln -sfn "$OB" "$ROOT"
fi
if [ ! -e /lib/ld-musl-x86_64.so.1 ]; then
	ln -sfn "$OB/musl/libc.so" /lib/ld-musl-x86_64.so.1
fi

# 2) crontab 双写保险（爱快 Web 计划任务若未配，当前周期内兜底）
grep -q 'ikuai/watchdog.sh' /etc/crontabs/root 2>/dev/null || \
	echo '* * * * * /opt/open-box/ikuai/watchdog.sh >/dev/null 2>&1' >> /etc/crontabs/root 2>/dev/null
if [ -d /etc/crontabs/cron.d ] && [ ! -f /etc/crontabs/cron.d/openbox ]; then
	echo '* * * * * /opt/open-box/ikuai/watchdog.sh >/dev/null 2>&1' > /etc/crontabs/cron.d/openbox
	chmod 644 /etc/crontabs/cron.d/openbox 2>/dev/null
fi

mkdir -p "$DATA/logs"
# 心跳：供排查 cron 是否真的每分钟触发
touch "$DATA/logs/.watchdog-alive"

for f in "$DATA/logs/core.log" "$DATA/logs/panel.log"; do
	if [ -f "$f" ]; then
		sz=$(wc -c < "$f" 2>/dev/null | tr -dc '0-9')
		if [ -n "$sz" ] && [ "$sz" -gt 2097152 ]; then
			tail -c 1048576 "$f" > "$f.tmp" 2>/dev/null && mv "$f.tmp" "$f"
		fi
	fi
done

# 3) 面板
if ! pgrep -f 'panel/server/index.mjs' >/dev/null 2>&1; then
	start-stop-daemon -S -b -x "$OB/ikuai/panel-run.sh" >> "$DATA/logs/panel.log" 2>&1
fi

# 4) 强制 autoRedirect=false（面板保存配置可能重置回 true；iKuai 无 nftables 必须恒 false）
[ -f "$OB/ikuai/force-tun.js" ] && \
	"$OB/musl/libc.so" --library-path "$OB/node/lib" "$OB/node/bin/node" "$OB/ikuai/force-tun.js" \
	>> "$DATA/logs/watchdog.log" 2>&1

# 5) 内核（仅在启用状态下）
[ -f "$DATA/.core-enabled" ] || exit 0
pgrep -f 'bin/sing-box run' >/dev/null 2>&1 && exit 0
if [ -f "$DATA/core-supervisor.pid" ] && kill -0 "$(cat "$DATA/core-supervisor.pid" 2>/dev/null)" 2>/dev/null; then
	exit 0
fi
# 直接后台拉起（flock 单实例锁防重）
"$OB/ikuai/core-supervisor.sh" >/dev/null 2>&1 &
exit 0
