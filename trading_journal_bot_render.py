    @discord.ui.button(label="💹 Live P&L", style=discord.ButtonStyle.primary, emoji="📊")
    async def live_pnl(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show live P&L for this trade"""
        if not POLYGON_API_KEY:
            await interaction.response.send_message(
                "❌ **Live P&L requires Polygon API key**\nAdd POLYGON_API_KEY environment variable to enable real-time data.",
                ephemeral=True
            )
            return
            
        trade_data = get_trade_from_db(self.trade_id)
        if trade_data and trade_data[22] == 'OPEN':  # status column
            symbol = trade_data[4]  # symbol
            current_price = await polygon.get_current_price(symbol)
            
            if current_price:
                embed = await create_live_pnl_embed(trade_data, current_price)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(
                    "❌ Unable to fetch current market price",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "❌ Trade not found or already closed",
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
            embed = await create_trades_page_embed(self.trades, self.current_page, self.trades_per_page)
            
            # Update button states
            self.children[0].disabled = self.current_page <= 0
            self.children[1].disabled = self.current_page >= self.max_pages - 1
            
            await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page"""
        if self.current_page < self.max_pages - 1:
            self.current_page += 1
            embed = await create_trades_page_embed(self.trades, self.current_page, self.trades_per_page)
            
            # Update button states
            self.children[0].disabled = self.current_page <= 0
            self.children[1].disabled = self.current_page >= self.max_pages - 1
            
            await interaction.response.edit_message(embed=embed, view=self)

# Database functions with better error handling and Polygon integration
def save_trade_to_db(trade_data):
    """Save trade to database with market price data"""
    try:
        db_path = os.path.join(os.getcwd(), 'trading_journal.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO trades (
                user_id, username, trade_id, symbol, trade_type,
                entry_price, quantity, entry_date, entry_time,
                stop_loss, take_profit, trade_reason, setup_type,
                risk_amount, status, market_price_at_entry
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            trade_data['user_id'], trade_data['username'], trade_data['trade_id'],
            trade_data['symbol'], trade_data['trade_type'], trade_data['entry_price'],
            trade_data['quantity'], trade_data['entry_date'], trade_data['entry_time'],
            trade_data['stop_loss'], trade_data['take_profit'], trade_data['trade_reason'],
            trade_data['setup_type'], trade_data['risk_amount'], trade_data['status'],
            trade_data.get('market_price_at_entry')
        ))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        print(f"Error saving trade: {e}")
        if 'conn' in locals():
            conn.close()
        return False

def close_trade_in_db(trade_id, exit_price, exit_reason, commission, user_id, market_price_at_exit=None):
    """Close trade and calculate P&L with market price tracking"""
    try:
        db_path = os.path.join(os.getcwd(), 'trading_journal.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get trade data first
        cursor.execute('SELECT * FROM trades WHERE trade_id = ? AND user_id = ?', (trade_id, user_id))
        trade = cursor.fetchone()
        
        if not trade:
            conn.close()
            return False
        
        # Calculate P&L
        entry_price = trade[6]    # entry_price column
        quantity = trade[7]       # quantity column
        trade_type = trade[5]     # trade_type column
        
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
                commission = ?, status = ?, market_price_at_exit = ?
            WHERE trade_id = ? AND user_id = ?
        ''', (
            exit_price, datetime.now().strftime('%Y-%m-%d'), 
            datetime.now().strftime('%H:%M:%S'), exit_reason,
            pnl, pnl_percentage, commission, 'CLOSED', market_price_at_exit,
            trade_id, user_id
        ))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        print(f"Error closing trade: {e}")
        if 'conn' in locals():
            conn.close()
        return False

def get_trade_from_db(trade_id):
    """Get specific trade from database"""
    try:
        db_path = os.path.join(os.getcwd(), 'trading_journal.db')
        conn = sqlite3.connect(db_path)
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
        db_path = os.path.join(os.getcwd(), 'trading_journal.db')
        conn = sqlite3.connect(db_path)
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
        db_path = os.path.join(os.getcwd(), 'trading_journal.db')
        conn = sqlite3.connect(db_path)
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
        db_path = os.path.join(os.getcwd(), 'trading_journal.db')
        conn = sqlite3.connect(db_path)
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

# Enhanced embed creation functions with Polygon API integration
async def create_trade_entry_embed(trade_data):
    """Create embed for new trade entry with market data"""
    color = 0x00ff88 if trade_data['trade_type'] in ['LONG', 'CALL'] else 0xff6b6b
    
    embed = discord.Embed(
        title=f"📈 Trade Logged: {trade_data['symbol']}",
        description=f"**{trade_data['trade_type']}** position opened",
        color=color,
        timestamp=datetime.now()
    )
    
    # Trade details with market comparison
    entry_info = f"**Price:** ${trade_data['entry_price']:.2f}\n**Quantity:** {trade_data['quantity']}\n**Date:** {trade_data['entry_date']} {trade_data['entry_time']}"
    
    if trade_data.get('market_price_at_entry') and trade_data['market_price_at_entry'] != trade_data['entry_price']:
        diff = trade_data['entry_price'] - trade_data['market_price_at_entry']
        diff_pct = (diff / trade_data['market_price_at_entry']) * 100
        entry_info += f"\n**Market Price:** ${trade_data['market_price_at_entry']:.2f}"
        entry_info += f"\n**Diff:** {diff:+.2f} ({diff_pct:+.1f}%)"
    
    embed.set_footer(text=f"Quote updated at {datetime.now().strftime('%H:%M:%S')}")
    
    return embed

def create_multi_price_embed(price_data):
    """Create embed for multiple symbol price check"""
    embed = discord.Embed(
        title="🔍 Multi-Symbol Price Check",
        color=0x3498db,
        timestamp=datetime.now()
    )
    
    found_prices = []
    not_found = []
    
    for symbol, price in price_data.items():
        if price:
            found_prices.append(f"**{symbol}:** ${price:.2f}")
        else:
            not_found.append(symbol)
    
    if found_prices:
        # Split into chunks if too many symbols
        chunk_size = 10
        for i in range(0, len(found_prices), chunk_size):
            chunk = found_prices[i:i+chunk_size]
            field_name = "💰 Current Prices" if i == 0 else f"💰 Prices (continued {i//chunk_size + 1})"
            embed.add_field(
                name=field_name,
                value="\n".join(chunk),
                inline=True
            )
    
    if not_found:
        embed.add_field(
            name="❌ Not Found",
            value=", ".join(not_found),
            inline=False
        )
    
    embed.set_footer(text="Real-time data from Polygon.io")
    
    return embed

async def create_live_pnl_embed(trade_data, current_price):
    """Create embed showing live P&L for an open trade"""
    symbol = trade_data[4]
    trade_type = trade_data[5]
    entry_price = trade_data[6]
    quantity = trade_data[7]
    
    # Calculate live P&L
    if trade_type in ['LONG', 'CALL']:
        live_pnl = (current_price - entry_price) * quantity
    else:  # SHORT, PUT
        live_pnl = (entry_price - current_price) * quantity
    
    investment = entry_price * quantity
    live_pnl_pct = (live_pnl / investment) * 100 if investment > 0 else 0
    
    # Color based on P&L
    color = 0x00ff88 if live_pnl > 0 else 0xff6b6b if live_pnl < 0 else 0xffd700
    
    embed = discord.Embed(
        title=f"📊 Live P&L: {symbol}",
        description=f"**{trade_type}** position • Real-time performance",
        color=color,
        timestamp=datetime.now()
    )
    
    # Trade details
    embed.add_field(
        name="📈 Position Details",
        value=f"**Entry Price:** ${entry_price:.2f}\n**Current Price:** ${current_price:.2f}\n**Quantity:** {quantity}",
        inline=True
    )
    
    # Live P&L
    pnl_emoji = "🟢" if live_pnl > 0 else "🔴" if live_pnl < 0 else "⚪"
    embed.add_field(
        name="💰 Live Performance",
        value=f"{pnl_emoji} **P&L:** ${live_pnl:+.2f}\n**Percentage:** {live_pnl_pct:+.1f}%\n**Per Share:** ${live_pnl/quantity:+.2f}" if quantity > 0 else f"{pnl_emoji} **P&L:** ${live_pnl:+.2f}\n**Percentage:** {live_pnl_pct:+.1f}%",
        inline=True
    )
    
    # Price movement
    price_change = current_price - entry_price
    price_change_pct = (price_change / entry_price) * 100
    
    embed.add_field(
        name="📊 Price Movement",
        value=f"**Change:** ${price_change:+.2f}\n**Change %:** {price_change_pct:+.1f}%",
        inline=True
    )
    
    # Risk management info if available
    if trade_data[10] or trade_data[11]:  # stop_loss or take_profit
        risk_text = ""
        if trade_data[10]:  # stop_loss
            stop_distance = abs(current_price - trade_data[10])
            risk_text += f"**Stop Loss:** ${trade_data[10]:.2f} (${stop_distance:.2f} away)\n"
        if trade_data[11]:  # take_profit
            target_distance = abs(trade_data[11] - current_price)
            risk_text += f"**Take Profit:** ${trade_data[11]:.2f} (${target_distance:.2f} away)"
        
        embed.add_field(
            name="⚖️ Risk Levels",
            value=risk_text,
            inline=False
        )
    
    embed.set_footer(text=f"Trade ID: {trade_data[3]} • Live data from Polygon.io")
    
    return embed

# Signal handler for graceful shutdown
def signal_handler(signum, frame):
    print(f'\n📊 Received signal {signum}. Shutting down gracefully...')
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

@bot.event
async def on_ready():
    print(f'✅ {bot.user} is online!')
    print('📊 Trading Journal Bot with Polygon API ready!')
    
    # Check Polygon API configuration
    if POLYGON_API_KEY:
        print('✅ Polygon API key found - live market data enabled')
    else:
        print('⚠️ No Polygon API key - market data features will be limited')
    
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
                    topic=f"🔒 {display_name}'s private trading journal - Track trades, analyze performance, live market data"
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
    """Setup personal trading journal interface with Polygon features"""
    try:
        # Clean old messages
        try:
            await channel.purge(limit=50, check=lambda m: m.author == bot.user)
        except:
            pass
        
        # Create personal journal interface
        embed = discord.Embed(
            title=f"📊 {display_name}'s Trading Journal",
            description="**Your Personal Trading Workspace with Live Market Data**\n\n*Track every trade, analyze performance, and access real-time market data with professional-grade tools powered by Polygon.io*",
            color=0x2ecc71,
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="📈 Trade Management",
            value="• **New Trade** - Log entry with detailed form and live price validation\n• **Close Trade** - Exit positions with real-time P&L calculation\n• **View Trades** - Browse history with live P&L for open positions\n• **Analytics** - Performance metrics and insights",
            inline=False
        )
        
        embed.add_field(
            name="💹 Market Data Features",
            value="• **Live Quotes** - Real-time bid/ask spreads\n• **Price Validation** - Symbol verification on entry\n• **Market Orders** - Use 'MARKET' for current price\n• **Live P&L** - Real-time performance tracking",
            inline=True
        )
        
        embed.add_field(
            name="🎯 Enhanced Features",
            value="• **Automatic P&L** - Calculated with live market data\n• **Price Comparisons** - Entry vs market price tracking\n• **Live Monitoring** - Real-time P&L for open positions\n• **Market Validation** - Symbol verification via Polygon API",
            inline=True
        )
        
        embed.add_field(
            name="💡 Quick Start Guide",
            value="1️⃣ Click **'📈 New Trade'** and use 'MARKET' for live pricing\n2️⃣ Fill out the detailed entry form (symbols auto-validated)\n3️⃣ Monitor **'💹 Market Data'** for real-time quotes\n4️⃣ Use **'📉 Close Trade'** with live exit pricing\n5️⃣ Review **'📊 Analytics'** with enhanced market insights",
            inline=False
        )
        
        embed.add_field(
            name="🔥 Pro Tips with Live Data",
            value="• **Use 'MARKET'** in price fields for real-time execution prices\n• **Monitor live P&L** on open positions via trade details\n• **Check quotes** before entering trades for better fills\n• **Validate symbols** automatically with Polygon integration\n• **Track price differences** between your fills and market prices",
            inline=False
        )
        
        # Add API status
        api_status = "🟢 Live Market Data Active" if POLYGON_API_KEY else "🟡 Limited Mode (Add POLYGON_API_KEY for full features)"
        embed.add_field(
            name="🔌 Market Data Status",
            value=api_status,
            inline=False
        )
        
        embed.set_footer(text=f"🔒 Welcome to #{channel.name} • Your private trading journal with live market data")
        
        view = TradingJournalView()
        
        await channel.send(
            f"🎯 **Welcome to your enhanced trading journal, {display_name}!**\n*Now with real-time market data integration via Polygon.io*",
            embed=embed,
            view=view
        )
        
        print(f"✅ Setup complete for {display_name} in #{channel.name}")
        
    except Exception as e:
        print(f"Error setting up personal journal for {display_name}: {e}")

# Enhanced commands with Polygon integration
@bot.command(name='setup_journal')
async def manual_setup(ctx):
    """Manually setup trading journal channels for Alex and Kyle"""
    if ctx.author.guild_permissions.administrator:
        await setup_trading_channels()
        api_note = " with live market data" if POLYGON_API_KEY else " (add POLYGON_API_KEY for market data)"
        await ctx.send(f"✅ **Trading journal setup complete{api_note}!**\n📊 Channels created: #alex-trades and #kyle-trades")
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
            await ctx.send(f"✅ **#{channel_name} reset successfully with enhanced features!**")
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

@bot.command(name='quote')
async def get_quote_command(ctx, symbol):
    """Get real-time quote for a symbol"""
    if not POLYGON_API_KEY:
        await ctx.send("❌ Polygon API key required for market data features")
        return
    
    try:
        symbol = symbol.upper().strip()
        current_price = await polygon.get_current_price(symbol)
        quote_data = await polygon.get_quote(symbol)
        prev_close = await polygon.get_previous_close(symbol)
        
        if current_price or quote_data:
            embed = await create_quote_embed(symbol, current_price, quote_data, prev_close)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Unable to fetch quote for `{symbol}`")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name='price')
async def get_price_command(ctx, *symbols):
    """Get current prices for multiple symbols"""
    if not POLYGON_API_KEY:
        await ctx.send("❌ Polygon API key required for market data features")
        return
    
    if not symbols:
        await ctx.send("❌ Please provide at least one symbol. Example: `!price AAPL SPY`")
        return
    
    if len(symbols) > 10:
        await ctx.send("❌ Too many symbols. Please limit to 10 symbols per request.")
        return
    
    try:
        price_data = {}
        for symbol in symbols:
            symbol = symbol.upper().strip()
            price = await polygon.get_current_price(symbol)
            price_data[symbol] = price
        
        embed = create_multi_price_embed(price_data)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name='live_pnl')
async def live_pnl_command(ctx, trade_id=None):
    """Get live P&L for an open trade"""
    if not trade_id:
        await ctx.send("❌ Please provide a trade ID. Example: `!live_pnl AAPL_20250625_143022`")
        return
    
    try:
        trade_data = get_trade_from_db(trade_id)
        if not trade_data:
            await ctx.send("❌ Trade not found")
            return
        
        if trade_data[1] != ctx.author.id:  # user_id check
            await ctx.send("❌ You can only view your own trades")
            return
        
        if trade_data[22] != 'OPEN':  # status check
            await ctx.send("❌ This trade is already closed")
            return
        
        symbol = trade_data[4]
        current_price = await polygon.get_current_price(symbol)
        
        if current_price:
            embed = await create_live_pnl_embed(trade_data, current_price)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Unable to fetch current price for {symbol}")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name='export_trades')
async def export_trades(ctx):
    """Export trades to CSV format with market data"""
    trades = get_user_trades(ctx.author.id, limit=1000)
    if trades:
        # Create CSV content with enhanced data
        csv_content = "Trade ID,Symbol,Type,Entry Price,Market Price Entry,Quantity,Entry Date,Exit Price,Market Price Exit,Exit Date,P&L,P&L %,Status\n"
        
        for trade in trades:
            market_entry = trade[24] if len(trade) > 24 else 'N/A'
            market_exit = trade[25] if len(trade) > 25 else 'N/A'
            csv_content += f"{trade[3]},{trade[4]},{trade[5]},{trade[6]},{market_entry or 'N/A'},{trade[7]},{trade[8]},{trade[15] or 'N/A'},{market_exit or 'N/A'},{trade[16] or 'N/A'},{trade[19] or 'N/A'},{trade[20] or 'N/A'},{trade[22]}\n"
        
        # Create file
        file = discord.File(io.StringIO(csv_content), filename=f"{ctx.author.display_name}_trades_enhanced.csv")
        
        await ctx.send(
            f"📊 **Enhanced Trade Export Complete**\nHere are your {len(trades)} trades with market data in CSV format:",
            file=file
        )
    else:
        await ctx.send("📭 No trades found to export")

# Health check endpoint for Render
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Bot is running with Polygon API integration')
        else:
            self.send_response(404)
            self.end_headers()

def start_health_server():
    """Start health check server for Render"""
    try:
        port = int(os.getenv('PORT', 8080))
        server = HTTPServer(('0.0.0.0', port), HealthHandler)
        print(f"🌐 Health server starting on port {port}")
        server.serve_forever()
    except Exception as e:
        print(f"Health server error: {e}")

if __name__ == "__main__":
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    
    if not TOKEN:
        print("❌ Error: DISCORD_BOT_TOKEN environment variable not set!")
        print("Please add your Discord bot token as an environment variable")
        sys.exit(1)
    
    if not POLYGON_API_KEY:
        print("⚠️ Warning: POLYGON_API_KEY not set!")
        print("Market data features will be limited. Get your API key from polygon.io")
    
    print("📊 Starting Enhanced Trading Journal Bot...")
    print("🔗 Polygon.io integration enabled for live market data!")
    print("Will auto-create trading channels for Alex and Kyle!")
    print("🌐 Running on Render hosting platform")
    
    # Start health check server in background thread
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    try:
        # Keep the bot alive for Render deployment
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Invalid Discord bot token! Please check your token")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Bot error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)add_field(
        name="💰 Entry Details",
        value=entry_info,
        inline=True
    )
    
    # Risk management
    risk_text = ""
    if trade_data.get('stop_loss'):
        risk_text += f"**Stop Loss:** ${trade_data['stop_loss']:.2f}\n"
    if trade_data.get('take_profit'):
        risk_text += f"**Take Profit:** ${trade_data['take_profit']:.2f}\n"
    if trade_data.get('risk_amount'):
        risk_text += f"**Risk Amount:** ${trade_data['risk_amount']:.2f}"
    
    if risk_text:
        embed.add_field(
            name="⚖️ Risk Management",
            value=risk_text,
            inline=True
        )
    
    # Setup and reason
    if trade_data.get('setup_type'):
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

async def create_trade_exit_embed(trade_data):
    """Create embed for trade exit with market data"""
    pnl = trade_data[19]  # pnl column
    color = 0x00ff88 if pnl > 0 else 0xff6b6b if pnl < 0 else 0xffd700
    
    embed = discord.Embed(
        title=f"📉 Trade Closed: {trade_data[4]}",  # symbol
        description=f"**{trade_data[5]}** position closed",  # trade_type
        color=color,
        timestamp=datetime.now()
    )
    
    # Entry vs Exit with market data
    trade_summary = f"**Entry:** ${trade_data[6]:.2f}\n**Exit:** ${trade_data[15]:.2f}\n**Quantity:** {trade_data[7]}"
    
    # Add market price comparison if available
    if len(trade_data) > 25 and trade_data[25]:  # market_price_at_exit
        diff = trade_data[15] - trade_data[25]  # exit_price - market_price_at_exit
        diff_pct = (diff / trade_data[25]) * 100 if trade_data[25] != 0 else 0
        trade_summary += f"\n**Market Price:** ${trade_data[25]:.2f}"
        trade_summary += f"\n**Fill Diff:** {diff:+.2f} ({diff_pct:+.1f}%)"
    
    embed.add_field(
        name="📊 Trade Summary",
        value=trade_summary,
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
        value=f"**Opened:** {trade_data[8]}\n**Closed:** {trade_data[16]}",  # entry_date, exit_date
        inline=True
    )
    
    # Exit reason
    embed.add_field(
        name="📝 Exit Reason",
        value=trade_data[18][:200] + "..." if len(trade_data[18]) > 200 else trade_data[18],  # exit_reason
        inline=False
    )
    
    embed.set_footer(text=f"Trade ID: {trade_data[3]} • Status: CLOSED")  # trade_id
    
    return embed

async def create_trades_summary_embed(trades, username):
    """Create summary embed for user's trades with live data"""
    total_trades = len(trades)
    open_trades = len([t for t in trades if t[22] == 'OPEN'])  # status column
    closed_trades = len([t for t in trades if t[22] == 'CLOSED'])
    
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
    closed_with_pnl = [t for t in trades if t[22] == 'CLOSED' and t[19] is not None]
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
            status_emoji = "🟢" if trade[22] == 'OPEN' else "🔴"
            recent_text += f"{status_emoji} **{trade[4]}** {trade[5]} - ${trade[6]:.2f}\n"
        
        embed.add_field(
            name="📋 Recent Trades",
            value=recent_text,
            inline=False
        )
    
    embed.set_footer(text="💡 Use pagination buttons to view all trades")
    
    return embed

async def create_trades_page_embed(trades, page, trades_per_page):
    """Create paginated embed for trades with live P&L for open positions"""
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
        symbol = trade[4]
        trade_type = trade[5]
        entry_price = trade[6]
        status = trade[22]
        trade_id = trade[3]
        
        # Status emoji and P&L
        if status == 'OPEN':
            status_emoji = "🟢"
            # Try to get live P&L if API key available
            if POLYGON_API_KEY:
                current_price = await polygon.get_current_price(symbol)
                if current_price:
                    quantity = trade[7]
                    if trade_type in ['LONG', 'CALL']:
                        live_pnl = (current_price - entry_price) * quantity
                    else:
                        live_pnl = (entry_price - current_price) * quantity
                    pnl_text = f"Live: ${live_pnl:+.2f}"
                else:
                    pnl_text = "Open Position"
            else:
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

async def create_detailed_trade_embed(trade_data):
    """Create detailed embed for a specific trade with market data"""
    symbol = trade_data[4]
    trade_type = trade_data[5]
    status = trade_data[22]
    
    color = 0x00ff88 if trade_type in ['LONG', 'CALL'] else 0xff6b6b
    
    embed = discord.Embed(
        title=f"🔍 Trade Details: {symbol}",
        description=f"**{trade_type}** • Status: **{status}**",
        color=color,
        timestamp=datetime.now()
    )
    
    # Entry details with market data
    entry_info = f"**Price:** ${trade_data[6]:.2f}\n**Quantity:** {trade_data[7]}\n**Date:** {trade_data[8]} {trade_data[9]}"
    if len(trade_data) > 24 and trade_data[24]:  # market_price_at_entry
        entry_info += f"\n**Market Price:** ${trade_data[24]:.2f}"
    
    embed.add_field(
        name="📈 Entry Information",
        value=entry_info,
        inline=True
    )
    
    # Exit details (if closed)
    if status == 'CLOSED' and trade_data[15]:  # exit_price exists
        exit_info = f"**Price:** ${trade_data[15]:.2f}\n**Date:** {trade_data[16]} {trade_data[17]}\n**P&L:** ${trade_data[19]:.2f}"
        if len(trade_data) > 25 and trade_data[25]:  # market_price_at_exit
            exit_info += f"\n**Market Price:** ${trade_data[25]:.2f}"
        
        embed.add_field(
            name="📉 Exit Information",
            value=exit_info,
            inline=True
        )
    elif status == 'OPEN' and POLYGON_API_KEY:
        # Show live P&L
        current_price = await polygon.get_current_price(symbol)
        if current_price:
            quantity = trade_data[7]
            if trade_type in ['LONG', 'CALL']:
                live_pnl = (current_price - trade_data[6]) * quantity
            else:
                live_pnl = (trade_data[6] - current_price) * quantity
            live_pnl_pct = (live_pnl / (trade_data[6] * quantity)) * 100
            
            embed.add_field(
                name="📊 Live P&L",
                value=f"**Current Price:** ${current_price:.2f}\n**Live P&L:** ${live_pnl:+.2f}\n**Live %:** {live_pnl_pct:+.1f}%",
                inline=True
            )
    
    # Risk management
    risk_text = ""
    if trade_data[10]:  # stop_loss
        risk_text += f"**Stop Loss:** ${trade_data[10]:.2f}\n"
    if trade_data[11]:  # take_profit
        risk_text += f"**Take Profit:** ${trade_data[11]:.2f}\n"
    if trade_data[14]:  # risk_amount
        risk_text += f"**Risk Amount:** ${trade_data[14]:.2f}"
    
    if risk_text:
        embed.add_field(
            name="⚖️ Risk Management",
            value=risk_text,
            inline=True
        )
    
    # Setup and reasoning
    if trade_data[13]:  # setup_type
        embed.add_field(
            name="🎯 Setup Type",
            value=trade_data[13],
            inline=True
        )
    
    embed.add_field(
        name="📝 Trade Reason",
        value=trade_data[12][:500] + "..." if len(trade_data[12]) > 500 else trade_data[12],
        inline=False
    )
    
    if status == 'CLOSED' and trade_data[18]:  # exit_reason
        embed.add_field(
            name="📝 Exit Reason",
            value=trade_data[18][:500] + "..." if len(trade_data[18]) > 500 else trade_data[18],
            inline=False
        )
    
    embed.set_footer(text=f"Trade ID: {trade_data[3]} • Created: {trade_data[23]}")
    
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

# New embed functions for Polygon API features
async def create_quote_embed(symbol, current_price, quote_data, prev_close):
    """Create detailed quote embed with Polygon data"""
    embed = discord.Embed(
        title=f"💹 Real-Time Quote: {symbol}",
        color=0x3498db,
        timestamp=datetime.now()
    )
    
    if current_price:
        # Calculate change from previous close
        change = None
        change_pct = None
        if prev_close:
            change = current_price - prev_close
            change_pct = (change / prev_close) * 100
        
        price_text = f"**Last Price:** ${current_price:.2f}"
        if change is not None:
            change_emoji = "🟢" if change >= 0 else "🔴"
            price_text += f"\n{change_emoji} **Change:** {change:+.2f} ({change_pct:+.1f}%)"
        if prev_close:
            price_text += f"\n**Prev Close:** ${prev_close:.2f}"
        
        embed.add_field(
            name="💰 Price Information",
            value=price_text,
            inline=True
        )
    
    if quote_data:
        bid = quote_data.get('bid')
        ask = quote_data.get('ask')
        spread = quote_data.get('spread')
        
        if bid and ask:
            quote_text = f"**Bid:** ${bid:.2f}\n**Ask:** ${ask:.2f}"
            if spread:
                quote_text += f"\n**Spread:** ${spread:.2f}"
            
            embed.add_field(
                name="📊 Bid/Ask Quote",
                value=quote_text,
                inline=True
            )
    
    embed.add_field(
        name="ℹ️ Data Source",
        value="Real-time data from Polygon.io",
        inline=False
    )
    
    embed.#!/usr/bin/env python3
"""
Personal Trading Journal Bot with Polygon API Integration
Professional trade tracking with forms, P&L calculations, analytics, and real-time market data
BULLETPROOF VERSION - ALL DEPENDENCIES FIXED
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
import signal
import sys
import aiohttp
import io
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Load environment variables
load_dotenv()

print("📊 Starting Trading Journal Bot with Polygon API...")

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Polygon API configuration
POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')
POLYGON_BASE_URL = "https://api.polygon.io"

class PolygonAPI:
    """Polygon API wrapper for market data - using only aiohttp"""
    
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = POLYGON_BASE_URL
    
    async def get_current_price(self, symbol):
        """Get current/last price for a symbol"""
        if not self.api_key:
            return None
            
        try:
            url = f"{self.base_url}/v2/last/trade/{symbol.upper()}"
            params = {"apikey": self.api_key}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('status') == 'OK' and 'results' in data:
                            return data['results']['p']  # price
            return None
        except Exception as e:
            print(f"Polygon API error for {symbol}: {e}")
            return None
    
    async def get_quote(self, symbol):
        """Get current bid/ask quote for a symbol"""
        if not self.api_key:
            return None
            
        try:
            url = f"{self.base_url}/v2/last/nbbo/{symbol.upper()}"
            params = {"apikey": self.api_key}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('status') == 'OK' and 'results' in data:
                            results = data['results']
                            return {
                                'bid': results.get('P'),  # bid price
                                'ask': results.get('p'),  # ask price
                                'spread': results.get('p', 0) - results.get('P', 0)
                            }
            return None
        except Exception as e:
            print(f"Polygon quote error for {symbol}: {e}")
            return None
    
    async def get_previous_close(self, symbol):
        """Get previous day's closing price"""
        if not self.api_key:
            return None
            
        try:
            url = f"{self.base_url}/v2/aggs/ticker/{symbol.upper()}/prev"
            params = {"apikey": self.api_key}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('status') == 'OK' and 'results' in data:
                            return data['results'][0]['c']  # close price
            return None
        except Exception as e:
            print(f"Polygon prev close error for {symbol}: {e}")
            return None
    
    async def validate_symbol(self, symbol):
        """Check if symbol exists and get basic info"""
        if not self.api_key:
            return True  # Assume valid if no API key
            
        try:
            url = f"{self.base_url}/v3/reference/tickers/{symbol.upper()}"
            params = {"apikey": self.api_key}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('status') == 'OK'
            return False
        except Exception as e:
            print(f"Symbol validation error for {symbol}: {e}")
            return True  # Assume valid on error

# Initialize Polygon API
polygon = PolygonAPI(POLYGON_API_KEY)

# Database setup with better error handling
def init_database():
    """Initialize SQLite database for trades"""
    try:
        # Use absolute path for database
        db_path = os.path.join(os.getcwd(), 'trading_journal.db')
        conn = sqlite3.connect(db_path)
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
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                market_price_at_entry REAL,
                market_price_at_exit REAL
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
        
        # Add new columns if they don't exist (for existing databases)
        try:
            cursor.execute('ALTER TABLE trades ADD COLUMN market_price_at_entry REAL')
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        try:
            cursor.execute('ALTER TABLE trades ADD COLUMN market_price_at_exit REAL')
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        conn.commit()
        conn.close()
        print("✅ Database initialized successfully")
        return True
        
    except Exception as e:
        print(f"❌ Database initialization error: {e}")
        return False

# Initialize database on startup
if not init_database():
    print("❌ Failed to initialize database. Exiting...")
    sys.exit(1)

class TradeEntryModal(discord.ui.Modal):
    """Modal form for entering new trades with live price validation"""
    
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
            label="Entry Price (or 'MARKET' for current price)",
            placeholder="e.g., 150.50 or MARKET",
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
            entry_price_input = self.entry_price.value.strip()
            quantity = int(self.quantity.value)
            trade_reason = self.trade_reason.value.strip()
            
            # Validate symbol with Polygon API
            await interaction.response.defer(ephemeral=True)
            
            is_valid_symbol = await polygon.validate_symbol(symbol)
            if not is_valid_symbol and POLYGON_API_KEY:
                await interaction.followup.send(
                    f"❌ **Invalid Symbol**: `{symbol}` not found in market data.\nPlease check the symbol and try again.",
                    ephemeral=True
                )
                return
            
            # Handle market price vs manual price
            market_price = None
            if entry_price_input.upper() == 'MARKET':
                market_price = await polygon.get_current_price(symbol)
                if market_price:
                    entry_price = market_price
                    price_note = f" (Market price: ${market_price:.2f})"
                else:
                    await interaction.followup.send(
                        f"❌ **Unable to fetch market price** for {symbol}.\nPlease enter a manual price.",
                        ephemeral=True
                    )
                    return
            else:
                entry_price = float(entry_price_input)
                market_price = await polygon.get_current_price(symbol)
                price_note = ""
            
            # Generate unique trade ID
            now = datetime.now()
            trade_id = f"{symbol}_{now.strftime('%Y%m%d_%H%M%S')}"
            
            # Create follow-up modal for additional details
            modal = TradeDetailsModal(
                symbol, trade_type, entry_price, quantity, 
                trade_reason, trade_id, market_price
            )
            await interaction.followup.send_modal(modal)
            
        except ValueError:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ **Invalid Input**\nPlease check your entry price and quantity values.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ **Invalid Input**\nPlease check your entry price and quantity values.",
                    ephemeral=True
                )
        except Exception as e:
            print(f"Error in trade entry: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ **Error**: {str(e)}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ **Error**: {str(e)}",
                    ephemeral=True
                )

class TradeDetailsModal(discord.ui.Modal):
    """Second modal for additional trade details"""
    
    def __init__(self, symbol, trade_type, entry_price, quantity, trade_reason, trade_id, market_price=None):
        super().__init__(title="📊 Trade Details", timeout=300)
        
        self.symbol = symbol
        self.trade_type = trade_type
        self.entry_price = entry_price
        self.quantity = quantity
        self.trade_reason = trade_reason
        self.trade_id = trade_id
        self.market_price = market_price
        
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
                'status': 'OPEN',
                'market_price_at_entry': self.market_price
            }
            
            success = save_trade_to_db(trade_data)
            
            if success:
                # Create beautiful confirmation embed with market data
                embed = await create_trade_entry_embed(trade_data)
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
            print(f"Error in trade details: {e}")
            await interaction.response.send_message(
                f"❌ **Error**: {str(e)}",
                ephemeral=True
            )

class TradeExitModal(discord.ui.Modal):
    """Modal for closing/exiting trades with live price option"""
    
    def __init__(self, trade_id):
        super().__init__(title="📉 Close Trade", timeout=300)
        self.trade_id = trade_id
        
        self.exit_price = discord.ui.TextInput(
            label="Exit Price (or 'MARKET' for current price)",
            placeholder="e.g., 155.75 or MARKET",
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
            exit_price_input = self.exit_price.value.strip()
            exit_reason = self.exit_reason.value.strip()
            commission = float(self.commission.value) if self.commission.value else 0.0
            
            # Get trade data first
            trade_data = get_trade_from_db(self.trade_id)
            if not trade_data:
                await interaction.response.send_message(
                    "❌ **Trade not found**. Please check the trade ID.",
                    ephemeral=True
                )
                return
            
            symbol = trade_data[4]  # symbol column
            
            await interaction.response.defer(ephemeral=True)
            
            # Handle market price vs manual price
            market_price = None
            if exit_price_input.upper() == 'MARKET':
                market_price = await polygon.get_current_price(symbol)
                if market_price:
                    exit_price = market_price
                else:
                    await interaction.followup.send(
                        f"❌ **Unable to fetch market price** for {symbol}.\nPlease enter a manual price.",
                        ephemeral=True
                    )
                    return
            else:
                exit_price = float(exit_price_input)
                market_price = await polygon.get_current_price(symbol)
            
            # Update trade in database
            success = close_trade_in_db(
                self.trade_id, 
                exit_price, 
                exit_reason, 
                commission,
                interaction.user.id,
                market_price
            )
            
            if success:
                # Get updated trade data with P&L
                updated_trade_data = get_trade_from_db(self.trade_id)
                if updated_trade_data:
                    embed = await create_trade_exit_embed(updated_trade_data)
                    await interaction.followup.send(
                        f"✅ **Trade Closed Successfully!**\nTrade ID: `{self.trade_id}`",
                        embed=embed
                    )
                else:
                    await interaction.followup.send(
                        "✅ Trade closed but error retrieving updated data.",
                        ephemeral=True
                    )
            else:
                await interaction.followup.send(
                    "❌ **Error closing trade**. Please check the trade ID and try again.",
                    ephemeral=True
                )
                
        except ValueError:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ **Invalid Input**\nPlease check your exit price and commission values.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ **Invalid Input**\nPlease check your exit price and commission values.",
                    ephemeral=True
                )
        except Exception as e:
            print(f"Error in trade exit: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ **Error**: {str(e)}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
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
            embed = await create_trades_summary_embed(trades, interaction.user.display_name)
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
    
    @discord.ui.button(
        label="💹 Market Data", 
        style=discord.ButtonStyle.primary, 
        custom_id="market_data",
        emoji="📊"
    )
    async def market_data(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show market data interface"""
        if not POLYGON_API_KEY:
            await interaction.response.send_message(
                "❌ **Market data features require Polygon API key**\nAdd POLYGON_API_KEY environment variable to enable real-time data.",
                ephemeral=True
            )
            return
        
        view = MarketDataView()
        await interaction.response.send_message(
            "💹 **Market Data Tools**\nGet real-time quotes and price information:",
            view=view,
            ephemeral=True
        )

class MarketDataView(discord.ui.View):
    """View for market data tools"""
    
    def __init__(self):
        super().__init__(timeout=300)
    
    @discord.ui.button(label="📊 Get Quote", style=discord.ButtonStyle.primary, emoji="💲")
    async def get_quote(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Get real-time quote for a symbol"""
        modal = QuoteModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📈 Price Check", style=discord.ButtonStyle.secondary, emoji="🔍")
    async def price_check(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Quick price check for multiple symbols"""
        modal = PriceCheckModal()
        await interaction.response.send_modal(modal)

class QuoteModal(discord.ui.Modal):
    """Modal for getting detailed quote information"""
    
    def __init__(self):
        super().__init__(title="💹 Get Real-Time Quote", timeout=300)
        
        self.symbol = discord.ui.TextInput(
            label="Symbol/Ticker",
            placeholder="e.g., AAPL, SPY, TSLA",
            required=True,
            max_length=10
        )
        
        self.add_item(self.symbol)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            symbol = self.symbol.value.upper().strip()
            
            await interaction.response.defer(ephemeral=True)
            
            # Get comprehensive quote data
            current_price = await polygon.get_current_price(symbol)
            quote_data = await polygon.get_quote(symbol)
            prev_close = await polygon.get_previous_close(symbol)
            
            if current_price or quote_data:
                embed = await create_quote_embed(symbol, current_price, quote_data, prev_close)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(
                    f"❌ **Unable to fetch quote data** for `{symbol}`.\nPlease check the symbol and try again.",
                    ephemeral=True
                )
                
        except Exception as e:
            print(f"Error in quote lookup: {e}")
            await interaction.followup.send(
                f"❌ **Error**: {str(e)}",
                ephemeral=True
            )

class PriceCheckModal(discord.ui.Modal):
    """Modal for checking multiple symbol prices"""
    
    def __init__(self):
        super().__init__(title="🔍 Multi-Symbol Price Check", timeout=300)
        
        self.symbols = discord.ui.TextInput(
            label="Symbols (comma-separated)",
            placeholder="e.g., AAPL, SPY, TSLA, NVDA",
            required=True,
            max_length=100
        )
        
        self.add_item(self.symbols)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            symbols_input = self.symbols.value.upper().strip()
            symbols = [s.strip() for s in symbols_input.split(',') if s.strip()]
            
            if len(symbols) > 10:
                await interaction.response.send_message(
                    "❌ **Too many symbols**. Please limit to 10 symbols per request.",
                    ephemeral=True
                )
                return
            
            await interaction.response.defer(ephemeral=True)
            
            # Get prices for all symbols
            price_data = {}
            for symbol in symbols:
                price = await polygon.get_current_price(symbol)
                price_data[symbol] = price
            
            embed = create_multi_price_embed(price_data)
            await interaction.followup.send(embed=embed)
                
        except Exception as e:
            print(f"Error in price check: {e}")
            await interaction.followup.send(
                f"❌ **Error**: {str(e)}",
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
                entry_date = trade[8]  # entry_date
                options.append(
                    discord.SelectOption(
                        label=f"{trade[4]} - {trade[5]}",  # symbol - trade_type
                        value=trade[3],  # trade_id
                        description=f"Entry: ${trade[6]:.2f} on {entry_date}",
                        emoji="📈" if trade[5] in ['LONG', 'CALL'] else "📉"
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
            embed = await create_detailed_trade_embed(trade_data)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(
                "❌ Trade not found",
                ephemeral=True
            )
    
    @discord.ui.button(label="💹 Live P&L", style=discord.ButtonStyle.primary, emoji="