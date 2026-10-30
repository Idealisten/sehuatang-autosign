#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
色花堂 (sehuatang.net) 自动后台签到工具
- 自动从本地 Chrome 提取登录 Cookies (包括 Discuz 认证与 Cloudflare cf_clearance)
- 自动识别验证码类型 (GoCaptcha: slide / drag / rotate) 并通过图像算法精准识别求解
- 遇到点选汉字验证码 (click) 自动刷新切换为滑块/拖拽/旋转验证码
- 自动完成每日签到并获取奖励统计
- 支持 macOS 原生系统通知
- 支持 launchd 后台定时任务和 daemon 守护进程模式
"""

import os
import sys
import time
import json
import base64
import shutil
import sqlite3
import logging
import argparse
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup
import cv2
import numpy as np
import pycookiecheat

# 基础配置
DEFAULT_DOMAIN = "https://www.sehuatang.net"
FORUM_URL = f"{DEFAULT_DOMAIN}/forum.php"
SIGN_PAGE_URL = f"{DEFAULT_DOMAIN}/plugin.php?id=dd_sign:index"
CAPTCHA_URL = f"{DEFAULT_DOMAIN}/misc.php?mod=captcha"
CAPTCHA_CHECK_URL = f"{DEFAULT_DOMAIN}/misc.php?mod=captcha&action=check"
DO_SIGN_URL = f"{DEFAULT_DOMAIN}/plugin.php?id=dd_sign&ac=sign_v2"

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
)

LOG_FILE = Path(__file__).resolve().parent / "sehuatang_sign.log"

# 配置日志记录器
logger = logging.getLogger("SehuatangSign")
logger.setLevel(logging.INFO)

formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

# 控制台输出
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# 文件输出
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


CONFIG_FILE = Path(__file__).resolve().parent / "config.json"
USER_CONFIG_FILE = Path.home() / ".sehuatang/config.json"


def load_config() -> dict:
    """加载配置信息 (从当前目录或 ~/.sehuatang/config.json)"""
    config = {}
    for p in [CONFIG_FILE, USER_CONFIG_FILE]:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    config.update(json.load(f))
            except Exception as e:
                logger.warning(f"读取配置文件 {p} 出错: {e}")

    # 支持环境变量覆盖
    if "BARK_KEY" in os.environ:
        config["bark_key"] = os.environ["BARK_KEY"]
    if "BARK_SERVER" in os.environ:
        config["bark_server"] = os.environ["BARK_SERVER"]
    return config


def send_macos_notification(title: str, message: str, subtitle: str = ""):
    """发送 macOS 原生通知"""
    try:
        sub_part = f'subtitle "{subtitle}"' if subtitle else ""
        cmd = f'display notification "{message}" with title "{title}" {sub_part}'
        subprocess.run(["osascript", "-e", cmd], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        logger.debug(f"发送系统通知失败: {e}")


def send_bark_notification(title: str, message: str, subtitle: str = "", bark_key: str = None, bark_server: str = None) -> bool:
    """发送 Bark iOS 客户端通知推送"""
    config = load_config()
    key = bark_key or config.get("bark_key", "")
    server = bark_server or config.get("bark_server", "https://api.day.app")

    if not key:
        return False

    key = str(key).strip()
    server = str(server).strip().rstrip("/")

    # 判断 key 是否本身就是完整 URL
    if key.startswith("http://") or key.startswith("https://"):
        target_url = key
    else:
        target_url = f"{server}/{key}"

    payload = {
        "title": title,
        "body": message,
        "group": "色花堂",
        "icon": "https://www.sehuatang.net/favicon.ico",
    }
    if subtitle:
        payload["subtitle"] = subtitle

    try:
        resp = requests.post(target_url, json=payload, timeout=8)
        if resp.status_code == 200:
            res_json = resp.json()
            if res_json.get("code") == 200:
                logger.info(f"📱 Bark 消息推送成功: 【{title}】{message}")
                return True
        logger.warning(f"Bark 推送响应非 200: HTTP {resp.status_code} - {resp.text}")
        return False
    except Exception as e:
        logger.error(f"Bark 推送失败: {e}")
        return False


def notify_user(title: str, message: str, subtitle: str = "", notify_macos: bool = True):
    """统一通知分发：系统通知 + Bark 远程推送"""
    if notify_macos:
        send_macos_notification(title, message, subtitle)
    send_bark_notification(title, message, subtitle)


def get_chrome_user_agent() -> str:
    """尝试获取本机安装的 Chrome 真实主版本号构造 UA"""
    try:
        chrome_bin = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if os.path.exists(chrome_bin):
            out = subprocess.check_output([chrome_bin, "--version"]).decode("utf-8").strip()
            # 输出例如: Google Chrome 156.0.8078.73
            parts = out.split()
            if len(parts) >= 3:
                version = parts[2]
                major = version.split(".")[0]
                return (
                    f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
                )
    except Exception:
        pass
    return DEFAULT_UA


def get_chrome_cookies(profile_name: str = "Default") -> dict:
    """
    从 Chrome 浏览器提取 sehuatang.net 的 cookies
    支持指定 Profile，若 Default 不存在则尝试自动探测有 cookie 的 profile
    """
    chrome_base = Path.home() / "Library/Application Support/Google/Chrome"
    cookie_paths = []

    if profile_name:
        cookie_paths.append(chrome_base / profile_name / "Cookies")
        cookie_paths.append(chrome_base / profile_name / "Network/Cookies")

    cookie_paths.append(chrome_base / "Default/Cookies")
    cookie_paths.append(chrome_base / "Default/Network/Cookies")

    # 遍历其他 profile 目录
    for p in chrome_base.glob("Profile *"):
        if p.is_dir():
            cookie_paths.append(p / "Cookies")
            cookie_paths.append(p / "Network/Cookies")

    cookies = {}
    found_path = None

    for c_path in cookie_paths:
        if not c_path.exists():
            continue
        try:
            # 首先尝试直接利用 pycookiecheat 读取
            res = pycookiecheat.chrome_cookies(DEFAULT_DOMAIN, cookie_file=c_path)
            if res and any("auth" in k or "saltkey" in k for k in res.keys()):
                cookies = res
                found_path = c_path
                break
        except Exception:
            # 如果直接读取被锁定，复制到临时文件再读
            try:
                with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                    tmp_path = tmp.name
                shutil.copy2(c_path, tmp_path)
                res = pycookiecheat.chrome_cookies(DEFAULT_DOMAIN, cookie_file=tmp_path)
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                if res and any("auth" in k or "saltkey" in k for k in res.keys()):
                    cookies = res
                    found_path = c_path
                    break
            except Exception:
                pass

    if not cookies:
        logger.error("未在 Chrome 中找到 sehuatang.net 的有效登录 Cookie！")
        logger.error("请确认已在 Chrome 浏览器中成功登录 sehuatang.net。")
        return {}

    logger.info(f"成功从 Chrome 读取到 {len(cookies)} 个 Cookie 项 (路径: {found_path})")
    return cookies


class SehuatangSigner:
    def __init__(self, cookies: dict, user_agent: str = None):
        self.session = requests.Session()
        self.user_agent = user_agent or get_chrome_user_agent()
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": SIGN_PAGE_URL,
        }
        self.session.headers.update(self.headers)
        self.session.cookies.update(cookies)
        self.username = None
        self.formhash = None

    def check_login(self) -> bool:
        """检查登录状态并解析用户名"""
        try:
            resp = self.session.get(FORUM_URL, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"访问论坛主页状态码异常: {resp.status_code}")
                return False

            soup = BeautifulSoup(resp.text, "html.parser")
            user_el = soup.select_one(".vwmy a") or soup.select_one("strong.vwmy")
            if user_el:
                self.username = user_el.get_text(strip=True)
                logger.info(f"登录状态正常，当前用户: 【{self.username}】")
            else:
                logger.warning("未在页面中找到用户信息，Cookie 可能已过期！")
                return False

            formhash_input = soup.find("input", {"name": "formhash"})
            if formhash_input:
                self.formhash = formhash_input.get("value")
            return True
        except Exception as e:
            logger.error(f"检查登录异常: {e}")
            return False

    def check_signed_in_status(self) -> tuple[bool, str]:
        """
        检查今日签到状态
        返回: (是否已签到, 状态描述文本)
        """
        try:
            resp = self.session.get(SIGN_PAGE_URL, timeout=15)
            if resp.status_code != 200:
                return False, f"访问签到页面失败 (HTTP {resp.status_code})"

            soup = BeautifulSoup(resp.text, "html.parser")
            btn = soup.find(id="signin-btn")
            btn_container = soup.select_one(".ddpc_sign_btna")

            # 如果存在 signin-btn，说明尚未签到
            if btn:
                btn_text = btn.get_text(strip=True)
                if "未签到" in btn_text or "点击签到" in btn_text:
                    return False, "今日未签到"

            # 如果容器中有 "已签到"
            if btn_container and "已签到" in btn_container.get_text():
                return True, "今日已签到"

            # 再次检查页面文本
            if "今日已签到" in resp.text:
                return True, "今日已签到"

            return False, "签到状态未知，尝试签到"
        except Exception as e:
            logger.error(f"检查签到状态出错: {e}")
            return False, f"检查出错: {e}"

    def _solve_slide(self, master_b64: str, thumb_b64: str, display_y: int) -> str:
        """求解 slide (水平滑块) 验证码"""
        m_bytes = base64.b64decode(master_b64.split(",", 1)[1])
        t_bytes = base64.b64decode(thumb_b64.split(",", 1)[1])
        master = cv2.imdecode(np.frombuffer(m_bytes, np.uint8), cv2.IMREAD_COLOR)
        thumb = cv2.imdecode(np.frombuffer(t_bytes, np.uint8), cv2.IMREAD_UNCHANGED)

        alpha = thumb[:, :, 3] if thumb.shape[2] == 4 else None
        thumb_bgr = thumb[:, :, :3] if thumb.shape[2] == 4 else thumb

        m_edges = cv2.Canny(cv2.cvtColor(master, cv2.COLOR_BGR2GRAY), 100, 200)
        t_edges = cv2.Canny(cv2.cvtColor(thumb_bgr, cv2.COLOR_BGR2GRAY), 100, 200)
        if alpha is not None:
            t_edges[alpha == 0] = 0

        res = cv2.matchTemplate(m_edges, t_edges, cv2.TM_CCOEFF_NORMED)
        _, _, _, max_loc = cv2.minMaxLoc(res)
        logger.info(f"[验证码识别] Slide 滑块匹配坐标: x={max_loc[0]}, y={display_y}")
        return f"{max_loc[0]},{display_y}"

    def _solve_drag(self, master_b64: str, thumb_b64: str) -> str:
        """求解 drag (区域拖拽) 验证码"""
        m_bytes = base64.b64decode(master_b64.split(",", 1)[1])
        t_bytes = base64.b64decode(thumb_b64.split(",", 1)[1])
        master = cv2.imdecode(np.frombuffer(m_bytes, np.uint8), cv2.IMREAD_COLOR)
        thumb = cv2.imdecode(np.frombuffer(t_bytes, np.uint8), cv2.IMREAD_UNCHANGED)

        alpha = thumb[:, :, 3] if thumb.shape[2] == 4 else None
        thumb_bgr = thumb[:, :, :3] if thumb.shape[2] == 4 else thumb

        m_edges = cv2.Canny(cv2.cvtColor(master, cv2.COLOR_BGR2GRAY), 100, 200)
        t_edges = cv2.Canny(cv2.cvtColor(thumb_bgr, cv2.COLOR_BGR2GRAY), 100, 200)
        if alpha is not None:
            t_edges[alpha == 0] = 0

        res = cv2.matchTemplate(m_edges, t_edges, cv2.TM_CCOEFF_NORMED)
        _, _, _, max_loc = cv2.minMaxLoc(res)
        logger.info(f"[验证码识别] Drag 拖拽匹配坐标: x={max_loc[0]}, y={max_loc[1]}")
        return f"{max_loc[0]},{max_loc[1]}"

    def _solve_rotate(self, master_b64: str, thumb_b64: str) -> str:
        """求解 rotate (旋转角度) 验证码"""
        m_bytes = base64.b64decode(master_b64.split(",", 1)[1])
        t_bytes = base64.b64decode(thumb_b64.split(",", 1)[1])
        master = cv2.imdecode(np.frombuffer(m_bytes, np.uint8), cv2.IMREAD_COLOR)
        thumb = cv2.imdecode(np.frombuffer(t_bytes, np.uint8), cv2.IMREAD_COLOR)

        H, W = master.shape[:2]
        h, w = thumb.shape[:2]
        cy, cx = H // 2, W // 2
        crop = master[cy - h // 2 : cy + h // 2, cx - w // 2 : cx + w // 2]

        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.circle(mask, (w // 2, h // 2), int(w // 2 * 0.9), 255, -1)

        best_angle = 0
        best_score = -1e9
        for angle in range(0, 360):
            M = cv2.getRotationMatrix2D((w // 2, h // 2), -angle, 1.0)
            rot = cv2.warpAffine(thumb, M, (w, h))
            res = cv2.matchTemplate(crop, rot, cv2.TM_CCORR_NORMED, mask=mask)
            score = res[0][0]
            if score > best_score:
                best_score = score
                best_angle = angle

        logger.info(f"[验证码识别] Rotate 旋转匹配角度: {best_angle}° (匹配度: {best_score:.4f})")
        return str(best_angle)

    def solve_captcha_and_verify(self, max_retries: int = 10) -> bool:
        """
        获取验证码、自动识别并提交校验
        遇到 click (点选汉字) 自动刷新切换为可计算类型
        """
        for attempt in range(1, max_retries + 1):
            time.sleep(2.0)  # 避免触发 429 频率限制
            try:
                resp = self.session.get(CAPTCHA_URL, timeout=10)
                res_data = resp.json()
            except Exception as e:
                logger.warning(f"获取验证码网络失败 (尝试 {attempt}/{max_retries}): {e}")
                continue

            if res_data.get("code") != 200:
                logger.warning(f"获取验证码服务端返回异常 (尝试 {attempt}/{max_retries}): {res_data}")
                time.sleep(3.0)
                continue

            d = res_data.get("data", {})
            c_type = d.get("type")
            logger.info(f"第 {attempt} 次获取验证码，类型: 【{c_type}】")

            if c_type == "click":
                logger.info("点选验证码较复杂，自动刷新切换为滑块/旋转...")
                continue

            value = None
            try:
                if c_type == "slide":
                    value = self._solve_slide(
                        d["master_image_base64"], d["thumb_image_base64"], d.get("display_y", 0)
                    )
                elif c_type == "drag":
                    value = self._solve_drag(d["master_image_base64"], d["thumb_image_base64"])
                elif c_type == "rotate":
                    value = self._solve_rotate(d["master_image_base64"], d["thumb_image_base64"])
                else:
                    logger.warning(f"未知验证码类型: {c_type}，刷新重试")
                    continue
            except Exception as e:
                logger.error(f"验证码图像处理异常: {e}")
                continue

            # 提交验证结果
            try:
                check_headers = {
                    "Content-Type": "text/plain",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": SIGN_PAGE_URL,
                }
                check_resp = self.session.post(
                    CAPTCHA_CHECK_URL,
                    headers=check_headers,
                    data=str(value),
                    timeout=10,
                )
                check_res = check_resp.json()
                if check_res.get("data") == "ok":
                    logger.info("🎉 验证码校验通过 (data: ok)！")
                    return True
                else:
                    logger.warning(f"验证码校验未通过: {check_res}，重新获取...")
            except Exception as e:
                logger.error(f"提交验证码校验异常: {e}")

        logger.error(f"连续 {max_retries} 次尝试均未能通过验证码校验")
        return False

    def do_sign(self) -> tuple[bool, str]:
        """执行签到请求并返回结果"""
        try:
            sign_headers = {
                "X-Requested-With": "XMLHttpRequest",
                "Referer": SIGN_PAGE_URL,
            }
            resp = self.session.get(DO_SIGN_URL, headers=sign_headers, timeout=10)
            data = resp.json()
            if data and data.get("code") == 200:
                msg = data.get("message", "签到成功")
                logger.info(f"✅ 签到成功: {msg}")
                return True, msg
            else:
                msg = data.get("message", "未知错误") if data else "无响应数据"
                logger.warning(f"签到请求返回非200: {msg}")
                return False, msg
        except Exception as e:
            logger.error(f"执行签到请求出错: {e}")
            return False, str(e)


def run_sign_process(notify: bool = True, profile: str = "Default") -> bool:
    """运行一次完整的签到流程"""
    logger.info("=" * 50)
    logger.info("开始执行色花堂自动签到流程")

    cookies = get_chrome_cookies(profile_name=profile)
    if not cookies:
        if notify:
            notify_user("色花堂自动签到", "未在 Chrome 中找到登录 Cookie，请先在 Chrome 登录", "失败")
        return False

    signer = SehuatangSigner(cookies)

    # 1. 检查登录状态
    if not signer.check_login():
        msg = "登录状态失效或无法连接，请在 Chrome 重新登录色花堂"
        logger.error(msg)
        if notify:
            notify_user("色花堂自动签到", msg, "登录失败")
        return False

    # 2. 检查是否已经签到
    already_signed, status_msg = signer.check_signed_in_status()
    if already_signed:
        info_msg = f"用户【{signer.username}】今日已完成签到，无需重复操作"
        logger.info(info_msg)
        if notify:
            notify_user("色花堂自动签到", info_msg, "今日已签到")
        return True

    logger.info(f"用户【{signer.username}】当前状态: {status_msg}，开始破解验证码并签到...")

    # 3. 求解验证码
    if not signer.solve_captcha_and_verify(max_retries=10):
        fail_msg = "验证码自动识别校验失败，稍后可重试"
        logger.error(fail_msg)
        if notify:
            notify_user("色花堂自动签到", fail_msg, "验证码失败")
        return False

    # 4. 执行签到
    success, result_msg = signer.do_sign()
    if success:
        ok_msg = f"用户【{signer.username}】{result_msg}"
        logger.info(f"🎉 {ok_msg}")
        if notify:
            notify_user("色花堂自动签到", ok_msg, "签到成功")
        return True
    else:
        err_msg = f"签到失败: {result_msg}"
        logger.error(err_msg)
        if notify:
            notify_user("色花堂自动签到", err_msg, "失败")
        return False


def run_daemon_loop(hour: int = 0, minute: int = 1, notify: bool = True, profile: str = "Default"):
    """常驻后台守护进程模式，每天固定时间自动签到"""
    logger.info(f"启动守护进程模式，每日 {hour:02d}:{minute:02d} 自动签到")
    # 启动时首先检查一次
    run_sign_process(notify=notify, profile=profile)

    while True:
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        sleep_seconds = (target - now).total_seconds()
        logger.info(f"下次签到时间: {target.strftime('%Y-%m-%d %H:%M:%S')} (等待 {int(sleep_seconds)} 秒)")
        time.sleep(sleep_seconds)
        try:
            run_sign_process(notify=notify, profile=profile)
        except Exception as e:
            logger.error(f"守护进程运行签到出现未捕获异常: {e}")


def main():
    parser = argparse.ArgumentParser(description="色花堂 (sehuatang.net) 自动后台签到工具")
    parser.add_argument("--check", action="store_true", help="仅检查登录与签到状态，不执行签到")
    parser.add_argument("--no-notify", action="store_true", help="禁用 macOS 桌面通知")
    parser.add_argument("--profile", default="Default", help="指定 Chrome Profile 名称 (默认: Default)")
    parser.add_argument("--daemon", action="store_true", help="以守护进程模式常驻后台运行")
    parser.add_argument("--hour", type=int, default=0, help="守护进程模式每日执行小时 (默认: 0)")
    parser.add_argument("--minute", type=int, default=1, help="守护进程模式每日执行分钟 (默认: 1)")
    parser.add_argument("--bark-key", help="设置或指定 Bark Key (或完整 Bark URL)")
    parser.add_argument("--test-bark", nargs="?", const="", help="测试发送一条 Bark 推送通知")

    args = parser.parse_args()

    if args.bark_key:
        cfg = load_config()
        cfg["bark_key"] = args.bark_key
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        if USER_CONFIG_FILE.parent.exists():
            with open(USER_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        print(f"✅ 已保存 Bark Key: {args.bark_key}")

    if args.test_bark is not None:
        key = args.test_bark if args.test_bark else args.bark_key
        ok = send_bark_notification("色花堂签到测试", "这是一条 Bark 测试推送通知，配置正常！", "推送测试", bark_key=key)
        if ok:
            print("🎉 Bark 测试通知推送成功！请在 iPhone 检查接收。")
            sys.exit(0)
        else:
            print("❌ Bark 测试通知推送失败，请检查 Key 或网络连接。")
            sys.exit(1)
    notify = not args.no_notify

    if args.check:
        cookies = get_chrome_cookies(profile_name=args.profile)
        if not cookies:
            print("❌ 未在 Chrome 中找到有效登录 Cookie")
            sys.exit(1)
        signer = SehuatangSigner(cookies)
        if not signer.check_login():
            print("❌ 登录失效，请在 Chrome 重新登录")
            sys.exit(1)
        signed, msg = signer.check_signed_in_status()
        print(f"✅ 用户: {signer.username} | 状态: {msg}")
        sys.exit(0)

    if args.daemon:
        run_daemon_loop(hour=args.hour, minute=args.minute, notify=notify, profile=args.profile)
    else:
        success = run_sign_process(notify=notify, profile=args.profile)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
