require("luci.sys")
require("luci.http")
require("luci.dispatcher")

local m = Map("autoupdate", translate("AutoUpdate"),
    translate("AutoUpdate LUCI supports one-click firmware upgrade and scheduled upgrade"))

local s = m:section(TypedSection, "login", "")
s.addremove = false
s.anonymous = true

local function safe_exec(command)
    local handle = io.popen(command .. " 2>&1")
    if handle then
        local result = handle:read("*a")
        handle:close()
        return result:gsub("%s+$", "")
    end
    return ""
end

local function get_sys_info()
    local info = {}
    
    os.execute("chmod +x /usr/bin/AutoUpdate 2>/dev/null")
    os.execute("echo auto > /tmp/autotimes 2>/dev/null")
    
    info.check_error = (os.execute("AutoUpdate > /tmp/autoupdate.log 2>&1") ~= 0)
    
    info.github_url = safe_exec([[awk -F'=' '/GITHUB_LINK=/ {gsub(/"/, "", $2); print $2}' /etc/openwrt_update]])
    info.local_version = safe_exec([[awk -F'=' '/FIRMWARE_VERSION=/ {gsub(/"/, "", $2); print $2}' /etc/openwrt_update]])
    info.cloud_version = safe_exec("cat /tmp/cloud_version 2>/dev/null")
    
    if nixio.fs.access("/tmp/tags_version") then
        info.equipment_name = safe_exec([[awk -F'=' '/EQUIPMENT_NAME=/ {gsub(/"/, "", $2); print $2}' /tmp/tags_version]])
        info.model_type = safe_exec([[awk -F'=' '/MODEL_TYPE=/ {gsub(/"/, "", $2); print $2}' /tmp/tags_version]])
        info.kernel_type = safe_exec([[awk -F'=' '/KERNEL_TYPE=/ {gsub(/"/, "", $2); print $2}' /tmp/tags_version]])
    else
        info.equipment_name = ""
        info.model_type = ""
        info.kernel_type = ""
    end
    
    return info
end

local o = s:option(Flag, "enable", translate("Enable AutoUpdate"),
    translate("Automatically update firmware during the specified time"))
o.default = o.disabled
o.rmempty = false

local week = s:option(ListValue, "week", translate("Week Day"))
week:value(7, translate("Everyday"))
for i = 0, 6 do
    local day_name = os.date("%A", os.time({year = 2000, month = 1, day = 2 + i}))
    week:value(i, translate(day_name))
end
week.default = 0

local hour = s:option(Value, "hour", translate("Fixed Hour"))
hour.datatype = "range(0,23)"
hour.rmempty = false

local minute = s:option(Value, "minute", translate("Fixed Minute"))
minute.datatype = "range(0,59)"
minute.rmempty = false

local sys_info = get_sys_info()

local github = s:option(Value, "github", translate("GitHub URL"))
github.default = sys_info.github_url
github.rmempty = false

local use_github_api = s:option(Flag, "use_github_api", translate("Use GitHub API"),
    translate("Use GitHub API directly instead of zzz_api file. Recommended for custom repositories."))
use_github_api.default = use_github_api.disabled

local github_proxy = s:option(Value, "github_proxy", translate("GitHub Proxy"))
github_proxy.default = ""
github_proxy.rmempty = true

local release_download = s:option(Value, "release_download", translate("Release Download Path"))
release_download.default = "releases/download"
release_download.rmempty = false

local source = s:option(Value, "source", translate("Source"))
source.default = "openwrt"
source.rmempty = false

local luci_edition = s:option(Value, "luci_edition", translate("LuCI Edition"))
luci_edition.default = "luci"
luci_edition.rmempty = false

local firmware_version = s:option(Value, "firmware_version", translate("Firmware Version"))
firmware_version.default = sys_info.local_version
firmware_version.rmempty = false

local target_board = s:option(Value, "target_board", translate("Target Board"))
target_board.default = "x86"
target_board.rmempty = false

local device_model = s:option(Value, "device_model", translate("Device Model"))
device_model.default = "generic"
device_model.rmempty = false

local firmware_suffix = s:option(Value, "firmware_suffix", translate("Firmware Suffix"))
firmware_suffix.default = ".img.gz"
firmware_suffix.rmempty = false

local use_no_config_update = s:option(Flag, "use_no_config_update", 
    translate("Do not keep configuration on update"))
use_no_config_update.default = use_no_config_update.disabled

local button_upgrade_firmware = s:option(Button, "_upgrade", translate("Upgrade to Latest Version"),
    translate("Click the button below to upgrade to the latest version. Please wait patiently until the router reboots.")..
    "<br><br><br>".. translate("Local firmware version:").. " <strong>".. sys_info.local_version.. "</strong>"..
    "<br>".. translate("Cloud firmware version:").. " <strong>".. sys_info.cloud_version.. "</strong>"..
    "<br><br>".. translate("Equipment name:").. " ".. sys_info.equipment_name..
    "<br>".. translate("Kernel version:").. " ".. sys_info.kernel_type..
    "<br>".. translate("Firmware type:").. " ".. sys_info.model_type)
if sys_info.check_error then
    button_upgrade_firmware.description = button_upgrade_firmware.description ..
        "<br><br><span style='color:red;font-weight:bold;'>" .. 
        translate("Error: Could not fetch cloud version information") .. "</span>"
end
button_upgrade_firmware.inputtitle = translate("Start Upgrade")
button_upgrade_firmware.template = "autoupdate/autoupdate"

function button_upgrade_firmware.write(self, section)
    local config_value = safe_exec("uci -q get autoupdate.@login[0].use_no_config_update || echo 0")
    local use_no_config = (config_value == "1")
    
    local upgrade_command = use_no_config and "AutoUpdate -k" or "AutoUpdate -u"
    os.execute(upgrade_command .. " >> /tmp/autoupdate.log 2>&1 &")
    
    luci.http.redirect(luci.dispatcher.build_url("admin/system/autoupdate") .. "?upgrade_started=1")
end

-- 自动刷新日志区域（默认开启，1秒刷新 /tmp/autoupdate.log）
local log_view = s:option(DummyValue, "_autoupdate_log", translate("更新日志"))
log_view.template = "autoupdate/log_view"

os.execute("rm -f /tmp/autotimes 2>/dev/null")

local uci = luci.model.uci.cursor()
uci:set("autoupdate", "config", "enable", "1")
if uci:changes() then
    uci:commit("autoupdate")
    os.execute("/etc/init.d/autoupdate restart >/dev/null 2>&1")
end

return m
