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

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

SOLANA_MAINNET_RPC = "https://api.mainnet-beta.solana.com"
SETTINGS_FILE = "settings.json"

APP_NAME = "Turbo"
APP_VERSION = "1.1.0"
COMPANY = "Turbo"
SUPPORT_EMAIL = "support@turbo.com"
WEBSITE = "https://turbo.com" 
TELEGRAM = "@turbo"

# --- Turbo Branding Colors (Updated Palette) ---
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
            logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
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
        self.panel = ctk.CTkFrame(self, fg_color=TURBO_NAVY, corner_radius=14, width=900)
        self.panel.pack(expand=True, fill="both", pady=40, padx=40)
        self.panel.pack_propagate(False)
        # Top: Start/Stop Buttons
        btns_frame = ctk.CTkFrame(self.panel, fg_color="transparent")
        btns_frame.pack(pady=(40, 10))
        self.start_btn = ctk.CTkButton(
            btns_frame, text="Start Bot", font=FONT_DASHBOARD,
            fg_color=TURBO_BLACK, border_color=TURBO_CYAN, border_width=3,
            text_color=TURBO_CYAN, corner_radius=14, width=170, height=54,
            hover_color=TURBO_NAVY, command=self.start_callback
        )
        self.start_btn.grid(row=0, column=0, padx=30)
        self.stop_btn = ctk.CTkButton(
            btns_frame, text="Stop Bot", font=FONT_DASHBOARD,
            fg_color=TURBO_BLACK, border_color=TURBO_PURPLE, border_width=3,
            text_color=TURBO_PURPLE, corner_radius=14, width=170, height=54,
            hover_color=TURBO_NAVY, command=self.stop_callback
        )
        self.stop_btn.grid(row=0, column=1, padx=30)
        # Centered Status Label
        self.status_var = ctk.StringVar(value="Status: stopped")
        self.status_label = ctk.CTkLabel(
            self.panel, textvariable=self.status_var, font=FONT_STATUS, text_color=TURBO_CYAN, fg_color="transparent"
        )
        self.status_label.pack(pady=(10, 20))
        self.after(1000, self.update_status)
        # --- Summary Panel ---
        self.summary_panel = ctk.CTkFrame(self.panel, fg_color=TURBO_DARK_GRAY, corner_radius=10)
        self.summary_panel.pack(pady=(0, 30), padx=20, fill="x")
        self.summary_labels = {}
        grid = [
            ("Initial Balance", 0, 0),
            ("Current Balance", 0, 1),
            ("Overall PnL", 0, 2),
            ("Win Rate", 0, 3),
            ("Last Updated", 0, 4),
        ]
        for label, row, col in grid:
            l = ctk.CTkLabel(self.summary_panel, text=f"{label}:", font=("Montserrat", 13, "bold"), text_color=TURBO_GRAY)
            l.grid(row=row, column=col*2, sticky="e", padx=(10,2), pady=10)
            v = ctk.CTkLabel(self.summary_panel, text="-", font=("Montserrat", 13, "bold"), text_color=TURBO_WHITE)
            v.grid(row=row, column=col*2+1, sticky="w", padx=(2,20), pady=10)
            self.summary_labels[label] = v
        self.summary_panel.grid_columnconfigure((1,3,5,7,9), weight=1)
        # Delay first summary refresh to avoid AttributeError
        self.after(500, self.refresh_summary)
        # --- Trades Panels ---
        bottom_frame = ctk.CTkFrame(self.panel, fg_color="transparent")
        bottom_frame.pack(expand=True, fill="both", pady=(0, 30))
        self.open_trades_panel = ctk.CTkFrame(bottom_frame, fg_color=TURBO_NAVY, corner_radius=14)
        self.closed_trades_panel = ctk.CTkFrame(bottom_frame, fg_color=TURBO_NAVY, corner_radius=14)
        self.open_trades_panel.pack(side="left", expand=True, fill="both", padx=(60, 15), pady=0)
        self.closed_trades_panel.pack(side="left", expand=True, fill="both", padx=(15, 60), pady=0)
        open_label = ctk.CTkLabel(self.open_trades_panel, text="Open Trades", font=FONT_DASHBOARD, text_color=TURBO_CYAN, fg_color="transparent")
        open_label.pack(pady=10)
        closed_label = ctk.CTkLabel(self.closed_trades_panel, text="Closed Trades", font=FONT_DASHBOARD, text_color=TURBO_PURPLE, fg_color="transparent")
        closed_label.pack(pady=10)
        self.open_scroll = ctk.CTkScrollableFrame(self.open_trades_panel, fg_color=TURBO_DARK_GRAY, corner_radius=10)
        self.open_scroll.pack(expand=True, fill="both", padx=10, pady=10)
        self.closed_scroll = ctk.CTkScrollableFrame(self.closed_trades_panel, fg_color=TURBO_DARK_GRAY, corner_radius=10)
        self.closed_scroll.pack(expand=True, fill="both", padx=10, pady=10)
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
                card = ctk.CTkFrame(self.open_scroll, fg_color=TURBO_BLACK, corner_radius=8)
                card.pack(fill="x", pady=6, padx=4)
                name = trade.get('name', 'N/A')
                symbol = trade.get('symbol', 'N/A')
                buy_price = trade.get('buy_price_usd', 0)
                cur_price = trade.get('price_usd', 0)
                pnl = ((cur_price - buy_price) / buy_price * 100) if buy_price else 0
                status = "HOLDING" if not trade.get('sold') else "SOLD"
                ctk.CTkLabel(card, text=f"{name} ({symbol})", font=("Montserrat", 15, "bold"), text_color=TURBO_CYAN, anchor="w").pack(anchor="w", padx=8, pady=(4,0))
                ctk.CTkLabel(card, text=f"Buy: ${buy_price:.6f} | Cur: ${cur_price:.6f}", font=("Montserrat", 12), text_color=TURBO_WHITE, anchor="w").pack(anchor="w", padx=8)
                ctk.CTkLabel(card, text=f"PnL: {pnl:+.2f}%", font=("Montserrat", 12, "bold"), text_color=TURBO_SUCCESS if pnl >= 0 else TURBO_ERROR, anchor="w").pack(anchor="w", padx=8)
                ctk.CTkLabel(card, text=f"Status: {status}", font=("Montserrat", 11), text_color=TURBO_GRAY, anchor="w").pack(anchor="w", padx=8, pady=(0,4))
                # Sell button
                sell_btn = ctk.CTkButton(card, text="Sell", fg_color=TURBO_ERROR, hover_color=TURBO_PURPLE, text_color=TURBO_WHITE, width=80, height=28, corner_radius=8, font=("Montserrat", 12, "bold"), command=lambda addr=trade.get('address'): self.handle_manual_sell(addr))
                sell_btn.pack(anchor="e", padx=8, pady=(0,6))
        else:
            ctk.CTkLabel(self.open_scroll, text="No open trades.", font=("Montserrat", 13, "italic"), text_color=TURBO_GRAY).pack(pady=20)
        # Modern card for each closed trade
        if closed_trades:
            for trade in closed_trades:
                card = ctk.CTkFrame(self.closed_scroll, fg_color=TURBO_BLACK, corner_radius=8)
                card.pack(fill="x", pady=6, padx=4)
                name = trade.get('name', 'N/A')
                symbol = trade.get('symbol', 'N/A')
                buy_price = trade.get('buy_price_usd', 0)
                sell_price = trade.get('sell_price_usd', 0)
                pnl = ((sell_price - buy_price) / buy_price * 100) if buy_price else 0
                ctk.CTkLabel(card, text=f"{name} ({symbol})", font=("Montserrat", 15, "bold"), text_color=TURBO_PURPLE, anchor="w").pack(anchor="w", padx=8, pady=(4,0))
                ctk.CTkLabel(card, text=f"Buy: ${buy_price:.6f} | Sell: ${sell_price:.6f}", font=("Montserrat", 12), text_color=TURBO_WHITE, anchor="w").pack(anchor="w", padx=8)
                ctk.CTkLabel(card, text=f"PnL: {pnl:+.2f}%", font=("Montserrat", 12, "bold"), text_color=TURBO_SUCCESS if pnl >= 0 else TURBO_ERROR, anchor="w").pack(anchor="w", padx=8)
                ctk.CTkLabel(card, text=f"Status: SOLD", font=("Montserrat", 11), text_color=TURBO_GRAY, anchor="w").pack(anchor="w", padx=8, pady=(0,4))
        else:
            ctk.CTkLabel(self.closed_scroll, text="No closed trades.", font=("Montserrat", 13, "italic"), text_color=TURBO_GRAY).pack(pady=20)
        # Schedule next refresh
        self.after(2000, self.refresh_trades)

    def handle_manual_sell(self, address):
        self.manual_sell_callback(address)
        self.refresh_trades()

class LogFrame(ctk.CTkFrame):
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.configure(fg_color=TURBO_BLACK)
        self.panel = ctk.CTkFrame(self, fg_color=TURBO_NAVY, corner_radius=14)
        self.panel.pack(expand=True, fill="both", pady=40, padx=40)
        self.panel.pack_propagate(False)
        self.textbox = ctk.CTkTextbox(self.panel, wrap="word", font=("Consolas", 12), fg_color=TURBO_DARK_GRAY, text_color=TURBO_CYAN)
        self.textbox.pack(fill="both", expand=True, padx=10, pady=10)
        self.textbox.configure(state="disabled")
        clear_btn = ctk.CTkButton(self.panel, text="Clear Log", command=self.clear_log, **button_kwargs)
        clear_btn.pack(pady=(0, 10))
        # Buffered log queue
        self._queue = deque()
        self.after(100, self._flush)

    def append_log(self, line):
        # push to queue, flush on timer
        self._queue.append(line)

    def _flush(self):
        if self._queue:
            self.textbox.configure(state="normal")
            while self._queue:
                self.textbox.insert("end", self._queue.popleft() + "\n")
            self.textbox.see("end")
            self.textbox.configure(state="disabled")
        self.after(100, self._flush)

    def clear_log(self):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")

class PlaceholderFrame(ctk.CTkFrame):
    def __init__(self, master, text, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.configure(fg_color=TURBO_BLACK)
        label = ctk.CTkLabel(self, text=text, **label_kwargs)
        label.pack(expand=True)

class SettingsFrame(ctk.CTkFrame):
    def __init__(self, master, get_bot_status, on_apply, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.configure(fg_color=TURBO_BLACK)
        self.get_bot_status = get_bot_status
        self.on_apply = on_apply
        self.vars = {}
        # Modern, full-width panel
        self.panel = ctk.CTkFrame(self, fg_color=TURBO_NAVY, corner_radius=14)
        self.panel.pack(expand=True, fill="both", pady=40, padx=40)
        self.panel.pack_propagate(False)
        self.panel.grid_columnconfigure(1, weight=1)
        row = 0
        # Wallet Type
        ctk.CTkLabel(self.panel, text="Wallet Type:", **label_kwargs).grid(row=row, column=0, sticky="w", padx=10, pady=2)
        self.vars['wallet_type'] = ctk.StringVar(value="private")
        wallet_type_menu = ctk.CTkOptionMenu(self.panel, variable=self.vars['wallet_type'], values=["private", "seed"], command=self._toggle_wallet_input)
        wallet_type_menu.grid(row=row, column=1, sticky="ew", padx=10, pady=2)
        row += 1
        # Private Key
        self.priv_label = ctk.CTkLabel(self.panel, text="Private Key:", **label_kwargs)
        self.priv_label.grid(row=row, column=0, sticky="w", padx=10, pady=2)
        self.vars['private_key'] = ctk.StringVar()
        self.priv_entry = ctk.CTkEntry(self.panel, textvariable=self.vars['private_key'], show="*", **entry_kwargs)
        self.priv_entry.grid(row=row, column=1, sticky="ew", padx=10, pady=2)
        # Seed Phrase
        self.seed_label = ctk.CTkLabel(self.panel, text="Seed Phrase:", **label_kwargs)
        self.vars['seed_phrase'] = ctk.StringVar()
        self.seed_entry = ctk.CTkEntry(self.panel, textvariable=self.vars['seed_phrase'], show="*", **entry_kwargs)
        row += 1
        # RPC URL
        ctk.CTkLabel(self.panel, text="RPC URL:", **label_kwargs).grid(row=row, column=0, sticky="w", padx=10, pady=2)
        self.vars['rpc_url'] = ctk.StringVar(value=SOLANA_MAINNET_RPC)
        ctk.CTkEntry(self.panel, textvariable=self.vars['rpc_url'], **entry_kwargs).grid(row=row, column=1, sticky="ew", padx=10, pady=2)
        row += 1
        # Position Size
        ctk.CTkLabel(self.panel, text="Position Size (USD):", **label_kwargs).grid(row=row, column=0, sticky="w", padx=10, pady=2)
        self.vars['position_size'] = ctk.StringVar(value="2.0")
        ctk.CTkEntry(self.panel, textvariable=self.vars['position_size'], placeholder_text="e.g. 2.0", **entry_kwargs).grid(row=row, column=1, sticky="ew", padx=10, pady=2)
        row += 1
        # Take Profit
        ctk.CTkLabel(self.panel, text="Take Profit (%):", **label_kwargs).grid(row=row, column=0, sticky="w", padx=10, pady=2)
        self.vars['take_profit'] = ctk.StringVar(value="30")
        ctk.CTkEntry(self.panel, textvariable=self.vars['take_profit'], placeholder_text="e.g. 30", **entry_kwargs).grid(row=row, column=1, sticky="ew", padx=10, pady=2)
        row += 1
        # Stop Loss
        ctk.CTkLabel(self.panel, text="Stop Loss (%):", **label_kwargs).grid(row=row, column=0, sticky="w", padx=10, pady=2)
        self.vars['stop_loss'] = ctk.StringVar(value="15")
        ctk.CTkEntry(self.panel, textvariable=self.vars['stop_loss'], placeholder_text="e.g. 15", **entry_kwargs).grid(row=row, column=1, sticky="ew", padx=10, pady=2)
        row += 1
        # Min Liquidity
        ctk.CTkLabel(self.panel, text="Min Liquidity (USD):", **label_kwargs).grid(row=row, column=0, sticky="w", padx=10, pady=2)
        self.vars['min_liquidity'] = ctk.StringVar(value="10000.0")
        ctk.CTkEntry(self.panel, textvariable=self.vars['min_liquidity'], placeholder_text="e.g. 10000", **entry_kwargs).grid(row=row, column=1, sticky="ew", padx=10, pady=2)
        row += 1
        # Min Volume 5m
        ctk.CTkLabel(self.panel, text="Min Volume (5m, USD):", **label_kwargs).grid(row=row, column=0, sticky="w", padx=10, pady=2)
        self.vars['min_volume_5m_usd'] = ctk.StringVar(value="2000.0")
        ctk.CTkEntry(self.panel, textvariable=self.vars['min_volume_5m_usd'], placeholder_text="e.g. 2000", **entry_kwargs).grid(row=row, column=1, sticky="ew", padx=10, pady=2)
        row += 1
        # Max Price
        ctk.CTkLabel(self.panel, text="Max Price (USD):", **label_kwargs).grid(row=row, column=0, sticky="w", padx=10, pady=2)
        self.vars['max_price'] = ctk.StringVar(value="1.0")
        ctk.CTkEntry(self.panel, textvariable=self.vars['max_price'], placeholder_text="e.g. 1.0", **entry_kwargs).grid(row=row, column=1, sticky="ew", padx=10, pady=2)
        row += 1
        # Min Pair Age
        ctk.CTkLabel(self.panel, text="Min Pair Age (s):", **label_kwargs).grid(row=row, column=0, sticky="w", padx=10, pady=2)
        self.vars['min_pair_age'] = ctk.StringVar(value="60")
        ctk.CTkEntry(self.panel, textvariable=self.vars['min_pair_age'], placeholder_text="e.g. 60", **entry_kwargs).grid(row=row, column=1, sticky="ew", padx=10, pady=2)
        row += 1
        # Max Pair Age
        ctk.CTkLabel(self.panel, text="Max Pair Age (s):", **label_kwargs).grid(row=row, column=0, sticky="w", padx=10, pady=2)
        self.vars['max_pair_age'] = ctk.StringVar(value="1800")
        ctk.CTkEntry(self.panel, textvariable=self.vars['max_pair_age'], placeholder_text="e.g. 1800", **entry_kwargs).grid(row=row, column=1, sticky="ew", padx=10, pady=2)
        row += 1
        # Min Buys 5m
        ctk.CTkLabel(self.panel, text="Min Buys (5m):", **label_kwargs).grid(row=row, column=0, sticky="w", padx=10, pady=2)
        self.vars['min_buys_5m'] = ctk.StringVar(value="20")
        ctk.CTkEntry(self.panel, textvariable=self.vars['min_buys_5m'], placeholder_text="e.g. 20", **entry_kwargs).grid(row=row, column=1, sticky="ew", padx=10, pady=2)
        row += 1
        # Min Buy/Sell Ratio
        ctk.CTkLabel(self.panel, text="Min Buy/Sell Ratio:", **label_kwargs).grid(row=row, column=0, sticky="w", padx=10, pady=2)
        self.vars['min_buy_tx_ratio'] = ctk.StringVar(value="1.05")
        ctk.CTkEntry(self.panel, textvariable=self.vars['min_buy_tx_ratio'], placeholder_text="e.g. 1.05", **entry_kwargs).grid(row=row, column=1, sticky="ew", padx=10, pady=2)
        row += 1
        # Duration
        ctk.CTkLabel(self.panel, text="Session Duration (min):", **label_kwargs).grid(row=row, column=0, sticky="w", padx=10, pady=2)
        self.vars['duration'] = ctk.StringVar(value="120")
        ctk.CTkEntry(self.panel, textvariable=self.vars['duration'], placeholder_text="e.g. 120", **entry_kwargs).grid(row=row, column=1, sticky="ew", padx=10, pady=2)
        row += 1
        # --- Advanced Filters ---
        # Require Socials
        ctk.CTkLabel(self.panel, text="Require Socials:", **label_kwargs).grid(row=row, column=0, sticky="w", padx=10, pady=2)
        self.vars['require_socials'] = ctk.BooleanVar()
        ctk.CTkCheckBox(self.panel, variable=self.vars['require_socials'], text="Enable", **button_kwargs).grid(row=row, column=1, sticky="w", padx=10, pady=2)
        row += 1
        # Min % Burned
        ctk.CTkLabel(self.panel, text="Min % Burned:", **label_kwargs).grid(row=row, column=0, sticky="w", padx=10, pady=2)
        self.vars['min_percent_burned'] = ctk.StringVar(value="0")
        ctk.CTkEntry(self.panel, textvariable=self.vars['min_percent_burned'], placeholder_text="e.g. 0", **entry_kwargs).grid(row=row, column=1, sticky="ew", padx=10, pady=2)
        row += 1
        # Require Immutable Metadata
        ctk.CTkLabel(self.panel, text="Require Immutable Metadata:", **label_kwargs).grid(row=row, column=0, sticky="w", padx=10, pady=2)
        self.vars['require_immutable'] = ctk.BooleanVar()
        ctk.CTkCheckBox(self.panel, variable=self.vars['require_immutable'], text="Enable", **button_kwargs).grid(row=row, column=1, sticky="w", padx=10, pady=2)
        row += 1
        # Max % in Top 5 Holders
        ctk.CTkLabel(self.panel, text="Max % in Top 5 Holders:", **label_kwargs).grid(row=row, column=0, sticky="w", padx=10, pady=2)
        self.vars['max_percent_top_holders'] = ctk.StringVar(value="100")
        ctk.CTkEntry(self.panel, textvariable=self.vars['max_percent_top_holders'], placeholder_text="e.g. 100", **entry_kwargs).grid(row=row, column=1, sticky="ew", padx=10, pady=2)
        row += 1
        # Block Known Risky Wallets
        ctk.CTkLabel(self.panel, text="Block Known Risky Wallets:", **label_kwargs).grid(row=row, column=0, sticky="w", padx=10, pady=2)
        self.vars['block_risky_wallets'] = ctk.BooleanVar()
        ctk.CTkCheckBox(self.panel, variable=self.vars['block_risky_wallets'], text="Enable", **button_kwargs).grid(row=row, column=1, sticky="w", padx=10, pady=2)
        row += 1
        # Simulation Mode
        ctk.CTkLabel(self.panel, text="Simulation Mode:", **label_kwargs).grid(row=row, column=0, sticky="w", padx=10, pady=2)
        self.vars['simulation'] = ctk.BooleanVar()
        ctk.CTkCheckBox(self.panel, variable=self.vars['simulation'], text="Enable", **button_kwargs).grid(row=row, column=1, sticky="w", padx=10, pady=2)
        row += 1
        # Save/Apply Button
        self.apply_btn = ctk.CTkButton(self.panel, text="Save / Apply", command=self._on_apply, **button_kwargs)
        self.apply_btn.grid(row=row, column=0, columnspan=2, pady=(10, 5))
        self.panel.grid_columnconfigure(1, weight=1)
        self._toggle_wallet_input(self.vars['wallet_type'].get())
        self.load_settings()
        self.after(1000, self._update_state)

    def _toggle_wallet_input(self, wallet_type):
        if wallet_type == "private":
            self.priv_label.grid()
            self.priv_entry.grid()
            self.seed_label.grid_remove()
            self.seed_entry.grid_remove()
        else:
            self.priv_label.grid_remove()
            self.priv_entry.grid_remove()
            self.seed_label.grid(row=2, column=0, sticky="w", padx=10, pady=2)
            self.seed_entry.grid(row=2, column=1, sticky="ew", padx=10, pady=2)

    def _update_state(self):
        running = self.get_bot_status() == "Running"
        state = "disabled" if running else "normal"
        for var in self.vars.values():
            if hasattr(var, 'set'):
                pass  # keep variable
        for widget in self.winfo_children():
            if isinstance(widget, (ctk.CTkEntry, ctk.CTkOptionMenu, ctk.CTkCheckBox)):
                widget.configure(state=state)
        self.apply_btn.configure(state=state)
        self.after(1000, self._update_state)

    def _on_apply(self):
        self.save_settings()
        self.on_apply(self.get_settings())

    def get_settings(self):
        return {
            "wallet_type": self.vars['wallet_type'].get(),
            "private_key": self.vars['private_key'].get(),
            "seed_phrase": self.vars['seed_phrase'].get(),
            "rpc_url": self.vars['rpc_url'].get(),
            "position_size": float(self.vars['position_size'].get()),
            "take_profit": float(self.vars['take_profit'].get()),
            "stop_loss": float(self.vars['stop_loss'].get()),
            "min_liquidity": float(self.vars['min_liquidity'].get()),
            "min_volume_5m_usd": float(self.vars['min_volume_5m_usd'].get()),
            "max_price": float(self.vars['max_price'].get()),
            "min_pair_age": int(self.vars['min_pair_age'].get()),
            "max_pair_age": int(self.vars['max_pair_age'].get()),
            "min_buys_5m": int(self.vars['min_buys_5m'].get()),
            "min_buy_tx_ratio": float(self.vars['min_buy_tx_ratio'].get()),
            "duration": int(self.vars['duration'].get()),
            "require_socials": self.vars['require_socials'].get(),
            "min_percent_burned": float(self.vars['min_percent_burned'].get()),
            "require_immutable": self.vars['require_immutable'].get(),
            "max_percent_top_holders": float(self.vars['max_percent_top_holders'].get()),
            "block_risky_wallets": self.vars['block_risky_wallets'].get(),
            "simulation": self.vars['simulation'].get(),
        }

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
            for k, v in data.items():
                if k in self.vars:
                    if isinstance(self.vars[k], ctk.BooleanVar):
                        self.vars[k].set(bool(v))
                    else:
                        self.vars[k].set(v)
        # If no value in settings, set default for RPC URL
        if not self.vars['rpc_url'].get():
            self.vars['rpc_url'].set(SOLANA_MAINNET_RPC)
        if not self.vars['min_buy_tx_ratio'].get():
            self.vars['min_buy_tx_ratio'].set("1.05")
        if not self.vars['min_percent_burned'].get():
            self.vars['min_percent_burned'].set("0")
        if not self.vars['max_percent_top_holders'].get():
            self.vars['max_percent_top_holders'].set("100")

    def save_settings(self):
        data = self.get_settings()
        # Preserve the license key if present
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                existing = json.load(f)
            if "license_key" in existing:
                data["license_key"] = existing["license_key"]
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)

class LicenseFrame(ctk.CTkFrame):
    def __init__(self, master, get_license_status, on_activate, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.configure(fg_color=TURBO_BLACK)
        self.panel = ctk.CTkFrame(self, fg_color=TURBO_NAVY, corner_radius=14)
        self.panel.pack(expand=True, fill="both", pady=40, padx=40)
        self.panel.pack_propagate(False)
        label = ctk.CTkLabel(self.panel, text="Enter License Key", **label_kwargs)
        label.pack(pady=(40, 10))
        self.entry = ctk.CTkEntry(self.panel, **entry_kwargs)
        self.entry.pack(pady=10)
        self.activate_btn = ctk.CTkButton(self.panel, text="Activate", **button_kwargs, command=self._activate)
        self.activate_btn.pack(pady=10)
        self.status_label = ctk.CTkLabel(self.panel, text="", font=("Montserrat", 14, "bold"), fg_color="transparent")
        self.status_label.pack(pady=10)
        self.get_license_status = get_license_status
        self.on_activate = on_activate
        # Show status on startup
        self.refresh_status()
        # If a license key is present, fill it in the entry
        key = master.license_key if hasattr(master, 'license_key') else ""
        if key:
            self.entry.delete(0, "end")
            self.entry.insert(0, key)

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
        self.panel = ctk.CTkFrame(self, fg_color=TURBO_NAVY, corner_radius=14)
        self.panel.pack(expand=True, fill="both", pady=40, padx=40)
        self.panel.pack_propagate(False)
        try:
            from PIL import Image
            logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
            if os.path.exists(logo_path):
                img = Image.open(logo_path).convert("RGBA").resize((80, 80))
                self.logo_img = ctk.CTkImage(light_image=img, dark_image=img, size=(80, 80))
                ctk.CTkLabel(self.panel, image=self.logo_img, text="", fg_color="transparent").pack(pady=(30, 10))
            else:
                ctk.CTkLabel(self.panel, text="[Turbo Logo]", **label_kwargs).pack(pady=(30, 10))
        except Exception as e:
            print("AboutFrame logo load error:", e)
            ctk.CTkLabel(self.panel, text="[Turbo Logo]", **label_kwargs).pack(pady=(30, 10))
        ctk.CTkLabel(self.panel, text=APP_NAME, **label_kwargs).pack(pady=(0, 5))
        ctk.CTkLabel(self.panel, text=f"Version {APP_VERSION}", **label_kwargs).pack(pady=(0, 10))
        ctk.CTkLabel(self.panel, text=f"by {COMPANY}", **label_kwargs).pack(pady=(0, 10))
        ctk.CTkLabel(self.panel, text=f"Contact: {SUPPORT_EMAIL}", **label_kwargs).pack(pady=(0, 2))
        label_kwargs_blue = label_kwargs.copy()
        label_kwargs_blue["text_color"] = TURBO_CYAN
        ctk.CTkLabel(self.panel, text=f"Website: {WEBSITE}", **label_kwargs_blue).pack(pady=(0, 2))
        ctk.CTkLabel(self.panel, text=f"Telegram: {TELEGRAM}", **label_kwargs).pack(pady=(0, 2))
        ctk.CTkLabel(self.panel, text="\u00A9 2024 Turbo. All rights reserved.", **label_kwargs).pack(pady=(20, 0))

class ManualBuyFrame(ctk.CTkFrame):
    def __init__(self, master, fetch_token_info_callback, manual_buy_callback, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.fetch_token_info_callback = fetch_token_info_callback
        self.manual_buy_callback = manual_buy_callback
        self.address_var = ctk.StringVar()
        ctk.CTkLabel(self, text="Paste Token Address:").pack(pady=10)
        ctk.CTkEntry(self, textvariable=self.address_var, width=400).pack(pady=5)
        ctk.CTkButton(self, text="Fetch Info", command=self.fetch_info).pack(pady=5)
        self.info_label = ctk.CTkLabel(self, text="Token info will appear here.")
        self.info_label.pack(pady=10)
        self.buy_button = ctk.CTkButton(self, text="Buy", command=self.buy_token)
        self.buy_button.pack(pady=5)
        self.warning_label = ctk.CTkLabel(self, text="Warning: Manual buy ignores all filters and settings. Proceed with caution!", text_color="orange")
        self.warning_label.pack(pady=5)
        self.log_label = ctk.CTkLabel(self, text="", wraplength=500)
        self.log_label.pack(pady=10)
        self.retry_button = ctk.CTkButton(self, text="Retry Buy", command=self.buy_token)
        self.retry_button.pack(pady=5)
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
                self.retry_button.pack(pady=5)
            elif not result:
                self.log_label.configure(text=(
                    "Token is tradable, but the buy failed.\n"
                    "Please check your wallet balance, network status, or try again."
                ))
                self.retry_button.pack(pady=5)
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
        # Show only the dashboard at first
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
            if os.path.exists("logo.ico"):
                img = Image.open("logo.ico")
                icon = ImageTk.PhotoImage(img)
                self.wm_iconphoto(True, icon)
            elif os.path.exists("logo.png"):
                img = Image.open("logo.png").resize((32, 32))
                icon = ImageTk.PhotoImage(img)
                self.wm_iconphoto(True, icon)
        except Exception:
            pass  # If PIL or logo not available, skip icon
        # For Windows packaging: use logo.ico for best results with PyInstaller

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
            current = sol_balance * sol_usd
            trades = getattr(self.session, 'trades', [])
            total_trades = len(trades)
            if total_trades == 0:
                pnl_usd = 0
                pnl_pct = 0
                pnl_str = "$0.00 (+0.00%)"
                win_rate = "0.0%"
            else:
                pnl_usd = current - initial
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

if __name__ == "__main__":
    app = MainApp()
    app.mainloop() 