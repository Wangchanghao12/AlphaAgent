"""
快速启动实盘交易API服务器
"""
import os
import sys

def main():
    print("🚀 正在启动实盘交易API服务器...")
    
    # 切换到项目根目录
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)
    
    # 执行启动脚本
    exit_code = os.system("python trade_apis/start_server.py")
    
    if exit_code != 0:
        print("❌ 启动失败，请检查依赖是否安装完整")
        print("安装依赖: pip install fastapi uvicorn pandas numpy")

if __name__ == "__main__":
    main()