#!/bin/sh
# Open-Box 面板启动脚本（iKuai 专用）
# 基于 debian/bin/openbox-panel-run，差异：
#  - iKuai 是 uClibc 系统，node 为 musl 版，必须 LD_LIBRARY_PATH 指向捆绑的 musl libstdc++/libgcc
#  - logread 替身用 ikuai/shim（读本地日志文件），不用 journalctl
OPENBOX_ROOT=/opt/open-box
NODE="$OPENBOX_ROOT/node/bin/node"
# iKuai 上 /opt/open-box 是指向 /etc/log/open-box 的符号链接。
# index.mjs 用 argv[1] 与 import.meta.url（已解析真实路径）比较来判断是否直接执行，
# 传符号链接路径会判定为"非直接执行"而静默退出——必须传真实路径
REAL_ROOT=$(readlink -f "$OPENBOX_ROOT" 2>/dev/null)
[ -n "$REAL_ROOT" ] || REAL_ROOT="$OPENBOX_ROOT"
ENTRY="$REAL_ROOT/panel/server/index.mjs"
DATA="$OPENBOX_ROOT/data"

if [ ! -x "$NODE" ]; then
	echo "openbox-panel: node runtime not found at $NODE" >&2
	exit 1
fi
if [ ! -f "$ENTRY" ]; then
	echo "openbox-panel: panel entry not found at $ENTRY" >&2
	exit 1
fi
mkdir -p "$DATA" "$DATA/logs"

# 命令行 open-box（看面板密码 / 检查升级）
if [ -f "$OPENBOX_ROOT/openwrt/bin/open-box" ] && { [ ! -e /usr/bin/open-box ] || [ -L /usr/bin/open-box ]; }; then
	chmod +x "$OPENBOX_ROOT/openwrt/bin/open-box" 2>/dev/null
	ln -sf "$OPENBOX_ROOT/openwrt/bin/open-box" /usr/bin/open-box 2>/dev/null
fi

panel_port=$(cat "$DATA/panel-port" 2>/dev/null | tr -dc '0-9')
[ -n "$panel_port" ] || panel_port=3036
heap_mb=160
mem_kb=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null)
[ -n "$mem_kb" ] && [ "$mem_kb" -lt 786432 ] && heap_mb=128

# musl 版 node 必须优先加载包内捆绑的 musl libstdc++/libgcc，
# 否则会误载 iKuai 系统的 uClibc 版导致符号缺失。
# 注意：不能用 export LD_LIBRARY_PATH——面板派生的 busybox（uClibc）会继承该变量，
# 其 libgcc_s.so.1 被劫持成 musl 版后报 "can't load library 'libc.musl-x86_64.so.1'"。
# 改为用 musl 加载器的 --library-path 参数，只对 node 本进程生效，不污染环境。
MUSL_LOADER="$REAL_ROOT/musl/libc.so"
[ -x "$MUSL_LOADER" ] || MUSL_LOADER=/lib/ld-musl-x86_64.so.1
unset LD_LIBRARY_PATH LD_PRELOAD
export PATH="$OPENBOX_ROOT/ikuai/shim:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export PORT="$panel_port" HOST=:: OPENBOX_ROOT="$OPENBOX_ROOT" OPENBOX_PANEL_HEAP_MB="$heap_mb" \
	ZASHBOARD_DB_PATH="$DATA/openbox.sqlite" OPENBOX_PLATFORM=systemd OPENSSL_CONF=/dev/null
# BusyBox start-stop-daemon -b 会把子进程输出丢进 /dev/null，
# 面板自己的日志重定向到这里（watchdog 负责截断）
exec >> "$DATA/logs/panel.log" 2>&1
exec "$MUSL_LOADER" --library-path "$OPENBOX_ROOT/node/lib" "$NODE" "--max-old-space-size=$heap_mb" "$ENTRY"
