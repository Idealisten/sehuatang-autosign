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
