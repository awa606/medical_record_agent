"""Start the synthetic classroom replay under the current user's local app-data folder."""
import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import requests


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "冻结资产"


def cli():
    parser = argparse.ArgumentParser(description="MediListen 课程演示 · 已保存首响应回放")
    parser.add_argument("--data-root", type=Path, default=Path(os.environ["LOCALAPPDATA"])/"MediListen课程现场")
    parser.add_argument("--port", type=int, default=26418)
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args()


def read_account(runtime):
    path = runtime/"本机账户.json"
    if not path.exists():
        with path.open("x", encoding="utf-8") as stream:
            json.dump({"admin_username":"course-maintainer", "admin_password":secrets.token_urlsafe(24),
                       "username":"course-doctor", "password":"K"+secrets.token_hex(5)}, stream)
    return json.loads(path.read_text(encoding="utf-8"))


def seed(session, base, account):
    def api(route, payload=None):
        r = (session.get(base+route, timeout=15) if payload is None else
             session.post(base+route, json=payload, timeout=15))
        if not r.ok:
            raise RuntimeError(f"课堂准备失败，{route} 返回 {r.status_code}。")
        return r.json()
    api("/api/auth/login", {"username":account["admin_username"],"password":account["admin_password"]})
    if not any(u["username"]==account["username"] for u in api("/api/auth/users")["users"]):
        api("/api/auth/users", {"username":account["username"],"password":account["password"],
                                 "role":"doctor","display_name":"课程模拟医生"})
    api("/api/auth/logout", {})
    api("/api/auth/login", {"username":account["username"],"password":account["password"]})
    # Only an already-created, tagged classroom case may be reopened.
    listed = api("/api/encounters")
    items = listed if isinstance(listed,list) else listed.get("items", listed.get("encounters", []))
    case = next((item for item in items if item.get("patient_deidentified_id")=="SIM-COURSE-FEVER-01"), None)
    if case is None:
        case = api("/api/encounters", {"patient_deidentified_id":"SIM-COURSE-FEVER-01","patient_display_name":"合成问诊"})
    eid = case["id"]
    case = api(f"/api/encounters/{eid}")
    case = case.get("encounter",case)
    if case.get("check_in_status")=="registered":
        api(f"/api/encounters/{eid}/check-in", {})
        case = {"check_in_status":"checked_in"}
    if case.get("check_in_status")=="checked_in":
        api(f"/api/encounters/{eid}/start", {})
    tid = case.get("task_id")
    if not tid:
        conversation = json.loads((SOURCE/"fixtures/input.json").read_text(encoding="utf8"))["text"]
        tid = api("/api/records/generate", {"encounter_id":eid,"conversation_text":conversation})["task_id"]
    for attempt in range(100):
        if (api(f"/api/tasks/{tid}").get("result_json") or {}).get("fields"):
            return eid
        time.sleep(.2)
    raise RuntimeError("等待固定回放草稿超时。")


def main():
    args = cli()
    if not (1024 <= args.port <= 65535) or args.port in (26324,26326,26327,8798):
        raise ValueError("请选择独立课程端口，默认 26418。")
    session = requests.Session()
    session.trust_env = False
    base = f"http://127.0.0.1:{args.port}"
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1",args.port)) == 0:
            try:
                identity = session.get(base+"/course/identity",timeout=2).json()
            except (ValueError,requests.RequestException):
                identity = {}
            if identity.get("service") != "medilisten-course-replay-20261118":
                raise RuntimeError("选定的端口已被其他程序占用。")
            print("课堂回放已经启动，登录信息在原启动窗口。")
            if not args.no_browser:
                webbrowser.open(base+"/static/doctor.html")
            return
    runtime = args.data_root.resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    account = read_account(runtime)
    env = os.environ.copy()
    env.update(COURSE_RUNTIME=str(runtime), COURSE_PORT=str(args.port), PYTHONDONTWRITEBYTECODE="1")
    # One foreground console controls this child and closes it on normal exit.
    with (runtime/"启动日志.txt").open("a",encoding="utf8") as log:
        child = subprocess.Popen([sys.executable,"-B","-X","utf8",str(HERE/"course_service.py")],
                                 cwd=runtime, env=env, stdout=log, stderr=log)
        try:
            for _ in range(100):
                if child.poll() is not None:
                    raise RuntimeError("服务启动失败，请查看本机数据目录中的启动日志。")
                try:
                    identity = session.get(base+"/course/identity",timeout=.8).json()
                    health = session.get(base+"/health",timeout=2).json()
                    if identity.get("variant") == "classroom-projection-1" and health.get("status") == "ok":
                        break
                except requests.RequestException:
                    pass
                time.sleep(.2)
            else:
                raise RuntimeError("服务未能在规定时间内就绪。")
            eid = seed(session,base,account)
            url = f"{base}/static/doctor.html?encounter_id={eid}#encounter"
            print("MediListen 课程回放已就绪，使用固定合成问诊。", flush=True)
            if args.no_browser:
                print("已启用受控验证模式。", flush=True)
                sys.stdin.readline()
            else:
                print("地址",url,"\n账号",account["username"],"\n本机试用密码",account["password"],flush=True)
                webbrowser.open(url)
                input("\n保留本窗口即可演示。结束时在此窗口按回车停止。\n")
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=12)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
