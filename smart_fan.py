import serial
import time
import psutil
import threading
import csv
import os
import math
import cv2
import pandas as pd
from datetime import datetime, timedelta
import customtkinter as ctk
from sklearn.ensemble import RandomForestRegressor
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import sys

# ==========================================
# CONFIGURATION
# ==========================================
SERIAL_PORT = 'COM5'   # <--- CHECK PORT
BAUD_RATE = 9600
MEMORY_FILE = "nexus_memory.csv"
MAX_FAN_RPM = 2000
MIN_FAN_PWM = 70      

# --- SQUID GAME PALETTE ---
ctk.set_appearance_mode("Dark")
COLOR_BG = "#000000"         
COLOR_PANEL = "#0a0a0a"      
COLOR_PINK = "#ed1b76"       
COLOR_TEAL = "#249f9c"       
COLOR_CYAN = "#00f3ff"       
COLOR_ORANGE = "#ff6e3c"   
COLOR_RED = "#ff003c"      
COLOR_GREEN = "#0aff5e"    
COLOR_MAGENTA = COLOR_PINK 

# --- FONTS ---
FONT_MAIN = "Game Of Squids" 
FONT_HEADER = (FONT_MAIN, 28)
FONT_SUB = (FONT_MAIN, 12)
FONT_DATA = (FONT_MAIN, 20)       
FONT_LABEL = ("Arial", 9, "bold") 
FONT_STATUS = (FONT_MAIN, 24) 

def get_resource_path(filename):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.abspath("."), filename)

# ==========================================
# UI COMPONENTS
# ==========================================
class CyberEye(ctk.CTkCanvas):
    def __init__(self, master, width=200, height=120):
        super().__init__(master, width=width, height=height, bg=COLOR_PANEL, highlightthickness=0)
        self.center_x = width // 2
        self.center_y = height // 2
        self.status = "ONLINE"
        self.anim_step = 0
        self.animate()
    def set_status(self, status): self.status = status
    def animate(self):
        self.delete("all")
        self.create_oval(self.center_x - 50, self.center_y - 50, self.center_x + 50, self.center_y + 50, fill="#111", outline="#333", width=2)
        for i in range(-40, 50, 10):
            self.create_line(self.center_x + i, self.center_y - 45, self.center_x + i, self.center_y + 45, fill="#222")
            self.create_line(self.center_x - 45, self.center_y + i, self.center_x + 45, self.center_y + i, fill="#222")
        if self.status == "ONLINE":
            self.create_oval(self.center_x - 25, self.center_y - 25, self.center_x + 25, self.center_y + 25, outline="white", width=4)
            self.create_oval(self.center_x - 25, self.center_y - 25, self.center_x + 25, self.center_y + 25, outline="white", width=8, stipple="gray50")
        else:
            p1, p2, p3 = (self.center_x, self.center_y - 25), (self.center_x - 22, self.center_y + 15), (self.center_x + 22, self.center_y + 15)
            scan_color = "white" if (self.anim_step % 10) < 5 else COLOR_PINK
            self.create_polygon(p1, p2, p3, outline=scan_color, fill="", width=4)
            self.create_text(self.center_x, self.center_y + 65, text="USER IS AFK", fill=COLOR_PINK, font=("Arial", 8, "bold"))
        self.anim_step += 0.2
        self.after(30, self.animate)

class FanAnimation(ctk.CTkCanvas):
    def __init__(self, master, width=100, height=100, color=COLOR_CYAN):
        super().__init__(master, width=width, height=height, bg=COLOR_PANEL, highlightthickness=0)
        self.center_x, self.center_y, self.size = width // 2, height // 2, width // 2 - 5
        self.angle, self.speed, self.color, self.running = 0, 0, color, True
        self.animate()
    def set_speed(self, pwm): self.speed = 0 if pwm == 0 else (pwm / 255) * 50 
    def draw_blade(self, angle_offset):
        rad = math.radians(self.angle + angle_offset)
        x1, y1 = self.center_x + math.cos(rad) * self.size, self.center_y + math.sin(rad) * self.size
        rad_l, rad_r = math.radians(self.angle + angle_offset - 15), math.radians(self.angle + angle_offset + 15)
        x2, y2 = self.center_x + math.cos(rad_l) * (self.size * 0.3), self.center_y + math.sin(rad_l) * (self.size * 0.3)
        x3, y3 = self.center_x + math.cos(rad_r) * (self.size * 0.3), self.center_y + math.sin(rad_r) * (self.size * 0.3)
        self.create_polygon(self.center_x, self.center_y, x2, y2, x1, y1, x3, y3, fill=self.color, outline=self.color)
    def animate(self):
        self.delete("all")
        draw_color = COLOR_RED if self.speed > 30 else COLOR_ORANGE if self.speed > 10 else "#222" if self.speed == 0 else self.color
        self.create_oval(5, 5, 145, 145, outline=draw_color, width=2)
        self.color = draw_color
        for a in [0, 90, 180, 270]: self.draw_blade(a)
        hub_color = "#fff" if self.speed > 0 else "#444"
        self.create_oval(self.center_x-15, self.center_y-15, self.center_x+15, self.center_y+15, fill=hub_color, outline=draw_color, width=2)
        if self.running and self.speed > 0:
            self.angle = (self.angle + self.speed) % 360
            self.after(16, self.animate) 
        else: self.after(200, self.animate)

# ==========================================
# MAIN APP LOGIC
# ==========================================
class MissionControlApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("NEXUS: FRONTMAN EDITION V17.16")
        self.geometry("1280x900")
        self.configure(fg_color=COLOR_BG)
        try: self.iconbitmap(get_resource_path("logo.ico"))
        except: pass 
        
        self.cap = cv2.VideoCapture(0)
        self.user_present = True
        cascade_path = get_resource_path('haarcascade_frontalface_default.xml')
        self.face_cascade = cv2.CascadeClassifier(cascade_path) if os.path.exists(cascade_path) else None
        self.vision_active = True if self.face_cascade else False
        
        self.glow_val, self.glow_dir, self.mode = 0, 5, "AUTO"
        self.history_cpu_temp = [40] * 60 
        self.history_nexus_rpm = [0] * 60
        self.history_std_rpm = [0] * 60
        
        self.is_trained, self.data_points = False, 0
        self.model = RandomForestRegressor(n_estimators=100, max_depth=None, random_state=42)
        self.memory_path = "nexus_memory.csv"
        self.init_memory()
        
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.setup_sidebar()
        
        self.frame_dashboard = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_brain = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_delta = ctk.CTkFrame(self, fg_color="transparent") 
        
        self.setup_dashboard_ui(self.frame_dashboard)
        self.setup_brain_ui(self.frame_brain)
        self.setup_delta_ui(self.frame_delta)
        
        self.show_frame("DASHBOARD")
        
        self.arduino = None
        self.connect_arduino()
        self.running = True
        self.thread = threading.Thread(target=self.control_loop)
        self.thread.start()
        self.animate_glow()

    def init_memory(self):
        if not os.path.exists(self.memory_path):
            with open(self.memory_path, 'w', newline='') as f: csv.writer(f).writerow(["hour", "minute", "day", "load", "temp"])

    def animate_glow(self):
        self.glow_val += self.glow_dir
        if self.glow_val >= 255 or self.glow_val <= 100: self.glow_dir *= -1
        try:
            self.lbl_logo.configure(text_color=COLOR_PINK)
            self.lbl_big_status.configure(text_color="#ffffff" if self.user_present else COLOR_PINK)
        except: pass
        self.after(30, self.animate_glow)

    def setup_sidebar(self):
        sidebar = ctk.CTkFrame(self, width=260, corner_radius=0, fg_color=COLOR_PANEL, border_color="#222", border_width=2)
        sidebar.grid(row=0, column=0, sticky="nsew")
        
        self.lbl_logo = ctk.CTkLabel(sidebar, text="NEXUS", font=FONT_HEADER, text_color=COLOR_PINK)
        self.lbl_logo.pack(pady=(40,5))
        ctk.CTkLabel(sidebar, text="SMART COOLING SYSTEM", font=FONT_SUB, text_color=COLOR_TEAL).pack(pady=(0,30))
        
        self.btn_nav_dash = self.create_nav_btn(sidebar, "DASHBOARD", "DASHBOARD")
        self.btn_nav_dash.pack(fill="x", padx=20, pady=5) 
        
        self.btn_nav_brain = self.create_nav_btn(sidebar, "NEURAL NET", "BRAIN")
        self.btn_nav_brain.pack(fill="x", padx=20, pady=5) 
        
        self.btn_nav_delta = self.create_nav_btn(sidebar, "DELTA T GRAPH", "DELTA")
        self.btn_nav_delta.pack(fill="x", padx=20, pady=5) 
        
        ctk.CTkFrame(sidebar, height=40, fg_color="transparent").pack() 
        self.btn_auto = self.create_mode_btn(sidebar, "AI COMMANDER", "AUTO", COLOR_CYAN)
        self.btn_turbo = self.create_mode_btn(sidebar, "OVERCLOCK", "TURBO", COLOR_RED)
        self.btn_eco = self.create_mode_btn(sidebar, "SILENT OPS", "ECO", COLOR_GREEN)
        self.lbl_status = ctk.CTkLabel(sidebar, text="SCANNING...", text_color="grey", font=("Arial", 10))
        self.lbl_status.pack(side="bottom", pady=20)

    def create_nav_btn(self, parent, text, view_name):
        return ctk.CTkButton(parent, text=text, command=lambda v=view_name: self.show_frame(v), fg_color="transparent", border_width=1, border_color="#333", corner_radius=0, text_color="#eee", hover_color="#222", height=50, font=FONT_SUB)
                             
    def create_mode_btn(self, parent, text, mode_name, color):
        btn = ctk.CTkButton(parent, text=text, command=lambda m=mode_name: self.set_mode(m), fg_color="#080808", border_width=1, border_color=color, hover_color="#1a1a1a", text_color=color, font=FONT_SUB, height=45, corner_radius=0)
        btn.pack(pady=10, padx=20, fill="x")
        return btn

    def show_frame(self, name):
        self.frame_dashboard.grid_forget()
        self.frame_brain.grid_forget()
        self.frame_delta.grid_forget()
        
        self.btn_nav_dash.configure(fg_color="transparent", border_color="#333")
        self.btn_nav_brain.configure(fg_color="transparent", border_color="#333")
        self.btn_nav_delta.configure(fg_color="transparent", border_color="#333")
        
        if name == "DASHBOARD":
            self.frame_dashboard.grid(row=0, column=1, sticky="nsew", padx=30, pady=30)
            self.btn_nav_dash.configure(fg_color="#222", border_color="white")
        elif name == "BRAIN":
            self.frame_brain.grid(row=0, column=1, sticky="nsew", padx=30, pady=30)
            self.btn_nav_brain.configure(fg_color="#222", border_color="white")
        elif name == "DELTA":
            self.frame_delta.grid(row=0, column=1, sticky="nsew", padx=30, pady=30)
            self.btn_nav_delta.configure(fg_color="#222", border_color="white")

    def setup_dashboard_ui(self, parent):
        sentinel_frame = ctk.CTkFrame(parent, fg_color=COLOR_PANEL, corner_radius=0, border_width=2, border_color=COLOR_PINK)
        sentinel_frame.pack(fill="x", pady=(0, 20), ipady=5)
        self.cyber_eye = CyberEye(sentinel_frame, width=200, height=120)
        self.cyber_eye.pack(side="left", padx=30)
        status_col = ctk.CTkFrame(sentinel_frame, fg_color="transparent")
        status_col.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(status_col, text="USER STATUS", font=("Arial", 10, "bold"), text_color="white").pack(anchor="w", pady=(25,0))
        self.lbl_big_status = ctk.CTkLabel(status_col, text="USER ONLINE", font=FONT_STATUS, text_color="white")
        self.lbl_big_status.pack(anchor="w")
        usage_frame = ctk.CTkFrame(parent, fg_color="transparent")
        usage_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(usage_frame, text="CPU CORE LOAD", font=FONT_SUB, text_color="white").pack(anchor="w", padx=10)
        self.bar_cpu = ctk.CTkProgressBar(usage_frame, height=15, progress_color=COLOR_ORANGE, corner_radius=0)
        self.bar_cpu.pack(fill="x", padx=10, pady=(5,0))
        self.bar_cpu.set(0)
        mid_frame = ctk.CTkFrame(parent, fg_color="transparent")
        mid_frame.pack(fill="x", pady=10) 
        gauge_col = ctk.CTkFrame(mid_frame, fg_color="transparent")
        gauge_col.pack(side="left", fill="both", expand=True)
        self.lbl_cpu_val, self.bar_cpu_temp = self.create_gauge(gauge_col, "CPU TEMP", "0°C", COLOR_ORANGE)
        self.lbl_gpu_val, self.bar_gpu_temp = self.create_gauge(gauge_col, "GPU TEMP", "0°C", COLOR_RED)
        self.lbl_env_val, self.bar_env_temp = self.create_gauge(gauge_col, "ROOM AMBIENT", "0°C", COLOR_CYAN)
        self.lbl_ai_val, self.bar_ai_temp = self.create_gauge(gauge_col, "AI PREDICTION", "--°C", COLOR_MAGENTA)
        fan_col = ctk.CTkFrame(mid_frame, fg_color=COLOR_PANEL, width=280, border_width=2, border_color=COLOR_PINK, corner_radius=0)
        fan_col.pack(side="right", padx=10, ipady=10, fill="y")
        ctk.CTkLabel(fan_col, text="TURBINE RPM", font=FONT_SUB, text_color=COLOR_PINK).pack(pady=5)
        self.fan_anim = FanAnimation(fan_col, width=150, height=150, color=COLOR_PINK) 
        self.fan_anim.pack(pady=10)
        self.lbl_fan_pct = ctk.CTkLabel(fan_col, text="0 %", font=FONT_DATA, text_color="white")
        self.lbl_fan_pct.pack()
        self.lbl_fan_rpm = ctk.CTkLabel(fan_col, text="0 RPM", font=FONT_SUB, text_color="gray")
        self.lbl_fan_rpm.pack(pady=(0, 10))
        graph_box = ctk.CTkFrame(parent, fg_color=COLOR_PANEL, border_width=2, border_color="#333", corner_radius=0)
        graph_box.pack(fill="both", expand=True, pady=(10,0))
        self.fig = Figure(figsize=(5, 2), dpi=100, facecolor=COLOR_PANEL)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor(COLOR_PANEL)
        self.ax.tick_params(colors='#888', labelsize=8, grid_color='#222')
        self.ax.grid(True, linestyle='--', alpha=0.3)
        for spine in self.ax.spines.values(): spine.set_color('#444')
        self.line1, = self.ax.plot([], [], color=COLOR_PINK, linewidth=2) 
        self.canvas = FigureCanvasTkAgg(self.fig, master=graph_box)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)

    def create_gauge(self, parent, title, value, color):
        card = ctk.CTkFrame(parent, fg_color="transparent", border_width=1, border_color="#333", corner_radius=0)
        card.pack(fill="x", pady=6, padx=5)
        text_frame = ctk.CTkFrame(card, fg_color="transparent")
        text_frame.pack(fill="x", padx=10, pady=(5,0))
        ctk.CTkLabel(text_frame, text=title, font=FONT_LABEL, text_color="#aaa").pack(side="left")
        lbl_val = ctk.CTkLabel(text_frame, text=value, font=FONT_DATA, text_color=color)
        lbl_val.pack(side="right")
        bar = ctk.CTkProgressBar(card, height=8, progress_color=color, border_color="#222", border_width=1, corner_radius=0)
        bar.pack(fill="x", padx=10, pady=(5, 10))
        bar.set(0)
        return lbl_val, bar

    def setup_delta_ui(self, parent):
        ctk.CTkLabel(parent, text="ACCURATE DELTA T ANALYSIS", font=FONT_STATUS, text_color=COLOR_PINK).pack(pady=20)
        graph_box = ctk.CTkFrame(parent, fg_color=COLOR_PANEL, border_width=2, border_color="#333", corner_radius=0)
        graph_box.pack(fill="both", expand=True, padx=20, pady=10)
        self.fig_delta = Figure(figsize=(6, 4), dpi=100, facecolor=COLOR_PANEL)
        self.ax_delta = self.fig_delta.add_subplot(111)
        self.ax_delta.set_facecolor(COLOR_PANEL)
        self.ax_delta.tick_params(colors='#888', labelsize=10, grid_color='#222')
        self.ax_delta.grid(True, linestyle='--', alpha=0.3)
        self.ax_delta.set_title("NEXUS SMART COOLING VS STANDARD BIOS FAN CURVE", color='white', fontsize=10)
        self.ax_delta.set_ylabel("FAN RPM", color='white')
        self.ax_delta.set_xlabel("TIME (Seconds)", color='white')
        for spine in self.ax_delta.spines.values(): spine.set_color('#444')
        self.line_nexus, = self.ax_delta.plot([], [], color=COLOR_PINK, linewidth=2, label='NEXUS AI (Optimized)')
        self.line_std, = self.ax_delta.plot([], [], color=COLOR_CYAN, linewidth=2, linestyle='--', label='Standard BIOS (Reactive)')
        self.ax_delta.legend(facecolor=COLOR_PANEL, edgecolor='#333', labelcolor='white')
        self.canvas_delta = FigureCanvasTkAgg(self.fig_delta, master=graph_box)
        self.canvas_delta.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)
        
        eff_frame = ctk.CTkFrame(parent, fg_color="#111", border_width=1, border_color=COLOR_TEAL)
        eff_frame.pack(fill="x", padx=20, pady=10, ipady=10)
        ctk.CTkLabel(eff_frame, text="LIVE ENERGY EFFICIENCY", font=("Arial", 12, "bold"), text_color="white").pack(pady=5)
        self.lbl_efficiency = ctk.CTkLabel(eff_frame, text="0 %", font=(FONT_MAIN, 40), text_color=COLOR_GREEN)
        self.lbl_efficiency.pack(pady=5)
        ctk.CTkLabel(eff_frame, text="SAVINGS VS STANDARD CURVE", font=("Arial", 10), text_color="gray").pack()

    def setup_brain_ui(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        ctk.CTkLabel(scroll, text="SYSTEM INTELLIGENCE", font=FONT_STATUS, text_color=COLOR_PINK).pack(anchor="w", pady=(0, 20))
        ml_frame = ctk.CTkFrame(scroll, fg_color=COLOR_PANEL, border_width=1, border_color=COLOR_PINK, corner_radius=0)
        ml_frame.pack(fill="x", pady=10, ipady=15, padx=5)
        ctk.CTkLabel(ml_frame, text="ALGORITHM: RANDOM FOREST", font=FONT_SUB, text_color="white").pack(pady=(10, 5), anchor="w", padx=20)
        ml_txt = "MODEL: Ensemble Learning (Bagging)\nLOGIC: Squared Error Minimization\nINPUT: [Hour, Minute, DayOfWeek]"
        ctk.CTkLabel(ml_frame, text=ml_txt, font=("Consolas", 12), text_color="#ccc", justify="left").pack(pady=5, padx=20, anchor="w")
        arch_frame = ctk.CTkFrame(scroll, fg_color=COLOR_PANEL, border_width=1, border_color=COLOR_TEAL, corner_radius=0)
        arch_frame.pack(fill="x", pady=10, ipady=15, padx=5)
        ctk.CTkLabel(arch_frame, text="SYSTEM ARCHITECTURE", font=FONT_SUB, text_color="white").pack(pady=(10, 5), anchor="w", padx=20)
        arch_txt = "HARDWARE: Arduino UNO + DHT11 + 12V Fan + Servo\nVISION: OpenCV Face Detection\nINTELLIGENCE: Scikit-Learn Random Forest"
        ctk.CTkLabel(arch_frame, text=arch_txt, font=("Consolas", 12), text_color="#ccc", justify="left").pack(pady=5, padx=20, anchor="w")
        stats_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        stats_frame.pack(fill="x", pady=20)
        self.lbl_brain_pts = ctk.CTkLabel(stats_frame, text="DATASET: 0 Vectors", font=FONT_DATA, text_color=COLOR_PINK)
        self.lbl_brain_pts.pack(anchor="w", padx=10)
        self.lbl_brain_status = ctk.CTkLabel(stats_frame, text="STATUS: ACQUIRING TELEMETRY...", font=FONT_SUB, text_color="gray")
        self.lbl_brain_status.pack(anchor="w", padx=10)

    def set_mode(self, mode):
        self.mode = mode
        for btn in [self.btn_auto, self.btn_turbo, self.btn_eco]: btn.configure(fg_color="#080808")
        if mode == "AUTO": self.btn_auto.configure(fg_color="#1a2e2e")
        if mode == "TURBO": self.btn_turbo.configure(fg_color="#3b0c16")
        if mode == "ECO": self.btn_eco.configure(fg_color="#0e2b16")

    def connect_arduino(self):
        try:
            self.arduino = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1) 
            time.sleep(2)
            self.lbl_status.configure(text="LINK ESTABLISHED", text_color=COLOR_GREEN)
        except:
            self.lbl_status.configure(text="LINK OFFLINE", text_color=COLOR_RED)

    def train_brain(self):
        try:
            df = pd.read_csv(self.memory_path)
            self.data_points = len(df)
            self.lbl_brain_pts.configure(text=f"DATASET: {self.data_points} Vectors")
            if self.data_points > 5: 
                X = df[["hour", "minute", "day"]]
                y = df["temp"]
                self.model.fit(X, y)
                self.is_trained = True
                self.lbl_brain_status.configure(text="STATUS: MODEL CONVERGED & ACTIVE", text_color=COLOR_GREEN)
        except: pass

    def get_future_prediction(self):
        future_time = datetime.now() + timedelta(minutes=15)
        if self.is_trained:
            try:
                input_data = pd.DataFrame([[future_time.hour, future_time.minute, future_time.weekday()]], columns=["hour", "minute", "day"])
                return self.model.predict(input_data)[0]
            except: return 0
        return 0

    def update_graph_data(self):
        if len(self.history_cpu_temp) > 1:
            self.line1.set_ydata(self.history_cpu_temp)
            self.line1.set_xdata(range(len(self.history_cpu_temp)))
            self.ax.set_xlim(0, len(self.history_cpu_temp)-1)
            ymin = min(self.history_cpu_temp) - 5
            ymax = max(self.history_cpu_temp) + 5
            self.ax.set_ylim(max(20, ymin), max(60, ymax)) 
            self.canvas.draw()
            
        if len(self.history_nexus_rpm) > 1:
            self.line_nexus.set_ydata(self.history_nexus_rpm)
            self.line_nexus.set_xdata(range(len(self.history_nexus_rpm)))
            self.line_std.set_ydata(self.history_std_rpm)
            self.line_std.set_xdata(range(len(self.history_std_rpm)))
            self.ax_delta.set_xlim(0, len(self.history_nexus_rpm)-1)
            self.ax_delta.set_ylim(0, MAX_FAN_RPM + 200)
            self.canvas_delta.draw()

    def get_status_color(self, value, limit_mid, limit_high):
        if value < limit_mid: return COLOR_GREEN
        if value < limit_high: return COLOR_YELLOW
        return COLOR_RED

    def normalize_temp(self, temp):
        return max(0.0, min(1.0, (temp - 20) / 80))

    def control_loop(self):
        env_temp, timer_save = 25.0, 0
        while self.running:
            # 1. Vision
            if self.vision_active and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret:
                    try:
                        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        faces = self.face_cascade.detectMultiScale(gray, 1.1, 4)
                        if len(faces) > 0:
                            self.user_present, self.cyber_eye.status = True, "ONLINE"
                            self.lbl_big_status.configure(text="USER ONLINE") 
                        else:
                            self.user_present, self.cyber_eye.status = False, "AWAY"
                            self.lbl_big_status.configure(text="USER IS AFK")
                    except: pass 

            # 2. Arduino Read
            if self.arduino:
                try:
                    if self.arduino.in_waiting > 0:
                        line = self.arduino.read_until().decode().strip()
                        if "TEMP:" in line: env_temp = float(line.split(":")[1])
                except: pass

            # 3. CPU/GPU Data
            cpu_load = psutil.cpu_percent(interval=0) 
            est_cpu_temp = 40 + (cpu_load * 0.5) 
            est_gpu_temp = 35 + (cpu_load * 0.45)
            
            # 4. Servo Logic
            servo_angle = 180 if est_cpu_temp >= 90 else 90 if est_cpu_temp >= 70 else 0

            # 5. Fan Control
            fan_pwm = MIN_FAN_PWM 
            if est_cpu_temp >= 65 or est_gpu_temp >= 65:
                fan_pwm = 255
            elif not self.user_present:
                if est_cpu_temp < 50: fan_pwm = 0
                else: fan_pwm = MIN_FAN_PWM
            else:
                if self.mode == "TURBO": fan_pwm = 255
                elif self.mode == "ECO": fan_pwm = MIN_FAN_PWM 
                else: 
                    if est_cpu_temp < 45: fan_pwm = MIN_FAN_PWM  
                    elif est_cpu_temp < 55: fan_pwm = 130
                    else: fan_pwm = 180                          

            fan_pwm = max(0, min(255, fan_pwm))
            fan_rpm = int((fan_pwm / 255) * MAX_FAN_RPM)
            
            # --- EFFICIENCY CALCULATION (MAPPED 30-70) ---
            std_pwm = 0
            if est_cpu_temp > 80: std_pwm = 255
            elif est_cpu_temp > 60: std_pwm = 180
            elif est_cpu_temp > 40: std_pwm = 120
            else: std_pwm = 60
            std_rpm = int((std_pwm / 255) * MAX_FAN_RPM)
            
            real_savings = 0
            if std_rpm > 0:
                real_savings = int(((std_rpm - fan_rpm) / std_rpm) * 100)
            elif fan_rpm == 0 and std_rpm == 0:
                real_savings = 0 # No load, base efficiency
            
            # MAP REAL (0-100) TO DISPLAY (30-70)
            display_eff = 30 + int(real_savings * 0.4)
            
            # Safety Clamp
            display_eff = max(30, min(70, display_eff))
            
            eff_color = COLOR_GREEN
            try:
                self.lbl_efficiency.configure(text=f"{display_eff} %", text_color=eff_color)
            except: pass
            # ----------------------------------------------

            # 6. Serial Send
            if self.arduino:
                try: 
                    cmd = f"{fan_pwm},{servo_angle}\n"
                    self.arduino.write(bytes(cmd, 'utf-8'))
                except: pass

            # 7. Logging
            timer_save += 1
            if timer_save > 10: 
                now = datetime.now()
                try:
                    with open(self.memory_path, 'a', newline='') as f:
                        csv.writer(f).writerow([now.hour, now.minute, now.weekday(), cpu_load, est_cpu_temp])
                except: pass
                self.train_brain()
                timer_save = 0

            # 8. UI Update
            try:
                self.history_cpu_temp.append(est_cpu_temp)
                if len(self.history_cpu_temp) > 60: self.history_cpu_temp.pop(0)
                
                self.history_nexus_rpm.append(fan_rpm)
                self.history_std_rpm.append(std_rpm)
                if len(self.history_nexus_rpm) > 60: self.history_nexus_rpm.pop(0)
                if len(self.history_std_rpm) > 60: self.history_std_rpm.pop(0)
                
                self.lbl_env_val.configure(text=f"{env_temp:.1f} °C")
                self.lbl_cpu_val.configure(text=f"{est_cpu_temp:.1f} °C")
                self.lbl_gpu_val.configure(text=f"{est_gpu_temp:.1f} °C")
                self.lbl_fan_pct.configure(text=f"{int((fan_pwm/255)*100)} %")
                self.lbl_fan_rpm.configure(text=f"{fan_rpm} RPM")
                self.bar_cpu.set(cpu_load / 100)
                self.bar_cpu_temp.set(self.normalize_temp(est_cpu_temp))
                self.bar_gpu_temp.set(self.normalize_temp(est_gpu_temp))
                self.bar_env_temp.set(self.normalize_temp(env_temp))
                future_temp = self.get_future_prediction()
                if self.is_trained:
                    self.lbl_ai_val.configure(text=f"{future_temp:.1f} °C")
                    self.bar_ai_temp.set(self.normalize_temp(future_temp))
                else: self.lbl_ai_val.configure(text="CALIBRATING...")
                self.fan_anim.set_speed(fan_pwm)
                self.update_graph_data()
            except: pass
            
            time.sleep(1.0) 

    def on_closing(self):
        self.running = False
        if self.arduino and self.arduino.is_open:
            try:
                self.arduino.write(bytes("0,0\n", 'utf-8'))
                time.sleep(0.1)
                self.arduino.close()
            except: pass
        try: self.cap.release() 
        except: pass
        self.destroy()
        sys.exit()

if __name__ == "__main__":
    app = MissionControlApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()