#!/bin/sh
# sing-box 内核守护循环（iKuai 专用）：等效 systemd openbox.service 的 Restart=on-failure
# 只要 data/.core-enabled 存在就反复拉起内核；日志写成 syslog short 格式供面板 logread 替身解析
ROOT=/opt/open-box
DATA="$ROOT/data"
ENABLED="$DATA/.core-enabled"
CTL="$ROOT/debian/bin/openbox-ctl"
LOG="$DATA/logs/core.log"
PIDFILE="$DATA/core-supervisor.pid"

mkdir -p "$DATA/logs"
# 单实例锁：防止看门狗与 ctl 并发拉起多个守护循环互踩
exec 9> "$DATA/core-supervisor.lock"
flock -n 9 || exit 0
echo $$ > "$PIDFILE"

# 与 debian systemd 单元一致的环境
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export OPENBOX_DIRECT_ANSWER_FLAG="$DATA/flip/direct-answer.on"

while [ -f "$ENABLED" ]; do
	"$CTL" pre-start || sleep 2
	# 9>&-：sing-box 和日志子壳不继承 flock 锁 fd，
	# 否则守护被杀后孤儿 sing-box 继续持有锁，新守护起不来
	"$ROOT/bin/sing-box" run -c "$ROOT/etc/config.json" -D "$DATA" 9>&- 2>&1 | \
	while IFS= read -r _line; do
		echo "$(date '+%b %e %H:%M:%S') iKuai sing-box[$$]: $_line" >> "$LOG"
	done 9>&-
	"$CTL" post-stop
	[ -f "$ENABLED" ] || break
	echo "$(date '+%b %e %H:%M:%S') iKuai sing-box[$$]: core exited, respawn in 5s" >> "$LOG"
	sleep 5
done
rm -f "$PIDFILE"
exit 0
