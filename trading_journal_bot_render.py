#!/usr/bin/env python3
"""
Personal Trading Journal Bot
Professional trade tracking with forms, P&L calculations, and analytics
"""

import discord
from discord.ext import commands
import sqlite3
import json
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import asyncio
from typing import Optional, Dict, List

load_dotenv()

print("📊 Starting Trading Journal Bot...")

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Database setup
def init_database():
    """Initialize SQLite database for trades"""
    conn = sqlite3.connect('trading_journal.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            trade_id TEXT UNIQUE NOT NULL,
            symbol TEXT NOT NULL,
            trade_type TEXT NOT NULL,
            entry_price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            entry_date TEXT NOT NULL,
            entry_time TEXT NOT NULL,
            stop_loss REAL,
            take_profit REAL,
            trade_reason TEXT,
            setup_type TEXT,
            risk_amount REAL,
            exit_price REAL,
            exit_date TEXT,
            exit_time TEXT,
            exit_reason TEXT,
            pnl REAL,
            pnl_percentage REAL,
            commission REAL DEFAULT 0,
            status TEXT DEFAULT 'OPEN',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            default_risk_percent REAL DEFAULT 1.0,
            default_commission REAL DEFAULT 0.0,
            account_size REAL DEFAULT 10000.0,
            preferred_timeframe TEXT DEFAULT 'Daily'
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database on startup
init_database()

class TradeEntryModal(discord.ui.Modal):
    """Modal form for entering new trades"""
    
    def __init__(self):
        super().__init__(title="📈 New Trade Entry", timeout=300)
        
        # Trade details
        self.symbol = discord.ui.TextInput(
            label="Symbol/Ticker",
            placeholder="e.g., AAPL, SPY, TSLA",
            required=True,
            max_length=10
        )
        
        self.trade_type = discord.ui.TextInput(
            label="Trade Type",
            placeholder="LONG, SHORT, CALL, PUT",
            required=True,
            max_length=10
        )
        
        self.entry_price = discord.ui.TextInput(
            label="Entry Price",
            placeholder="e.g., 150.50",
            required=True,
            max_length=15
        )
        
        self.quantity = discord.ui.TextInput(
            label="Quantity/Shares",
            placeholder="e.g., 100 shares or 1 contract",
            required=True,
            max_length=10
        )
        
        self.trade_reason = discord.ui.TextInput(
            label="Why did you take this trade?",
            placeholder="Describe your setup, analysis, and reasoning...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )
        
        # Add all inputs
        self.add_item(self.symbol)
        self.add_item(self.trade_type)
        self.add_item(self.entry_price)
        self.add_item(self.quantity)
        self.add_item(self.trade_reason)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Validate inputs
            symbol = self.symbol.value.upper().strip()
            trade_type = self.trade_type.value.upper().strip()
            entry_price = float(self.entry_price.value)
            quantity = int(self.quantity.value)
            trade_reason = self.trade_reason.value.strip()
            
            # Generate unique trade ID
            now = datetime.now()
            trade_id = f"{symbol}_{now.strftime('%Y%m%d_%H%M%S')}"
            
            # Create follow-up modal for additional details
            await interaction.response.send_modal(
                TradeDetailsModal(symbol, trade_type, entry_price, quantity, trade_reason, trade_id)
            )
            
        except ValueError:
            await interaction.response.send_message(
                "❌ **Invalid Input**\nPlease check your entry price and quantity values.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ **Error**: {str(e)}",
                ephemeral=True
            )

class TradeDetailsModal(discord.ui.Modal):
    """Second modal for additional trade details"""
    
    def __init__(self, symbol, trade_type, entry_price, quantity, trade_reason, trade_id):
        super().__init__(title="📊 Trade Details", timeout=300)
        
        self.symbol = symbol
        self.trade_type = trade_type
        self.entry_price = entry_price
        self.quantity = quantity
        self.trade_reason = trade_reason
        self.trade_id = trade_id
        
        # Additional details
        self.stop_loss = discord.ui.TextInput(
            label="Stop Loss (Optional)",
            placeholder="e.g., 145.00",
            required=False,
            max_length=15
        )
        
        self.take_profit = discord.ui.TextInput(
            label="Take Profit Target (Optional)",
            placeholder="e.g., 160.00",
            required=False,
            max_length=15
        )
        
        self.setup_type = discord.ui.TextInput(
            label="Setup Type",
            placeholder="e.g., Breakout, Support/Resistance, Moving Average",
            required=False,
            max_length=50
        )
        
        self.risk_amount = discord.ui.TextInput(
            label="Risk Amount ($)",
            placeholder="e.g., 200 (how much you're willing to lose)",
            required=False,
            max_length=15
        )
        
        # Add inputs
        self.add_item(self.stop_loss)
        self.add_item(self.take_profit)
        self.add_item(self.setup_type)
        self.add_item(self.risk_amount)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Process optional fields
            stop_loss = float(self.stop_loss.value) if self.stop_loss.value else None
            take_profit = float(self.take_profit.value) if self.take_profit.value else None
            setup_type = self.setup_type.value.strip() if self.setup_type.value else None
            risk_amount = float(self.risk_amount.value) if self.risk_amount.value else None
            
            # Save trade to database
            trade_data = {
                'user_id': interaction.user.id,
                'username': interaction.user.display_name,
                'trade_id': self.trade_id,
                'symbol': self.symbol,
                'trade_type': self.trade_type,
                'entry_price': self.entry_price,
                'quantity': self.quantity,
                'entry_date': datetime.now().strftime('%Y-%m-%d'),
                'entry_time': datetime.now().strftime('%H:%M:%S'),
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'trade_reason': self.trade_reason,
                'setup_type': setup_type,
                'risk_amount': risk_amount,
                'status': 'OPEN'
            }
            
            success = save_trade_to_db(trade_data)
            
            if success:
                # Create beautiful confirmation embed
                embed = create_trade_entry_embed(trade_data)
                view = TradeManagementView(self.trade_id)
                
                await interaction.response.send_message(
                    f"✅ **Trade Logged Successfully!**\nTrade ID: `{self.trade_id}`",
                    embed=embed,
                    view=view
                )
            else:
                await interaction.response.send_message(
                    "❌ **Error saving trade**. Please try again.",
                    ephemeral=True
                )
                
        except ValueError:
            await interaction.response.send_message(
                "❌ **Invalid Input**\nPlease check your numerical values.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ **Error**: {str(e)}",
                ephemeral=True
            )

class TradeExitModal(discord.ui.Modal):
    """Modal for closing/exiting trades"""
    
    def __init__(self, trade_id):
        super().__init__(title="📉 Close Trade", timeout=300)
        self.trade_id = trade_id
        
        self.exit_price = discord.ui.TextInput(
            label="Exit Price",
            placeholder="e.g., 155.75",
            required=True,
            max_length=15
        )
        
        self.exit_reason = discord.ui.TextInput(
            label="Exit Reason",
            placeholder="Why did you close this trade?",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500
        )
        
        self.commission = discord.ui.TextInput(
            label="Total Commission/Fees",
            placeholder="e.g., 2.50 (optional)",
            required=False,
            max_length=10
        )
        
        self.add_item(self.exit_price)
        self.add_item(self.exit_reason)
        self.add_item(self.commission)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            exit_price = float(self.exit_price.value)
            exit_reason = self.exit_reason.value.strip()
            commission = float(self.commission.value) if self.commission.value else 0.0
            
            # Update trade in database
            success = close_trade_in_db(
                self.trade_id, 
                exit_price, 
                exit_reason, 
                commission,
                interaction.user.id
            )
            
            if success:
                # Get updated trade data with P&L
                trade_data = get_trade_from_db(self.trade_id)
                if trade_data:
                    embed = create_trade_exit_embed(trade_data)
                    await interaction.response.send_message(
                        f"✅ **Trade Closed Successfully!**\nTrade ID: `{self.trade_id}`",
                        embed=embed
                    )
                else:
                    await interaction.response.send_message(
                        "✅ Trade closed but error retrieving updated data.",
                        ephemeral=True
                    )
            else:
                await interaction.response.send_message(
                    "❌ **Error closing trade**. Please check the trade ID and try again.",
                    ephemeral=True
                )
                
        except ValueError:
            await interaction.response.send_message(
                "❌ **Invalid Input**\nPlease check your exit price and commission values.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ **Error**: {str(e)}",
                ephemeral=True
            )

class TradingJournalView(discord.ui.View):
    """Main trading journal interface"""
    
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="📈 New Trade", 
        style=discord.ButtonStyle.primary, 
        custom_id="new_trade",
        emoji="💰"
    )
    async def new_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open new trade entry form"""
        modal = TradeEntryModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(
        label="📉 Close Trade", 
        style=discord.ButtonStyle.secondary, 
        custom_id="close_trade",
        emoji="🔒"
    )
    async def close_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show close trade interface"""
        view = CloseTradeSelectView(interaction.user.id)
        await interaction.response.send_message(
            "📉 **Select a trade to close:**",
            view=view,
            ephemeral=True
        )
    
    @discord.ui.button(
        label="📊 My Trades", 
        style=discord.ButtonStyle.success, 
        custom_id="view_trades",
        emoji="📋"
    )
    async def view_trades(self, interaction: discord.Interaction, button: discord.ui.Button):
        """View user's trades"""
        trades = get_user_trades(interaction.user.id)
        if trades:
            embed = create_trades_summary_embed(trades, interaction.user.display_name)
            view = TradesPaginationView(trades, interaction.user.id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(
                "📭 **No trades found**\nStart by logging your first trade!",
                ephemeral=True
            )
    
    @discord.ui.button(
        label="📈 Analytics", 
        style=discord.ButtonStyle.danger, 
        custom_id="analytics",
        emoji="📊"
    )
    async def analytics(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show trading analytics"""
        analytics = calculate_user_analytics(interaction.user.id)
        if analytics:
            embed = create_analytics_embed(analytics, interaction.user.display_name)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(
                "📊 **No analytics available**\nComplete some trades first!",
                ephemeral=True
            )

class CloseTradeSelectView(discord.ui.View):
    """View for selecting which trade to close"""
    
    def __init__(self, user_id):
        super().__init__(timeout=300)
        self.user_id = user_id
        
        # Get open trades
        open_trades = get_open_trades(user_id)
        
        if open_trades:
            options = []
            for trade in open_trades[:25]:  # Max 25 options
                entry_date = trade[6]  # entry_date
                options.append(
                    discord.SelectOption(
                        label=f"{trade[3]} - {trade[4]}",  # symbol - trade_type
                        value=trade[2],  # trade_id
                        description=f"Entry: ${trade[5]:.2f} on {entry_date}",
                        emoji="📈" if trade[4] in ['LONG', 'CALL'] else "📉"
                    )
                )
            
            select = discord.ui.Select(
                placeholder="Choose a trade to close...",
                options=options,
                custom_id="trade_selector"
            )
            
            async def select_callback(interaction):
                trade_id = select.values[0]
                modal = TradeExitModal(trade_id)
                await interaction.response.send_modal(modal)
            
            select.callback = select_callback
            self.add_item(select)
        else:
            # No open trades
            pass

class TradeManagementView(discord.ui.View):
    """View for managing individual trades"""
    
    def __init__(self, trade_id):
        super().__init__(timeout=600)
        self.trade_id = trade_id
    
    @discord.ui.button(label="📉 Close This Trade", style=discord.ButtonStyle.danger, emoji="🔒")
    async def close_this_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Close this specific trade"""
        modal = TradeExitModal(self.trade_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📝 View Details", style=discord.ButtonStyle.secondary, emoji="🔍")
    async def view_details(self, interaction: discord.Interaction, button: discord.ui.Button):
        """View detailed trade information"""
        trade_data = get_trade_from_db(self.trade_id)
        if trade_data:
            embed = create_detailed_trade_embed(trade_data)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(
                "❌ Trade not found",
                ephemeral=True
            )

class TradesPaginationView(discord.ui.View):
    """Pagination view for trades list"""
    
    def __init__(self, trades, user_id):
        super().__init__(timeout=300)
        self.trades = trades
        self.user_id = user_id
        self.current_page = 0
        self.trades_per_page = 5
        self.max_pages = (len(trades) - 1) // self.trades_per_page + 1
    
    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.secondary, disabled=True)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page"""
        if self.current_page > 0:
            self.current_page -= 1
            embed = create_trades_page_embed(self.trades, self.current_page, self.trades_per_page)
            
            # Update button states
            self.children[0].disabled = self.current_page <= 0
            self.children[1].disabled = self.current_page >= self.max_pages - 1
            
            await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page"""
        if self.current_page < self.max_pages - 1:
            self.current_page += 1
            embed = create_trades_page_embed(self.trades, self.current_page, self.trades_per_page)
            
            # Update button states
            self.children[0].disabled = self.current_page <= 0
            self.children[1].disabled = self.current_page >= self.max_pages - 1
            
            await interaction.response.edit_message(embed=embed, view=self)

# Database functions
def save_trade_to_db(trade_data):
    """Save trade to database"""
    try:
        conn = sqlite3.connect('trading_journal.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO trades (
                user_id, username, trade_id, symbol, trade_type,
                entry_price, quantity, entry_date, entry_time,
                stop_loss, take_profit, trade_reason, setup_type,
                risk_amount, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            trade_data['user_id'], trade_data['username'], trade_data['trade_id'],
            trade_data['symbol'], trade_data['trade_type'], trade_data['entry_price'],
            trade_data['quantity'], trade_data['entry_date'], trade_data['entry_time'],
            trade_data['stop_loss'], trade_data['take_profit'], trade_data['trade_reason'],
            trade_data['setup_type'], trade_data['risk_amount'], trade_data['status']
        ))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        print(f"Error saving trade: {e}")
        return False

def close_trade_in_db(trade_id, exit_price, exit_reason, commission, user_id):
    """Close trade and calculate P&L"""
    try:
        conn = sqlite3.connect('trading_journal.db')
        cursor = conn.cursor()
        
        # Get trade data first
        cursor.execute('SELECT * FROM trades WHERE trade_id = ? AND user_id = ?', (trade_id, user_id))
        trade = cursor.fetchone()
        
        if not trade:
            return False
        
        # Calculate P&L
        entry_price = trade[5]  # entry_price column
        quantity = trade[6]      # quantity column
        trade_type = trade[4]    # trade_type column
        
        if trade_type in ['LONG', 'CALL']:
            pnl = (exit_price - entry_price) * quantity - commission
        else:  # SHORT, PUT
            pnl = (entry_price - exit_price) * quantity - commission
        
        # Calculate percentage
        investment = entry_price * quantity
        pnl_percentage = (pnl / investment) * 100 if investment > 0 else 0
        
        # Update trade
        cursor.execute('''
            UPDATE trades SET 
                exit_price = ?, exit_date = ?, exit_time = ?,
                exit_reason = ?, pnl = ?, pnl_percentage = ?,
                commission = ?, status = ?
            WHERE trade_id = ? AND user_id = ?
        ''', (
            exit_price, datetime.now().strftime('%Y-%m-%d'), 
            datetime.now().strftime('%H:%M:%S'), exit_reason,
            pnl, pnl_percentage, commission, 'CLOSED', trade_id, user_id
        ))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        print(f"Error closing trade: {e}")
        return False

def get_trade_from_db(trade_id):
    """Get specific trade from database"""
    try:
        conn = sqlite3.connect('trading_journal.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM trades WHERE trade_id = ?', (trade_id,))
        trade = cursor.fetchone()
        
        conn.close()
        return trade
        
    except Exception as e:
        print(f"Error getting trade: {e}")
        return None

def get_user_trades(user_id, limit=50):
    """Get all trades for a user"""
    try:
        conn = sqlite3.connect('trading_journal.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM trades 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (user_id, limit))
        
        trades = cursor.fetchall()
        conn.close()
        return trades
        
    except Exception as e:
        print(f"Error getting user trades: {e}")
        return []

def get_open_trades(user_id):
    """Get open trades for a user"""
    try:
        conn = sqlite3.connect('trading_journal.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM trades 
            WHERE user_id = ? AND status = 'OPEN'
            ORDER BY created_at DESC
        ''', (user_id,))
        
        trades = cursor.fetchall()
        conn.close()
        return trades
        
    except Exception as e:
        print(f"Error getting open trades: {e}")
        return []

def calculate_user_analytics(user_id):
    """Calculate trading analytics for user"""
    try:
        conn = sqlite3.connect('trading_journal.db')
        cursor = conn.cursor()
        
        # Get closed trades
        cursor.execute('''
            SELECT * FROM trades 
            WHERE user_id = ? AND status = 'CLOSED' AND pnl IS NOT NULL
        ''', (user_id,))
        
        trades = cursor.fetchall()
        conn.close()
        
        if not trades:
            return None
        
        # Calculate analytics
        total_trades = len(trades)
        winning_trades = len([t for t in trades if t[19] > 0])  # pnl column
        losing_trades = len([t for t in trades if t[19] < 0])
        
        total_pnl = sum(t[19] for t in trades)
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
        
        avg_win = sum(t[19] for t in trades if t[19] > 0) / winning_trades if winning_trades > 0 else 0
        avg_loss = sum(t[19] for t in trades if t[19] < 0) / losing_trades if losing_trades > 0 else 0
        
        profit_factor = abs(avg_win * winning_trades) / abs(avg_loss * losing_trades) if losing_trades > 0 and avg_loss != 0 else float('inf')
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'best_trade': max(t[19] for t in trades),
            'worst_trade': min(t[19] for t in trades)
        }
        
    except Exception as e:
        print(f"Error calculating analytics: {e}")
        return None

# Embed creation functions
def create_trade_entry_embed(trade_data):
    """Create embed for new trade entry"""
    color = 0x00ff88 if trade_data['trade_type'] in ['LONG', 'CALL'] else 0xff6b6b
    
    embed = discord.Embed(
        title=f"📈 Trade Logged: {trade_data['symbol']}",
        description=f"**{trade_data['trade_type']}** position opened",
        color=color,
        timestamp=datetime.now()
    )
    
    # Trade details
    embed.add_field(
        name="💰 Entry Details",
        value=f"**Price:** ${trade_data['entry_price']:.2f}\n**Quantity:** {trade_data['quantity']}\n**Date:** {trade_data['entry_date']} {trade_data['entry_time']}",
        inline=True
    )
    
    # Risk management
    risk_text = ""
    if trade_data['stop_loss']:
        risk_text += f"**Stop Loss:** ${trade_data['stop_loss']:.2f}\n"
    if trade_data['take_profit']:
        risk_text += f"**Take Profit:** ${trade_data['take_profit']:.2f}\n"
    if trade_data['risk_amount']:
        risk_text += f"**Risk Amount:** ${trade_data['risk_amount']:.2f}"
    
    if risk_text:
        embed.add_field(
            name="⚖️ Risk Management",
            value=risk_text,
            inline=True
        )
    
    # Setup and reason
    if trade_data['setup_type']:
        embed.add_field(
            name="🎯 Setup Type",
            value=trade_data['setup_type'],
            inline=True
        )
    
    embed.add_field(
        name="📝 Trade Reason",
        value=trade_data['trade_reason'][:200] + "..." if len(trade_data['trade_reason']) > 200 else trade_data['trade_reason'],
        inline=False
    )
    
    embed.set_footer(text=f"Trade ID: {trade_data['trade_id']} • Status: OPEN")
    
    return embed

def create_trade_exit_embed(trade_data):
    """Create embed for trade exit"""
    pnl = trade_data[19]  # pnl column
    color = 0x00ff88 if pnl > 0 else 0xff6b6b if pnl < 0 else 0xffd700
    
    embed = discord.Embed(
        title=f"📉 Trade Closed: {trade_data[3]}",  # symbol
        description=f"**{trade_data[4]}** position closed",  # trade_type
        color=color,
        timestamp=datetime.now()
    )
    
    # Entry vs Exit
    embed.add_field(
        name="📊 Trade Summary",
        value=f"**Entry:** ${trade_data[5]:.2f}\n**Exit:** ${trade_data[15]:.2f}\n**Quantity:** {trade_data[6]}",
        inline=True
    )
    
    # P&L
    pnl_emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
    embed.add_field(
        name="💰 Profit/Loss",
        value=f"{pnl_emoji} **${pnl:.2f}**\n**{trade_data[20]:.1f}%**",  # pnl_percentage
        inline=True
    )
    
    # Dates
    embed.add_field(
        name="📅 Duration",
        value=f"**Opened:** {trade_data[7]}\n**Closed:** {trade_data[16]}",  # entry_date, exit_date
        inline=True
    )
    
    # Exit reason
    embed.add_field(
        name="📝 Exit Reason",
        value=trade_data[18][:200] + "..." if len(trade_data[18]) > 200 else trade_data[18],  # exit_reason
        inline=False
    )
    
    embed.set_footer(text=f"Trade ID: {trade_data[2]} • Status: CLOSED")  # trade_id
    
    return embed

def create_trades_summary_embed(trades, username):
    """Create summary embed for user's trades"""
    total_trades = len(trades)
    open_trades = len([t for t in trades if t[23] == 'OPEN'])  # status column
    closed_trades = len([t for t in trades if t[23] == 'CLOSED'])
    
    embed = discord.Embed(
        title=f"📊 {username}'s Trading Journal",
        description=f"**Total Trades:** {total_trades}",
        color=0x3498db,
        timestamp=datetime.now()
    )
    
    embed.add_field(
        name="📈 Trade Status",
        value=f"**Open:** {open_trades}\n**Closed:** {closed_trades}",
        inline=True
    )
    
    # Calculate basic stats for closed trades
    closed_with_pnl = [t for t in trades if t[23] == 'CLOSED' and t[19] is not None]
    if closed_with_pnl:
        total_pnl = sum(t[19] for t in closed_with_pnl)
        winning_trades = len([t for t in closed_with_pnl if t[19] > 0])
        win_rate = (winning_trades / len(closed_with_pnl)) * 100
        
        pnl_emoji = "🟢" if total_pnl > 0 else "🔴" if total_pnl < 0 else "⚪"
        
        embed.add_field(
            name="💰 Performance",
            value=f"{pnl_emoji} **${total_pnl:.2f}**\n**Win Rate:** {win_rate:.1f}%",
            inline=True
        )
    
    # Recent trades preview
    recent_trades = trades[:3]  # Last 3 trades
    if recent_trades:
        recent_text = ""
        for trade in recent_trades:
            status_emoji = "🟢" if trade[23] == 'OPEN' else "🔴"
            recent_text += f"{status_emoji} **{trade[3]}** {trade[4]} - ${trade[5]:.2f}\n"
        
        embed.add_field(
            name="📋 Recent Trades",
            value=recent_text,
            inline=False
        )
    
    embed.set_footer(text="💡 Use pagination buttons to view all trades")
    
    return embed

def create_trades_page_embed(trades, page, trades_per_page):
    """Create paginated embed for trades"""
    start_idx = page * trades_per_page
    end_idx = start_idx + trades_per_page
    page_trades = trades[start_idx:end_idx]
    
    embed = discord.Embed(
        title=f"📋 Your Trades - Page {page + 1}",
        color=0x3498db,
        timestamp=datetime.now()
    )
    
    for trade in page_trades:
        # Trade info
        symbol = trade[3]
        trade_type = trade[4]
        entry_price = trade[5]
        status = trade[23]
        trade_id = trade[2]
        
        # Status emoji and P&L
        if status == 'OPEN':
            status_emoji = "🟢"
            pnl_text = "Open Position"
        else:
            pnl = trade[19] if trade[19] is not None else 0
            status_emoji = "💚" if pnl > 0 else "❤️" if pnl < 0 else "💛"
            pnl_text = f"${pnl:.2f} ({trade[20]:.1f}%)" if trade[20] else f"${pnl:.2f}"
        
        embed.add_field(
            name=f"{status_emoji} {symbol} - {trade_type}",
            value=f"**Entry:** ${entry_price:.2f}\n**P&L:** {pnl_text}\n**ID:** `{trade_id}`",
            inline=True
        )
    
    total_pages = (len(trades) - 1) // trades_per_page + 1
    embed.set_footer(text=f"Page {page + 1} of {total_pages} • {len(trades)} total trades")
    
    return embed

def create_detailed_trade_embed(trade_data):
    """Create detailed embed for a specific trade"""
    symbol = trade_data[3]
    trade_type = trade_data[4]
    status = trade_data[23]
    
    color = 0x00ff88 if trade_type in ['LONG', 'CALL'] else 0xff6b6b
    
    embed = discord.Embed(
        title=f"🔍 Trade Details: {symbol}",
        description=f"**{trade_type}** • Status: **{status}**",
        color=color,
        timestamp=datetime.now()
    )
    
    # Entry details
    embed.add_field(
        name="📈 Entry Information",
        value=f"**Price:** ${trade_data[5]:.2f}\n**Quantity:** {trade_data[6]}\n**Date:** {trade_data[7]} {trade_data[8]}",
        inline=True
    )
    
    # Exit details (if closed)
    if status == 'CLOSED' and trade_data[15]:  # exit_price exists
        embed.add_field(
            name="📉 Exit Information",
            value=f"**Price:** ${trade_data[15]:.2f}\n**Date:** {trade_data[16]} {trade_data[17]}\n**P&L:** ${trade_data[19]:.2f}",
            inline=True
        )
    
    # Risk management
    risk_text = ""
    if trade_data[9]:  # stop_loss
        risk_text += f"**Stop Loss:** ${trade_data[9]:.2f}\n"
    if trade_data[10]:  # take_profit
        risk_text += f"**Take Profit:** ${trade_data[10]:.2f}\n"
    if trade_data[13]:  # risk_amount
        risk_text += f"**Risk Amount:** ${trade_data[13]:.2f}"
    
    if risk_text:
        embed.add_field(
            name="⚖️ Risk Management",
            value=risk_text,
            inline=True
        )
    
    # Setup and reasoning
    if trade_data[12]:  # setup_type
        embed.add_field(
            name="🎯 Setup Type",
            value=trade_data[12],
            inline=True
        )
    
    embed.add_field(
        name="📝 Trade Reason",
        value=trade_data[11][:500] + "..." if len(trade_data[11]) > 500 else trade_data[11],
        inline=False
    )
    
    if status == 'CLOSED' and trade_data[18]:  # exit_reason
        embed.add_field(
            name="📝 Exit Reason",
            value=trade_data[18][:500] + "..." if len(trade_data[18]) > 500 else trade_data[18],
            inline=False
        )
    
    embed.set_footer(text=f"Trade ID: {trade_data[2]} • Created: {trade_data[24]}")
    
    return embed

def create_analytics_embed(analytics, username):
    """Create analytics embed"""
    embed = discord.Embed(
        title=f"📊 {username}'s Trading Analytics",
        description="**Performance Overview**",
        color=0x9b59b6,
        timestamp=datetime.now()
    )
    
    # Basic stats
    embed.add_field(
        name="📈 Trade Statistics",
        value=f"**Total Trades:** {analytics['total_trades']}\n**Win Rate:** {analytics['win_rate']:.1f}%\n**Winners:** {analytics['winning_trades']}\n**Losers:** {analytics['losing_trades']}",
        inline=True
    )
    
    # P&L
    total_pnl = analytics['total_pnl']
    pnl_emoji = "🟢" if total_pnl > 0 else "🔴" if total_pnl < 0 else "⚪"
    
    embed.add_field(
        name="💰 Profit & Loss",
        value=f"{pnl_emoji} **Total P&L:** ${total_pnl:.2f}\n**Avg Win:** ${analytics['avg_win']:.2f}\n**Avg Loss:** ${analytics['avg_loss']:.2f}",
        inline=True
    )
    
    # Performance metrics
    profit_factor = analytics['profit_factor']
    pf_display = f"{profit_factor:.2f}" if profit_factor != float('inf') else "∞"
    
    embed.add_field(
        name="📊 Performance Metrics",
        value=f"**Profit Factor:** {pf_display}\n**Best Trade:** ${analytics['best_trade']:.2f}\n**Worst Trade:** ${analytics['worst_trade']:.2f}",
        inline=True
    )
    
    # Performance analysis
    analysis_text = ""
    if analytics['win_rate'] >= 60:
        analysis_text += "🎯 **Excellent win rate!**\n"
    elif analytics['win_rate'] >= 50:
        analysis_text += "👍 **Good win rate**\n"
    else:
        analysis_text += "📈 **Focus on trade selection**\n"
    
    if profit_factor > 2:
        analysis_text += "💎 **Strong profit factor**\n"
    elif profit_factor > 1:
        analysis_text += "📊 **Profitable overall**\n"
    else:
        analysis_text += "⚠️ **Review risk management**\n"
    
    if abs(analytics['avg_loss']) > analytics['avg_win']:
        analysis_text += "🛡️ **Consider tighter stops**"
    else:
        analysis_text += "✅ **Good risk/reward ratio**"
    
    embed.add_field(
        name="🎯 Analysis",
        value=analysis_text,
        inline=False
    )
    
    embed.set_footer(text="💡 Based on closed trades only")
    
    return embed

@bot.event
async def on_ready():
    print(f'✅ {bot.user} is online!')
    print('📊 Trading Journal Bot ready!')
    
    try:
        await setup_trading_channels()
    except Exception as e:
        print(f"Setup error: {e}")

async def setup_trading_channels():
    """Setup specific trading journal channels for Alex and Kyle"""
    try:
        guild = bot.guilds[0] if bot.guilds else None
        if not guild:
            print("❌ No guild found")
            return
        
        # Create or find trading journal category
        category = discord.utils.get(guild.categories, name="📊 Trading Journals")
        if not category:
            category = await guild.create_category("📊 Trading Journals")
        
        # Specific channels for Alex and Kyle
        channels_to_create = [
            {"name": "alex-trades", "display_name": "Alex"},
            {"name": "kyle-trades", "display_name": "Kyle"}
        ]
        
        for channel_info in channels_to_create:
            channel_name = channel_info["name"]
            display_name = channel_info["display_name"]
            
            channel = discord.utils.get(guild.text_channels, name=channel_name)
            
            if not channel:
                # Create the trading channel
                channel = await guild.create_text_channel(
                    channel_name,
                    category=category,
                    topic=f"🔒 {display_name}'s private trading journal - Track trades, analyze performance"
                )
                print(f"✅ Created #{channel_name}")
            else:
                print(f"📍 Found existing #{channel_name}")
            
            # Setup journal interface in the channel
            await setup_personal_journal(channel, display_name)
        
        print(f"✅ Trading journal channels ready for Alex and Kyle!")
        
    except Exception as e:
        print(f"❌ Setup error: {e}")

async def setup_personal_journal(channel, display_name):
    """Setup personal trading journal interface"""
    try:
        # Clean old messages
        try:
            await channel.purge(limit=50, check=lambda m: m.author == bot.user)
        except:
            pass
        
        # Create personal journal interface
        embed = discord.Embed(
            title=f"📊 {display_name}'s Trading Journal",
            description="**Your Personal Trading Workspace**\n\n*Track every trade, analyze performance, and improve your strategy with professional-grade tools.*",
            color=0x2ecc71,
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="📈 Trade Management",
            value="• **New Trade** - Log entry with detailed form\n• **Close Trade** - Exit positions with P&L calculation\n• **View Trades** - Browse your trading history\n• **Analytics** - Performance metrics and insights",
            inline=False
        )
        
        embed.add_field(
            name="📊 What Gets Tracked",
            value="• **Entry & Exit Details** - Prices, dates, quantities\n• **Trade Reasoning** - Why you took the trade\n• **Risk Management** - Stop losses, position sizing\n• **Performance Metrics** - P&L, win rate, profit factor",
            inline=True
        )
        
        embed.add_field(
            name="🎯 Key Features",
            value="• **Automatic P&L** - Calculated on exit\n• **Trade History** - Searchable and paginated\n• **Performance Analytics** - Win rate, profit factor\n• **Private & Secure** - Only you can see your trades",
            inline=True
        )
        
        embed.add_field(
            name="💡 Quick Start Guide",
            value="1️⃣ Click **'📈 New Trade'** to log your first position\n2️⃣ Fill out the detailed entry form (2 steps)\n3️⃣ Come back and **'📉 Close Trade'** when you exit\n4️⃣ Review your **'📊 Analytics'** to improve performance",
            inline=False
        )
        
        embed.add_field(
            name="🔥 Pro Tips",
            value="• **Be detailed** in your trade reasoning - future you will thank you\n• **Set stops** on every trade for proper risk management\n• **Review analytics** weekly to spot patterns and improve\n• **Export data** monthly for deeper analysis",
            inline=False
        )
        
        embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/3135/3135715.png")
        embed.set_footer(text=f"🔒 Welcome to #{channel.name} • Your private trading journal")
        
        view = TradingJournalView()
        
        await channel.send(
            f"🎯 **Welcome to your personal trading journal, {display_name}!**\n*Everything you need to track and improve your trading performance*",
            embed=embed,
            view=view
        )
        
        # Send trading tips specific to the journal
        tips_embed = discord.Embed(
            title="💡 Trading Journal Best Practices",
            description="Get the most out of your trading journal",
            color=0xf39c12
        )
        
        tips_embed.add_field(
            name="📝 Journaling Excellence",
            value="• **Log every trade** - Winners and losers\n• **Write detailed reasons** - Why did you enter?\n• **Note your emotions** - Were you confident? FOMO?\n• **Review regularly** - What patterns do you see?",
            inline=True
        )
        
        tips_embed.add_field(
            name="⚖️ Risk Management",
            value="• **Always set stop losses** - Define risk upfront\n• **Position sizing** - Risk 1-2% per trade max\n• **R:R Ratio** - Target 2:1 or better rewards\n• **Max positions** - Don't over-leverage account",
            inline=True
        )
        
        tips_embed.add_field(
            name="📊 Performance Tracking",
            value="• **Win rate** isn't everything - focus on profit factor\n• **Average win** should be > average loss\n• **Consecutive losses** - when to take a break\n• **Monthly reviews** - spot improvement areas",
            inline=False
        )
        
        await channel.send(embed=tips_embed)
        
        # Add sample trade example
        example_embed = discord.Embed(
            title="📚 Example Trade Entry",
            description="Here's how to properly log a trade:",
            color=0x3498db
        )
        
        example_embed.add_field(
            name="📈 Entry Example",
            value="**Symbol:** AAPL\n**Type:** LONG\n**Entry:** $150.50\n**Quantity:** 100 shares\n**Stop Loss:** $148.00\n**Target:** $155.00",
            inline=True
        )
        
        example_embed.add_field(
            name="📝 Reasoning Example",
            value="\"AAPL breaking above resistance at $150 with strong volume. RSI showing bullish momentum, and broader market is trending up. Risk/reward is 2.5:1 with clear stop below support.\"",
            inline=False
        )
        
        example_embed.add_field(
            name="📉 Exit Example",
            value="**Exit:** $154.25\n**Reason:** \"Target nearly reached, taking profits as RSI hit overbought and volume declining.\"\n**Result:** +$375 (+2.49%)",
            inline=False
        )
        
        await channel.send(embed=example_embed)
        
        print(f"✅ Setup complete for {display_name} in #{channel.name}")
        
    except Exception as e:
        print(f"Error setting up personal journal for {display_name}: {e}")

@bot.command(name='setup_journal')
async def manual_setup(ctx):
    """Manually setup trading journal channels for Alex and Kyle"""
    if ctx.author.guild_permissions.administrator:
        await setup_trading_channels()
        await ctx.send("✅ **Trading journal setup complete!**\n📊 Channels created: #alex-trades and #kyle-trades")
    else:
        await ctx.send("❌ Admin permissions required to setup channels")

@bot.command(name='reset_journal')
async def reset_journal(ctx, channel_name=None):
    """Reset a specific journal channel"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Admin permissions required")
        return
    
    if channel_name in ["alex-trades", "kyle-trades"]:
        channel = discord.utils.get(ctx.guild.text_channels, name=channel_name)
        if channel:
            display_name = "Alex" if channel_name == "alex-trades" else "Kyle"
            await setup_personal_journal(channel, display_name)
            await ctx.send(f"✅ **#{channel_name} reset successfully!**")
        else:
            await ctx.send(f"❌ Channel #{channel_name} not found")
    else:
        await ctx.send("❌ Invalid channel. Use: alex-trades or kyle-trades")

@bot.command(name='trade_stats')
async def quick_stats(ctx):
    """Quick command to see trade statistics"""
    analytics = calculate_user_analytics(ctx.author.id)
    if analytics:
        embed = create_analytics_embed(analytics, ctx.author.display_name)
        await ctx.send(embed=embed)
    else:
        await ctx.send("📊 No trading data found. Start logging trades in your personal journal!")

@bot.command(name='export_trades')
async def export_trades(ctx):
    """Export trades to CSV format"""
    trades = get_user_trades(ctx.author.id, limit=1000)
    if trades:
        # Create CSV content
        csv_content = "Trade ID,Symbol,Type,Entry Price,Quantity,Entry Date,Exit Price,Exit Date,P&L,P&L %,Status\n"
        
        for trade in trades:
            csv_content += f"{trade[2]},{trade[3]},{trade[4]},{trade[5]},{trade[6]},{trade[7]},{trade[15] or 'N/A'},{trade[16] or 'N/A'},{trade[19] or 'N/A'},{trade[20] or 'N/A'},{trade[23]}\n"
        
        # Create file
        import io
        file = discord.File(io.StringIO(csv_content), filename=f"{ctx.author.display_name}_trades.csv")
        
        await ctx.send(
            f"📊 **Trade Export Complete**\nHere are your {len(trades)} trades in CSV format:",
            file=file
        )
    else:
        await ctx.send("📭 No trades found to export")

if __name__ == "__main__":
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    
    if not TOKEN:
        print("❌ Error: DISCORD_BOT_TOKEN environment variable not set!")
        print("Please add your Discord bot token as an environment variable")
        exit(1)
    
    print("📊 Starting Trading Journal Bot...")
    print("Will auto-create trading channels for Alex and Kyle!")
    print("🌐 Running on Render hosting platform")
    
    try:
        # Keep the bot alive for Render deployment
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Invalid Discord bot token! Please check your token")
        exit(1)
    except Exception as e:
        print(f"❌ Bot error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)