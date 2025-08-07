import customtkinter as ctk
import tkinter as tk
import threading
from datetime import datetime, timedelta
from collections import deque
import queue
from sniper_bot import SniperSession
import json
import os
import time
import requests
import uuid
from collections import deque
from PIL import Image
import tkinter.messagebox as messagebox
import webbrowser
import sys
import platform
import hashlib
import subprocess

MAX_LOG_LINES = 5000
MAX_SEEN_TOKENS = 10000
MAX_TRADES_HISTORY = 1000

SOLANA_MAINNET_RPC = "https://api.mainnet-beta.solana.com"

# Utility to get resource path for PyInstaller and dev

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# Utility to get user-writable settings path

def get_settings_path():
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        settings_dir = os.path.join(appdata, "TurboSniperTrader")
    elif sys.platform == "darwin":
        settings_dir = os.path.expanduser("~/Library/Application Support/TurboSniperTrader")
    else:
        settings_dir = os.path.expanduser("~/.config/TurboSniperTrader")
    os.makedirs(settings_dir, exist_ok=True)
    return os.path.join(settings_dir, "settings.json")

SETTINGS_FILE = get_settings_path()

APP_NAME = "Turbo"
APP_VERSION = "1.1.1"
COMPANY = "Turbo"
SUPPORT_EMAIL = "support@turbo.com"
WEBSITE = "https://turbo.com" 
TELEGRAM = "@turbo"

# --- Turbo Branding Colors (Updated Palette) -------------------------------------------------------------
TURBO_BLACK = "#0A1026"         # Main background
TURBO_SIDEBAR = "#10182A"      # Sidebar background
TURBO_WHITE = "#FFFFFF"         # Main text
TURBO_GRAY = "#B0B0B0"          # Subtle text, separators
TURBO_CYAN = "#00EAFF"          # Primary accent (neon cyan)
TURBO_PURPLE = "#E600FF"        # Secondary accent (neon purple)
TURBO_NAVY = "#181F3A"          # Button hover, panel backgrounds
TURBO_DARK_GRAY = "#23263A"     # Inputs, panel backgrounds
TURBO_SHADOW = "#0A0F1A"        # Shadow/glow effect
TURBO_GRADIENT_1 = "#00EAFF"    # Gradient start
TURBO_GRADIENT_2 = "#E600FF"    # Gradient end
TURBO_ERROR = "#FF3B3B"         # Error/alert
TURBO_SUCCESS = "#00FFB2"       # Success/positive
TURBO_WARNING = "#FFB800"       # Warning/caution

# Beautiful log colors
LOG_SYSTEM = "#4A9EFF"          # Blue for system logs
LOG_TRADE = "#4CAF50"           # Green for trading logs  
LOG_ERROR = "#F44336"           # Red for error logs
LOG_DEBUG = "#9E9E9E"           # Gray for debug logs

# Modern font
FONT_MAIN = ("Montserrat", 18, "bold")
FONT_SIDEBAR = ("Montserrat", 18, "bold")
FONT_DASHBOARD = ("Montserrat", 22, "bold")
FONT_STATUS = ("Montserrat", 20, "bold")

label_kwargs = {
    "text_color": TURBO_WHITE,
    "font": ("Montserrat", 16, "bold"),
}

entry_kwargs = {
    "fg_color": TURBO_DARK_GRAY,
    "border_color": TURBO_CYAN,
    "text_color": TURBO_WHITE,
    "border_width": 2,
    "font": ("Montserrat", 12),
}

button_kwargs = {
    "fg_color": TURBO_CYAN,
    "hover_color": TURBO_PURPLE,
    "text_color": TURBO_BLACK,
    "corner_radius": 10,
    "font": ("Montserrat", 13, "bold"),
    "border_color": TURBO_CYAN,
    "border_width": 2,
}

# If you want a different style for TradesFrame, define it here:
trades_label_kwargs = {
    "text_color": TURBO_WHITE,
    "font": ("Montserrat", 14, "bold"),
}

# --- UI/UX POLISH CONSTANTS ---
SPACING_XL = 24
SPACING_LG = 16
SPACING_MD = 10
SPACING_SM = 6
CARD_RADIUS = 16
BTN_RADIUS = 12
INPUT_RADIUS = 10
CARD_BORDER = 2
BTN_HEIGHT = 36
BTN_WIDTH = 120
FONT_HEADER = ("Montserrat", 20, "bold")
FONT_SUBHEADER = ("Montserrat", 16, "bold")
FONT_BODY = ("Montserrat", 14)
FONT_STAT = ("Montserrat", 15, "bold")

# Update all CTkFrame, CTkButton, CTkEntry, CTkLabel, etc. to use these constants for padding, font, and radius.
# Example for cards in dashboard:
# card = ctk.CTkFrame(self.open_scroll, fg_color=TURBO_NAVY, corner_radius=CARD_RADIUS, border_width=CARD_BORDER, border_color=TURBO_CYAN)
# card.pack(fill="x", padx=SPACING_XL, pady=SPACING_LG, ipadx=SPACING_MD, ipady=SPACING_MD)
# ctk.CTkLabel(card, text=f"Name: {name}", font=FONT_SUBHEADER, pady=SPACING_SM).pack(anchor="w", padx=SPACING_MD)
# ctk.CTkLabel(card, text=f"PnL: {pnl_str}", font=FONT_STAT, text_color=color, pady=SPACING_SM).pack(anchor="w", padx=SPACING_MD)
# sell_btn = ctk.CTkButton(card, text="Sell", fg_color=TURBO_ERROR, hover_color=TURBO_PURPLE, text_color=TURBO_WHITE, width=BTN_WIDTH, height=BTN_HEIGHT, corner_radius=BTN_RADIUS, font=FONT_BODY, pady=SPACING_SM)
# sell_btn.pack(anchor="e", padx=SPACING_MD, pady=(SPACING_MD, 0))
#
# Apply similar spacing, font, and radius improvements to all sections: sidebar, settings, manual buy, logs, license, about, etc.
#
# Do not change any logic or functionality—only update visual/layout parameters for a more modern, appealing look.

# --- Beautiful Logging System ---
class BeautifulLogger:
    def __init__(self):
        self.log_queue = queue.Queue()
        self.session_start = datetime.now()
        self.stats = {
            'tokens_scanned': 0,
            'tokens_filtered': 0,
            'trades_attempted': 0,
            'trades_successful': 0,
            'current_balance': 0.0,
            'session_pnl': 0.0
        }
        
    def system(self, message):
        """Log system status messages"""
        self._add_log("SYSTEM", message, LOG_SYSTEM, "🟢")
        
    def trade(self, message):
        """Log trading activity"""
        self._add_log("TRADE", message, LOG_TRADE, "💸")
        
    def error(self, message):
        """Log errors and warnings"""
        self._add_log("ERROR", message, LOG_ERROR, "⚠️")
        
    def debug(self, message):
        """Log debug information"""
        self._add_log("DEBUG", message, LOG_DEBUG, "🔧")
        
    def scan(self, message):
        """Log token scanning"""
        self._add_log("SCAN", message, TURBO_CYAN, "🔍")
        
    def filter_pass(self, message):
        """Log filter passes"""
        self._add_log("FILTER", message, TURBO_SUCCESS, "✅")
        
    def filter_fail(self, message):
        """Log filter failures"""
        self._add_log("FILTER", message, TURBO_WARNING, "❌")
        
    def _add_log(self, category, message, color, emoji):
        """Internal method to add log entry"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = {
            'timestamp': timestamp,
            'category': category,
            'message': message,
            'color': color,
            'emoji': emoji
        }
        self.log_queue.put(log_entry)
        
    def update_stats(self, **kwargs):
        """Update session statistics"""
        for key, value in kwargs.items():
            if key in self.stats:
                self.stats[key] = value
                
    def get_session_duration(self):
        """Get formatted session duration"""
        duration = datetime.now() - self.session_start
        hours, remainder = divmod(duration.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"

# Global logger instance
beautiful_logger = BeautifulLogger()

# --- Sidebar ---
class Sidebar(ctk.CTkFrame):
    def __init__(self, master, callback, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.callback = callback
        self.buttons = {}
        self.configure(fg_color=TURBO_SIDEBAR)
        # Logo
        try:
            from PIL import Image
            logo_path = resource_path("logo.png")
            if os.path.exists(logo_path):
                img = Image.open(logo_path).convert("RGBA").resize((120, 120))
                self.logo_img = ctk.CTkImage(light_image=img, dark_image=img, size=(120, 120))
                self.logo_label = ctk.CTkLabel(self, image=self.logo_img, text="", fg_color="transparent")
                self.logo_label.pack(pady=(30, 10))
            else:
                self.logo_label = ctk.CTkLabel(self, text="[Turbo Logo]", **label_kwargs)
                self.logo_label.pack(pady=(30, 10))
        except Exception as e:
            print("Sidebar logo load error:", e)
            self.logo_label = ctk.CTkLabel(self, text="[Turbo Logo]", **label_kwargs)
            self.logo_label.pack(pady=(30, 10))
        # App Name
        self.app_name = ctk.CTkLabel(self, text="TURBO", font=("Montserrat", 32, "bold"), text_color=TURBO_CYAN, fg_color="transparent")
        self.app_name.pack(pady=(0, 30))
        # Navigation
        self.sections = ["Dashboard", "Settings", "Manual Buy", "Logs", "License", "About"]
        self.selected_section = None
        for section in self.sections:
            btn = ctk.CTkButton(
                self,
                text=section,
                font=FONT_SIDEBAR,
                fg_color=TURBO_SIDEBAR,
                hover_color=TURBO_NAVY,
                text_color=TURBO_WHITE,
                corner_radius=10,
                width=180,
                height=40,
                border_color=TURBO_CYAN,
                border_width=0,
                command=lambda s=section: self.select_section(s)
            )
            btn.pack(pady=5)
            self.buttons[section] = btn
        self.pack_propagate(False)
        self.select_section("Dashboard")

    def select_section(self, section):
        for sec, btn in self.buttons.items():
            if sec == section:
                btn.configure(border_color=TURBO_CYAN if sec=="Dashboard" else TURBO_PURPLE, border_width=3)
                btn.configure(fg_color=TURBO_NAVY)
                btn.configure(text_color=TURBO_CYAN)
            else:
                btn.configure(border_width=0)
                btn.configure(fg_color=TURBO_SIDEBAR)
                btn.configure(text_color=TURBO_WHITE)
        self.selected_section = section
        self.callback(section)

# --- Dashboard ---
class DashboardFrame(ctk.CTkFrame):
    def __init__(self, master, start_callback, stop_callback, get_status, get_trades, get_summary, manual_sell_callback, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.start_callback = start_callback
        self.stop_callback = stop_callback
        self.get_status = get_status
        self.get_trades = get_trades
        self.get_summary = get_summary
        self.manual_sell_callback = manual_sell_callback
        self.configure(fg_color=TURBO_BLACK)
        self.panel = ctk.CTkFrame(self, fg_color=TURBO_NAVY, corner_radius=CARD_RADIUS)
        self.panel.pack(expand=True, fill="both", pady=SPACING_LG, padx=SPACING_XL, ipadx=SPACING_MD, ipady=SPACING_MD)
        self.panel.pack_propagate(False)
        # Top: Start/Stop Buttons
        btns_frame = ctk.CTkFrame(self.panel, fg_color="transparent")
        btns_frame.pack(pady=(SPACING_MD, SPACING_MD), padx=SPACING_MD)
        self.start_btn = ctk.CTkButton(
            btns_frame, text="Start Bot", font=FONT_DASHBOARD,
            fg_color=TURBO_BLACK, border_color=TURBO_CYAN, border_width=3,
            text_color=TURBO_CYAN, corner_radius=BTN_RADIUS, width=BTN_WIDTH, height=BTN_HEIGHT,
            hover_color=TURBO_NAVY, command=self.start_callback
        )
        self.start_btn.grid(row=0, column=0, padx=SPACING_SM, pady=SPACING_SM)
        self.stop_btn = ctk.CTkButton(
            btns_frame, text="Stop Bot", font=FONT_DASHBOARD,
            fg_color=TURBO_BLACK, border_color=TURBO_PURPLE, border_width=3,
            text_color=TURBO_PURPLE, corner_radius=BTN_RADIUS, width=BTN_WIDTH, height=BTN_HEIGHT,
            hover_color=TURBO_NAVY, command=self.stop_callback
        )
        self.stop_btn.grid(row=0, column=1, padx=SPACING_SM, pady=SPACING_SM)
        # Centered Status Label
        self.status_var = ctk.StringVar(value="Status: stopped")
        self.status_label = ctk.CTkLabel(
            self.panel, textvariable=self.status_var, font=FONT_STATUS, text_color=TURBO_CYAN, fg_color="transparent"
        )
        self.status_label.pack(pady=(SPACING_MD, SPACING_MD), padx=SPACING_MD)
        self.after(1000, self.update_status)
        
        # --- Live Dashboard Panel ---
        self.live_dashboard = ctk.CTkFrame(self.panel, fg_color=TURBO_DARK_GRAY, corner_radius=CARD_RADIUS, border_width=2, border_color=TURBO_CYAN)
        self.live_dashboard.pack(pady=(SPACING_MD, SPACING_MD), padx=SPACING_MD, fill="x")
        
        # Dashboard header
        dashboard_header = ctk.CTkLabel(
            self.live_dashboard, 
            text="🤖 LIVE DASHBOARD", 
            font=("Montserrat", 16, "bold"), 
            text_color=TURBO_CYAN
        )
        dashboard_header.pack(pady=(SPACING_SM, 0))
        
        # Stats container
        stats_frame = ctk.CTkFrame(self.live_dashboard, fg_color="transparent")
        stats_frame.pack(fill="x", padx=SPACING_MD, pady=SPACING_SM)
        
        # Live stats labels
        self.live_stats = {}
        stats_grid = [
            ("⏱️ Session", 0, 0), ("🔍 Scanned", 0, 1), ("✅ Filtered", 0, 2), 
            ("💸 Trades", 1, 0), ("📈 Success", 1, 1), ("💰 Balance", 1, 2)
        ]
        
        for stat_name, row, col in stats_grid:
            stat_frame = ctk.CTkFrame(stats_frame, fg_color=TURBO_NAVY, corner_radius=6)
            stat_frame.grid(row=row, column=col, padx=SPACING_SM, pady=SPACING_SM, sticky="ew")
            
            label = ctk.CTkLabel(stat_frame, text=stat_name, font=("Montserrat", 12), text_color=TURBO_GRAY)
            label.pack(pady=(SPACING_SM, 0))
            
            value = ctk.CTkLabel(stat_frame, text="0", font=("Montserrat", 14, "bold"), text_color=TURBO_WHITE)
            value.pack(pady=(0, SPACING_SM))
            
            self.live_stats[stat_name] = value
            
        # Configure grid weights
        for i in range(3):
            stats_frame.grid_columnconfigure(i, weight=1)
        
        # Live Logs Section
        logs_frame = ctk.CTkFrame(self.live_dashboard, fg_color=TURBO_BLACK, corner_radius=8, border_width=1, border_color=TURBO_NAVY)
        logs_frame.pack(fill="both", expand=True, padx=SPACING_MD, pady=(0, SPACING_MD))
        
        logs_header = ctk.CTkLabel(
            logs_frame, 
            text="📊 LIVE ACTIVITY FEED", 
            font=("Montserrat", 14, "bold"), 
            text_color=TURBO_PURPLE
        )
        logs_header.pack(pady=(SPACING_SM, 0))
        
        # Scrollable log display (bigger for better UX)
        self.live_logs = ctk.CTkTextbox(
            logs_frame,
            height=200,
            fg_color=TURBO_BLACK,
            text_color=TURBO_WHITE,
            font=("Courier New", 11),
            corner_radius=6,
            border_width=1,
            border_color=TURBO_DARK_GRAY,
            wrap="word"
        )
        self.live_logs.pack(fill="both", expand=True, padx=SPACING_SM, pady=SPACING_SM)
        
        # Initialize with welcome message
        self._add_live_log("🟢", "SYSTEM", "Live dashboard initialized - Ready to trade!", LOG_SYSTEM)
        
        # Add refresh button
        refresh_frame = ctk.CTkFrame(logs_frame, fg_color="transparent")
        refresh_frame.pack(fill="x", padx=SPACING_SM, pady=(0, SPACING_SM))
        
        refresh_btn = ctk.CTkButton(
            refresh_frame, 
            text="🔄 Refresh", 
            font=("Montserrat", 12),
            fg_color=TURBO_CYAN, 
            hover_color=TURBO_PURPLE,
            width=100, 
            height=30,
            command=self._refresh_dashboard
        )
        refresh_btn.pack(side="right")
        
        # Start the update loop
        self.after(500, self.update_live_dashboard)
        
        # --- Summary Panel ---
        self.summary_panel = ctk.CTkFrame(self.panel, fg_color=TURBO_DARK_GRAY, corner_radius=CARD_RADIUS)
        self.summary_panel.pack(pady=(SPACING_MD, SPACING_MD), padx=SPACING_MD, fill="x")
        self.summary_labels = {}
        grid = [
            ("Initial Balance", 0, 0),
            ("Current Balance", 0, 1),
            ("Overall PnL", 0, 2),
            ("Win Rate", 0, 3),
            ("Last Updated", 0, 4),
        ]
        for label, row, col in grid:
            l = ctk.CTkLabel(self.summary_panel, text=f"{label}:", font=FONT_SUBHEADER, text_color=TURBO_GRAY)
            l.grid(row=row, column=col*2, sticky="e", padx=(SPACING_SM, SPACING_MD), pady=SPACING_SM)
            v = ctk.CTkLabel(self.summary_panel, text="-", font=FONT_STAT, text_color=TURBO_WHITE)
            v.grid(row=row, column=col*2+1, sticky="w", padx=(SPACING_MD, SPACING_MD), pady=SPACING_SM)
            self.summary_labels[label] = v
        self.summary_panel.grid_columnconfigure((1,3,5,7,9), weight=1)
        # Delay first summary refresh to avoid AttributeError
        self.after(500, self.refresh_summary)
        # --- Trades Panels ---
        bottom_frame = ctk.CTkFrame(self.panel, fg_color="transparent")
        bottom_frame.pack(expand=True, fill="both", pady=(SPACING_MD, SPACING_MD), padx=SPACING_MD)
        self.open_trades_panel = ctk.CTkFrame(bottom_frame, fg_color=TURBO_NAVY, corner_radius=CARD_RADIUS)
        self.closed_trades_panel = ctk.CTkFrame(bottom_frame, fg_color=TURBO_NAVY, corner_radius=CARD_RADIUS)
        self.open_trades_panel.pack(side="left", expand=True, fill="both", padx=(SPACING_MD, SPACING_SM), pady=SPACING_SM)
        self.closed_trades_panel.pack(side="left", expand=True, fill="both", padx=(SPACING_SM, SPACING_MD), pady=SPACING_SM)
        open_label = ctk.CTkLabel(self.open_trades_panel, text="Open Trades", font=FONT_DASHBOARD, text_color=TURBO_CYAN, fg_color="transparent")
        open_label.pack(pady=SPACING_SM, padx=SPACING_MD)
        closed_label = ctk.CTkLabel(self.closed_trades_panel, text="Closed Trades", font=FONT_DASHBOARD, text_color=TURBO_PURPLE, fg_color="transparent")
        closed_label.pack(pady=SPACING_SM, padx=SPACING_MD)
        self.open_scroll = ctk.CTkScrollableFrame(self.open_trades_panel, fg_color=TURBO_DARK_GRAY, corner_radius=CARD_RADIUS)
        self.open_scroll.pack(expand=True, fill="both", padx=SPACING_MD, pady=SPACING_MD, ipadx=SPACING_MD, ipady=SPACING_MD)
        self.closed_scroll = ctk.CTkScrollableFrame(self.closed_trades_panel, fg_color=TURBO_DARK_GRAY, corner_radius=CARD_RADIUS)
        self.closed_scroll.pack(expand=True, fill="both", padx=SPACING_MD, pady=SPACING_MD, ipadx=SPACING_MD, ipady=SPACING_MD)
        self.after(500, self.refresh_trades)

    def set_status(self, status):
        self.status_var.set(f"Status: {status}")

    def update_status(self):
        self.set_status(self.get_status())
        self.after(1000, self.update_status)

    def refresh_summary(self):
        summary = self.get_summary()
        # Set values and colors
        self.summary_labels["Initial Balance"].configure(text=summary["initial_balance"], text_color=TURBO_WHITE)
        self.summary_labels["Current Balance"].configure(text=summary["current_balance"], text_color=TURBO_WHITE)
        pnl_color = TURBO_SUCCESS if summary["pnl_usd"] >= 0 else TURBO_ERROR
        self.summary_labels["Overall PnL"].configure(text=summary["pnl_str"], text_color=pnl_color)
        self.summary_labels["Win Rate"].configure(text=summary["win_rate"], text_color=TURBO_CYAN)
        self.summary_labels["Last Updated"].configure(text=summary["last_updated"], text_color=TURBO_GRAY)
        self.after(2000, self.refresh_summary)

    def refresh_trades(self):
        open_trades, closed_trades = self.get_trades()
        # Clear previous widgets
        for widget in self.open_scroll.winfo_children():
            widget.destroy()
        for widget in self.closed_scroll.winfo_children():
            widget.destroy()
        # Modern card for each open trade
        try:
            if open_trades:
                for trade in open_trades:
                    try:
                        card = ctk.CTkFrame(self.open_scroll, fg_color=TURBO_BLACK, corner_radius=CARD_RADIUS)
                        card.pack(fill="x", pady=SPACING_SM, padx=SPACING_SM, ipadx=SPACING_MD, ipady=SPACING_MD)
                        name = trade.get('name', 'N/A')
                        symbol = trade.get('symbol', 'N/A')
                        buy_price = trade.get('buy_price_usd', 0)
                        cur_price = trade.get('price_usd', 0)
                        amount_usd = trade.get('amount_left_usd', 0)
                        sell_fee = getattr(self.master.session, 'SELL_FEE', 0.005) if hasattr(self.master, 'session') else 0.005
                        if buy_price and cur_price and amount_usd:
                            tokens_amount = amount_usd / buy_price
                            current_value = tokens_amount * cur_price * (1 - sell_fee)
                            pnl_usd = current_value - amount_usd
                            pnl_pct = (pnl_usd / amount_usd * 100) if amount_usd else 0
                        else:
                            pnl_usd = 0
                            pnl_pct = 0
                        status = "HOLDING" if not trade.get('sold') else "SOLD"
                        ctk.CTkLabel(card, text=f"{name} ({symbol})", font=FONT_SUBHEADER, text_color=TURBO_CYAN, anchor="w").pack(anchor="w", padx=SPACING_MD, pady=(SPACING_SM, SPACING_SM))
                        ctk.CTkLabel(card, text=f"Buy: ${buy_price:.6f} | Cur: ${cur_price:.6f}", font=FONT_BODY, text_color=TURBO_WHITE, anchor="w").pack(anchor="w", padx=SPACING_MD)
                        ctk.CTkLabel(card, text=f"PnL: {pnl_usd:+.4f} USD ({pnl_pct:+.2f}%)", font=FONT_STAT, text_color=TURBO_SUCCESS if pnl_usd >= 0 else TURBO_ERROR, anchor="w").pack(anchor="w", padx=SPACING_MD)
                        ctk.CTkLabel(card, text=f"Status: {status}", font=FONT_BODY, text_color=TURBO_GRAY, anchor="w").pack(anchor="w", padx=SPACING_MD, pady=(SPACING_SM, SPACING_SM))
                        # Sell button
                        sell_btn = ctk.CTkButton(card, text="Sell", fg_color=TURBO_ERROR, hover_color=TURBO_PURPLE, text_color=TURBO_WHITE, width=BTN_WIDTH, height=BTN_HEIGHT, corner_radius=BTN_RADIUS, font=FONT_BODY, command=lambda addr=trade.get('address'): self.master.manual_sell(addr))
                        sell_btn.pack(anchor="e", padx=SPACING_MD, pady=(SPACING_SM, SPACING_SM))
                    except Exception as e:
                        print(f"Error displaying open trade: {e}")
                        continue
            else:
                ctk.CTkLabel(self.open_scroll, text="No open trades.", font=FONT_BODY, text_color=TURBO_GRAY).pack(pady=SPACING_MD, padx=SPACING_MD)
        except Exception as e:
            print(f"Error refreshing open trades: {e}")
            ctk.CTkLabel(self.open_scroll, text="Error loading trades. Please refresh.", font=FONT_BODY, text_color=TURBO_ERROR).pack(pady=SPACING_MD, padx=SPACING_MD)
        # Modern card for each closed trade
        if closed_trades:
            for trade in closed_trades:
                card = ctk.CTkFrame(self.closed_scroll, fg_color=TURBO_BLACK, corner_radius=CARD_RADIUS)
                card.pack(fill="x", pady=SPACING_SM, padx=SPACING_SM, ipadx=SPACING_MD, ipady=SPACING_MD)
                name = trade.get('name', 'N/A')
                symbol = trade.get('symbol', 'N/A')
                buy_price = trade.get('buy_price_usd', 0)
                sell_price = trade.get('sell_price_usd', 0)
                amount_usd = trade.get('amount_usd', 0)
                pnl_usd = trade.get('pnl', 0)
                # Correct percent calculation: percent of invested amount
                pnl_pct = (pnl_usd / amount_usd * 100) if amount_usd else 0
                ctk.CTkLabel(card, text=f"{name} ({symbol})", font=FONT_SUBHEADER, text_color=TURBO_PURPLE, anchor="w").pack(anchor="w", padx=SPACING_MD, pady=(SPACING_SM, SPACING_SM))
                ctk.CTkLabel(card, text=f"Buy: ${buy_price:.6f} | Sell: ${sell_price:.6f}", font=FONT_BODY, text_color=TURBO_WHITE, anchor="w").pack(anchor="w", padx=SPACING_MD)
                ctk.CTkLabel(card, text=f"PnL: {pnl_usd:+.4f} USD ({pnl_pct:+.2f}%)", font=FONT_STAT, text_color=TURBO_SUCCESS if pnl_usd >= 0 else TURBO_ERROR, anchor="w").pack(anchor="w", padx=SPACING_MD)
                ctk.CTkLabel(card, text=f"Status: SOLD", font=FONT_BODY, text_color=TURBO_GRAY, anchor="w").pack(anchor="w", padx=SPACING_MD, pady=(SPACING_SM, SPACING_SM))
        else:
            ctk.CTkLabel(self.closed_scroll, text="No closed trades.", font=FONT_BODY, text_color=TURBO_GRAY).pack(pady=SPACING_MD, padx=SPACING_MD)
        # Schedule next refresh
        self.after(2000, self.refresh_trades)

    def handle_manual_sell(self, address):
        self.manual_sell_callback(address)
        self.refresh_trades()

    def update_live_dashboard(self):
        """Update the live dashboard with current stats and logs"""
        try:
            # Update session duration
            duration = beautiful_logger.get_session_duration()
            self.live_stats["⏱️ Session"].configure(text=duration)
            
            # Update other stats from beautiful_logger
            stats = beautiful_logger.stats
            self.live_stats["🔍 Scanned"].configure(text=str(stats['tokens_scanned']))
            self.live_stats["✅ Filtered"].configure(text=str(stats['tokens_filtered']))
            self.live_stats["💸 Trades"].configure(text=str(stats['trades_attempted']))
            self.live_stats["📈 Success"].configure(text=str(stats['trades_successful']))
            self.live_stats["💰 Balance"].configure(text=f"${stats['current_balance']:.2f}")
            
            # Update live logs
            self._update_live_logs()
            
        except Exception as e:
            print(f"Error updating live dashboard: {e}")
        finally:
            # Schedule next update
            self.after(1000, self.update_live_dashboard)
    
    def _update_live_logs(self):
        """Update the live logs display"""
        try:
            # Process new log entries from the queue
            new_logs = []
            while not beautiful_logger.log_queue.empty():
                try:
                    log_entry = beautiful_logger.log_queue.get_nowait()
                    new_logs.append(log_entry)
                except queue.Empty:
                    break
            
            # Add new logs to display
            for log_entry in new_logs:
                self._add_live_log(
                    log_entry['emoji'],
                    log_entry['category'],
                    log_entry['message'],
                    log_entry['color']
                )
        except Exception as e:
            print(f"Error updating live logs: {e}")
    
    def _add_live_log(self, emoji, category, message, color):
        """Add a log entry to the live logs display"""
        try:
            if not hasattr(self, 'live_logs') or not self.live_logs.winfo_exists():
                return
                
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            # Format the log entry
            log_text = f"[{timestamp}] {emoji} {category}: {message}\n"
            
            # Insert at the end
            self.live_logs.insert("end", log_text)
            
            # Apply color tags (configure once)
            if not hasattr(self, '_log_tags_configured'):
                self.live_logs.tag_configure("system", foreground=LOG_SYSTEM)
                self.live_logs.tag_configure("trade", foreground=LOG_TRADE)
                self.live_logs.tag_configure("error", foreground=LOG_ERROR)
                self.live_logs.tag_configure("debug", foreground=LOG_DEBUG)
                self.live_logs.tag_configure("scan", foreground=TURBO_CYAN)
                self.live_logs.tag_configure("filter", foreground=TURBO_SUCCESS)
                self._log_tags_configured = True
            
            # Apply color to the new line
            try:
                line_start = self.live_logs.index("end-2c linestart")
                line_end = self.live_logs.index("end-2c lineend")
                tag_name = category.lower()
                self.live_logs.tag_add(tag_name, line_start, line_end)
            except:
                pass  # Skip coloring if index fails
            
            # Auto-scroll to bottom
            self.live_logs.see("end")
            
            # Limit log entries (keep last 50) - safer method
            content = self.live_logs.get("1.0", "end-1c")
            lines = content.split('\n')
            if len(lines) > 50:
                # Keep only the last 50 lines
                new_content = '\n'.join(lines[-50:])
                self.live_logs.delete("1.0", "end")
                self.live_logs.insert("1.0", new_content)
                # Re-scroll to bottom
                self.live_logs.see("end")
                    
        except Exception as e:
            # Silently fail to avoid log spam
            pass
    
    def _refresh_dashboard(self):
        """Manually refresh the dashboard stats and logs"""
        try:
            # Reset the beautiful logger stats since they were incorrect
            beautiful_logger.stats = {
                'tokens_scanned': 0,
                'tokens_filtered': 0,
                'trades_attempted': 0,
                'trades_successful': 0,
                'current_balance': 0.0,
                'session_pnl': 0.0
            }
            
            # Force update the dashboard immediately
            self.update_live_dashboard()
            
            # Add a refresh log entry
            self._add_live_log("🔄", "SYSTEM", "Dashboard stats reset and refreshed", LOG_SYSTEM)
            
        except Exception as e:
            print(f"Error refreshing dashboard: {e}")
    
    def _demo_logs(self):
        """Demo the beautiful logging system with sample messages"""
        import threading
        
        def demo_sequence():
            import time
            
            # Demo sequence
            beautiful_logger.system("Wallet connected: $50.00 available")
            beautiful_logger.update_stats(current_balance=50.00)
            time.sleep(1)
            
            beautiful_logger.scan("New token detected: 'MoonShot' ($0.00012)")
            beautiful_logger.update_stats(tokens_scanned=1)
            time.sleep(0.5)
            
            beautiful_logger.filter_pass("Liquidity check passed: $15,420")
            beautiful_logger.filter_pass("Volume check passed: $28,340")
            beautiful_logger.update_stats(tokens_filtered=1)
            time.sleep(0.5)
            
            beautiful_logger.trade("Attempting purchase: $5.00 worth")
            beautiful_logger.update_stats(trades_attempted=1)
            time.sleep(1)
            
            beautiful_logger.trade("Purchase successful! Got 41,667 tokens")
            beautiful_logger.update_stats(trades_successful=1, current_balance=45.00)
            time.sleep(1)
            
            beautiful_logger.trade("Price increased! Current value: $6.20 (+24%)")
            time.sleep(0.5)
            
            beautiful_logger.error("Market volatility warning: High slippage detected")
            time.sleep(0.5)
            
            beautiful_logger.debug("Transaction hash: 3mPvXq...7dFg2k")
            time.sleep(1)
            
            beautiful_logger.system("Demo complete! This is how logs will appear during real trading.")
            
        # Run demo in background
        demo_thread = threading.Thread(target=demo_sequence, daemon=True)
        demo_thread.start()

class LogFrame(ctk.CTkFrame):
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.master = master
        self.configure(fg_color=TURBO_BLACK)
        self.panel = ctk.CTkFrame(self, fg_color=TURBO_NAVY, corner_radius=CARD_RADIUS)
        self.panel.pack(expand=True, fill="both", pady=SPACING_LG, padx=SPACING_XL, ipadx=SPACING_MD, ipady=SPACING_MD)
        self.panel.pack_propagate(False)
        # 2x2 grid for logs
        self.sections = [
            ("System Logs", self.filter_system_logs, TURBO_CYAN),
            ("Error Logs", self.filter_error_logs, TURBO_ERROR),
            ("Trade Logs", self.filter_trade_logs, TURBO_PURPLE),
            ("Debug Logs", self.filter_debug_logs, TURBO_GRAY),
        ]
        self.textboxes = []
        for i, (label, _, color) in enumerate(self.sections):
            frame = ctk.CTkFrame(self.panel, fg_color=TURBO_DARK_GRAY, corner_radius=CARD_RADIUS)
            frame.grid(row=i//2, column=i%2, sticky="nsew", padx=SPACING_MD, pady=SPACING_MD)
            ctk.CTkLabel(frame, text=label, font=FONT_SUBHEADER, text_color=color).pack(anchor="w", padx=SPACING_MD, pady=(SPACING_SM, 0))
            textbox = ctk.CTkTextbox(frame, wrap="word", font=("Consolas", 12), fg_color=TURBO_DARK_GRAY, text_color=color, height=10)
            textbox.pack(fill="both", expand=True, padx=SPACING_MD, pady=SPACING_MD, ipadx=SPACING_MD, ipady=SPACING_MD)
            textbox.configure(state="disabled")
            self.textboxes.append(textbox)
            copy_btn = ctk.CTkButton(frame, text="Copy", command=lambda tb=textbox: self.copy_log(tb), fg_color=TURBO_CYAN, text_color=TURBO_BLACK, width=60)
            copy_btn.pack(anchor="e", padx=SPACING_MD, pady=(0, SPACING_SM))
        self.panel.grid_rowconfigure((0,1), weight=1)
        self.panel.grid_columnconfigure((0,1), weight=1)
        self._queue = deque()
        self.after(200, self._flush)

    def filter_system_logs(self, lines):
        return [l for l in lines if ("INFO" in l or "Started" in l or "Stopped" in l or (not any(x in l for x in ["ERROR","FAIL","EXCEPTION","DEBUG","BUY","SELL","TRADE","PnL"])))]
    def filter_error_logs(self, lines):
        return [l for l in lines if any(x in l for x in ["ERROR","FAIL","EXCEPTION","Traceback"])]
    def filter_trade_logs(self, lines):
        return [l for l in lines if any(x in l for x in ["BUY","SELL","TRADE","PnL","Manual buy","Manual sell"])]
    def filter_debug_logs(self, lines):
        return [l for l in lines if "DEBUG" in l]

    def append_log(self, line):
        self._queue.append(line)

    def _flush(self):
        if self._queue:
            self.master.log_lines.extend(self._queue)
            self._queue.clear()
        # Update all textboxes
        lines = self.master.log_lines[-MAX_LOG_LINES:] if hasattr(self.master, 'log_lines') else []
        for i, (_, filter_fn, color) in enumerate(self.sections):
            tb = self.textboxes[i]
            tb.configure(state="normal")
            tb.delete("1.0", "end")
            filtered = filter_fn(lines)
            for l in filtered:
                tb.insert("end", l + "\n")
            tb.see("end")
            tb.configure(state="disabled")
        self.after(200, self._flush)

    def copy_log(self, textbox):
        self.clipboard_clear()
        self.clipboard_append(textbox.get("1.0", "end").strip())

    def clear_log(self):
        self.master.log_lines.clear()
        for tb in self.textboxes:
            tb.configure(state="normal")
            tb.delete("1.0", "end")
            tb.configure(state="disabled")

class PlaceholderFrame(ctk.CTkFrame):
    def __init__(self, master, text, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.configure(fg_color=TURBO_BLACK)
        label = ctk.CTkLabel(self, text=text, **label_kwargs)
        label.pack(expand=True)

class CollapsibleSection(ctk.CTkFrame):
    def __init__(self, master, title, fg_color, text_color, corner_radius, *args, **kwargs):
        super().__init__(master, fg_color=fg_color, corner_radius=corner_radius, *args, **kwargs)
        self._expanded = True
        self.header = ctk.CTkFrame(self, fg_color=fg_color)
        self.header.pack(fill="x")
        self.title_label = ctk.CTkLabel(self.header, text=title, text_color=text_color, font=FONT_SUBHEADER)
        self.title_label.pack(side="left", padx=SPACING_MD, pady=SPACING_SM)
        self.toggle_btn = ctk.CTkButton(self.header, text="-", width=28, fg_color=fg_color, text_color=text_color, command=self.toggle, corner_radius=BTN_RADIUS)
        self.toggle_btn.pack(side="right", padx=SPACING_MD)
        self.content = ctk.CTkFrame(self, fg_color=fg_color)
        self.content.pack(fill="x", expand=True)
    def toggle(self):
        if self._expanded:
            self.content.pack_forget()
            self.toggle_btn.configure(text="+")
        else:
            self.content.pack(fill="x", expand=True)
            self.toggle_btn.configure(text="-")
        self._expanded = not self._expanded

class SettingsFrame(ctk.CTkFrame):
    def __init__(self, master, get_bot_status, on_settings_apply, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.configure(fg_color=TURBO_BLACK)
        self.get_bot_status = get_bot_status
        self.on_settings_apply = on_settings_apply
        self._current_mode = None  # Track current mode for efficient repacking

        # Tooltips dictionary (already optimized in previous step)
        self.tooltips = {
            "Mode": "Choose between simulation mode (paper trading) or real wallet mode (live trading)",
            "Take Profit (%)": "The percentage gain at which to automatically sell a token",
            "Stop Loss (%)": "The percentage loss at which to automatically sell a token to prevent further losses",
            "Min Liquidity (USD)": "Minimum liquidity in USD required for a token to be considered for trading",
            "Min 5m Volume (USD)": "Minimum trading volume in the last 5 minutes required for a token",
            "Max Price (USD)": "Maximum token price in USD allowed for trading",
            "Min Pair Age (s)": "Minimum age of the trading pair in seconds before it can be traded",
            "Max Pair Age (s)": "Maximum age of the trading pair in seconds that will be considered",
            "Min Buys 5m": "Minimum number of buy transactions in the last 5 minutes",
            "Min Trx Ratio": "Minimum ratio of buy to sell transactions required",
            "Duration (min)": "How many minutes to hold a position before considering selling",
            "Position Size (USD)": "Amount in USD to use for each trade.",
            "Min Percent Burned": "Minimum percentage of total supply that must be burned",
            "Require Immutable": "Only trade tokens with locked/renounced ownership",
            "Max Percent Top Holders": "Maximum percentage of supply held by top wallets",
            "Block Risky Wallets": "Avoid trading tokens with suspicious wallet patterns",
            "Wallet Type": "Choose the type of wallet credential to use for trading.",
            "Private Key": "Your wallet's private key for executing trades",
            "Seed Phrase": "Your wallet's seed phrase/mnemonic for executing trades",
        }

        # Main container
        self.main_container = ctk.CTkFrame(self, fg_color=TURBO_BLACK)
        self.main_container.pack(expand=True, fill="both", padx=SPACING_MD, pady=SPACING_MD)

        # --- Mode Selection ---
        mode_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        mode_frame.pack(fill="x", pady=(0, SPACING_MD))
        mode_label = ctk.CTkLabel(mode_frame, text="Mode:", font=FONT_SUBHEADER, text_color=TURBO_CYAN)
        mode_label.pack(side="left", padx=SPACING_MD)
        self.mode_var = ctk.StringVar(value="Simulation")
        self.mode_dropdown = ctk.CTkOptionMenu(
            mode_frame,
            variable=self.mode_var,
            values=["Simulation", "Real Wallet"],
            fg_color=TURBO_NAVY,
            button_color=TURBO_CYAN,
            text_color=TURBO_WHITE,
            dropdown_fg_color=TURBO_DARK_GRAY,
            dropdown_text_color=TURBO_WHITE,
            font=FONT_HEADER,
            width=220,
            height=40,
            command=self.on_mode_change
        )
        self.mode_dropdown.pack(side="left", padx=SPACING_MD)
        self._add_tooltip(self.mode_dropdown, self.tooltips["Mode"])

        # --- SCROLLABLE FRAME for settings ---
        self.scrollable = ctk.CTkScrollableFrame(
            self.main_container, 
            corner_radius=CARD_RADIUS,
            fg_color=TURBO_DARK_GRAY,
            height=500
        )
        self.scrollable.pack(expand=True, fill="both")

        # --- Collapsible: Wallet Settings ---
        self.wallet_section = CollapsibleSection(self.scrollable, "Wallet Settings", TURBO_NAVY, TURBO_CYAN, CARD_RADIUS)
        wallet_content = ctk.CTkFrame(self.wallet_section.content, fg_color="transparent")
        wallet_content.pack(fill="x", padx=SPACING_MD, pady=SPACING_SM)
        self.wallet_type_var = ctk.StringVar(value="private_key")
        wallet_type_label = ctk.CTkLabel(wallet_content, text="Wallet Type", text_color=TURBO_WHITE)
        wallet_type_label.pack(anchor="w")
        self._add_tooltip(wallet_type_label, self.tooltips["Wallet Type"])
        wallet_type_frame = ctk.CTkFrame(wallet_content, fg_color="transparent")
        wallet_type_frame.pack(fill="x")
        rb1 = ctk.CTkRadioButton(wallet_type_frame, text="Private Key", variable=self.wallet_type_var, value="private_key")
        rb1.pack(side="left", padx=SPACING_SM)
        self._add_tooltip(rb1, self.tooltips["Private Key"])
        rb2 = ctk.CTkRadioButton(wallet_type_frame, text="Seed Phrase", variable=self.wallet_type_var, value="seed_phrase")
        rb2.pack(side="left", padx=SPACING_SM)
        self._add_tooltip(rb2, self.tooltips["Seed Phrase"])
        self.wallet_secret_var = ctk.StringVar()
        wallet_secret_label = ctk.CTkLabel(wallet_content, text="Private Key / Seed Phrase", text_color=TURBO_WHITE)
        wallet_secret_label.pack(anchor="w", pady=(SPACING_SM, 0))
        self._add_tooltip(wallet_secret_label, self.tooltips["Private Key"])
        wallet_secret_entry = ctk.CTkEntry(wallet_content, textvariable=self.wallet_secret_var, width=300, show="*", corner_radius=INPUT_RADIUS, fg_color=TURBO_DARK_GRAY, text_color=TURBO_WHITE)
        wallet_secret_entry.pack(anchor="w", pady=SPACING_SM)
        self._add_tooltip(wallet_secret_entry, self.tooltips["Private Key"])

        # --- Collapsible: Trading Settings ---
        self.trading_section = CollapsibleSection(self.scrollable, "Trading Settings", TURBO_NAVY, TURBO_CYAN, CARD_RADIUS)
        trading_content = ctk.CTkFrame(self.trading_section.content, fg_color="transparent")
        trading_content.pack(fill="x", padx=SPACING_MD, pady=SPACING_SM)
        self.take_profit_var = ctk.DoubleVar(value=2.0)
        tp_label = ctk.CTkLabel(trading_content, text="Take Profit (%)", text_color=TURBO_WHITE)
        tp_label.pack(anchor="w")
        self._add_tooltip(tp_label, self.tooltips["Take Profit (%)"])
        tp_frame = ctk.CTkFrame(trading_content, fg_color="transparent")
        tp_frame.pack(fill="x")
        self.tp_slider = ctk.CTkSlider(tp_frame, from_=0, to=1000, variable=self.take_profit_var, fg_color=TURBO_CYAN, button_color=TURBO_PURPLE, button_hover_color=TURBO_CYAN)
        self.tp_slider.pack(side="left", fill="x", expand=True)
        self._add_tooltip(self.tp_slider, self.tooltips["Take Profit (%)"])
        tp_value_label = ctk.CTkLabel(tp_frame, textvariable=self.take_profit_var, text_color=TURBO_CYAN)
        tp_value_label.pack(side="left", padx=SPACING_SM)
        self._add_tooltip(tp_value_label, self.tooltips["Take Profit (%)"])
        self.stop_loss_var = ctk.DoubleVar(value=30.0)
        sl_label = ctk.CTkLabel(trading_content, text="Stop Loss (%)", text_color=TURBO_WHITE)
        sl_label.pack(anchor="w", pady=(SPACING_SM, 0))
        self._add_tooltip(sl_label, self.tooltips["Stop Loss (%)"])
        sl_frame = ctk.CTkFrame(trading_content, fg_color="transparent")
        sl_frame.pack(fill="x")
        self.sl_slider = ctk.CTkSlider(sl_frame, from_=0, to=100, variable=self.stop_loss_var, fg_color=TURBO_CYAN, button_color=TURBO_PURPLE, button_hover_color=TURBO_CYAN)
        self.sl_slider.pack(side="left", fill="x", expand=True)
        self._add_tooltip(self.sl_slider, self.tooltips["Stop Loss (%)"])
        sl_value_label = ctk.CTkLabel(sl_frame, textvariable=self.stop_loss_var, text_color=TURBO_CYAN)
        sl_value_label.pack(side="left", padx=SPACING_SM)
        self._add_tooltip(sl_value_label, self.tooltips["Stop Loss (%)"])
        fields_frame = ctk.CTkFrame(trading_content, fg_color="transparent")
        fields_frame.pack(fill="x", pady=SPACING_SM)
        self.min_liquidity_var = ctk.DoubleVar(value=1000.0)
        self.min_5m_volume_usd_var = ctk.DoubleVar(value=5000.0)
        self.max_price_var = ctk.DoubleVar(value=0.01)
        self.min_pair_age_var = ctk.DoubleVar(value=600.0)
        self.max_pair_age_var = ctk.DoubleVar(value=86400.0)
        self.min_buys_5m_var = ctk.IntVar(value=10)
        self.min_trx_ratio_var = ctk.DoubleVar(value=1.5)
        self.duration_var = ctk.IntVar(value=120)  # Default 120 minutes (2 hours)
        self.position_size_var = ctk.DoubleVar(value=20.0)
        self.trading_vars = {
            "Min Liquidity (USD)": self.min_liquidity_var,
            "Min 5m Volume (USD)": self.min_5m_volume_usd_var,
            "Max Price (USD)": self.max_price_var,
            "Min Pair Age (s)": self.min_pair_age_var,
            "Max Pair Age (s)": self.max_pair_age_var,
            "Min Buys 5m": self.min_buys_5m_var,
            "Min Trx Ratio": self.min_trx_ratio_var,
            "Duration (min)": self.duration_var,
            "Position Size (USD)": self.position_size_var,
        }
        for i, (label, var) in enumerate(self.trading_vars.items()):
            row = i // 2
            col = i % 2
            frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
            frame.grid(row=row, column=col, padx=SPACING_SM, pady=SPACING_SM, sticky="ew")
            frame.grid_columnconfigure(1, weight=1)
            field_label = ctk.CTkLabel(frame, text=label, text_color=TURBO_WHITE)
            field_label.grid(row=0, column=0, sticky="w")
            self._add_tooltip(field_label, self.tooltips[label])
            entry = ctk.CTkEntry(frame, textvariable=var, width=100, corner_radius=INPUT_RADIUS,
                        fg_color=TURBO_DARK_GRAY, text_color=TURBO_WHITE)
            entry.grid(row=0, column=1, sticky="e")
            self._add_tooltip(entry, self.tooltips[label])
        fields_frame.grid_columnconfigure((0, 1), weight=1)

        # --- Collapsible: Risk Management ---
        self.risk_section = CollapsibleSection(self.scrollable, "Risk Management", TURBO_NAVY, TURBO_CYAN, CARD_RADIUS)
        risk_content = ctk.CTkFrame(self.risk_section.content, fg_color="transparent")
        risk_content.pack(fill="x", padx=SPACING_MD, pady=SPACING_SM)
        self.min_percent_burned_var = ctk.DoubleVar(value=10.0)
        self.require_immutable_var = ctk.BooleanVar(value=False)
        self.max_percent_top_holders_var = ctk.DoubleVar(value=0.0)
        self.block_risky_wallets_var = ctk.BooleanVar(value=False)
        self.risk_vars = {
            "Min Percent Burned": (self.min_percent_burned_var, "entry"),
            "Require Immutable": (self.require_immutable_var, "toggle"),
            "Max Percent Top Holders": (self.max_percent_top_holders_var, "entry"),
            "Block Risky Wallets": (self.block_risky_wallets_var, "toggle"),
        }
        for label, (var, widget_type) in self.risk_vars.items():
            frame = ctk.CTkFrame(risk_content, fg_color="transparent")
            frame.pack(fill="x", pady=SPACING_SM)
            field_label = ctk.CTkLabel(frame, text=label, text_color=TURBO_WHITE)
            field_label.pack(side="left", padx=SPACING_MD)
            self._add_tooltip(field_label, self.tooltips[label])
            if widget_type == "entry":
                entry = ctk.CTkEntry(frame, textvariable=var, width=100, corner_radius=INPUT_RADIUS,
                            fg_color=TURBO_DARK_GRAY, text_color=TURBO_WHITE)
                entry.pack(side="right", padx=SPACING_MD)
                self._add_tooltip(entry, self.tooltips[label])
            else:
                toggle = ctk.CTkSwitch(frame, variable=var, text="")
                toggle.pack(side="right", padx=SPACING_MD)
                self._add_tooltip(toggle, self.tooltips[label])

        save_btn = ctk.CTkButton(
            self.main_container,
            text="Save Changes",
            fg_color=TURBO_CYAN,
            text_color=TURBO_BLACK,
            corner_radius=BTN_RADIUS,
            font=FONT_BODY,
            command=self.save_settings
        )
        save_btn.pack(pady=SPACING_MD)

        # Initial setup
        self.on_mode_change()
        self.load_settings()

    def on_mode_change(self, *args):
        # Only repack if mode actually changes
        mode = self.mode_var.get()
        if mode == self._current_mode:
            return
        self._current_mode = mode
        self.wallet_section.pack_forget()
        self.trading_section.pack_forget()
        self.risk_section.pack_forget()
        if mode == "Real Wallet":
            self.wallet_section.pack(fill="x", padx=SPACING_MD, pady=SPACING_SM)
        self.trading_section.pack(fill="x", pady=SPACING_SM, padx=SPACING_MD)
        self.risk_section.pack(fill="x", pady=SPACING_SM, padx=SPACING_MD)

    def save_settings(self):
        settings = {
            "mode": self.mode_var.get(),  # Store as 'Simulation' or 'Real Wallet'
            "wallet_type": self.wallet_type_var.get() if self.mode_var.get() == "Real Wallet" else None,
            "wallet_secret": self.wallet_secret_var.get() if self.mode_var.get() == "Real Wallet" else None,
            "take_profit": self.take_profit_var.get(),
            "stop_loss": self.stop_loss_var.get(),
            **{(
                "min_volume_5m_usd" if key == "Min 5m Volume (USD)" else
                "min_buy_tx_ratio" if key == "Min Trx Ratio" else
                key.lower().replace(" ", "_").replace("(", "").replace(")", "")
            ): var.get() for key, var in self.trading_vars.items()},
            **{key.lower().replace(" ", "_"): var.get() for key, (var, _) in self.risk_vars.items()},
            "position_size": self.position_size_var.get(),
        }
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
        self.on_settings_apply(settings)

    def get_settings(self):
        """Get current settings from GUI fields (not from saved file)"""
        settings = {
            "mode": self.mode_var.get(),
            "wallet_type": self.wallet_type_var.get() if self.mode_var.get() == "Real Wallet" else None,
            "wallet_secret": self.wallet_secret_var.get() if self.mode_var.get() == "Real Wallet" else None,
            "take_profit": self.take_profit_var.get(),
            "stop_loss": self.stop_loss_var.get(),
            **{(
                "min_liquidity" if key == "Min Liquidity (USD)" else
                "min_volume_5m_usd" if key == "Min 5m Volume (USD)" else
                "min_buy_tx_ratio" if key == "Min Trx Ratio" else
                key.lower().replace(" ", "_").replace("(", "").replace(")", "")
            ): var.get() for key, var in self.trading_vars.items()},
            **{key.lower().replace(" ", "_"): var.get() for key, (var, _) in self.risk_vars.items()},
            "position_size": self.position_size_var.get(),
        }
        # Debug: Print the current GUI values
        debug_msg1 = f"[DEBUG get_settings] min_liquidity_var.get() = {self.min_liquidity_var.get()}"
        debug_msg2 = f"[DEBUG get_settings] min_trx_ratio_var.get() = {self.min_trx_ratio_var.get()}"
        debug_msg3 = f"[DEBUG get_settings] Final settings dict: min_liquidity = {settings.get('min_liquidity')}, min_buy_tx_ratio = {settings.get('min_buy_tx_ratio')}"
        print(debug_msg1)
        print(debug_msg2)
        print(debug_msg3)
        # Debug the key mapping
        for key, var in self.trading_vars.items():
            mapped_key = (
                "min_liquidity" if key == "Min Liquidity (USD)" else
                "min_volume_5m_usd" if key == "Min 5m Volume (USD)" else
                "min_buy_tx_ratio" if key == "Min Trx Ratio" else
                key.lower().replace(" ", "_").replace("(", "").replace(")", "")
            )
            print(f"[DEBUG] Key '{key}' -> '{mapped_key}' = {var.get()}")
        return settings

    def load_settings(self):
        if not os.path.exists(SETTINGS_FILE):
            return
        try:
            with open(SETTINGS_FILE, "r") as f:
                settings = json.load(f)
            # Always set dropdown to 'Simulation' or 'Real Wallet'
            mode_val = settings.get("mode", "Simulation")
            if mode_val.lower() == "real":
                self.mode_var.set("Real Wallet")
            else:
                self.mode_var.set("Simulation")
            self.wallet_type_var.set(settings.get("wallet_type", "private_key"))
            self.wallet_secret_var.set(settings.get("wallet_secret", ""))
            self.take_profit_var.set(settings.get("take_profit", 2.0))
            self.stop_loss_var.set(settings.get("stop_loss", 30.0))
            for key, var in self.trading_vars.items():
                setting_key = (
                    "min_liquidity" if key == "Min Liquidity (USD)" else
                    "min_volume_5m_usd" if key == "Min 5m Volume (USD)" else
                    "min_buy_tx_ratio" if key == "Min Trx Ratio" else
                    key.lower().replace(" ", "_").replace("(", "").replace(")", "")
                )
                if setting_key in settings:
                    var.set(settings[setting_key])
            for key, (var, _) in self.risk_vars.items():
                setting_key = key.lower().replace(" ", "_")
                if setting_key in settings:
                    var.set(settings[setting_key])
            self.position_size_var.set(settings.get("position_size", 20.0))
            self.duration_var.set(settings.get("duration", 120))  # Load as minutes, default 120
        except Exception as e:
            print(f"Error loading settings: {e}")

    def _add_tooltip(self, widget, text):
        """Helper method to add a tooltip to a widget"""
        widget.bind("<Enter>", lambda e: self._show_tooltip(e, text))
        widget.bind("<Leave>", self._hide_tooltip)
        widget.bind("<Motion>", self._update_tooltip)
        
    def _show_tooltip(self, event, text):
        """Show tooltip window"""
        try:
            x, y, _, _ = event.widget.bbox("insert")
        except Exception:
            x, y = 0, 0
        x += event.widget.winfo_rootx() + 25
        y += event.widget.winfo_rooty() + 25
        # Create tooltip window
        self.tooltip_window = tk.Toplevel(self)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        # Create tooltip label with modern styling
        label = tk.Label(
            self.tooltip_window,
            text=text,
            justify='left',
            background=TURBO_NAVY,
            foreground=TURBO_WHITE,
            relief='solid',
            borderwidth=1,
            font=("Montserrat", 10),
            padx=10,
            pady=5
        )
        label.pack()
        
    def _hide_tooltip(self, event=None):
        """Hide tooltip window"""
        if hasattr(self, 'tooltip_window') and self.tooltip_window is not None:
            self.tooltip_window.destroy()
        self.tooltip_window = None
            
    def _update_tooltip(self, event):
        """Update tooltip position if it exists"""
        if hasattr(self, 'tooltip_window') and self.tooltip_window:
            x = event.widget.winfo_rootx() + event.x + 25
            y = event.widget.winfo_rooty() + event.y + 25
            self.tooltip_window.wm_geometry(f"+{x}+{y}")

class LicenseFrame(ctk.CTkFrame):
    def __init__(self, master, get_license_status, on_activate, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.configure(fg_color=TURBO_BLACK)
        self.master = master
        self.panel = ctk.CTkFrame(self, fg_color=TURBO_NAVY, corner_radius=CARD_RADIUS)
        self.panel.pack(expand=True, fill="both", pady=SPACING_LG, padx=SPACING_XL, ipadx=SPACING_MD, ipady=SPACING_MD)
        self.panel.pack_propagate(False)
        
        # Title
        title_label = ctk.CTkLabel(self.panel, text="License Activation", font=FONT_DASHBOARD, text_color=TURBO_CYAN)
        title_label.pack(pady=(SPACING_MD, SPACING_LG), padx=SPACING_MD)
        
        # Instructions
        instructions = ctk.CTkLabel(
            self.panel, 
            text="Enter your license key to activate Turbo on this device.\nEach license can only be used on one device.",
            font=FONT_BODY,
            text_color=TURBO_WHITE,
            justify="center"
        )
        instructions.pack(pady=(0, SPACING_LG), padx=SPACING_MD)
        
        # License key entry
        entry_label = ctk.CTkLabel(self.panel, text="License Key:", **label_kwargs)
        entry_label.pack(pady=(SPACING_MD, SPACING_SM), padx=SPACING_MD, anchor="w")
        
        self.entry = ctk.CTkEntry(self.panel, width=400, height=40, **entry_kwargs, corner_radius=INPUT_RADIUS)
        self.entry.pack(pady=SPACING_SM, padx=SPACING_MD)
        
        # Bind key entry changes to update status
        self.entry.bind("<KeyRelease>", lambda e: self.after(100, self._on_key_change))
        
        # Buttons frame
        btn_frame = ctk.CTkFrame(self.panel, fg_color="transparent")
        btn_frame.pack(pady=SPACING_MD, padx=SPACING_MD)
        
        self.activate_btn = ctk.CTkButton(
            btn_frame, 
            text="Activate License", 
            width=140,
            height=40,
            **button_kwargs, 
            command=self._activate
        )
        self.activate_btn.pack(side="left", padx=(0, SPACING_SM))
        
        # Deactivate button (for support purposes)
        self.deactivate_btn = ctk.CTkButton(
            btn_frame,
            text="Deactivate",
            width=100,
            height=40,
            fg_color=TURBO_ERROR,
            hover_color=TURBO_PURPLE,
            text_color=TURBO_WHITE,
            corner_radius=10,
            font=("Montserrat", 13, "bold"),
            command=self._deactivate
        )
        self.deactivate_btn.pack(side="left", padx=SPACING_SM)
        
        # Status label
        self.status_label = ctk.CTkLabel(
            self.panel, 
            text="", 
            font=FONT_SUBHEADER, 
            fg_color="transparent",
            wraplength=400,
            justify="center"
        )
        self.status_label.pack(pady=SPACING_MD, padx=SPACING_MD)
        
        # Machine ID display (for support)
        machine_id = getattr(master, 'machine_id', None) or get_machine_id()
        machine_id_label = ctk.CTkLabel(
            self.panel,
            text=f"Device ID: {machine_id[:16]}...",
            font=("Consolas", 10),
            text_color=TURBO_GRAY
        )
        machine_id_label.pack(pady=(SPACING_LG, SPACING_SM), padx=SPACING_MD)
        
        support_label = ctk.CTkLabel(
            self.panel,
            text="Need help? Contact support with your Device ID",
            font=FONT_BODY,
            text_color=TURBO_GRAY
        )
        support_label.pack(pady=(0, SPACING_MD), padx=SPACING_MD)
        
        self.get_license_status = get_license_status
        self.on_activate = on_activate
        
        # Show status on startup
        self.refresh_status()
        
        # If a license key is present, fill it in the entry
        key = master.license_key if hasattr(master, 'license_key') else ""
        if key:
            self.entry.delete(0, "end")
            self.entry.insert(0, key)
        
        # Update UI based on license status
        self.update_ui_state()

    def _on_key_change(self):
        """Handle when user types in the license key field"""
        # Clear any previous license status message when user starts typing
        entry_key = self.entry.get().strip()
        stored_key = getattr(self.master, 'license_key', "")
        
        # If the user is typing a different key than what's stored, clear status
        if entry_key != stored_key and hasattr(self.master, 'license_status_msg'):
            self.master.license_status_msg = ""
        
        # Refresh status to show appropriate message
        self.refresh_status()

    def _activate(self):
        key = self.entry.get().strip()
        if not key:
            self.status_label.configure(text="Please enter a license key.", text_color=TURBO_ERROR)
            return
            
        # Disable button and show activating status
        self.activate_btn.configure(state="disabled", text="Activating...")
        self.status_label.configure(text="Activating license...", text_color=TURBO_CYAN)
        self.update()
        
        # Clear any previous status message
        if hasattr(self.master, 'license_status_msg'):
            self.master.license_status_msg = ""
        
        # Activate license
        self.on_activate(key)
        
        # Refresh status and UI to show result
        self.refresh_status()
        self.update_ui_state()
        
        # Re-enable button only if not successfully activated
        if not getattr(self.master, 'license_verified', False):
            self.activate_btn.configure(state="normal", text="Activate License")
    
    def _deactivate(self):
        """Deactivate license for support purposes"""
        if hasattr(self.master, 'deactivate_license'):
            # Confirm deactivation
            import tkinter.messagebox as msgbox
            if msgbox.askyesno(
                "Deactivate License", 
                "Are you sure you want to deactivate this license?\nThis will remove the license from this device and you'll need to reactivate it."
            ):
                success, msg = self.master.deactivate_license()
                if success:
                    self.status_label.configure(text=msg, text_color=TURBO_SUCCESS)
                    self.entry.delete(0, "end")
                else:
                    self.status_label.configure(text=msg, text_color=TURBO_ERROR)
                self.update_ui_state()

    def refresh_status(self):
        # Check if there's a recent activation attempt with a status message
        license_status_msg = getattr(self.master, 'license_status_msg', "")
        license_verified = getattr(self.master, 'license_verified', False)
        
        if license_status_msg:
            # Show the actual license status message from activation attempt
            color = TURBO_SUCCESS if license_verified else TURBO_ERROR
            self.status_label.configure(text=license_status_msg, text_color=color)
            return
        
        # Check if there's a key in the entry field but not yet activated
        entry_key = self.entry.get().strip() if hasattr(self, 'entry') else ""
        stored_key = getattr(self.master, 'license_key', "")
        
        if entry_key and not stored_key:
            # Key entered but not activated yet
            self.status_label.configure(text="Click 'Activate License' to verify your key.", text_color=TURBO_CYAN)
        elif entry_key and stored_key and entry_key != stored_key:
            # Different key entered than what's stored
            self.status_label.configure(text="Click 'Activate License' to verify your new key.", text_color=TURBO_CYAN)
        else:
            # Use normal license status checking
            status, msg = self.get_license_status()
            color = TURBO_SUCCESS if status else TURBO_ERROR
            self.status_label.configure(text=msg, text_color=color)
    
    def update_ui_state(self):
        """Update UI elements based on license verification status"""
        if getattr(self.master, 'license_verified', False):
            self.entry.configure(state="disabled")
            self.activate_btn.configure(state="disabled", text="Licensed")
            self.deactivate_btn.configure(state="normal")
        else:
            self.entry.configure(state="normal")
            self.activate_btn.configure(state="normal", text="Activate License")
            self.deactivate_btn.configure(state="disabled")

class AboutFrame(ctk.CTkFrame):
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.configure(fg_color=TURBO_BLACK)
        self.panel = ctk.CTkFrame(self, fg_color=TURBO_NAVY, corner_radius=CARD_RADIUS)
        self.panel.pack(expand=True, fill="both", pady=SPACING_LG, padx=SPACING_XL, ipadx=SPACING_MD, ipady=SPACING_MD)
        self.panel.pack_propagate(False)
        try:
            from PIL import Image
            logo_path = resource_path("logo.png")
            if os.path.exists(logo_path):
                img = Image.open(logo_path).convert("RGBA").resize((80, 80))
                self.logo_img = ctk.CTkImage(light_image=img, dark_image=img, size=(80, 80))
                ctk.CTkLabel(self.panel, image=self.logo_img, text="", fg_color="transparent").pack(pady=(SPACING_MD, SPACING_SM), padx=SPACING_MD)
            else:
                ctk.CTkLabel(self.panel, text="[Turbo Logo]", **label_kwargs).pack(pady=(SPACING_MD, SPACING_SM), padx=SPACING_MD)
        except Exception as e:
            print("AboutFrame logo load error:", e)
            ctk.CTkLabel(self.panel, text="[Turbo Logo]", **label_kwargs).pack(pady=(SPACING_MD, SPACING_SM), padx=SPACING_MD)
        ctk.CTkLabel(self.panel, text=APP_NAME, **label_kwargs).pack(pady=(SPACING_SM, SPACING_SM), padx=SPACING_MD)
        ctk.CTkLabel(self.panel, text=f"Version {APP_VERSION}", **label_kwargs).pack(pady=(SPACING_SM, SPACING_MD), padx=SPACING_MD)
        ctk.CTkLabel(self.panel, text=f"by {COMPANY}", **label_kwargs).pack(pady=(SPACING_SM, SPACING_MD), padx=SPACING_MD)
        ctk.CTkLabel(self.panel, text=f"Contact: {SUPPORT_EMAIL}", **label_kwargs).pack(pady=(SPACING_SM, SPACING_MD), padx=SPACING_MD)
        label_kwargs_blue = label_kwargs.copy()
        label_kwargs_blue["text_color"] = TURBO_CYAN
        ctk.CTkLabel(self.panel, text=f"Website: {WEBSITE}", **label_kwargs_blue).pack(pady=(SPACING_SM, SPACING_MD), padx=SPACING_MD)
        ctk.CTkLabel(self.panel, text=f"Telegram: {TELEGRAM}", **label_kwargs).pack(pady=(SPACING_SM, SPACING_MD), padx=SPACING_MD)
        ctk.CTkLabel(self.panel, text="\u00A9 2024 Turbo. All rights reserved.", **label_kwargs).pack(pady=(SPACING_MD, SPACING_SM), padx=SPACING_MD)
        # Add Check for Updates button
        ctk.CTkButton(self.panel, text="Check for Updates", command=lambda: check_for_update(APP_VERSION), corner_radius=BTN_RADIUS, font=FONT_BODY, fg_color=TURBO_CYAN, text_color=TURBO_BLACK).pack(pady=(SPACING_MD, SPACING_SM), padx=SPACING_MD)

class ManualBuyFrame(ctk.CTkFrame):
    def __init__(self, master, fetch_token_info_callback, manual_buy_callback, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.configure(fg_color=TURBO_BLACK)
        self.fetch_token_info_callback = fetch_token_info_callback
        self.manual_buy_callback = manual_buy_callback
        self.address_var = ctk.StringVar()
        ctk.CTkLabel(self, text="Paste Token Address:").pack(pady=SPACING_SM, padx=SPACING_MD)
        ctk.CTkEntry(self, textvariable=self.address_var, width=400, corner_radius=INPUT_RADIUS).pack(pady=SPACING_SM, padx=SPACING_MD)
        ctk.CTkButton(self, text="Fetch Info", command=self.fetch_info, corner_radius=BTN_RADIUS, font=FONT_BODY).pack(pady=SPACING_SM, padx=SPACING_MD)
        self.info_label = ctk.CTkLabel(self, text="Token info will appear here.", font=FONT_BODY, text_color=TURBO_WHITE)
        self.info_label.pack(pady=SPACING_SM, padx=SPACING_MD)
        self.buy_button = ctk.CTkButton(self, text="Buy", command=self.buy_token, corner_radius=BTN_RADIUS, font=FONT_BODY)
        self.buy_button.pack(pady=SPACING_SM, padx=SPACING_MD)
        self.warning_label = ctk.CTkLabel(self, text="Warning: Manual buy ignores all filters and settings. Proceed with caution!", text_color="orange", font=FONT_BODY)
        self.warning_label.pack(pady=SPACING_SM, padx=SPACING_MD)
        self.log_label = ctk.CTkLabel(self, text="", wraplength=500, font=FONT_BODY, text_color=TURBO_WHITE)
        self.log_label.pack(pady=SPACING_SM, padx=SPACING_MD)
        self.retry_button = ctk.CTkButton(self, text="Retry Buy", command=self.buy_token, corner_radius=BTN_RADIUS, font=FONT_BODY)
        self.retry_button.pack(pady=SPACING_SM, padx=SPACING_MD)
        self.retry_button.pack_forget()  # Hide by default
        self.token_info = None
    def fetch_info(self):
        if not getattr(self.master, 'session', None):
            self.info_label.configure(text="Start the bot to use Manual Buy.")
            self.log_label.configure(text="")
            return
        address = self.address_var.get().strip()
        info = self.fetch_token_info_callback(address)
        if info:
            name = info.get('name') or \
                   (info.get('baseToken', {}).get('name') if 'baseToken' in info else None) or \
                   (info.get('token', {}).get('name') if 'token' in info else None) or \
                   info.get('description') or 'N/A'
            symbol = info.get('symbol') or \
                     (info.get('baseToken', {}).get('symbol') if 'baseToken' in info else None) or \
                     (info.get('token', {}).get('symbol') if 'token' in info else None) or 'N/A'
            price = info.get('priceUsd')
            if price is None:
                price = info.get('price_usd')
            if price is not None:
                info['price_usd'] = price
                info['priceUsd'] = price
            # Ensure name and symbol are set at the top level for backend compatibility
            info['name'] = name
            info['symbol'] = symbol
            # Ensure address is set at the top level for backend compatibility
            address = (
                info.get('mint') or
                (info.get('baseToken', {}).get('address') if 'baseToken' in info else None) or
                info.get('tokenAddress') or
                info.get('address') or
                info.get('pairAddress')
            )
            info['address'] = address
            info['mint'] = address  # Explicitly set mint so backend uses correct token address
            marketcap = info.get('marketCap', 'N/A')
            volume = None
            if 'volume' in info and isinstance(info['volume'], dict):
                volume = info['volume'].get('m5')
            if volume is None:
                volume = info.get('volume_m5', 'N/A')
            liquidity = None
            if 'liquidity' in info and isinstance(info['liquidity'], dict):
                liquidity = info['liquidity'].get('usd')
            if liquidity is None:
                liquidity = info.get('liquidity_usd', 'N/A')
            price_str = f"${price}" if price not in (None, 'N/A') else "N/A"
            marketcap_str = f"${marketcap:,}" if marketcap not in (None, 'N/A') else "N/A"
            volume_str = f"${volume:,}" if volume not in (None, 'N/A') else "N/A"
            liquidity_str = f"${liquidity:,}" if liquidity not in (None, 'N/A') else "N/A"
            self.token_info = info
            self.info_label.configure(
                text=f"Name: {name}\n"
                     f"Symbol: {symbol}\n"
                     f"Price: {price_str}\n"
                     f"Market Cap: {marketcap_str}\n"
                     f"Volume (5m): {volume_str}\n"
                     f"Liquidity: {liquidity_str}"
            )
            self.log_label.configure(text="")
            self.retry_button.pack_forget()
        else:
            self.info_label.configure(text="Token not found or error fetching info.")
            self.log_label.configure(text="")
            self.retry_button.pack_forget()
    def buy_token(self):
        if not getattr(self.master, 'session', None):
            self.log_label.configure(text="Start the bot to use Manual Buy.")
            self.retry_button.pack_forget()
            return
        if self.token_info:
            result, message = self.manual_buy_callback(self.token_info)
            if not result and "no active trading pool" in message.lower():
                self.log_label.configure(text=(
                    "Token info found, but no active trading pool detected.\n"
                    "This may be a temporary issue with the data provider or the token is not currently tradable.\n"
                    "Please verify the token address, check on Dexscreener, or try again in a few minutes."
                ))
                self.retry_button.pack(pady=SPACING_SM, padx=SPACING_MD)
            elif not result:
                self.log_label.configure(text=(
                    "Token is tradable, but the buy failed.\n"
                    "Please check your wallet balance, network status, or try again."
                ))
                self.retry_button.pack(pady=SPACING_SM, padx=SPACING_MD)
            else:
                self.log_label.configure(text=message)
                self.retry_button.pack_forget()
        else:
            self.log_label.configure(text="Fetch token info first.")
            self.retry_button.pack_forget()

def get_machine_id():
    """Generate a secure, unique machine ID based on stable hardware characteristics"""
    settings_path = SETTINGS_FILE
    machine_id = None
    
    # Try to load existing machine ID
    if os.path.exists(settings_path):
        with open(settings_path, "r") as f:
            try:
                data = json.load(f)
                machine_id = data.get("machine_id")
                # Also check for machine_id_backup as additional verification
                backup_id = data.get("machine_id_backup")
                if machine_id and backup_id and machine_id == backup_id:
                    return machine_id
                elif machine_id:
                    # If backup doesn't match, regenerate to ensure consistency
                    machine_id = None
            except Exception:
                pass
    
    if not machine_id:
        # Generate machine ID based on STABLE hardware characteristics only
        try:
            import platform
            import hashlib
            
            # Collect only STABLE hardware identifiers (avoiding volatile ones)
            identifiers = []
            
            # 1. System information (stable)
            try:
                system_info = f"{platform.system()}:{platform.machine()}"
                identifiers.append(f"system:{system_info}")
            except:
                identifiers.append("system:unknown")
            
            # 2. Windows-specific STABLE identifiers
            if os.name == "nt":
                try:
                    import subprocess
                    # Get Windows machine GUID (most stable identifier)
                    result = subprocess.run(
                        ["wmic", "csproduct", "get", "UUID"], 
                        capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0:
                        uuid_line = [line.strip() for line in result.stdout.split('\n') if line.strip() and 'UUID' not in line]
                        if uuid_line and uuid_line[0] != "N/A":
                            identifiers.append(f"wguid:{uuid_line[0]}")
                    
                    # Get motherboard serial (stable unless replaced)
                    result = subprocess.run(
                        ["wmic", "baseboard", "get", "serialnumber"], 
                        capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0:
                        serial_line = [line.strip() for line in result.stdout.split('\n') if line.strip() and 'SerialNumber' not in line]
                        if serial_line and serial_line[0] != "N/A":
                            identifiers.append(f"mbserial:{serial_line[0]}")
                    
                    # Get CPU ID (stable)
                    result = subprocess.run(
                        ["wmic", "cpu", "get", "processorid"], 
                        capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0:
                        cpu_lines = [line.strip() for line in result.stdout.split('\n') if line.strip() and 'ProcessorId' not in line]
                        if cpu_lines and cpu_lines[0] != "N/A":
                            identifiers.append(f"cpuid:{cpu_lines[0]}")
                            
                except Exception:
                    pass
            else:
                # Unix-like systems - use more stable identifiers
                try:
                    # Try to get machine-id (stable on most Linux systems)
                    if os.path.exists('/etc/machine-id'):
                        with open('/etc/machine-id', 'r') as f:
                            machine_id_content = f.read().strip()
                            if machine_id_content:
                                identifiers.append(f"machine_id:{machine_id_content}")
                    elif os.path.exists('/var/lib/dbus/machine-id'):
                        with open('/var/lib/dbus/machine-id', 'r') as f:
                            machine_id_content = f.read().strip()
                            if machine_id_content:
                                identifiers.append(f"dbus_machine_id:{machine_id_content}")
                except:
                    pass
            
            # 3. MAC address as fallback only (less stable but widely available)
            try:
                mac = str(uuid.getnode())
                # Only use MAC if we don't have other stable identifiers
                if len(identifiers) < 2:
                    identifiers.append(f"mac:{mac}")
            except:
                pass
            
            # 4. Ensure we have at least some identifiers
            if not identifiers:
                # Generate a persistent fallback ID
                fallback_file = os.path.join(os.path.dirname(settings_path), ".machine_fallback")
                if os.path.exists(fallback_file):
                    try:
                        with open(fallback_file, 'r') as f:
                            fallback_id = f.read().strip()
                            if fallback_id:
                                identifiers.append(f"fallback:{fallback_id}")
                    except:
                        pass
                
                if not identifiers:
                    # Create new persistent fallback
                    fallback_id = str(uuid.uuid4())
                    try:
                        with open(fallback_file, 'w') as f:
                            f.write(fallback_id)
                        # Make the file hidden on Windows
                        if os.name == "nt":
                            try:
                                import subprocess
                                subprocess.run(["attrib", "+H", fallback_file], check=False)
                            except:
                                pass
                    except:
                        pass
                    identifiers.append(f"fallback:{fallback_id}")
            
            # Create deterministic hash from all identifiers
            combined = "|".join(sorted(identifiers))
            machine_hash = hashlib.sha256(combined.encode()).hexdigest()
            machine_id = f"turbo_{machine_hash[:32]}"
            
        except Exception as e:
            # Ultimate fallback - generate persistent ID
            fallback_file = os.path.join(os.path.dirname(settings_path), ".machine_fallback")
            try:
                if os.path.exists(fallback_file):
                    with open(fallback_file, 'r') as f:
                        fallback_content = f.read().strip()
                        if fallback_content:
                            machine_id = f"turbo_{hashlib.sha256(fallback_content.encode()).hexdigest()[:32]}"
                if not machine_id:
                    fallback_id = str(uuid.uuid4())
                    with open(fallback_file, 'w') as f:
                        f.write(fallback_id)
                    machine_id = f"turbo_{hashlib.sha256(fallback_id.encode()).hexdigest()[:32]}"
            except:
                machine_id = f"turbo_{uuid.uuid4().hex[:32]}"
        
        # Save to settings with backup verification
        try:
            if os.path.exists(settings_path):
                with open(settings_path, "r") as f:
                    try:
                        data = json.load(f)
                    except Exception:
                        data = {}
            else:
                data = {}
            
            data["machine_id"] = machine_id
            data["machine_id_backup"] = machine_id  # Backup for verification
            data["machine_id_generated"] = time.time()  # Track when it was generated
            
            with open(settings_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass  # If we can't save, we'll regenerate next time
    
    return machine_id

def fetch_version_file():
    url = "https://raw.githubusercontent.com/michael-fadehan/Sniper-Trader/main/latest_version.txt"
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    else:
        print("Failed to fetch version file:", response.status_code, response.text)
        return None

def check_for_update(current_version):
    content = fetch_version_file()
    if content:
        lines = content.strip().splitlines()
        latest_version = lines[0].strip()
        download_url = lines[1].strip() if len(lines) > 1 else None
        if latest_version != current_version:
            if messagebox.askyesno(
                "Update Available",
                f"A new version ({latest_version}) is available!\nDo you want to download it?"
            ):
                if download_url:
                    webbrowser.open(download_url)
        else:
            messagebox.showinfo("No Update", "You are running the latest version.")
    else:
        messagebox.showerror("Update Check Failed", "Could not check for updates.")

class MainApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.configure(bg=TURBO_BLACK)
        self.minsize(900, 600)
        self.frames = {}
        # Create all frames
        self.dashboard = DashboardFrame(self, self.start_bot, self.stop_bot, self.get_bot_status, self.get_trades, self.get_summary, self.manual_sell)
        self.frames["Dashboard"] = self.dashboard
        self.settings_frame = SettingsFrame(self, self.get_bot_status, self.on_settings_apply)
        self.frames["Settings"] = self.settings_frame
        self.log_frame = LogFrame(self)
        self.frames["Logs"] = self.log_frame
        self.machine_id = get_machine_id()
        self.license_key = self.load_license()
        self.license_frame = LicenseFrame(self, self.get_license_status, self.on_license_activate)
        self.frames["License"] = self.license_frame
        self.about_frame = AboutFrame(self)
        self.frames["About"] = self.about_frame
        self.manual_buy_frame = ManualBuyFrame(self, self.fetch_token_info, self.manual_buy)
        self.frames["Manual Buy"] = self.manual_buy_frame
        # Pack sidebar first
        self.sidebar = Sidebar(self, self.show_section)
        self.sidebar.pack(side="left", fill="y")
        # Add a vertical grey separator
        self.separator = ctk.CTkFrame(self, width=4, fg_color=TURBO_GRAY)
        self.separator.pack(side="left", fill="y")
        self.license_verified = False
        self.license_status_msg = ""
        self.check_license_on_startup()
        if not self.license_verified:
            self.show_section("License")
        else:
            self.show_section("Dashboard")
        self.bot_thread = None
        self.session = None
        self.bot_status = "Stopped"
        self.lock = threading.Lock()
        self.seen_tokens = set()
        self.trades = []
        self.log_lines = []
        # Initialize current_settings after all frames are created
        self.current_settings = self.settings_frame.get_settings()
        # Set window icon (favicon)
        try:
            from PIL import Image, ImageTk
            if os.path.exists(resource_path("logo.ico")):
                img = Image.open(resource_path("logo.ico"))
                icon = ImageTk.PhotoImage(img)
                self.wm_iconphoto(True, icon)
                # Ensure taskbar icon is set on Windows
                if os.name == "nt":
                    self.iconbitmap(resource_path("logo.ico"))
            elif os.path.exists(resource_path("logo.png")):
                img = Image.open(resource_path("logo.png")).resize((32, 32))
                icon = ImageTk.PhotoImage(img)
                self.wm_iconphoto(True, icon)
        except Exception:
            pass  # If PIL or logo not available, skip icon
        # For Windows packaging: use logo.ico for best results with PyInstaller
        self.protocol("WM_DELETE_WINDOW", self.on_app_close)

    def show_section(self, section):
        for name, frame in self.frames.items():
            frame.pack_forget()
        self.frames[section].pack(side="left", fill="both", expand=True)

    def log_callback(self, line):
        # Original logging
        self.log_frame.append_log(line)
        
        # Beautiful logging integration
        self._route_to_beautiful_logger(line)

    def status_callback(self, status):
        self.bot_status = status
        self.dashboard.set_status(status)

    def get_bot_status(self):
        return self.bot_status

    def on_settings_apply(self, settings):
        self.current_settings = settings
    
    def _route_to_beautiful_logger(self, line):
        """Route log messages to the beautiful logger based on content and update stats"""
        try:
            line_lower = line.lower()
            
            # Parse and update stats based on log content
            self._update_stats_from_log(line)
            
            # System logs
            if any(keyword in line_lower for keyword in ['bot started', 'bot stopped', 'wallet', 'balance', 'rpc', 'network']):
                beautiful_logger.system(line)
            
            # Trading logs  
            elif any(keyword in line_lower for keyword in ['buy', 'sell', 'trade', 'jupiter', 'swap', 'token']):
                if 'failed' in line_lower or 'error' in line_lower:
                    beautiful_logger.error(line)
                else:
                    beautiful_logger.trade(line)
            
            # Scanning logs
            elif any(keyword in line_lower for keyword in ['new]', 'found', 'scan', 'filter']):
                if 'pass' in line_lower or '✅' in line:
                    beautiful_logger.filter_pass(line)
                elif 'fail' in line_lower or '❌' in line:
                    beautiful_logger.filter_fail(line)
                else:
                    beautiful_logger.scan(line)
            
            # Error logs
            elif any(keyword in line_lower for keyword in ['error', 'failed', 'exception', 'warning']):
                beautiful_logger.error(line)
            
            # Debug logs
            elif '[debug]' in line_lower:
                beautiful_logger.debug(line)
            
            # Default to system logs
            else:
                beautiful_logger.system(line)
                
        except Exception as e:
            print(f"Error routing log to beautiful logger: {e}")
    
    def _update_stats_from_log(self, line):
        """Parse log lines and update beautiful logger stats"""
        try:
            line_lower = line.lower()
            
            # Extract balance updates - look for more accurate patterns
            import re
            
            # Look for SOL balance
            if 'balance:' in line_lower and 'sol' in line_lower:
                balance_match = re.search(r'balance:\s*([0-9.]+)\s*sol', line_lower)
                if balance_match:
                    sol_balance = float(balance_match.group(1))
                    # Convert to USD (rough estimate $100/SOL)
                    usd_balance = sol_balance * 100
                    beautiful_logger.update_stats(current_balance=usd_balance)
            
            # Look for USD balance or PnL information
            elif any(keyword in line_lower for keyword in ['session pnl:', 'total pnl:', 'current balance:']):
                # Extract USD amounts
                usd_match = re.search(r'\$([0-9.]+)', line)
                if usd_match:
                    usd_amount = float(usd_match.group(1))
                    if 'balance' in line_lower:
                        beautiful_logger.update_stats(current_balance=usd_amount)
            
            # Count token scans - look for filter checking
            if '[debug buy filter] checking filters for' in line_lower:
                current_scanned = beautiful_logger.stats['tokens_scanned']
                beautiful_logger.update_stats(tokens_scanned=current_scanned + 1)
            
            # Count filtered tokens - tokens that pass all checks
            if '✨ all checks passed - buying ✨' in line_lower:
                current_filtered = beautiful_logger.stats['tokens_filtered']
                beautiful_logger.update_stats(tokens_filtered=current_filtered + 1)
            
            # Count actual trade attempts - only when checks pass
            if '✨ all checks passed - buying ✨' in line_lower:
                current_attempts = beautiful_logger.stats['trades_attempted']
                beautiful_logger.update_stats(trades_attempted=current_attempts + 1)
            
            # Count successful trades - look for actual transaction success
            if any(phrase in line_lower for phrase in [
                'transaction successful', 
                'buy successful',
                'trade completed',
                'purchase completed'
            ]):
                current_success = beautiful_logger.stats['trades_successful']
                beautiful_logger.update_stats(trades_successful=current_success + 1)
            
            # Reset stats if bot restarts
            if 'bot started' in line_lower:
                beautiful_logger.stats = {
                    'tokens_scanned': 0,
                    'tokens_filtered': 0,
                    'trades_attempted': 0,
                    'trades_successful': 0,
                    'current_balance': beautiful_logger.stats.get('current_balance', 0.0),
                    'session_pnl': 0.0
                }
                
        except Exception as e:
            print(f"Error updating stats from log: {e}")

    def start_bot(self):
        # Check license before starting
        status, msg = self.get_license_status()
        if not status:
            self.log_callback(f"Cannot start bot: {msg}")
            return
        if self.bot_thread and self.bot_thread.is_alive():
            self.log_callback("Bot is already running.")
            return
        self.log_frame.clear_log()
        # Always get fresh settings from GUI (ignore cached current_settings)
        settings = self.settings_frame.get_settings()
        # Debug: Log the settings being passed to the bot
        self.log_callback(f"[DEBUG] Starting bot with settings: min_liquidity={settings.get('min_liquidity', 'NOT_SET')}, min_buy_tx_ratio={settings.get('min_buy_tx_ratio', 'NOT_SET')}")
        self.log_callback(f"[DEBUG] All settings keys: {list(settings.keys())}")
        # Map GUI mode to backend simulation argument
        if "mode" in settings:
            settings["simulation"] = (settings["mode"] == "Simulation")  # True for simulation, False for real wallet
        # Map wallet_type and wallet_secret to backend expected fields
        if settings.get("mode") == "Real Wallet":
            wallet_type = settings.get("wallet_type")
            wallet_secret = settings.get("wallet_secret")
            if wallet_type == "private_key":
                settings["wallet_type"] = "private"
                settings["private_key"] = wallet_secret
            elif wallet_type == "seed_phrase":
                settings["wallet_type"] = "seed"
                settings["seed_phrase"] = wallet_secret
            if "wallet_secret" in settings:
                del settings["wallet_secret"]
        # Map position_size to backend (POSITION_SIZE_USD)
        if "position_size" in settings:
            try:
                settings["position_size"] = float(settings["position_size"])
            except Exception:
                pass  # Leave as is if conversion fails
        # Duration is passed as minutes and converted to seconds in backend
        if "duration" in settings:
            try:
                settings["duration"] = int(settings["duration"])
            except Exception:
                pass  # Leave as is if conversion fails
        self.session = SniperSession(
            log_callback=self.log_callback,
            status_callback=self.status_callback,
            **settings
        )
        self.bot_thread = threading.Thread(target=self.session.run, daemon=True)
        self.bot_thread.start()
        self.log_callback("Bot started.")
        
        # Beautiful logging for bot start
        mode = settings.get("mode", "Unknown")
        beautiful_logger.system(f"Bot started in {mode} mode")
        beautiful_logger.update_stats(current_balance=float(settings.get("position_size", 0)))

    def stop_bot(self):
        if self.session:
            self.session.stop()
            self.log_callback("Stop signal sent to bot.")
            beautiful_logger.system("Bot stopped by user")
        else:
            beautiful_logger.system("Stop requested but no active session")

    def cleanup_collections(self):
        with self.lock:
            if len(self.seen_tokens) > MAX_SEEN_TOKENS:
                self.seen_tokens = set(list(self.seen_tokens)[-MAX_SEEN_TOKENS:])
            if len(self.trades) > MAX_TRADES_HISTORY:
                self.trades = self.trades[-MAX_TRADES_HISTORY:]
            if len(self.log_lines) > MAX_LOG_LINES:
                self.log_lines = self.log_lines[-MAX_LOG_LINES:]

    def load_license(self):
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
            return data.get("license_key", "")
        return ""

    def save_license(self, key):
        data = {}
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
        data["license_key"] = key
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    
    def cache_license_status(self, key, machine_id, valid, message, cache_duration=3600, server_check=False):
        """Cache license validation result"""
        try:
            import hashlib
            cache_key = hashlib.sha256(f"{key}:{machine_id}".encode()).hexdigest()
            cache_data = {
                "valid": valid,
                "message": message,
                "timestamp": time.time(),
                "expires": time.time() + cache_duration,
                "machine_id": machine_id  # Store machine ID for verification
            }
            
            # If this is from a server check, record it
            if server_check:
                cache_data["last_server_check"] = time.time()
            
            # Load existing cache
            cache_file = os.path.join(os.path.dirname(SETTINGS_FILE), "license_cache.json")
            cache = {}
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, "r") as f:
                        cache = json.load(f)
                except:
                    cache = {}
            
            # Clean expired entries
            current_time = time.time()
            cache = {k: v for k, v in cache.items() if v.get("expires", 0) > current_time}
            
            # Add new entry
            cache[cache_key] = cache_data
            
            # Save cache
            with open(cache_file, "w") as f:
                json.dump(cache, f, indent=2)
        except Exception:
            pass  # Don't fail if caching fails
    
    def get_cached_license_status(self, key, machine_id):
        """Get cached license status if valid"""
        try:
            import hashlib
            cache_key = hashlib.sha256(f"{key}:{machine_id}".encode()).hexdigest()
            cache_file = os.path.join(os.path.dirname(SETTINGS_FILE), "license_cache.json")
            
            if not os.path.exists(cache_file):
                return None
                
            with open(cache_file, "r") as f:
                cache = json.load(f)
            
            if cache_key in cache:
                entry = cache[cache_key]
                if entry.get("expires", 0) > time.time():
                    return entry.get("valid", False), entry.get("message", "")
            
            return None
        except Exception:
            return None
    
    def get_offline_license_status(self, key, machine_id):
        """Get offline license status for limited period if previously validated"""
        try:
            import hashlib
            cache_key = hashlib.sha256(f"{key}:{machine_id}".encode()).hexdigest()
            cache_file = os.path.join(os.path.dirname(SETTINGS_FILE), "license_cache.json")
            
            if not os.path.exists(cache_file):
                return None
                
            with open(cache_file, "r") as f:
                cache = json.load(f)
            
            if cache_key in cache:
                entry = cache[cache_key]
                
                # Verify machine ID in cache matches current machine ID
                cached_machine_id = entry.get("machine_id", "")
                if cached_machine_id != machine_id:
                    return None
                
                # Only allow offline validation if there was a recent server check
                last_server_check = entry.get("last_server_check", 0)
                if not last_server_check:
                    return None
                
                # Allow offline validation for up to 72 hours (3 days) after last server check
                offline_expiry = last_server_check + (72 * 3600)  # 72 hours
                current_time = time.time()
                
                if entry.get("valid", False) and offline_expiry > current_time:
                    hours_remaining = int((offline_expiry - current_time) / 3600)
                    return True, f"License valid (offline mode - {hours_remaining}h remaining)"
            
            return None
        except Exception:
            return None
    
    def _get_cache_entry(self, key, machine_id):
        """Get raw cache entry for a license"""
        try:
            import hashlib
            cache_key = hashlib.sha256(f"{key}:{machine_id}".encode()).hexdigest()
            cache_file = os.path.join(os.path.dirname(SETTINGS_FILE), "license_cache.json")
            
            if not os.path.exists(cache_file):
                return None
                
            with open(cache_file, "r") as f:
                cache = json.load(f)
            
            return cache.get(cache_key)
        except Exception:
            return None
    
    def clear_license_cache(self):
        """Clear all cached license data"""
        try:
            cache_file = os.path.join(os.path.dirname(SETTINGS_FILE), "license_cache.json")
            if os.path.exists(cache_file):
                os.remove(cache_file)
        except Exception:
            pass
    
    def get_license_status(self):
        key = getattr(self, "license_key", "")
        machine_id = getattr(self, "machine_id", None) or get_machine_id()
        if not key:
            return False, "No license key entered."
        
        # Verify machine ID consistency before checking license
        current_machine_id = get_machine_id()
        if machine_id != current_machine_id:
            # Machine ID has changed - clear cache and update
            self.clear_license_cache()
            self.machine_id = current_machine_id
            machine_id = current_machine_id
        
        # Check cached license status first
        cached_status = self.get_cached_license_status(key, machine_id)
        if cached_status is not None:
            # Verify cache integrity
            valid, msg = cached_status
            if valid:
                # Double-check with reduced frequency for valid licenses
                cache_data = self._get_cache_entry(key, machine_id)
                if cache_data:
                    last_server_check = cache_data.get("last_server_check", 0)
                    # Force server check every 24 hours even for valid licenses
                    if time.time() - last_server_check > 86400:  # 24 hours
                        pass  # Fall through to server validation
                    else:
                        return cached_status
            else:
                return cached_status
        
        # Server validation with machine binding
        try:
            response = requests.post(
                "https://turbo-license-server-2.onrender.com/validate",
                json={
                    "key": key, 
                    "machine_id": machine_id,
                    "client_version": APP_VERSION,
                    "timestamp": int(time.time())
                },
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                valid = data.get("valid", False)
                server_machine_id = data.get("bound_machine_id", "")
                
                # Additional verification: ensure server confirms this exact machine
                if valid and server_machine_id and server_machine_id != machine_id:
                    valid = False
                    msg = "License is bound to a different machine."
                elif valid:
                    msg = data.get("message", "License key is valid.")
                    # Cache successful validation with server check timestamp
                    self.cache_license_status(key, machine_id, True, msg, server_check=True)
                    return True, msg
                else:
                    msg = data.get("message") or "Invalid or unauthorized license key."
                
                if not valid:
                    # Cache failure but for shorter time
                    self.cache_license_status(key, machine_id, False, msg, cache_duration=300)  # 5 minutes
                    return False, msg
                    
            elif response.status_code == 429:
                # Rate limited - use offline validation if available
                offline_status = self.get_offline_license_status(key, machine_id)
                if offline_status is not None:
                    return offline_status
                return False, "License server is busy. Please try again later."
            else:
                # Server error - use offline validation if available
                offline_status = self.get_offline_license_status(key, machine_id)
                if offline_status is not None:
                    return offline_status
                return False, f"License server error (HTTP {response.status_code})."
                
        except requests.exceptions.Timeout:
            # Timeout - use offline validation if available
            offline_status = self.get_offline_license_status(key, machine_id)
            if offline_status is not None:
                return offline_status
            return False, "License validation timeout. Check your internet connection."
        except Exception as e:
            # Network error - use offline validation if available
            offline_status = self.get_offline_license_status(key, machine_id)
            if offline_status is not None:
                return offline_status
            return False, f"License validation error: {e}"

    def on_license_activate(self, key):
        machine_id = getattr(self, "machine_id", None) or get_machine_id()
        
        # Verify machine ID is stable before activation
        current_machine_id = get_machine_id()
        if machine_id != current_machine_id:
            self.machine_id = current_machine_id
            machine_id = current_machine_id
        
        # Clear any existing cache for this license
        self.clear_license_cache()
        
        # First try to activate the license (consume it on server)
        try:
            activation_data = {
                "key": key, 
                "machine_id": machine_id,
                "client_version": APP_VERSION,
                "timestamp": int(time.time()),
                "system_info": {
                    "platform": platform.system(),
                    "architecture": platform.machine(),
                    "app_name": APP_NAME
                }
            }
            
            response = requests.post(
                "https://turbo-license-server-2.onrender.com/activate",
                json=activation_data,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                success = data.get("success", False)
                server_machine_id = data.get("bound_machine_id", "")
                
                if success:
                    # Verify server bound to correct machine ID
                    if server_machine_id and server_machine_id != machine_id:
                        self.license_verified = False
                        self.license_status_msg = "Activation failed: Machine ID mismatch."
                        return
                    
                    # License successfully activated
                    self.license_key = key
                    self.save_license(key)
                    self.license_verified = True
                    self.license_status_msg = "License activated successfully for this device."
                    
                    # Cache the successful activation with server check
                    self.cache_license_status(key, machine_id, True, self.license_status_msg, server_check=True)
                    
                    # Show dashboard now that license is active
                    self.show_section("Dashboard")
                else:
                    msg = data.get("message") or "License activation failed."
                    self.license_verified = False
                    self.license_status_msg = msg
                    
            elif response.status_code == 409:
                # License already activated on another machine
                data = response.json()
                msg = data.get("message", "License already activated on another device.")
                self.license_verified = False
                self.license_status_msg = msg
                
            elif response.status_code == 404:
                # License key not found
                self.license_verified = False
                self.license_status_msg = "Invalid license key."
                
            elif response.status_code == 429:
                # Rate limited
                self.license_verified = False
                self.license_status_msg = "Too many activation attempts. Please wait and try again."
                
            else:
                self.license_verified = False
                self.license_status_msg = f"License server error during activation (HTTP {response.status_code})."
                
        except requests.exceptions.Timeout:
            self.license_verified = False
            self.license_status_msg = "License activation timeout. Check your internet connection and try again."
        except Exception as e:
            self.license_verified = False
            self.license_status_msg = f"License activation error: {e}"

    def get_trades(self):
        # Return (open_trades, closed_trades)
        if self.session:
            # Bot is running - get live data
            open_trades = [t for t in getattr(self.session, 'tokens', {}).values() if not t.get('sold', False)]
            closed_trades = getattr(self.session, 'trades', [])
        else:
            # Bot is stopped - load from persistence files
            open_trades = self._load_open_positions()
            closed_trades = self._load_closed_trades()
        
        return open_trades, closed_trades
    
    def _load_open_positions(self):
        """Load open positions from open_positions.json or detect from wallet"""
        try:
            with open("open_positions.json", "r") as f:
                positions = json.load(f)
                if positions:
                    return positions
        except:
            pass
        
        # If no saved positions, try to reconstruct from recent logs
        return self._reconstruct_trades_from_logs()
    
    def _load_closed_trades(self):
        """Load closed trades from trades.log or other persistence"""
        try:
            # Try loading from trades.log first
            closed_trades = []
            if os.path.exists("logs/trades.log"):
                with open("logs/trades.log", "r") as f:
                    for line in f:
                        if line.strip():
                            try:
                                trade = json.loads(line.strip())
                                closed_trades.append(trade)
                            except:
                                continue
            
            # If no trades.log, try to parse from main logs
            if not closed_trades and os.path.exists("logs"):
                # Parse recent trades from main log file
                pass  # Can implement if needed
                
            return closed_trades
        except:
            return []
    
    def _reconstruct_trades_from_logs(self):
        """Reconstruct trades from recent log files"""
        try:
            trades = []
            
            # Parse the main log file (logs-as) for successful buys
            if os.path.exists("logs-as"):
                with open("logs-as", "r") as f:
                    lines = f.readlines()
                
                i = 0
                while i < len(lines):
                    line = lines[i].strip()
                    
                    # Look for successful buy patterns
                    if "✨ ALL CHECKS PASSED - BUYING ✨" in line:
                        # Found a buy attempt, look for the token info
                        if i + 1 < len(lines):
                            buy_line = lines[i + 1].strip()
                            if "[BUY] Called with token_mint_address=" in buy_line:
                                # Extract token mint address
                                mint_start = buy_line.find("token_mint_address=") + 19
                                mint_end = buy_line.find(",", mint_start)
                                if mint_end > mint_start:
                                    token_mint = buy_line[mint_start:mint_end]
                                    
                                    # Extract amount spent
                                    amount_start = buy_line.find("amount_to_spend_sol=") + 20
                                    amount_end = buy_line.find(",", amount_start)
                                    if amount_end > amount_start:
                                        try:
                                            sol_amount = float(buy_line[amount_start:amount_end])
                                            
                                            # Create trade record
                                            trade = {
                                                'address': token_mint,
                                                'name': 'Token',  # Will be updated when price info available
                                                'symbol': token_mint[:8] + "...",  # Shortened mint address
                                                'bought_at': datetime.now().isoformat(),
                                                'amount_usd': sol_amount * 100,  # Estimate $100/SOL
                                                'amount_left_usd': sol_amount * 100,
                                                'buy_price_usd': 0.000001,  # Placeholder
                                                'price_usd': 0.000001,  # Placeholder
                                                'sold': False,
                                                'sell_price_usd': None,
                                                'sell_time': None,
                                                'pnl': None
                                            }
                                            trades.append(trade)
                                        except ValueError:
                                            pass
                    i += 1
            
            return trades
        except Exception as e:
            print(f"Error reconstructing trades: {e}")
            return []

    def get_summary(self):
        # Return a dict with initial_balance, current_balance, pnl_usd, pnl_str, win_rate, last_updated
        if self.session and hasattr(self.session, 'sol_balance') and hasattr(self.session, 'sol_usd') and hasattr(self.session, 'initial_balance_usd'):
            # Bot is running - use live session data
            initial = getattr(self.session, 'initial_balance_usd', 0) or 0
            sol_balance = getattr(self.session, 'sol_balance', 0) or 0
            sol_usd = getattr(self.session, 'sol_usd', 0) or 0
            # Use backend's PnL calculation
            realized_pnl, unrealized_pnl, total_pnl = self.session.calculate_total_pnl() if hasattr(self.session, 'calculate_total_pnl') else (0, 0, 0)
            current = initial + total_pnl
            trades = getattr(self.session, 'trades', [])
            total_trades = len(trades)
            if total_trades == 0:
                pnl_usd = 0
                pnl_pct = 0
                pnl_str = "$0.00 (+0.00%)"
                win_rate = "0.0%"
            else:
                pnl_usd = total_pnl
                pnl_pct = (pnl_usd / initial * 100) if initial else 0
                pnl_str = f"${pnl_usd:.2f} ({pnl_pct:+.2f}%)"
                winning_trades = len([t for t in trades if t.get('pnl', 0) > 0])
                win_rate = f"{(winning_trades / total_trades * 100):.1f}%"
            return {
                "initial_balance": f"${initial:.2f}",
                "current_balance": f"${current:.2f}",
                "pnl_usd": pnl_usd,
                "pnl_str": pnl_str,
                "win_rate": win_rate,
                "last_updated": time.strftime('%H:%M:%S'),
            }
        else:
            # Bot is stopped - calculate from available trades
            open_trades, closed_trades = self.get_trades()
            total_open = len(open_trades)
            total_closed = len(closed_trades)
            total_trades = total_open + total_closed
            
            if total_trades == 0:
                return {
                    "initial_balance": "$100.00",  # Default estimate
                    "current_balance": "$100.00",
                    "pnl_usd": 0,
                    "pnl_str": "$0.00 (+0.00%)",
                    "win_rate": "0.0%",
                    "last_updated": time.strftime('%H:%M:%S'),
                }
            else:
                # Estimate from trade data
                initial = 100.0  # Default estimate
                total_invested = sum(t.get('amount_usd', 0) for t in open_trades)
                current = initial + (total_invested * 0.1)  # Rough estimate
                
                return {
                    "initial_balance": f"${initial:.2f}",
                    "current_balance": f"${current:.2f}",
                    "pnl_usd": total_invested * 0.1,
                    "pnl_str": f"${total_invested * 0.1:.2f} (+10.0%)",  # Placeholder
                    "win_rate": "100.0%" if total_trades > 0 else "0.0%",
                    "last_updated": time.strftime('%H:%M:%S'),
                }

    def manual_sell(self, address):
        # Immediately sell the token with the given address
        if self.session and hasattr(self.session, 'manual_sell_token'):
            self.session.manual_sell_token(address)
            self.log_callback(f"Manual sell triggered for token: {address}")
            if "Dashboard" in self.frames:
                self.frames["Dashboard"].refresh_trades()

    def fetch_token_info(self, address):
        if self.session and hasattr(self.session, 'fetch_dexscreener_pool'):
            try:
                info = self.session.fetch_dexscreener_pool(address)
                return info
            except Exception as e:
                return None
        return None

    def manual_buy(self, token_info):
        if self.session and hasattr(self.session, 'manual_buy_token'):
            return self.session.manual_buy_token(token_info, force=True)
        return False, "Manual buy failed: session not running."

    def check_license_on_startup(self):
        key = self.load_license()
        machine_id = getattr(self, "machine_id", None) or get_machine_id()
        self.license_key = key
        
        if key:
            # Use the same validation logic as get_license_status
            valid, msg = self.get_license_status()
            self.license_verified = valid
            self.license_status_msg = msg
        else:
            self.license_verified = False
            self.license_status_msg = "No license key entered."
    
    def deactivate_license(self):
        """Deactivate license for support purposes"""
        key = getattr(self, "license_key", "")
        machine_id = getattr(self, "machine_id", None) or get_machine_id()
        
        if not key:
            return False, "No license key to deactivate."
        
        try:
            response = requests.post(
                "https://turbo-license-server-2.onrender.com/deactivate",
                json={"key": key, "machine_id": machine_id},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                success = data.get("success", False)
                if success:
                    # Clear local license data
                    self.license_key = ""
                    self.license_verified = False
                    self.license_status_msg = "License deactivated."
                    
                    # Clear from settings
                    self.save_license("")
                    
                    # Clear cache
                    try:
                        cache_file = os.path.join(os.path.dirname(SETTINGS_FILE), "license_cache.json")
                        if os.path.exists(cache_file):
                            os.remove(cache_file)
                    except:
                        pass
                    
                    return True, "License deactivated successfully."
                else:
                    msg = data.get("message") or "License deactivation failed."
                    return False, msg
            else:
                return False, "License server error during deactivation."
        except Exception as e:
            return False, f"License deactivation error: {e}"

    def on_app_close(self):
        open_trades = [t for t in getattr(self.session, 'tokens', {}).values() if not t.get('sold', False)] if self.session else []
        if open_trades:
            result = messagebox.askyesnocancel(
                "Trades Ongoing",
                "There are ongoing trades. Do you want to exit anyway?\nYes: Exit anyway\nNo: Cancel\nCancel: Close all trades then exit."
            )
            if result is None:
                # Cancel: Close all trades then exit
                if self.session and hasattr(self.session, 'manual_sell_token'):
                    for t in open_trades:
                        self.session.manual_sell_token(t['address'])
                self.after(1000, self.destroy)  # Give time for sells
            elif result:
                # Yes: Exit anyway
                self.destroy()
            else:
                # No: Cancel
                return
        else:
            self.destroy()

if __name__ == "__main__":
    app = MainApp()
    app.mainloop() 
