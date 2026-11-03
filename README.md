# 色花堂 (sehuatang.net) 自动后台签到工具

专为 macOS 设计的色花堂（98堂）自动后台签到工具。直接读取本机 Chrome 浏览器的登录 Cookie 与 Cloudflare `cf_clearance`，结合计算机视觉算法全自动通过 GoCaptcha 行为验证码完成每日签到。

---

## ✨ 核心特性

1. **直接复用 Chrome Cookie**：
   - 自动解密 macOS Chrome 的 Cookie 数据库（支持 Default 及多 Profile 配置文件）。
   - 自动携带 Discuz 认证 Cookie (`cPNj_2132_auth` 等) 与 Cloudflare 防火墙过盾 Cookie (`cf_clearance`)。
   - 匹配真实 Chrome User-Agent，无需手动抓包或复制 Cookie。
2. **AI 视觉自动破解 GoCaptcha 验证码**：
   - **Slide（水平滑块）**：使用 OpenCV Canny 边缘检测 + 模板匹配，像素级精确定位缺口。
   - **Drag（区域拼图）**：透明通道掩码提取拼图块，自动定位底图目标位置。
   - **Rotate（旋转角度）**：计算圆心切片旋转归一化互相关系数（TM_CCORR_NORMED），精确定位旋转还原角度。
   - **Click（点选汉字）**：遇到点选汉字自动智能模拟“刷新”切换为滑块/旋转，免去复杂 OCR。
3. **原生 macOS 后台定时服务**：
   - 提供基于 macOS 原生 `launchd` 的定时后台服务，支持休眠唤醒补跑，每日准时静默运行，无需常驻占用内存。
   - 也支持 `--daemon` 守护进程模式。
4. **macOS 原生桌面通知**：
   - 签到成功或出现异常时，通过 macOS 系统通知栏弹出通知，结果一目了然。
5. **完整运行日志**：
   - 控制台与 `sehuatang_sign.log` 实时记录详细操作与验证过程。

---

## 🚀 快速使用

### 1. 确认前置条件
确保已在 Chrome 浏览器中正常登录过 `sehuatang.net`。

### 2. 检查状态（不触发签到）
```bash
./run.sh --check
```
控制台将输出当前识别到的 Chrome 用户名及今日签到状态，例如：
```text
[INFO] 成功从 Chrome 读取到 20 个 Cookie 项
[INFO] 登录状态正常，当前用户: 【your_username】
✅ 用户: your_username | 状态: 今日已签到
```

### 3. 手动立即执行签到
```bash
./run.sh
```
如果今日尚未签到，将自动抓取验证码、识别求解、完成签到并弹出系统通知；如果今日已签到，将提示已完成。

---

## 💻 跨电脑全自动无感同步（电脑 A 自动导出，电脑 B 自动导入并签到）

如果你外出携带笔记本电脑（电脑 A），希望放在家里的常开电脑（电脑 B，如 Mac mini、软路由、Linux 服务器或 NAS）负责每日定时签到：

### 方式 1：如果电脑 B 也是 Mac（通过 iCloud Drive 全自动零配置同步 🌟 最推荐）
如果家里电脑 B 也是 Mac 且登录同一个 Apple ID：
1. **电脑 A（笔记本）开启后台自动导出**：
   ```bash
   ./install_exporter.sh
   ```
   电脑 A 会在后台自动将 Chrome 最新 Cookie 解密并同步至 iCloud Drive（`~/Library/Mobile Documents/com~apple~CloudDocs/.sehuatang/cookies.json`）。你在外地只要打开过论坛，iCloud 会在数秒内自动同步给家里的电脑 B！
2. **电脑 B（家里 Mac）直接开启自动签到**：
   ```bash
   ./install_service.sh 0 1
   ```
   电脑 B 运行时会自动优先检测并读取 iCloud Drive 中的最新凭据，**完全全自动无感，无需人工传输任何文件**！

---

### 方式 2：如果电脑 B 是 Linux / NAS / 树莓派（通过 SSH / Tailscale 自动推送）
1. 在电脑 A 的 `config.json` 中开启 `remote_sync` 配置：
   ```json
   {
     "bark_key": "...",
     "remote_sync": {
       "enabled": true,
       "host": "192.168.1.100",    // 电脑 B 的局域网 IP 或 Tailscale 虚拟 IP (如 100.x.x.x)
       "user": "root",            // 电脑 B 的用户名
       "remote_path": "~/.sehuatang/cookies.json",
       "port": 22
     }
   }
   ```
2. 配置好免密 SSH 登录后，电脑 A 执行导出（或后台定时器触发时）会自动通过 `scp` 毫秒级推送到电脑 B 的目标目录。
3. 电脑 B 配置签到后台定时服务：
   ```bash
   ./install_service.sh 0 1
   ```

---

## 📱 配置 Bark 手机推送消息提醒

除了 macOS 本地桌面通知外，本工具支持配置 **Bark** 将签到结果实时推送到 iPhone 手机端：

### 快速配置 Bark
只需运行提供的辅助脚本：
```bash
# 传入你的 Bark 设备 Key 或完整链接
./set_bark.sh YOUR_BARK_KEY
# 或者完整自定义地址：
./set_bark.sh https://api.day.app/YOUR_BARK_KEY
```
配置完成后，脚本会自动发送一条测试推送验证手机能否正常接收，并自动同步到后台定时服务的配置文件中。

---

## ⏰ 配置后台自动每日签到

### 方式一：推荐 - macOS 原生 launchd 定时服务（节能可靠）

运行提供的安装脚本：
```bash
# 默认每天凌晨 00:01 自动在后台静默签到
./install_service.sh
```

也可以指定自定义时间（例如每天 09:15）：
```bash
./install_service.sh 9 15
```

- **休眠唤醒补跑**：若到点时电脑处于睡眠状态，Mac 唤醒后系统会自动补跑。
- **开机自启**：安装后会自动配置为开机加载。
- **卸载后台服务**：
  ```bash
  ./uninstall_service.sh
  ```

---

### 方式二：常驻后台守护进程（Daemon 模式）

若希望以常驻进程方式在终端或后台运行：
```bash
# 每日 08:30 执行签到并常驻后台
nohup ./run.sh --daemon --hour 8 --minute 30 > /dev/null 2>&1 &
```

---

## 📁 项目文件清单

| 文件名 | 说明 |
| :--- | :--- |
| `sehuatang_sign.py` | 核心签到脚本（Cookie 提取、验证码识别求解、签到执行、通知） |
| `run.sh` | 一键执行入口（自动激活虚拟环境 Python） |
| `install_service.sh` | 一键安装 macOS launchd 后台定时任务 |
| `set_bark.sh` | 一键设置并测试 Bark 消息推送配置 |
| `config.json` | 配置文件（存储 Bark Key 等配置项） |
| `uninstall_service.sh` | 一键卸载 macOS launchd 后台定时任务 |
| `sehuatang_sign.log` | 签到运行日志文件 |
| `.venv/` | 包含 OpenCV、PyCookieCheat、Requests 等依赖的独立虚拟环境 |

---

## 🛠️ 参数说明

```bash
./run.sh [参数]

参数列表:
  --check          仅检查当前登录状态和今日签到状态，不执行签到
  --no-notify      执行完成后不弹出 macOS 桌面系统通知
  --profile NAME   指定 Chrome Profile 目录名称（默认为 Default）
  --daemon         常驻后台守护进程模式
  --hour H         守护进程每日签到小时（默认 8）
  --minute M       守护进程每日签到分钟（默认 30）
```

---

## 📝 查看日志
```bash
tail -f sehuatang_sign.log
```
