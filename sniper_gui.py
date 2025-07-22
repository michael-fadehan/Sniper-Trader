import customtkinter as ctk
import tkinter as tk
import threading
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

MAX_LOG_LINES = 5000

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
        if open_trades:
            for trade in open_trades:
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
        else:
            ctk.CTkLabel(self.open_scroll, text="No open trades.", font=FONT_BODY, text_color=TURBO_GRAY).pack(pady=SPACING_MD, padx=SPACING_MD)
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
                # Correct percent calculation: percent of invested amount, but also show price-based PnL percent
                pnl_pct = ((sell_price - buy_price) / buy_price * 100) if buy_price else 0
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
        self.duration_var = ctk.IntVar(value=1)  # Default 1 minute
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
            **{key.lower().replace(" ", "_").replace("(", "").replace(")", ""): var.get() 
               for key, var in self.trading_vars.items()},
            **{key.lower().replace(" ", "_"): var.get() 
               for key, (var, _) in self.risk_vars.items()},
            "position_size": self.position_size_var.get(),
        }
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
        self.on_settings_apply(settings)

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
                setting_key = key.lower().replace(" ", "_").replace("(", "").replace(")", "")
                if setting_key in settings:
                    var.set(settings[setting_key])
            for key, (var, _) in self.risk_vars.items():
                setting_key = key.lower().replace(" ", "_")
                if setting_key in settings:
                    var.set(settings[setting_key])
            self.position_size_var.set(settings.get("position_size", 20.0))
            self.duration_var.set(settings.get("duration", 1))  # Load as minutes
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
        self.panel = ctk.CTkFrame(self, fg_color=TURBO_NAVY, corner_radius=CARD_RADIUS)
        self.panel.pack(expand=True, fill="both", pady=SPACING_LG, padx=SPACING_XL, ipadx=SPACING_MD, ipady=SPACING_MD)
        self.panel.pack_propagate(False)
        label = ctk.CTkLabel(self.panel, text="Enter License Key", **label_kwargs)
        label.pack(pady=(SPACING_MD, SPACING_SM), padx=SPACING_MD)
        self.entry = ctk.CTkEntry(self.panel, **entry_kwargs, corner_radius=INPUT_RADIUS)
        self.entry.pack(pady=SPACING_SM, padx=SPACING_MD)
        self.activate_btn = ctk.CTkButton(self.panel, text="Activate", **button_kwargs, command=self._activate)
        self.activate_btn.pack(pady=SPACING_SM, padx=SPACING_MD)
        self.status_label = ctk.CTkLabel(self.panel, text="", font=FONT_SUBHEADER, fg_color="transparent")
        self.status_label.pack(pady=SPACING_SM, padx=SPACING_MD)
        self.get_license_status = get_license_status
        self.on_activate = on_activate
        # Show status on startup
        self.refresh_status()
        # If a license key is present, fill it in the entry
        key = master.license_key if hasattr(master, 'license_key') else ""
        if key:
            self.entry.delete(0, "end")
            self.entry.insert(0, key)
        # Show verified message if already licensed
        if getattr(master, 'license_verified', False):
            self.status_label.configure(text=master.license_status_msg, text_color=TURBO_SUCCESS)
            self.entry.configure(state="disabled")
            self.activate_btn.configure(state="disabled")

    def _activate(self):
        key = self.entry.get().strip()
        self.on_activate(key)
        self.refresh_status()

    def refresh_status(self):
        status, msg = self.get_license_status()
        color = TURBO_SUCCESS if status else TURBO_ERROR
        self.status_label.configure(text=msg, text_color=color)

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
    # Generate a unique machine ID (persisted in settings.json)
    settings_path = SETTINGS_FILE
    machine_id = None
    if os.path.exists(settings_path):
        with open(settings_path, "r") as f:
            try:
                data = json.load(f)
                machine_id = data.get("machine_id")
            except Exception:
                pass
    if not machine_id:
        # Use uuid.getnode() (MAC address) as base, fallback to random UUID
        try:
            machine_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(uuid.getnode())))
        except Exception:
            machine_id = str(uuid.uuid4())
        # Save to settings
        if os.path.exists(settings_path):
            with open(settings_path, "r") as f:
                try:
                    data = json.load(f)
                except Exception:
                    data = {}
        else:
            data = {}
        data["machine_id"] = machine_id
        with open(settings_path, "w") as f:
            json.dump(data, f, indent=2)
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
        self.log_frame.append_log(line)

    def status_callback(self, status):
        self.bot_status = status
        self.dashboard.set_status(status)

    def get_bot_status(self):
        return self.bot_status

    def on_settings_apply(self, settings):
        self.current_settings = settings

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
        settings = getattr(self, 'current_settings', None)
        if settings is None:
            settings = self.settings_frame.get_settings()
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
        # Map duration to backend (DURATION_MINUTES)
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

    def stop_bot(self):
        if self.session:
            self.session.stop()
            self.log_callback("Stop signal sent to bot.")

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

    def get_license_status(self):
        key = getattr(self, "license_key", "")
        machine_id = getattr(self, "machine_id", None) or get_machine_id()
        if not key:
            return False, "No license key entered."
        # Server validation with machine binding
        try:
            response = requests.post(
                "https://turbo-license-server-2.onrender.com/validate",
                json={"key": key, "machine_id": machine_id},
                timeout=5
            )
            if response.status_code == 200:
                valid = response.json().get("valid", False)
                if valid:
                    return True, "License key is valid."
                else:
                    msg = response.json().get("message") or "Invalid or unauthorized license key."
                    return False, msg
            else:
                return False, "License server error."
        except Exception as e:
            return False, f"License validation error: {e}"

    def on_license_activate(self, key):
        self.license_key = key
        self.save_license(key)
        # No log_callback here; LicenseFrame handles status display

    def get_trades(self):
        # Return (open_trades, closed_trades)
        open_trades = [t for t in getattr(self.session, 'tokens', {}).values() if not t.get('sold', False)] if self.session else []
        closed_trades = getattr(self.session, 'trades', []) if self.session else []
        return open_trades, closed_trades

    def get_summary(self):
        # Return a dict with initial_balance, current_balance, pnl_usd, pnl_str, win_rate, last_updated
        if self.session and hasattr(self.session, 'sol_balance') and hasattr(self.session, 'sol_usd') and hasattr(self.session, 'initial_balance_usd'):
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
            return {
                "initial_balance": "-",
                "current_balance": "-",
                "pnl_usd": 0,
                "pnl_str": "-",
                "win_rate": "-",
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
        if key:
            try:
                response = requests.post(
                    "https://turbo-license-server-2.onrender.com/validate",
                    json={"key": key, "machine_id": machine_id},
                    timeout=5
                )
                if response.status_code == 200:
                    valid = response.json().get("valid", False)
                    if valid:
                        self.license_verified = True
                        self.license_status_msg = "License verified for this device."
                        self.license_key = key
                    else:
                        self.license_verified = False
                        self.license_status_msg = response.json().get("message") or "Invalid or unauthorized license key."
                else:
                    self.license_verified = False
                    self.license_status_msg = "License server error."
            except Exception as e:
                self.license_verified = False
                self.license_status_msg = f"License validation error: {e}"
        else:
            self.license_verified = False
            self.license_status_msg = "No license key entered."

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
