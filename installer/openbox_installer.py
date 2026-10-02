# -*- coding: utf-8 -*-
"""
Open-Box 爱快安装程序
- 自定义主机地址 / 用户名 / 端口(默认22) / SSH密码 / 面板密码
- Ping 测试、SSH 连接测试
- 一键安装，实时显示安装日志
- 修复内核（关闭 autoRedirect + 重启内核 + 验证）
"""
import base64
import hashlib
import io
import json
import os
import queue
import socket
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
import urllib.error

import tkinter as tk
from tkinter import scrolledtext, messagebox

import paramiko

APP_TITLE = "Open-Box 爱快安装程序"
OB_DIR = "/etc/log/open-box"
OB_LINK = "/opt/open-box"
PANEL_PORT = 3036

# ---------- GitHub 云端下载 ----------
GH_REPO = "liandu2024/Open-Box"
GH_RELEASE_API = f"https://api.github.com/repos/{GH_REPO}/releases/latest"
GH_API_MIRRORS = [
    "https://api.kkgithub.com/repos/liandu2024/Open-Box/releases/latest",
]
# 下载镜像前缀（空串=直连），按顺序依次尝试
GH_DL_MIRRORS = [
    "",
    "https://gh-proxy.com/",
    "https://ghfast.top/",
    "https://ghproxy.net/",
]
HTTP_HEADERS = {"User-Agent": "openbox-ikuai-installer/1.0"}

# ---------- Deep Dark Pro 主题色 ----------
C_BG      = "#1a1a2e"  # 窗口主背景
C_HDR     = "#16213e"  # 头部背景
C_PANEL   = "#16213e"  # 卡片背景
C_ACCENT  = "#e94560"  # 强调红
C_ACCENT2 = "#7ecfff"  # 强调青
C_INPUT   = "#0d0d1a"  # 输入框背景
C_BORDER  = "#2a2a4a"  # 边框
C_TEXT    = "#eeeeee"  # 主文字
C_HINT    = "#8888aa"  # 提示文字
C_LOG     = "#0d0d1a"  # 日志背景
C_LOGFG   = "#00ff88"  # 日志文字（终端绿）

# 资源目录：PyInstaller 打包后在 sys._MEIPASS，开发时在脚本同级的 payload/
def res_path(*parts):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "payload", *parts)


class Installer:
    def __init__(self, log):
        self.log = log
        self.ssh = None

    # ---------- 基础工具 ----------
    def connect(self, host, port, user, password):
        self.log(f"SSH 连接 {user}@{host}:{port} ...")
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(host, port=port, username=user, password=password,
                  timeout=10, banner_timeout=10, auth_timeout=10,
                  look_for_keys=False, allow_agent=False)
        # 显示主机指纹便于人工核对
        fp = base64.b64encode(hashlib.sha256(
            c.get_transport().get_remote_server_key().asbytes()).digest()).decode().rstrip("=")
        self.log(f"  主机密钥指纹 SHA256:{fp}")
        self.ssh = c
        return c

    def run(self, cmd, timeout=120, check=True):
        """执行远程命令，返回 (code, out)；check=True 时非 0 抛异常"""
        stdin, stdout, stderr = self.ssh.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        code = stdout.channel.recv_exit_status()
        text = (out + err).strip()
        if check and code != 0:
            raise RuntimeError(f"命令失败(exit {code}): {cmd}\n{text[-800:]}")
        return code, text

    def upload(self, local, remote, size_mb_warn=1.0):
        """爱快无 sftp-server：用 cat 管道推文件，带进度"""
        total = os.path.getsize(local)
        self.log(f"  上传 {os.path.basename(local)} ({total/1048576:.1f} MB) → {remote}")
        stdin, stdout, stderr = self.ssh.exec_command(f"cat > {remote}", timeout=600)
        sent, t0, last = 0, time.time(), 0
        with open(local, "rb") as f:
            while True:
                chunk = f.read(1048576)
                if not chunk:
                    break
                stdin.write(chunk)
                stdin.flush()
                sent += len(chunk)
                pct = sent * 100 // total
                if pct // 10 > last // 10:
                    self.log(f"    {pct}%  ({sent/1048576:.0f}/{total/1048576:.0f} MB)")
                    last = pct
        stdin.channel.shutdown_write()
        code = stdout.channel.recv_exit_status()
        err = stderr.read().decode("utf-8", "replace").strip()
        if code != 0:
            raise RuntimeError(f"上传失败(exit {code}): {err[-400:]}")
        self.log(f"  上传完成，用时 {time.time()-t0:.0f}s")

    def step(self, n, title):
        self.log(f"\n== 第 {n} 步：{title} ==")

    # ---------- 云端检测 / 加速下载 ----------
    def _http_get_json(self, url, timeout=20):
        req = urllib.request.Request(url, headers=HTTP_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _sha256_file(self, path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1048576), b""):
                h.update(chunk)
        return h.hexdigest()

    def cloud_latest(self):
        """查询 GitHub 最新 release，返回 (tag, {资产名: (大小, sha256)})。"""
        errs, data = [], None
        for api in [GH_RELEASE_API] + GH_API_MIRRORS:
            try:
                data = self._http_get_json(api)
                self.log(f"  版本探测：{api.split('/')[2]} OK")
                break
            except Exception as e:
                errs.append(f"{api}: {e}")
        if data is None:
            raise RuntimeError("GitHub 版本检测失败：\n" + "\n".join(errs))
        tag = data.get("tag_name", "")
        assets = {a.get("name"): a for a in data.get("assets", [])}
        result = {}
        for name in (f"open-box-{tag}-linux-x64.tar.gz", f"open-box-{tag}-linux-x64-runtime.tar.gz"):
            if name not in assets:  # 兼容无版本前缀的别名资产
                alias = name.replace(f"-{tag}", "", 1)
                if alias in assets:
                    name = alias
            info = assets.get(name)
            if not info:
                raise RuntimeError(f"release {tag} 中找不到资产 {name}")
            size = int(info.get("size", 0))
            sha256 = ""
            sha_url = assets.get(name + ".sha256", {}).get("browser_download_url", "")
            if sha_url:
                for m in GH_DL_MIRRORS:
                    try:
                        req = urllib.request.Request(m + sha_url, headers=HTTP_HEADERS)
                        with urllib.request.urlopen(req, timeout=20) as r:
                            sha256 = r.read().decode("utf-8").split()[0].strip().lower()
                        if sha256:
                            break
                    except Exception:
                        continue
            result[name] = (size, sha256)
        return tag, result

    def cloud_download(self, tag, name, size, sha256, dest_dir):
        """多镜像依次尝试下载（带进度与缓存），完成后校验大小+SHA256。"""
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, name)
        if os.path.exists(dest) and os.path.getsize(dest) == size:
            if not sha256 or self._sha256_file(dest) == sha256:
                self.log(f"  本地缓存已是最新（{name}），跳过重下")
                return dest
            os.unlink(dest)
        base = f"https://github.com/{GH_REPO}/releases/download/{tag}/{name}"
        last_err = None
        for m in GH_DL_MIRRORS:
            url = m + base
            try:
                self.log(f"  下载 {name}（{size / 1048576:.0f} MB），via {m or '直连'} ...")
                req = urllib.request.Request(url, headers=HTTP_HEADERS)
                t0, got, mark = time.time(), 0, -10
                with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
                    while True:
                        chunk = r.read(1048576)
                        if not chunk:
                            break
                        f.write(chunk)
                        got += len(chunk)
                        if size:
                            pct = got * 100 // size
                            if pct >= mark + 10:
                                mark = pct - pct % 10
                                spd = got / 1048576 / max(time.time() - t0, 0.1)
                                self.log(f"    {mark}%  ({got / 1048576:.0f}/{size / 1048576:.0f} MB, {spd:.1f} MB/s)")
                if size and os.path.getsize(dest) != size:
                    raise RuntimeError(f"文件大小不符 {os.path.getsize(dest)} != {size}")
                if sha256 and self._sha256_file(dest) != sha256:
                    raise RuntimeError("SHA256 与官方发布值不符")
                self.log(f"  下载完成、校验通过，用时 {time.time() - t0:.0f}s")
                return dest
            except Exception as e:
                last_err = e
                self.log(f"  [提示] {m or '直连'} 失败：{e}，换下一镜像...")
                if os.path.exists(dest):
                    os.unlink(dest)
        raise RuntimeError(f"所有镜像均下载失败：{last_err}")

    # ---------- 安装主流程 ----------
    def install(self, host, port, user, password, panel_password, dest_dir):
        """全流程：云端检测下载 → SSH → 安装（大文件全走云端，exe 只带 musl 加载器与脚本）"""
        s = self.step

        s(1, "云端检测 GitHub 最新 release")
        tag, assets = self.cloud_latest()
        self.log(f"  云端最新版：{tag}")
        paths = {}
        for name, (size, sha256) in assets.items():
            label = "主安装包" if "runtime" not in name else "Node 运行时"
            self.log(f"  组件[{label}] {name}（{size / 1048576:.0f} MB）")
            paths[name] = self.cloud_download(tag, name, size, sha256, dest_dir)
        bundle_name = next(n for n in paths if "runtime" not in n)
        runtime_name = next(n for n in paths if "runtime" in n)
        bundle, bundle_sha = paths[bundle_name], assets[bundle_name][1]
        runtime, runtime_sha = paths[runtime_name], assets[runtime_name][1]

        s(2, "SSH 连接与环境检查")
        self.connect(host, port, user, password)
        _, uname = self.run("uname -m")
        if "x86_64" not in uname:
            raise RuntimeError(f"目标机器架构为 {uname}，本安装包仅支持 x86_64")
        _, tun = self.run("ls /dev/net/tun && echo TUN_OK")
        if "TUN_OK" not in tun:
            self.log("  [警告] 未发现 /dev/net/tun，继续安装但内核可能无法启动")
        self.log(f"  架构 {uname.strip()}，TUN 设备就绪")

        s(3, "上传并校验主安装包")
        self.upload(bundle, "/tmp/ob.tar.gz")
        if bundle_sha:
            _, sha = self.run("sha256sum /tmp/ob.tar.gz | awk '{print $1}'")
            if sha.strip() != bundle_sha:
                self.run("rm -f /tmp/ob.tar.gz", check=False)
                raise RuntimeError(f"SHA256 校验失败：{sha.strip()}，请重试")
            self.log("  SHA256 校验通过（对照官方发布值）")
        else:
            self.log("  [提示] 云端未提供校验值，跳过 SHA256 校验")

        s(4, "解包到 /etc/log/open-box 并建立 /opt 链接")
        self.run("mkdir -p /etc/log/open-box && tar -xzf /tmp/ob.tar.gz -C /etc/log/open-box "
                 "&& chown -R 0:0 /etc/log/open-box && rm -f /tmp/ob.tar.gz", timeout=300)
        self.run("mkdir -p /opt && ln -sfn /etc/log/open-box /opt/open-box && ls /opt/open-box/meta.json")
        self.log("  主程序解包完成")

        s(5, "部署 Node 运行时（云端 runtime + 内置 musl 加载器）")
        self.upload(runtime, "/tmp/runtime.tgz")
        if runtime_sha:
            _, sha = self.run("sha256sum /tmp/runtime.tgz | awk '{print $1}'")
            if sha.strip() != runtime_sha:
                raise RuntimeError(f"runtime 包 SHA256 校验失败：{sha.strip()}")
            self.log("  runtime 包 SHA256 校验通过")
        self.upload(res_path("musl", "libc.so"), "/etc/log/open-box/musl/libc.so")
        self.run("mkdir -p /etc/log/open-box/musl && cd /tmp && mkdir -p rt && tar -xzf runtime.tgz -C rt "
                 "&& cp -r rt/node/* /etc/log/open-box/node/ "
                 "&& rm -rf /etc/log/open-box/node/.flavor rt /tmp/runtime.tgz "
                 "&& chmod 755 /etc/log/open-box/node/bin/node /etc/log/open-box/musl/libc.so /etc/log/open-box/node/lib/* "
                 "&& ln -sf /etc/log/open-box/musl/libc.so /lib/ld-musl-x86_64.so.1", timeout=300)
        _, nver = self.run("/etc/log/open-box/musl/libc.so --library-path /opt/open-box/node/lib "
                           "/opt/open-box/node/bin/node -v")
        if "v24" not in nver:
            raise RuntimeError(f"Node 验证失败：{nver}")
        self.log(f"  Node {nver.strip()} 运行正常")

        s(6, "部署爱快适配脚本")
        tgz = self._build_scripts_tgz()
        tmp_local = os.path.join(os.environ.get("TEMP", "."), "ob-scripts.tgz")
        with open(tmp_local, "wb") as f:
            f.write(tgz)
        self.upload(tmp_local, "/tmp/scripts.tgz")
        os.unlink(tmp_local)
        self.run("mkdir -p /etc/log/open-box/ikuai/shim /etc/log/open-box/data/logs && cd /tmp "
                 "&& tar -xzf scripts.tgz "
                 "&& cp openbox-ctl openbox-panel-ctl /etc/log/open-box/debian/bin/ "
                 "&& cp ikuai/panel-run.sh ikuai/core-supervisor.sh ikuai/watchdog.sh ikuai/bootstrap.sh /etc/log/open-box/ikuai/ "
                 "&& cp ikuai/force-tun.js /etc/log/open-box/ikuai/ "
                 "&& cp ikuai/shim/logread /etc/log/open-box/ikuai/shim/ "
                 "&& cp cron.d.openbox /etc/crontabs/cron.d/openbox "
                 "&& mkdir -p /etc/log/disk_user/openbox && cp disk-user-install.sh /etc/log/disk_user/openbox/install.sh "
                 "&& chmod 755 /etc/log/disk_user/openbox/install.sh "
                 "&& rm -rf /tmp/ikuai /tmp/openbox-ctl /tmp/openbox-panel-ctl /tmp/cron.d.openbox /tmp/scripts.tgz "
                 "&& chmod 755 /etc/log/open-box/ikuai/panel-run.sh /etc/log/open-box/ikuai/core-supervisor.sh "
                 "/etc/log/open-box/ikuai/watchdog.sh /etc/log/open-box/ikuai/bootstrap.sh "
                 "/etc/log/open-box/ikuai/shim/logread /etc/log/open-box/debian/bin/openbox-ctl "
                 "/etc/log/open-box/debian/bin/openbox-panel-ctl && chmod 644 /etc/crontabs/cron.d/openbox "
                 f"&& printf '{PANEL_PORT}\\n' > /etc/log/open-box/data/panel-port")
        self.log("  控制脚本与看门狗脚本安装完成")

        s(7, "写入开机自启（crontab 双保险）")
        # 爱快 crond 读 /etc/crontabs/root，且会把 cron.d/* 周期性合并重建 root。
        # 两处都写：cron.d 为爱快原生机制，root 追加防老版本不合并。重复行无害（看门狗幂等）。
        self.run("grep -q 'ikuai/watchdog.sh' /etc/crontabs/root 2>/dev/null || "
                 "echo '* * * * * /opt/open-box/ikuai/watchdog.sh >/dev/null 2>&1' >> /etc/crontabs/root")
        _c1, in_root = self.run("grep -c 'ikuai/watchdog.sh' /etc/crontabs/root 2>/dev/null; true", check=False)
        _c2, in_crond = self.run("grep -c 'ikuai/watchdog.sh' /etc/crontabs/cron.d/openbox 2>/dev/null; true", check=False)
        n_root = int((in_root.strip() or "0").split("\n")[-1] or 0)
        n_crond = int((in_crond.strip() or "0").split("\n")[-1] or 0)
        if n_root + n_crond == 0:
            raise RuntimeError("crontab 写入失败：root 与 cron.d 均无看门狗条目")
        self.log(f"  看门狗定时任务已写入（root 主表 {n_root} 条 + cron.d {n_crond} 条）")
        self.log("  ⚠ 注意：爱快重启会重建根文件系统并清空 crontab，此写入仅当前周期有效！")
        self.log("    永久方案见安装完成后的【开机自启】提示。")

        s(8, "启动面板并验证")
        self.run("/opt/open-box/ikuai/watchdog.sh")
        ok = False
        for i in range(15):
            time.sleep(2)
            code, http = self.run("curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:3036/ 2>/dev/null",
                                  check=False)
            if http.strip() == "200":
                ok = True
                break
        if not ok:
            _, plog = self.run("tail -20 /opt/open-box/data/logs/panel.log 2>/dev/null", check=False)
            raise RuntimeError(f"面板 30 秒未就绪，面板日志：\n{plog[-800:]}")
        self.log(f"  面板已监听 http://{host}:{PANEL_PORT} (HTTP 200)")

        if panel_password:
            s(9, "设置面板管理密码")
            self._set_panel_password(host, panel_password)

        s(10, "修复内核（关闭 autoRedirect，预防首次启动崩溃）")
        out = self.force_tun_off()
        self.log(f"  {out.strip()}")
        if "profile not found" in out:
            self.log("  profile 尚未初始化，5 秒后重试 ...")
            time.sleep(5)
            out = self.force_tun_off()
            self.log(f"  {out.strip()}")
        _c, _flag = self.run(f"ls {OB_DIR}/data/.core-enabled 2>/dev/null", check=False)
        if _c == 0:
            self.log("  检测到内核此前已启用（重装场景），重启内核使配置生效 ...")
            self.run("/opt/open-box/debian/bin/openbox-ctl restart", timeout=60, check=False)
            time.sleep(6)
            _c2, st = self.run("pgrep -f 'bin/sing-box [r]un' >/dev/null && echo RUNNING || echo STOPPED", check=False)
            self.log(f"  内核状态：{st.strip()}")

        self.log("\n==========================================")
        self.log("安装完成！浏览器打开：")
        self.log(f"  http://{host}:{PANEL_PORT}")
        if panel_password:
            self.log("用安装时设置的面板密码登录，添加订阅后点「启动」。")
        else:
            self.log("首次访问自行设置管理密码，添加订阅后点「启动」。")
        self.log("提示：已自动关闭 autoRedirect（纯 TUN 兼容模式），面板里点「启动」内核即可正常运行。")
        # 开机自启：优先固件 patch-9 钩子（修改版固件），否则引导用户加 Web 计划任务
        code, _ = self.run("grep -q 'disk_user/openbox/install.sh' /usr/ikuai/script/rc 2>/dev/null", check=False)
        self.log("")
        if code == 0:
            self.log("【开机自启】本固件自带 openbox 开机钩子（patch-9），安装脚本已部署到")
            self.log("  /etc/log/disk_user/openbox/install.sh，路由器重启后面板和内核自动恢复。")
        else:
            self.log("【必做】爱快重启会清空 crontab，面板不会自动启动。请登录爱快 Web 后台：")
            self.log("  系统设置 → 计划任务 → 添加，填写：")
            self.log("    名称：OpenBox 看门狗")
            self.log("    时间：每分钟（分=* 时=* 日=* 月=* 星期=*）")
            self.log("    命令：sh /etc/log/open-box/ikuai/watchdog.sh")
            self.log("  保存后，以后路由器重启，面板和内核会在 1 分钟内自动恢复。")

    # ---------- 修复内核 ----------
    def force_tun_off(self):
        """用面板同款 node:sqlite 把 profile.tun.autoRedirect 压为 false。
        JS 经 cat 管道推临时文件执行（node -e 内嵌引号会被 ash 截断）。"""
        fix_js = r"""
const { DatabaseSync } = require('node:sqlite');
const db = new DatabaseSync('/opt/open-box/data/openbox.sqlite');
const row = db.prepare("SELECT value FROM app_storage WHERE key = 'openbox/profile'").get();
if (!row) { console.log('ERROR: profile not found'); process.exit(1); }
const p = JSON.parse(row.value);
if (!p.tun) p.tun = {};
const old = p.tun.autoRedirect;
p.tun.autoRedirect = false;
db.prepare("UPDATE app_storage SET value = ? WHERE key = 'openbox/profile'").run(JSON.stringify(p));
db.close();
console.log('OK: autoRedirect ' + old + ' -> false');
"""
        stdin, stdout, _stderr = self.ssh.exec_command("cat > /tmp/ob-fix-core.js", timeout=30)
        stdin.write(fix_js.encode())
        stdin.channel.shutdown_write()
        if stdout.channel.recv_exit_status() != 0:
            raise RuntimeError("上传修复脚本到 /tmp 失败")
        _code, out = self.run(
            "/opt/open-box/musl/libc.so --library-path /opt/open-box/node/lib "
            "/opt/open-box/node/bin/node /tmp/ob-fix-core.js 2>&1; "
            "rc=$?; rm -f /tmp/ob-fix-core.js; exit $rc",
            timeout=20, check=False,
        )
        return out

    def fix_core(self, host, port, user, password):
        """修复内核：关闭 autoRedirect → 重启内核 → 验证运行"""
        self.step(1, "SSH 连接")
        self.connect(host, port, user, password)

        # 检查 open-box 是否已安装
        code, _ = self.run(f"ls {OB_DIR}/meta.json 2>/dev/null", check=False)
        if code != 0:
            raise RuntimeError(
                f"未找到 {OB_DIR}/meta.json，Open-Box 可能尚未安装。\n"
                "请先使用「开始安装」完成初始安装。"
            )
        self.log("  Open-Box 安装目录确认 ✓")

        self.step(2, "关闭 autoRedirect（纯 TUN 模式）")
        out = self.force_tun_off()
        self.log(out)
        if "OK:" not in out:
            raise RuntimeError(f"关闭 autoRedirect 失败：{out}")

        self.step(3, "重启内核")
        code, out = self.run(
            "/opt/open-box/debian/bin/openbox-ctl restart",
            timeout=60, check=False,
        )
        self.log(f"  restart exit code: {code}")
        if code != 0:
            # restart 可能返回非零但实际成功了，继续验证
            self.log("  [提示] restart 返回非零，继续验证...")

        # 等待内核启动
        self.log("  等待内核启动...")
        time.sleep(5)

        self.step(4, "验证内核状态")
        for attempt in range(6):
            code, status_out = self.run(
                "/opt/open-box/debian/bin/openbox-ctl status 2>&1",
                check=False,
            )
            self.log(f"  检查 {attempt + 1}/6: {status_out.strip()}")
            if "running" in status_out.lower():
                self.log("  sing-box 内核运行中 ✓")
                break
            time.sleep(3)
        else:
            # 最后一次检查进程
            code, ps_out = self.run(
                "ps w | grep 'bin/sing-box' | grep -v grep",
                check=False,
            )
            if "sing-box" in ps_out:
                self.log("  sing-box 进程存在（status 可能误判）✓")
            else:
                raise RuntimeError("内核启动失败，请查看面板日志。")

        # 显示最近内核日志
        code, core_log = self.run(
            "tail -3 /opt/open-box/data/logs/core.log 2>/dev/null",
            check=False,
        )
        if core_log.strip():
            last_line = core_log.strip().splitlines()[-1]
            self.log(f"  内核日志：{last_line}")

        self.log("\n==========================================")
        self.log("内核修复完成！浏览器打开面板确认：")
        self.log(f"  http://{host}:{PANEL_PORT}")
        self.log("autoRedirect 已关闭（纯 TUN 模式），内核应显示「运行中」。")

    def _set_panel_password(self, host, password):
        url = f"http://{host}:{PANEL_PORT}/api/auth/setup"
        body = json.dumps({"password": password}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                json.loads(r.read())
            self.log("  面板密码设置成功")
        except urllib.error.HTTPError as e:
            if e.code == 409:
                self.log("  [提示] 面板已设置过密码，跳过（如需改密请在面板「设置」里修改）")
            elif e.code == 400:
                self.log("  [警告] 面板密码太短（至少 4 位），未设置；请首次访问时在浏览器设置")
            else:
                self.log(f"  [警告] 设置面板密码失败 HTTP {e.code}，请首次访问时在浏览器设置")

    def _build_scripts_tgz(self):
        buf = io.BytesIO()
        sdir = res_path("scripts")
        with tarfile.open(fileobj=buf, mode="w:gz") as t:
            for root, _dirs, files in os.walk(sdir):
                for fn in files:
                    full = os.path.join(root, fn)
                    arc = os.path.relpath(full, sdir).replace(os.sep, "/")
                    t.add(full, arcname=arc)
        return buf.getvalue()


# ---------------- GUI ----------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("760x600")
        # 窗口图标（打包后从 _MEIPASS 读取）
        try:
            self.iconbitmap(os.path.join(
                getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))),
                "assets", "openbox.ico"))
        except Exception:
            pass
        self.q = queue.Queue()
        self.busy = False
        self._build()
        self._disable_maximize()
        self.after(100, self._drain)

    def _disable_maximize(self):
        """禁用最大化按钮 + 禁止拖拽改窗口大小（固定 760x600 布局）"""
        self.resizable(False, False)
        if sys.platform == "win32":
            try:
                import ctypes
                GWL_STYLE = -16
                WS_MAXIMIZEBOX = 0x00010000
                self.update_idletasks()
                hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
                style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style & ~WS_MAXIMIZEBOX)
            except Exception:
                pass

    def _build(self):
        self.configure(bg=C_BG)

        # ===== 头部 =====
        hdr = tk.Frame(self, bg=C_HDR)
        hdr.pack(fill="x")
        tk.Label(hdr, text="OPEN-BOX", bg=C_HDR, fg=C_TEXT,
                 font=("Segoe UI", 18, "bold")).pack(side="left", padx=(16, 6), pady=(12, 6))
        tk.Label(hdr, text="爱快安装程序", bg=C_HDR, fg=C_ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(side="left", pady=(16, 6))
        tk.Label(hdr, text="云端版", bg=C_HDR, fg=C_HINT,
                 font=("Consolas", 9)).pack(side="right", padx=16, pady=(18, 6))
        tk.Frame(self, bg=C_ACCENT, height=2).pack(fill="x")

        # ===== 连接信息卡片 =====
        card = tk.Frame(self, bg=C_PANEL, padx=14, pady=12,
                        highlightbackground=C_BORDER, highlightthickness=1)
        card.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(card, text="连 接 信 息", bg=C_PANEL, fg=C_ACCENT2,
                 font=("Segoe UI", 9, "bold")).grid(row=0, column=0, columnspan=3,
                                                   sticky="w", pady=(0, 8))

        self.v_host = tk.StringVar(value="192.168.9.9")
        self.v_user = tk.StringVar(value="sshd")
        self.v_port = tk.StringVar(value="22")
        self.v_pass = tk.StringVar(value="tths4425")
        self.v_panel = tk.StringVar(value="tths4425")

        def row(r, label, var, width=24, show=None, hint=""):
            tk.Label(card, text=label, bg=C_PANEL, fg=C_TEXT, anchor="e", width=10,
                     font=("Segoe UI", 9)).grid(row=r, column=0, sticky="e",
                                                padx=(0, 8), pady=4)
            e = tk.Entry(card, textvariable=var, width=width, show=show,
                         bg=C_INPUT, fg=C_TEXT, insertbackground=C_TEXT,
                         relief="flat", font=("Consolas", 10),
                         highlightthickness=1, highlightbackground=C_BORDER,
                         highlightcolor=C_ACCENT)
            e.grid(row=r, column=1, sticky="w", padx=(0, 10), pady=4, ipady=3)
            if hint:
                tk.Label(card, text=hint, bg=C_PANEL, fg=C_HINT, anchor="w",
                         font=("Segoe UI", 8)).grid(row=r, column=2, sticky="w")

        row(1, "主机地址", self.v_host, hint="爱快的 LAN IP")
        row(2, "用户名", self.v_user, hint="爱快 SSH 用户名（通常 sshd）")
        row(3, "端口", self.v_port, width=8, hint="默认 22")
        row(4, "SSH密码", self.v_pass, show="*")
        row(5, "面板密码", self.v_panel, show="*", hint="可选，≥4位；留空则浏览器首访自设")

        # ===== 操作按钮 =====
        btns = tk.Frame(self, bg=C_BG)
        btns.pack(fill="x", padx=14, pady=(6, 6))

        self.b_ping = tk.Button(btns, text="Ping 测试", width=12, command=self.do_ping,
                                bg="#0f3460", fg=C_ACCENT2, relief="flat", bd=0,
                                cursor="hand2", activebackground="#1a4a8a",
                                activeforeground="white", disabledforeground="#4a5a7a",
                                font=("Segoe UI", 9, "bold"))
        self.b_ssh = tk.Button(btns, text="SSH 连接测试", width=14, command=self.do_ssh_test,
                               bg="#0f3460", fg=C_ACCENT2, relief="flat", bd=0,
                               cursor="hand2", activebackground="#1a4a8a",
                               activeforeground="white", disabledforeground="#4a5a7a",
                               font=("Segoe UI", 9, "bold"))
        self.b_go = tk.Button(btns, text="开始安装", width=14, command=self.do_install,
                              bg=C_ACCENT, fg="white", relief="flat", bd=0,
                              cursor="hand2", activebackground="#ff6b81",
                              activeforeground="white", disabledforeground="#7a5560",
                              font=("Segoe UI", 9, "bold"))
        self.b_fix = tk.Button(btns, text="修复内核", width=14, command=self.do_fix_core,
                               bg="#f39c12", fg="white", relief="flat", bd=0,
                               cursor="hand2", activebackground="#f7b955",
                               activeforeground="white", disabledforeground="#7a6a4a",
                               font=("Segoe UI", 9, "bold"))
        self.b_clear = tk.Button(btns, text="清空日志", width=10,
                                 command=lambda: self.txt.delete("1.0", "end"),
                                 bg=C_BORDER, fg=C_HINT, relief="flat", bd=0,
                                 cursor="hand2", activebackground="#3a3a5a",
                                 activeforeground=C_TEXT,
                                 font=("Segoe UI", 9))
        for b in (self.b_ping, self.b_ssh, self.b_go, self.b_fix, self.b_clear):
            b.pack(side="left", padx=(0, 8))

        # ===== 日志区 =====
        logfrm = tk.Frame(self, bg=C_BORDER, padx=1, pady=1)
        logfrm.pack(fill="both", expand=True, padx=14, pady=(4, 12))
        self.txt = scrolledtext.ScrolledText(logfrm, font=("Consolas", 9),
                                             bg=C_LOG, fg=C_LOGFG,
                                             insertbackground=C_LOGFG,
                                             selectbackground=C_ACCENT,
                                             relief="flat", bd=0)
        self.txt.pack(fill="both", expand=True)

    # ---- 日志线程安全 ----
    def log(self, msg):
        self.q.put(str(msg))

    def _drain(self):
        try:
            while True:
                m = self.q.get_nowait()
                self.txt.insert("end", m + "\n")
                self.txt.see("end")
        except queue.Empty:
            pass
        self.after(100, self._drain)

    def _set_busy(self, b):
        self.busy = b
        for w in (self.b_ping, self.b_ssh, self.b_go, self.b_fix):
            w.config(state="disabled" if b else "normal")

    def _run_bg(self, fn):
        if self.busy:
            messagebox.showinfo("提示", "正在执行中，请等待完成")
            return
        self._set_busy(True)
        def wrap():
            try:
                fn()
            except Exception as e:
                self.log(f"\n[失败] {e}")
            finally:
                self.q.put("__DONE__")
        threading.Thread(target=wrap, daemon=True).start()

    def _drain_done_hook(self):
        pass

    # ---- 输入 ----
    def _inputs(self):
        host = self.v_host.get().strip()
        user = self.v_user.get().strip() or "sshd"
        port = self.v_port.get().strip() or "22"
        pw = self.v_pass.get()
        panel = self.v_panel.get()
        if not host:
            raise ValueError("请填写主机地址")
        try:
            port = int(port)
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            raise ValueError("端口必须是 1-65535 的数字")
        if panel and len(panel) < 4:
            raise ValueError("面板密码至少 4 位（或留空）")
        return host, port, user, pw, panel

    # ---- 按钮动作 ----
    def do_ping(self):
        def fn():
            host = self.v_host.get().strip()
            self.log(f"ping {host} ...")
            r = subprocess.run(["ping", "-n", "2", "-w", "1000", host],
                               capture_output=True, text=True, timeout=10)
            out = r.stdout or ""
            ok = "TTL=" in out.upper()
            for line in out.splitlines():
                if "TTL" in line.upper() or "统计" in line or "统计信息" in line or "Packets" in line \
                   or "丢失" in line or "Lost" in line:
                    self.log("  " + line.strip())
            self.log("  结果：" + ("可达 ✓" if ok else "不可达 ✗（检查地址/网线/防火墙）"))
        self._run_bg(fn)

    def do_ssh_test(self):
        def fn():
            host, port, user, pw, _panel = self._inputs()
            inst = Installer(self.log)
            inst.connect(host, port, user, pw)
            _, out = inst.run("id; uname -m; df -h /etc/log | tail -1")
            for line in out.splitlines():
                self.log("  " + line)
            inst.ssh.close()
            self.log("SSH 连接正常 ✓")
        self._run_bg(fn)

    def do_install(self):
        def fn():
            host, port, user, pw, panel = self._inputs()
            if not pw:
                raise ValueError("请填写 SSH 密码")
            base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
                else os.path.dirname(os.path.abspath(__file__))
            dest_dir = os.path.join(base_dir, "downloads")
            self.log(f"开始安装 Open-Box 云端最新版到 {host} ...")
            inst = Installer(self.log)
            try:
                inst.install(host, port, user, pw, panel, dest_dir)
            finally:
                if inst.ssh:
                    try:
                        inst.ssh.close()
                    except Exception:
                        pass
        self._run_bg(fn)

    def do_fix_core(self):
        def fn():
            host, port, user, pw, panel = self._inputs()
            if not pw:
                raise ValueError("请填写 SSH 密码")
            self.log(f"开始修复 Open-Box 内核（{host}）...")
            self.log("修复内容：关闭 autoRedirect（纯 TUN 模式）→ 重启内核 → 验证")
            inst = Installer(self.log)
            try:
                inst.fix_core(host, port, user, pw)
            finally:
                if inst.ssh:
                    try:
                        inst.ssh.close()
                    except Exception:
                        pass
        self._run_bg(fn)

    # 完成标记处理
    def _drain_done(self):
        self._set_busy(False)


# 覆写 _drain 处理完成标记
_orig_drain = App._drain
def _drain2(self):
    try:
        while True:
            m = self.q.get_nowait()
            if m == "__DONE__":
                self._set_busy(False)
                continue
            self.txt.insert("end", m + "\n")
            self.txt.see("end")
    except queue.Empty:
        pass
    self.after(100, self._drain)
App._drain = _drain2


if __name__ == "__main__":
    App().mainloop()
