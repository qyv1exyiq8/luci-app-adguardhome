// force-tun.js —— 由 watchdog 每分钟调用（iKuai 专用）
// iKuai 内核无 nf_tables，sing-box 的 autoRedirect 必须为 false，
// 否则内核 FATAL 崩溃且面板自动降级机制二次重启会超时（iKuai 实测）。
// 面板保存某些设置时可能把 profile.tun.autoRedirect 重置回 true，本脚本负责压回 false。
const { DatabaseSync } = require('node:sqlite');
try {
  const db = new DatabaseSync('/opt/open-box/data/openbox.sqlite');
  const row = db.prepare("SELECT value FROM app_storage WHERE key = 'openbox/profile'").get();
  if (!row) { db.close(); process.exit(0); }
  const p = JSON.parse(row.value);
  if (p.tun && p.tun.autoRedirect === true) {
    p.tun.autoRedirect = false;
    db.prepare("UPDATE app_storage SET value = ? WHERE key = 'openbox/profile'").run(JSON.stringify(p));
    console.log(new Date().toISOString(), 'autoRedirect true -> false');
  }
  db.close();
} catch (e) {
  console.error('force-tun:', e.message);
  process.exit(0);
}
