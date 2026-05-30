#!/usr/bin/env python
import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict

# ---------- 自动检测工具路径 ----------
def find_vs_installation() -> str:
    """使用 vswhere.exe 查找最新的 VS 安装路径"""
    vswhere = (
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
        / "Microsoft Visual Studio"
        / "Installer"
        / "vswhere.exe"
    )
    if not vswhere.exists():
        return ""

    try:
        result = subprocess.run(
            [
                str(vswhere),
                "-latest",
                "-products", "*",
                "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                "-property", "installationPath",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def find_msys2() -> str:
    """自动检测 MSYS2 安装目录"""
    candidates = [
        Path("D:/msys64"),
        Path("C:/msys64"),
        Path.home() / "msys64",
    ]
    for p in candidates:
        if (p / "msys2_shell.cmd").exists():
            return str(p)

    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\MSYS2") as key:
            return winreg.QueryValueEx(key, "InstallFolder")[0]
    except Exception:
        pass

    return ""


# ---------- 捕获 VS 环境变量 ----------
def capture_vc_env(vcvars_path: str, arch: str = "x64") -> Dict[str, str]:
    """运行 vcvarsall.bat 并捕获其设置的所有环境变量"""
    env = os.environ.copy()
    env["MSYS_NO_PATHCONV"] = "1"
    env["COMPOSE_CONVERT_WINDOWS_PATHS"] = "0"
    result = subprocess.run(
        ['cmd', '/c', vcvars_path,arch, '&&', 'set'],
        capture_output=True,
        input=None,
        shell=False,
        text=True,
        check=False,
        env=env
    )
    if result.returncode != 0:
        raise RuntimeError(f"vcvarsall.bat failed with exit code {result.returncode}\nError: {result.stderr}")

    env = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().upper()
        env[key] = value
    return env


# ---------- 主函数 ----------
def main():
    # 自动探测默认值
    default_vs = os.environ.get("VS_INSTALL_DIR") or find_vs_installation()
    default_msys2 = os.environ.get("MSYS2_ROOT") or find_msys2()

    # 配置命令行参数解析
    parser = argparse.ArgumentParser(
        description="在带有 Visual Studio 编译环境的 MSYS2 Bash 中执行指定命令。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog="使用示例: python run_build.py --arch x64 -- make -j8 PREFIX=/usr"
    )
    
    # 脚本自身的可选参数
    parser.add_argument(
        "-a", "--arch", 
        default=os.environ.get("TARGET_ARCH", "x64"),
        choices=["x86", "amd64", "x64", "arm", "arm64"],
        help="目标架构 (VS vcvarsall 参数)"
    )
    parser.add_argument(
        "--vs-dir", 
        default=default_vs,
        help="Visual Studio 安装目录"
    )
    parser.add_argument(
        "--msys-dir", 
        default=default_msys2,
        help="MSYS2 安装根目录"
    )
    
    # 核心改动：使用 parse_known_args 配合剩余参数收集 `--` 后面的命令
    args, remaining = parser.parse_known_args()

    # 如果剩余参数中包含 '--'，则取其后面的所有内容作为命令；
    # 如果用户没写 '--' 但有剩余参数，也一并当作命令处理；若没有则默认执行 'make'
    if remaining and remaining[0] == '--':
        build_cmd_list = remaining[1:]
    else:
        build_cmd_list = remaining

    # 将参数列表组合成一个完整的 shell 命令字符串
    build_cmd = " ".join(map(lambda x:f'"{x}"',build_cmd_list)) if build_cmd_list else "make"

    # 路径有效性校验
    if not args.vs_dir:
        print("[ERROR] 未检测到 Visual Studio 路径，请使用 --vs-dir 手动指定。", file=sys.stderr)
        sys.exit(1)
        
    if not args.msys_dir:
        print("[ERROR] 未检测到 MSYS2 路径，请使用 --msys-dir 手动指定。", file=sys.stderr)
        sys.exit(1)

    vcvars = Path(args.vs_dir) / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat"
    if not vcvars.exists():
        print(f"[ERROR] 找不到 vcvarsall.bat，请检查 VS 路径: {vcvars}", file=sys.stderr)
        sys.exit(1)

    msys2_shell = Path(args.msys_dir) / "usr" / "bin" / "bash.exe"
    # msys2_shell = Path(args.msys_dir) / "msys2_shell.cmd"
    if not msys2_shell.exists():
        print(f"[ERROR] 找不到 MSYS2 Bash，请检查 MSYS2 路径: {msys2_shell}", file=sys.stderr)
        sys.exit(1)

    # 打印运行配置信息
    print(f"[INFO] Visual Studio : {args.vs_dir}")
    print(f"[INFO] MSYS2         : {args.msys_dir}")
    print(f"[INFO] Target Arch   : {args.arch}")
    print(f"[INFO] Build Command : {build_cmd}")

    # 提取 VS 编译环境
    print("[INFO] Capturing Visual Studio environment variables...")
    try:
        vc_env = capture_vc_env(str(vcvars), args.arch)
        print(f"[INFO] Captured {len(vc_env)} environment variables.")
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    # 组装环境变量
    env = os.environ.copy()
    env.update(vc_env)
    pollution_vars = ["MSYSTEM", "MSYS2_PATH_TYPE", "ORIGINAL_PATH", "EXEPATH", "PLINK_PROTOCOL"]
    for var in pollution_vars:
        if var in env:
            del env[var]
    env["MSYSTEM"] = "MSYS2"
    env["MSYS2_PATH_TYPE"] = "inherit"
    env["MSYS_NO_PATHCONV"] = "1"
    env["MSYS2_NOSTART"] = "yes"
    env["MSYSCON"] = "defterm"

    # 执行命令 (-lc 会将整个字符串作为一个完整的命令行在 bash 中执行)
    msys2_cmd = [str(msys2_shell), "-lc", build_cmd]
    # msys2_cmd = [str(msys2_shell), "-full-path","-no-start","-defterm","-here","-c", build_cmd]
    print(f"[INFO] Launching MSYS2 bash and executing...",msys2_cmd)
    
    result = subprocess.run(msys2_cmd, env=env, check=False)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()