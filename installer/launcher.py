"""
AI自动写小说系统 - 主启动器
图形界面启动器，可以启动所有服务
"""

import sys
import os
import subprocess
import threading
import time
import json
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional

# 尝试导入tkinter
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False

# 尝试导入psutil
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class ServiceManager:
    """服务管理器"""
    
    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}
        # 支持多种部署方式：同目录、bin目录、installer/dist目录
        self.exe_dir = self._find_exe_dir()
        # base_dir: 打包后用exe_dir，开发时用__file__的上级
        if getattr(sys, 'frozen', False):
            self.base_dir = self.exe_dir
        else:
            self.base_dir = Path(__file__).parent.parent
        self.config = self._load_config()
        self.service_status: Dict[str, str] = {
            "ai_service": "stopped",
            "novel_service": "stopped",
            "frontend": "stopped",
        }
    
    def _find_exe_dir(self) -> Path:
        """查找exe文件所在目录"""
        # PyInstaller打包后，exe和启动器在同一目录
        if getattr(sys, 'frozen', False):
            launcher_dir = Path(sys.executable).parent
        else:
            launcher_dir = Path(__file__).parent
        
        print(f"[启动器] 查找exe目录，启动器位置: {launcher_dir}")
        
        # 优先级1：启动器同目录
        if (launcher_dir / "AI_NovelService.exe").exists():
            print(f"[启动器] 找到exe目录: {launcher_dir}")
            return launcher_dir
        
        # 优先级2：installer/dist目录
        dist_dir = launcher_dir / "dist"
        if (dist_dir / "AI_NovelService.exe").exists():
            print(f"[启动器] 找到exe目录: {dist_dir}")
            return dist_dir
        
        # 优先级3：项目根目录/bin
        bin_dir = launcher_dir.parent / "bin"
        if (bin_dir / "AI_NovelService.exe").exists():
            print(f"[启动器] 找到exe目录: {bin_dir}")
            return bin_dir
        
        print(f"[启动器] 未找到exe文件，默认使用: {launcher_dir}")
        return launcher_dir
    
    def _load_config(self) -> dict:
        """加载配置"""
        config_file = self.base_dir / "config.json"
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "ai_service_port": 8001,
            "novel_service_port": 8002,
            "frontend_port": 3000,
            "auto_open_browser": True,
        }
    
    def _save_config(self):
        """保存配置"""
        config_file = self.base_dir / "config.json"
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
    
    def start_ai_service(self) -> bool:
        """启动AI服务"""
        try:
            exe_path = self.exe_dir / "AI_NovelService.exe"
            print(f"[启动器] AI服务路径: {exe_path}")
            if not exe_path.exists():
                print(f"[启动器] AI服务可执行文件不存在: {exe_path}")
                return False
            
            # 设置环境变量
            env = os.environ.copy()
            env['PYTHONPATH'] = str(self.base_dir)
            
            # 启动进程
            process = subprocess.Popen(
                [str(exe_path)],
                cwd=str(self.exe_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            
            self.processes["ai_service"] = process
            self.service_status["ai_service"] = "running"
            
            # 等待服务启动
            time.sleep(2)
            
            if process.poll() is None:
                print("AI服务启动成功")
                return True
            else:
                print("AI服务启动失败")
                return False
                
        except Exception as e:
            print(f"启动AI服务失败: {e}")
            return False
    
    def start_novel_service(self) -> bool:
        """启动小说服务"""
        try:
            exe_path = self.exe_dir / "NovelGenerator.exe"
            print(f"[启动器] 小说服务路径: {exe_path}")
            if not exe_path.exists():
                print(f"[启动器] 小说服务可执行文件不存在: {exe_path}")
                return False
            
            # 设置环境变量
            env = os.environ.copy()
            env['PYTHONPATH'] = str(self.base_dir)
            
            # 启动进程
            process = subprocess.Popen(
                [str(exe_path)],
                cwd=str(self.exe_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            
            self.processes["novel_service"] = process
            self.service_status["novel_service"] = "running"
            
            # 等待服务启动
            time.sleep(2)
            
            if process.poll() is None:
                print("小说服务启动成功")
                return True
            else:
                print("小说服务启动失败")
                return False
                
        except Exception as e:
            print(f"启动小说服务失败: {e}")
            return False
    
    def start_frontend(self) -> bool:
        """启动前端服务"""
        try:
            # 检查是否有编译后的前端
            frontend_dir = self.base_dir / "frontend" / "build"
            if not frontend_dir.exists():
                # 使用简单的HTTP服务器
                frontend_dir = self.base_dir / "frontend" / "public"
            if not frontend_dir.exists():
                # 尝试exe同级的frontend目录
                frontend_dir = self.exe_dir / "frontend"
            
            if not frontend_dir.exists():
                print(f"前端目录不存在，已尝试: {self.base_dir / 'frontend' / 'public'}")
                # 创建一个简单的前端页面
                frontend_dir = self.exe_dir / "frontend"
                frontend_dir.mkdir(exist_ok=True)
                self._create_simple_frontend(frontend_dir)
            
            # 打开浏览器直接访问前端HTML文件
            frontend_file = frontend_dir / "index.html"
            if frontend_file.exists():
                import webbrowser
                webbrowser.open(f"file:///{frontend_file}")
                self.service_status["frontend"] = "running"
                print("前端服务已打开（本地文件模式）")
                return True
            
            # 使用系统命令启动HTTP服务器
            port = self.config["frontend_port"]
            if sys.platform == 'win32':
                # Windows: 使用start命令启动
                process = subprocess.Popen(
                    ["cmd", "/c", "start", "cmd", "/k", f"python -m http.server {port}"],
                    cwd=str(frontend_dir),
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
            else:
                process = subprocess.Popen(
                    ["python3", "-m", "http.server", str(port)],
                    cwd=str(frontend_dir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            
            self.processes["frontend"] = process
            self.service_status["frontend"] = "running"
            
            # 等待服务启动
            time.sleep(1)
            
            if process.poll() is None:
                print("前端服务启动成功")
                return True
            else:
                print("前端服务启动失败")
                return False
                
        except Exception as e:
            print(f"启动前端服务失败: {e}")
            return False
    
    def _create_simple_frontend(self, frontend_dir: Path):
        """创建简单的前端页面"""
        html_content = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>AI自动写小说系统</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; }
        header { text-align: center; color: white; padding: 40px 0; }
        header h1 { font-size: 2.5rem; margin-bottom: 10px; }
        .card { background: white; border-radius: 15px; padding: 30px; margin-bottom: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); }
        .status { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 20px; }
        .status-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; text-align: center; }
        .status-card h3 { font-size: 1.5rem; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: 600; }
        .form-control { width: 100%; padding: 10px; border: 2px solid #ddd; border-radius: 8px; font-size: 14px; }
        .btn { padding: 12px 30px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; }
        .result { background: #f5f5f5; padding: 20px; border-radius: 8px; margin-top: 20px; white-space: pre-wrap; min-height: 100px; }
        .loading { display: none; text-align: center; padding: 20px; }
        .loading.active { display: block; }
    </style>
</head>
<body>
    <div class="container">
        <header><h1>AI自动写小说系统</h1><p>使用人工智能创作小说</p></header>
        <div class="card">
            <h2>服务状态</h2>
            <div class="status">
                <div class="status-card"><h3 id="ai-status">检查中</h3><p>AI服务</p></div>
                <div class="status-card"><h3 id="novel-status">检查中</h3><p>小说服务</p></div>
                <div class="status-card"><h3 id="model-count">0</h3><p>可用模型</p></div>
            </div>
        </div>
        <div class="card">
            <h2>生成小说</h2>
            <div class="form-group"><label>小说标题</label><input type="text" id="title" class="form-control" placeholder="请输入标题"></div>
            <div class="form-group"><label>小说简介</label><textarea id="synopsis" class="form-control" rows="3" placeholder="请输入简介"></textarea></div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:15px">
                <div class="form-group"><label>小说类型</label><select id="type" class="form-control"><option value="scifi">科幻</option><option value="mystery">悬疑</option><option value="romance">言情</option><option value="fantasy">奇幻</option><option value="urban">都市</option></select></div>
                <div class="form-group"><label>章节数量</label><select id="chapters" class="form-control"><option value="3">3章</option><option value="5">5章</option><option value="10">10章</option></select></div>
            </div>
            <button class="btn" onclick="generate()">开始生成</button>
            <div class="loading" id="loading"><p>正在生成中...</p></div>
            <div class="result" id="result">等待生成...</div>
        </div>
    </div>
    <script>
        const API = "http://localhost:8002";
        async function checkHealth() {
            try {
                let r = await fetch(API+"/health");
                let d = await r.json();
                document.getElementById("novel-status").textContent = d.status==="healthy"?"正常":"异常";
            } catch(e) { document.getElementById("novel-status").textContent = "离线"; }
            try {
                let r = await fetch("http://localhost:8001/health");
                let d = await r.json();
                document.getElementById("ai-status").textContent = d.status==="healthy"?"正常":"异常";
                document.getElementById("model-count").textContent = d.models_available?.length||0;
            } catch(e) { document.getElementById("ai-status").textContent = "离线"; }
        }
        async function generate() {
            let title = document.getElementById("title").value;
            let synopsis = document.getElementById("synopsis").value;
            if(!title||!synopsis) { alert("请填写标题和简介"); return; }
            document.getElementById("loading").classList.add("active");
            document.getElementById("result").textContent = "生成中...";
            try {
                let r = await fetch(API+"/api/v1/generate/novel", {
                    method:"POST", headers:{"Content-Type":"application/json"},
                    body: JSON.stringify({title,synopsis,novel_type:document.getElementById("type").value,chapter_count:parseInt(document.getElementById("chapters").value)})
                });
                let d = await r.json();
                if(d.success) {
                    let text = "《"+d.title+"》\\n类型:"+d.novel_type+"\\n章节数:"+d.statistics.total_chapters+"\\n总字数:"+d.statistics.total_words+"\\n\\n";
                    d.chapters.forEach(c => { text += c.title+"\\n"+c.content+"\\n\\n"; });
                    document.getElementById("result").textContent = text;
                } else { document.getElementById("result").textContent = "生成失败: "+(d.error||"未知错误"); }
            } catch(e) { document.getElementById("result").textContent = "请求失败: "+e.message; }
            document.getElementById("loading").classList.remove("active");
        }
        checkHealth(); setInterval(checkHealth, 5000);
    </script>
</body>
</html>'''
        with open(frontend_dir / "index.html", "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"[启动器] 已创建简单前端页面: {frontend_dir / 'index.html'}")
    
    def stop_service(self, service_name: str) -> bool:
        """停止服务"""
        try:
            if service_name in self.processes:
                process = self.processes[service_name]
                
                # 尝试优雅地停止
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
                
                # 如果还在运行，强制停止
                if process.poll() is None:
                    process.kill()
                
                del self.processes[service_name]
                self.service_status[service_name] = "stopped"
                print(f"{service_name} 已停止")
                return True
            
            return False
            
        except Exception as e:
            print(f"停止服务失败: {e}")
            return False
    
    def stop_all_services(self):
        """停止所有服务"""
        for service_name in list(self.processes.keys()):
            self.stop_service(service_name)
    
    def get_service_status(self, service_name: str) -> str:
        """获取服务状态"""
        if service_name in self.processes:
            process = self.processes[service_name]
            if process.poll() is None:
                return "running"
            else:
                # 进程已结束
                self.service_status[service_name] = "stopped"
                return "stopped"
        return "stopped"
    
    def get_all_status(self) -> Dict[str, str]:
        """获取所有服务状态"""
        for service_name in list(self.processes.keys()):
            self.get_service_status(service_name)
        return self.service_status.copy()
    
    def open_browser(self, url: str):
        """打开浏览器"""
        webbrowser.open(url)


class LauncherGUI:
    """启动器图形界面"""
    
    def __init__(self):
        self.service_manager = ServiceManager()
        self.root = tk.Tk()
        self.root.title("AI自动写小说系统 - 启动器")
        self.root.geometry("600x500")
        self.root.resizable(False, False)
        
        # 设置图标
        try:
            icon_path = Path(__file__).parent.parent / "icon.ico"
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
        except Exception:
            pass
        
        # 创建界面
        self._create_widgets()
        
        # 启动状态更新
        self._update_status()
        
        # 延迟自动启动所有服务
        self.root.after(1000, self._auto_start_services)
    
    def _create_widgets(self):
        """创建界面组件"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        title_label = ttk.Label(
            main_frame,
            text="AI自动写小说系统",
            font=("微软雅黑", 18, "bold")
        )
        title_label.pack(pady=(0, 20))
        
        # 服务状态框架
        status_frame = ttk.LabelFrame(main_frame, text="服务状态", padding="10")
        status_frame.pack(fill=tk.X, pady=(0, 20))
        
        # AI服务状态
        ai_frame = ttk.Frame(status_frame)
        ai_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(ai_frame, text="AI模型服务:", width=15).pack(side=tk.LEFT)
        self.ai_status_label = ttk.Label(ai_frame, text="已停止", foreground="red")
        self.ai_status_label.pack(side=tk.LEFT, padx=10)
        
        ttk.Button(
            ai_frame,
            text="启动",
            command=self._start_ai_service,
            width=8
        ).pack(side=tk.RIGHT, padx=5)
        
        ttk.Button(
            ai_frame,
            text="停止",
            command=lambda: self._stop_service("ai_service"),
            width=8
        ).pack(side=tk.RIGHT)
        
        # 小说服务状态
        novel_frame = ttk.Frame(status_frame)
        novel_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(novel_frame, text="小说生成服务:", width=15).pack(side=tk.LEFT)
        self.novel_status_label = ttk.Label(novel_frame, text="已停止", foreground="red")
        self.novel_status_label.pack(side=tk.LEFT, padx=10)
        
        ttk.Button(
            novel_frame,
            text="启动",
            command=self._start_novel_service,
            width=8
        ).pack(side=tk.RIGHT, padx=5)
        
        ttk.Button(
            novel_frame,
            text="停止",
            command=lambda: self._stop_service("novel_service"),
            width=8
        ).pack(side=tk.RIGHT)
        
        # 前端服务状态
        frontend_frame = ttk.Frame(status_frame)
        frontend_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(frontend_frame, text="前端服务:", width=15).pack(side=tk.LEFT)
        self.frontend_status_label = ttk.Label(frontend_frame, text="已停止", foreground="red")
        self.frontend_status_label.pack(side=tk.LEFT, padx=10)
        
        ttk.Button(
            frontend_frame,
            text="启动",
            command=self._start_frontend,
            width=8
        ).pack(side=tk.RIGHT, padx=5)
        
        ttk.Button(
            frontend_frame,
            text="停止",
            command=lambda: self._stop_service("frontend"),
            width=8
        ).pack(side=tk.RIGHT)
        
        # 操作按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 20))
        
        ttk.Button(
            button_frame,
            text="启动所有服务",
            command=self._start_all_services,
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame,
            text="停止所有服务",
            command=self._stop_all_services,
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame,
            text="打开前端",
            command=self._open_frontend,
            width=10
        ).pack(side=tk.RIGHT, padx=5)
        
        ttk.Button(
            button_frame,
            text="打开API文档",
            command=self._open_api_docs,
            width=10
        ).pack(side=tk.RIGHT, padx=5)
        
        # 日志框架
        log_frame = ttk.LabelFrame(main_frame, text="运行日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        # 日志文本框
        self.log_text = tk.Text(
            log_frame,
            height=10,
            width=60,
            font=("Consolas", 9)
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(self.log_text, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)
        
        # 底部状态栏
        status_bar = ttk.Label(
            main_frame,
            text="就绪",
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        status_bar.pack(fill=tk.X, pady=(10, 0))
        
        # 初始日志
        self._log("系统启动器已就绪")
        self._log("请点击'启动所有服务'开始使用")
    
    def _log(self, message: str):
        """添加日志"""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
    
    def _update_status(self):
        """更新状态显示"""
        status = self.service_manager.get_all_status()
        
        # 更新AI服务状态
        if status["ai_service"] == "running":
            self.ai_status_label.config(text="运行中", foreground="green")
        else:
            self.ai_status_label.config(text="已停止", foreground="red")
        
        # 更新小说服务状态
        if status["novel_service"] == "running":
            self.novel_status_label.config(text="运行中", foreground="green")
        else:
            self.novel_status_label.config(text="已停止", foreground="red")
        
        # 更新前端服务状态
        if status["frontend"] == "running":
            self.frontend_status_label.config(text="运行中", foreground="green")
        else:
            self.frontend_status_label.config(text="已停止", foreground="red")
        
        # 每秒更新一次
        self.root.after(1000, self._update_status)
    
    def _start_ai_service(self):
        """启动AI服务"""
        self._log("正在启动AI模型服务...")
        if self.service_manager.start_ai_service():
            self._log("AI模型服务启动成功")
        else:
            self._log("AI模型服务启动失败")
    
    def _start_novel_service(self):
        """启动小说服务"""
        self._log("正在启动小说生成服务...")
        if self.service_manager.start_novel_service():
            self._log("小说生成服务启动成功")
        else:
            self._log("小说生成服务启动失败")
    
    def _start_frontend(self):
        """启动前端服务"""
        self._log("正在启动前端服务...")
        if self.service_manager.start_frontend():
            self._log("前端服务启动成功")
        else:
            self._log("前端服务启动失败")
    
    def _start_all_services(self):
        """启动所有服务"""
        self._log("正在启动所有服务...")
        
        # 启动AI服务
        self._start_ai_service()
        time.sleep(1)
        
        # 启动小说服务
        self._start_novel_service()
        time.sleep(1)
        
        # 启动前端服务
        self._start_frontend()
        
        self._log("所有服务启动完成")
    
    def _stop_service(self, service_name: str):
        """停止服务"""
        self._log(f"正在停止 {service_name}...")
        if self.service_manager.stop_service(service_name):
            self._log(f"{service_name} 已停止")
        else:
            self._log(f"停止 {service_name} 失败")
    
    def _stop_all_services(self):
        """停止所有服务"""
        self._log("正在停止所有服务...")
        self.service_manager.stop_all_services()
        self._log("所有服务已停止")
    
    def _auto_start_services(self):
        """自动启动所有服务"""
        self._log("正在自动启动所有服务...")
        
        # 启动AI服务
        self._log(f"查找exe目录: {self.service_manager.exe_dir}")
        self._start_ai_service()
        time.sleep(1)
        
        # 启动小说服务
        self._start_novel_service()
        time.sleep(1)
        
        self._log("自动启动完成")
    
    def _open_frontend(self):
        """打开前端"""
        port = self.service_manager.config["frontend_port"]
        url = f"http://localhost:{port}"
        self._log(f"打开前端: {url}")
        self.service_manager.open_browser(url)
    
    def _open_api_docs(self):
        """打开API文档"""
        ai_port = self.service_manager.config["ai_service_port"]
        novel_port = self.service_manager.config["novel_service_port"]
        
        # 打开AI服务API文档
        url = f"http://localhost:{ai_port}/docs"
        self._log(f"打开AI服务API文档: {url}")
        self.service_manager.open_browser(url)
        
        # 打开小说服务API文档
        url = f"http://localhost:{novel_port}/docs"
        self._log(f"打开小说服务API文档: {url}")
        self.service_manager.open_browser(url)
    
    def run(self):
        """运行启动器"""
        # 设置关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # 运行主循环
        self.root.mainloop()
    
    def _on_close(self):
        """关闭事件"""
        # 停止所有服务
        self.service_manager.stop_all_services()
        
        # 关闭窗口
        self.root.destroy()


def main():
    """主函数"""
    if not HAS_TKINTER:
        print("错误: 未安装tkinter，无法启动图形界面")
        print("请使用命令行模式启动服务")
        return
    
    # 创建并运行启动器
    launcher = LauncherGUI()
    launcher.run()


if __name__ == "__main__":
    main()
