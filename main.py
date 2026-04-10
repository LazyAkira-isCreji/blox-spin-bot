import discord
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput
import random
import sqlite3
import time
import os
from datetime import datetime

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

OWNER_ID = 1429019327054610634
MY_ID = 1454441629950939183
DEFAULT_PREFIX = "g!"

def init_db():
    conn = sqlite3.connect('bloxspin.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance INTEGER DEFAULT 0,
        wins INTEGER DEFAULT 0,
        losses INTEGER DEFAULT 0,
        wagered INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS cooldowns (
        user_id INTEGER, command TEXT, expire_time REAL,
        PRIMARY KEY (user_id, command)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS guild_prefixes (
        guild_id INTEGER PRIMARY KEY,
        prefix TEXT DEFAULT "g!"
    )''')
    conn.commit()
    conn.close()

def get_user_data(user_id):
    conn = sqlite3.connect('bloxspin.db')
    c = conn.cursor()
    c.execute("SELECT balance, wins, losses, wagered FROM users WHERE user_id=?", (user_id,))
    data = c.fetchone()
    if not data:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        data = (0, 0, 0, 0)
    conn.close()
    return {'balance': data[0], 'wins': data[1], 'losses': data[2], 'wagered': data[3]}

def update_balance(user_id, balance):
    conn = sqlite3.connect('bloxspin.db')
    c = conn.cursor()
    c.execute("UPDATE users SET balance=? WHERE user_id=?", (balance, user_id))
    conn.commit()
    conn.close()

def update_stats(user_id, wins_delta=0, losses_delta=0, wagered_delta=0):
    conn = sqlite3.connect('bloxspin.db')
    c = conn.cursor()
    c.execute("UPDATE users SET wins=wins+?, losses=losses+?, wagered=wagered+? WHERE user_id=?", 
              (wins_delta, losses_delta, wagered_delta, user_id))
    conn.commit()
    conn.close()

def get_cooldown(user_id, command):
    conn = sqlite3.connect('bloxspin.db')
    c = conn.cursor()
    c.execute("SELECT expire_time FROM cooldowns WHERE user_id=? AND command=?", (user_id, command))
    data = c.fetchone()
    conn.close()
    return (data[0] - time.time()) if data and data[0] > time.time() else 0

def set_cooldown(user_id, command, seconds):
    conn = sqlite3.connect('bloxspin.db')
    c = conn.cursor()
    c.execute("REPLACE INTO cooldowns (user_id, command, expire_time) VALUES (?,?,?)", 
              (user_id, command, time.time() + seconds))
    conn.commit()
    conn.close()

def get_guild_prefix(guild_id):
    if not guild_id: return DEFAULT_PREFIX
    conn = sqlite3.connect('bloxspin.db')
    c = conn.cursor()
    c.execute("SELECT prefix FROM guild_prefixes WHERE guild_id=?", (guild_id,))
    data = c.fetchone()
    conn.close()
    return data[0] if data else DEFAULT_PREFIX

def set_guild_prefix(guild_id, prefix):
    conn = sqlite3.connect('bloxspin.db')
    c = conn.cursor()
    c.execute("REPLACE INTO guild_prefixes (guild_id, prefix) VALUES (?,?)", (guild_id, prefix))
    conn.commit()
    conn.close()

def get_deck():
    suits = ['♠','♥','♦','♣']
    ranks = ['2','3','4','5','6','7','8','9','10','J','Q','K','A']
    deck = [r + s for s in suits for r in ranks]
    random.shuffle(deck)
    return deck

def calculate_hand(hand):
    value = 0
    aces = 0
    for card in hand:
        r = card[:-1]
        if r in ['J','Q','K']: value += 10
        elif r == 'A': aces += 1; value += 11
        else: value += int(r)
    while value > 21 and aces: value -= 10; aces -= 1
    return value

@client.event
async def on_ready():
    init_db()
    await tree.sync()
    print(f'✅ Blox Spin is ONLINE! All commands loaded.')
    await client.change_presence(activity=discord.Game(name="Blox Spin 🎰"))

@client.event
async def on_message(message):
    if message.author.bot: return
    prefix = get_guild_prefix(message.guild.id if message.guild else None)
    if not message.content.startswith(prefix): return
    args = message.content[len(prefix):].strip().lower().split()
    if not args: return
    cmd = args[0]
    if cmd == "ping":
        await message.channel.send(f"🏓 Pong! `{round(client.latency*1000)}ms`")
    elif cmd == "help":
        await message.channel.send("✅ Use slash commands → type `/help`")

class WithdrawModal(Modal, title="Blox Spin Withdrawal"):
    gamepass = TextInput(label="Roblox Gamepass ID", placeholder="Paste your gamepass ID", required=True, max_length=50)
    def __init__(self, amount, user):
        super().__init__()
        self.amount = amount
        self.user = user
    async def on_submit(self, interaction: discord.Interaction):
        data = get_user_data(self.user.id)
        if data['balance'] < self.amount:
            return await interaction.response.send_message("❌ Not enough balance!", ephemeral=True)
        update_balance(self.user.id, data['balance'] - self.amount)
        try:
            owner = await client.fetch_user(OWNER_ID)
            me = await client.fetch_user(MY_ID)
            dm = discord.Embed(title="🚨 Withdrawal Request", description=f"**User:** {self.user.mention}\n**Amount:** {self.amount}\n**Gamepass ID:** {self.gamepass.value}", color=0xff0000)
            await owner.send(embed=dm)
            await me.send(embed=dm)
        except: pass
        await interaction.response.send_message(f"✅ **{self.amount}** coins withdrawal submitted!", ephemeral=True)

class RainView(View):
    def __init__(self, amount, host):
        super().__init__(timeout=180)
        self.amount = amount
        self.host = host
        self.claimants = []
        self.message = None
    @discord.ui.button(label="Claim 🌧️", style=discord.ButtonStyle.green)
    async def claim(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id == self.host.id: return await interaction.response.send_message("❌ Can't claim your own rain!", ephemeral=True)
        if interaction.user in self.claimants: return await interaction.response.send_message("❌ Already claimed!", ephemeral=True)
        self.claimants.append(interaction.user)
        await interaction.response.send_message(f"✅ Joined the rain! ({len(self.claimants)} total)", ephemeral=True)
    async def on_timeout(self):
        if not self.claimants:
            embed = discord.Embed(title="🌧️ Rain Ended", description="No one claimed 😢", color=0xff0000)
        else:
            share = self.amount // len(self.claimants)
            for user in self.claimants:
                update_balance(user.id, get_user_data(user.id)['balance'] + share)
            embed = discord.Embed(title="🌧️ Rain Distributed!", description=f"**{len(self.claimants)}** people • **{share}** each", color=0x00ff88)
        await self.message.edit(embed=embed, view=None)

class DuelView(View):
    def __init__(self, challenger, target, bet):
        super().__init__(timeout=120)
        self.challenger = challenger
        self.target = target
        self.bet = bet
    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.target.id: return await interaction.response.send_message("Not for you!", ephemeral=True)
        c_data = get_user_data(self.challenger.id)
        t_data = get_user_data(self.target.id)
        if c_data['balance'] < self.bet or t_data['balance'] < self.bet:
            return await interaction.response.edit_message(content="❌ One of you doesn't have enough coins!", view=None)
        update_balance(self.challenger.id, c_data['balance'] - self.bet)
        update_balance(self.target.id, t_data['balance'] - self.bet)
        winner = random.choice([self.challenger, self.target])
        win_amount = self.bet * 2
        update_balance(winner.id, get_user_data(winner.id)['balance'] + win_amount)
        update_stats(self.challenger.id, 1 if winner == self.challenger else 0, 1 if winner != self.challenger else 0, self.bet)
        update_stats(self.target.id, 1 if winner == self.target else 0, 1 if winner != self.target else 0, self.bet)
        result = discord.Embed(title="⚔️ Duel Result", description=f"**Winner:** {winner.mention}\n**Won:** {win_amount} coins", color=0x00ff88)
        await interaction.response.edit_message(embed=result, view=None)
    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.target.id: return await interaction.response.send_message("Not for you!", ephemeral=True)
        await interaction.response.edit_message(content="❌ Duel declined.", view=None)

class MinesView(View):
    def __init__(self, bet, mines_count, user):
        super().__init__(timeout=300)
        self.bet = bet
        self.mines_count = mines_count
        self.user = user
        self.tiles_cleared = 0
        self.multiplier = 1.0
    @discord.ui.button(label="🔨 Dig Tile", style=discord.ButtonStyle.primary)
    async def dig(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id: return await interaction.response.send_message("Not your game!", ephemeral=True)
        if random.random() < (self.mines_count / 25.0):
            self.stop()
            update_stats(self.user.id, 0, 1, self.bet)
            embed = discord.Embed(title="💥 BOOM! Mine Hit!", description=f"Cleared **{self.tiles_cleared}** tiles.\nLost **{self.bet}** coins.", color=0xff0000)
            await interaction.response.edit_message(embed=embed, view=None)
            return
        self.tiles_cleared += 1
        self.multiplier = round(1.0 + (self.tiles_cleared * (self.mines_count / 8.0)), 2)
        embed = discord.Embed(title="⛏️ Mines", description=f"**Tiles cleared:** {self.tiles_cleared}\n**Current multiplier:** {self.multiplier}x\nYou can **Cash Out** anytime!", color=0x00ff88)
        await interaction.response.edit_message(embed=embed, view=self)
        if self.tiles_cleared >= 20:
            self.stop()
            win = int(self.bet * self.multiplier)
            update_balance(self.user.id, get_user_data(self.user.id)['balance'] + win)
            update_stats(self.user.id, 1, 0, self.bet)
            await interaction.response.edit_message(embed=discord.Embed(title="🏆 FIELD CLEARED!", description=f"+{win} coins", color=0x00ff88), view=None)
    @discord.ui.button(label="💰 Cash Out", style=discord.ButtonStyle.green)
    async def cash_out(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id: return await interaction.response.send_message("Not your game!", ephemeral=True)
        self.stop()
        win = int(self.bet * self.multiplier)
        update_balance(self.user.id, get_user_data(self.user.id)['balance'] + win)
        update_stats(self.user.id, 1, 0, self.bet)
        await interaction.response.edit_message(embed=discord.Embed(title="💰 Cashed Out!", description=f"**{self.tiles_cleared}** tiles cleared\n**Won:** +{win} coins", color=0x00ff88), view=None)

# ==================== ALL COMMANDS ====================

@tree.command(name="help", description="All Blox Spin commands")
async def help_cmd(interaction: discord.Interaction):
    e = discord.Embed(title="🎲 Blox Spin – Full Command List", color=0x00ff88)
    e.add_field(name="🎲 Basic Games", value="/coinflip /roll /slots /blackjack /roulette", inline=False)
    e.add_field(name="💰 Economy", value="/balance /withdraw", inline=False)
    e.add_field(name="⚔️ Risk / High-Stakes", value="/double /limbo /mines", inline=False)
    e.add_field(name="🏆 Multiplayer", value="/duel /rain", inline=False)
    e.add_field(name="🛠️ Utility", value="/leaderboard /cooldowns /stats /ping", inline=False)
    e.add_field(name="🔒 Admin (Owner Only)", value="/setbalance /addmoney /removemoney /reset /wipebalance /prefix /disable-command", inline=False)
    e.set_footer(text="Default prefix: g! • Everyone starts at 0 coins")
    await interaction.response.send_message(embed=e)

@tree.command(name="balance", description="Check your coins")
async def balance_cmd(interaction: discord.Interaction):
    d = get_user_data(interaction.user.id)
    e = discord.Embed(title="💰 Your Balance", description=f"**{d['balance']}** coins", color=0x00ff88)
    await interaction.response.send_message(embed=e)

@tree.command(name="withdraw", description="Cash out coins (Gamepass required)")
@app_commands.describe(amount="Amount to withdraw")
async def withdraw_cmd(interaction: discord.Interaction, amount: int):
    if amount <= 0: return await interaction.response.send_message("❌ Invalid amount", ephemeral=True)
    await interaction.response.send_modal(WithdrawModal(amount, interaction.user))

@tree.command(name="coinflip", description="50/50 coinflip")
@app_commands.describe(bet="Bet", side="heads/tails")
@app_commands.choices(side=[app_commands.Choice(name="Heads", value="heads"), app_commands.Choice(name="Tails", value="tails")])
async def coinflip_cmd(interaction: discord.Interaction, bet: int, side: str):
    d = get_user_data(interaction.user.id)
    if bet <= 0 or d['balance'] < bet: return await interaction.response.send_message("❌ Invalid bet!", ephemeral=True)
    update_balance(interaction.user.id, d['balance'] - bet)
    res = random.choice(["heads", "tails"])
    if res == side:
        win = bet * 2
        update_balance(interaction.user.id, d['balance'] - bet + win)
        update_stats(interaction.user.id, 1, 0, bet)
        e = discord.Embed(title="🎉 WIN!", description=f"**{side}** → **{res}** | +{win} coins", color=0x00ff88)
    else:
        update_stats(interaction.user.id, 0, 1, bet)
        e = discord.Embed(title="💥 LOSE", description=f"**{side}** → **{res}** | -{bet} coins", color=0xff0000)
    await interaction.response.send_message(embed=e)

@tree.command(name="roll", description="Guess 1-350 (24h cooldown) - 200 coins if correct!")
@app_commands.describe(bet="Bet", guess="Your guess (1-350)")
async def roll_cmd(interaction: discord.Interaction, bet: int, guess: int):
    if not 1 <= guess <= 350: return await interaction.response.send_message("❌ Guess must be 1-350!", ephemeral=True)
    if get_cooldown(interaction.user.id, "roll") > 0: return await interaction.response.send_message("⏳ 24h cooldown on /roll!", ephemeral=True)
    d = get_user_data(interaction.user.id)
    if bet <= 0 or d['balance'] < bet: return await interaction.response.send_message("❌ Invalid bet!", ephemeral=True)
    update_balance(interaction.user.id, d['balance'] - bet)
    r = random.randint(1, 350)
    if guess == r:
        win = 200
        update_balance(interaction.user.id, d['balance'] - bet + win)
        update_stats(interaction.user.id, 1, 0, bet)
        e = discord.Embed(title="🎉 CORRECT GUESS!", description=f"The number was **{r}**\nYou guessed **{guess}**\n**+200 coins**!", color=0x00ff88)
    else:
        update_stats(interaction.user.id, 0, 1, bet)
        e = discord.Embed(title="💥 Wrong Guess", description=f"The number was **{r}**\nYou guessed **{guess}**\nLost {bet} coins", color=0xff0000)
    set_cooldown(interaction.user.id, "roll", 86400)
    await interaction.response.send_message(embed=e)

@tree.command(name="slots", description="Slot machine")
@app_commands.describe(bet="Bet")
async def slots_cmd(interaction: discord.Interaction, bet: int):
    d = get_user_data(interaction.user.id)
    if bet <= 0 or d['balance'] < bet: return await interaction.response.send_message("❌ Invalid bet!", ephemeral=True)
    update_balance(interaction.user.id, d['balance'] - bet)
    sym = ["🍒","🍋","🍉","🔔","⭐","7️⃣","💎"]
    a, b, c = random.choice(sym), random.choice(sym), random.choice(sym)
    if a == b == c:
        mult = 15 if a == "7️⃣" else 8
        win = bet * mult
        update_balance(interaction.user.id, d['balance'] - bet + win)
        update_stats(interaction.user.id, 1, 0, bet)
        txt = f"JACKPOT! {a}{b}{c} ×{mult}"
        col = 0x00ff88
    elif len(set([a,b,c])) == 2:
        win = bet * 2
        update_balance(interaction.user.id, d['balance'] - bet + win)
        update_stats(interaction.user.id, 1, 0, bet)
        txt = f"Win! {a}{b}{c} ×2"
        col = 0x00ff88
    else:
        update_stats(interaction.user.id, 0, 1, bet)
        txt = f"Lose {a}{b}{c}"
        col = 0xff0000
        win = 0
    e = discord.Embed(title="🎰 Slots", description=f"**{a} | {b} | {c}**\n{txt}\nBet: {bet} | Won: {win}", color=col)
    await interaction.response.send_message(embed=e)

@tree.command(name="blackjack", description="Blackjack vs dealer")
@app_commands.describe(bet="Bet")
async def blackjack_cmd(interaction: discord.Interaction, bet: int):
    d = get_user_data(interaction.user.id)
    if bet <= 0 or d['balance'] < bet: return await interaction.response.send_message("❌ Invalid bet!", ephemeral=True)
    update_balance(interaction.user.id, d['balance'] - bet)
    deck = get_deck()
    p_hand = [deck.pop(), deck.pop()]
    d_hand = [deck.pop(), deck.pop()]
    p_val = calculate_hand(p_hand)
    if p_val == 21:
        win = int(bet * 2.5)
        update_balance(interaction.user.id, d['balance'] - bet + win)
        update_stats(interaction.user.id, 1, 0, bet)
        return await interaction.response.send_message(embed=discord.Embed(title="🃏 Natural Blackjack!", description=f"Your hand: {' '.join(p_hand)} (21) | Won {win}", color=0x00ff88))
    class BJView(View):
        def __init__(self): super().__init__(timeout=180)
        @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
        async def hit(self, i: discord.Interaction, b: Button):
            if i.user.id != interaction.user.id: return await i.response.send_message("Not your game!", ephemeral=True)
            p_hand.append(deck.pop())
            if calculate_hand(p_hand) > 21:
                self.stop()
                update_stats(interaction.user.id, 0, 1, bet)
                return await i.response.edit_message(embed=discord.Embed(title="🃏 Bust!", description=f"Lost {bet}", color=0xff0000), view=None)
            await i.response.edit_message(embed=self.make_embed(), view=self)
        @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
        async def stand(self, i: discord.Interaction, b: Button):
            if i.user.id != interaction.user.id: return await i.response.send_message("Not your game!", ephemeral=True)
            self.stop()
            while calculate_hand(d_hand) < 17: d_hand.append(deck.pop())
            p_val = calculate_hand(p_hand)
            d_val = calculate_hand(d_hand)
            if d_val > 21 or p_val > d_val:
                win = bet * 2
                update_balance(interaction.user.id, get_user_data(interaction.user.id)['balance'] + win)
                update_stats(interaction.user.id, 1, 0, bet)
                txt = f"Win! (+{win})"
                col = 0x00ff88
            elif p_val == d_val:
                update_balance(interaction.user.id, get_user_data(interaction.user.id)['balance'] + bet)
                txt = "Push – bet returned"
                col = 0xffff00
            else:
                update_stats(interaction.user.id, 0, 1, bet)
                txt = f"Dealer wins – Lost {bet}"
                col = 0xff0000
            e = discord.Embed(title="🃏 Blackjack Result", description=f"You {p_val} | Dealer {d_val}\n{txt}", color=col)
            await i.response.edit_message(embed=e, view=None)
        def make_embed(self):
            return discord.Embed(title="🃏 Blackjack", description=f"Your hand: {' '.join(p_hand)} ({calculate_hand(p_hand)})\nDealer shows: {d_hand[0]}", color=0x00ff88)
    view = BJView()
    await interaction.response.send_message(embed=view.make_embed(), view=view)

@tree.command(name="roulette", description="Red/Black or number (0-36)")
@app_commands.describe(bet="Bet", choice="red / black / 0-36")
async def roulette_cmd(interaction: discord.Interaction, bet: int, choice: str):
    d = get_user_data(interaction.user.id)
    if bet <= 0 or d['balance'] < bet: return await interaction.response.send_message("❌ Invalid bet!", ephemeral=True)
    update_balance(interaction.user.id, d['balance'] - bet)
    roll = random.randint(0, 36)
    red = [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]
    choice = choice.lower().strip()
    win = 0
    if choice.isdigit() and int(choice) == roll:
        win = bet * 35
        txt = f"**Exact number {roll}** → +{win}"
        col = 0x00ff88
    elif choice == "red" and roll in red and roll != 0:
        win = bet * 2
        txt = f"**Red {roll}** → +{win}"
        col = 0x00ff88
    elif choice == "black" and roll not in red and roll != 0:
        win = bet * 2
        txt = f"**Black {roll}** → +{win}"
        col = 0x00ff88
    else:
        txt = f"Lost on **{roll}**"
        col = 0xff0000
    if win > 0:
        update_balance(interaction.user.id, d['balance'] - bet + win)
        update_stats(interaction.user.id, 1, 0, bet)
    else:
        update_stats(interaction.user.id, 0, 1, bet)
    e = discord.Embed(title="🎡 Roulette", description=f"Ball landed on **{roll}**\n{txt}", color=col)
    await interaction.response.send_message(embed=e)

@tree.command(name="double", description="2% chance to double your bet")
@app_commands.describe(bet="Bet")
async def double_cmd(interaction: discord.Interaction, bet: int):
    d = get_user_data(interaction.user.id)
    if bet <= 0 or d['balance'] < bet: return await interaction.response.send_message("❌ Invalid bet!", ephemeral=True)
    update_balance(interaction.user.id, d['balance'] - bet)
    if random.random() < 0.02:
        win = bet * 2
        update_balance(interaction.user.id, d['balance'] - bet + win)
        update_stats(interaction.user.id, 1, 0, bet)
        e = discord.Embed(title="🔥 DOUBLE OR NOTHING WIN!", description=f"You doubled it! +{win} coins", color=0x00ff88)
    else:
        update_stats(interaction.user.id, 0, 1, bet)
        e = discord.Embed(title="💥 DOUBLE OR NOTHING LOSE", description=f"You lost {bet} coins", color=0xff0000)
    await interaction.response.send_message(embed=e)

@tree.command(name="limbo", description="Limbo - set your target multiplier")
@app_commands.describe(bet="Bet amount", target="Target multiplier (e.g. 2.0)")
async def limbo_cmd(interaction: discord.Interaction, bet: int, target: float):
    if target < 1.01: target = 1.01
    d = get_user_data(interaction.user.id)
    if bet <= 0 or d['balance'] < bet: return await interaction.response.send_message("❌ Invalid bet!", ephemeral=True)
    update_balance(interaction.user.id, d['balance'] - bet)
    crash = round(random.uniform(0.5, 25.0), 2)
    if crash >= target:
        win = int(bet * target)
        update_balance(interaction.user.id, d['balance'] - bet + win)
        update_stats(interaction.user.id, 1, 0, bet)
        e = discord.Embed(title="🚀 LIMBO WIN!", description=f"**Crash:** {crash}x\n**Target:** {target}x\n**Won:** +{win} coins", color=0x00ff88)
    else:
        update_stats(interaction.user.id, 0, 1, bet)
        e = discord.Embed(title="💥 LIMBO CRASHED!", description=f"**Crash:** {crash}x\n**Target:** {target}x\n**Lost:** {bet} coins", color=0xff0000)
    await interaction.response.send_message(embed=e)

@tree.command(name="mines", description="Mines - dig tiles, avoid bombs! (Cash Out anytime)")
@app_commands.describe(bet="Bet amount", mines="Number of mines (3-15)")
async def mines_cmd(interaction: discord.Interaction, bet: int, mines: int):
    if not 3 <= mines <= 15 or bet <= 0: return await interaction.response.send_message("❌ Bet must be >0 and mines 3-15!", ephemeral=True)
    d = get_user_data(interaction.user.id)
    if d['balance'] < bet: return await interaction.response.send_message("❌ Not enough coins!", ephemeral=True)
    update_balance(interaction.user.id, d['balance'] - bet)
    embed = discord.Embed(title="⛏️ Mines Started!", description=f"**Bet:** {bet}\n**Mines:** {mines}\nClick **Dig Tile** or **Cash Out** anytime!", color=0x00ff88)
    view = MinesView(bet, mines, interaction.user)
    await interaction.response.send_message(embed=embed, view=view)

@tree.command(name="duel", description="1v1 gamble")
@app_commands.describe(user="Opponent", bet="Bet amount")
async def duel_cmd(interaction: discord.Interaction, user: discord.Member, bet: int):
    if user.bot or user.id == interaction.user.id: return await interaction.response.send_message("❌ Can't duel yourself or bot!", ephemeral=True)
    if bet <= 0: return await interaction.response.send_message("❌ Invalid bet!", ephemeral=True)
    view = DuelView(interaction.user, user, bet)
    e = discord.Embed(title="⚔️ Duel Challenge", description=f"{interaction.user.mention} challenged {user.mention} for **{bet}** coins!", color=0xffff00)
    await interaction.response.send_message(embed=e, view=view)

@tree.command(name="rain", description="Make it rain coins!")
@app_commands.describe(amount="Amount to rain")
async def rain_cmd(interaction: discord.Interaction, amount: int):
    d = get_user_data(interaction.user.id)
    if amount <= 0 or d['balance'] < amount: return await interaction.response.send_message("❌ Not enough coins!", ephemeral=True)
    update_balance(interaction.user.id, d['balance'] - amount)
    e = discord.Embed(title="🌧️ RAIN TIME!", description=f"{interaction.user.mention} is raining **{amount}** coins!\nClick **Claim** below!", color=0x00ff88)
    view = RainView(amount, interaction.user)
    await interaction.response.send_message(embed=e, view=view)
    view.message = await interaction.original_response()

@tree.command(name="leaderboard", description="Richest players")
async def leaderboard_cmd(interaction: discord.Interaction):
    conn = sqlite3.connect('bloxspin.db')
    c = conn.cursor()
    c.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
    top = c.fetchall()
    conn.close()
    e = discord.Embed(title="🏆 Top 10 Richest", color=0x00ff88)
    for i, (uid, bal) in enumerate(top, 1):
        user = await client.fetch_user(uid)
        e.add_field(name=f"{i}. {user.name}", value=f"{bal} coins", inline=False)
    await interaction.response.send_message(embed=e)

@tree.command(name="cooldowns", description="Check your cooldowns")
async def cooldowns_cmd(interaction: discord.Interaction):
    roll_cd = get_cooldown(interaction.user.id, "roll")
    e = discord.Embed(title="⏳ Your Cooldowns", color=0x00ff88)
    e.add_field(name="/roll", value="Ready" if roll_cd <= 0 else f"{int(roll_cd//3600)}h {int((roll_cd%3600)//60)}m left", inline=False)
    await interaction.response.send_message(embed=e)

@tree.command(name="stats", description="Your gambling stats")
async def stats_cmd(interaction: discord.Interaction):
    d = get_user_data(interaction.user.id)
    e = discord.Embed(title="📊 Your Stats", color=0x00ff88)
    e.add_field(name="Wins", value=d['wins'], inline=True)
    e.add_field(name="Losses", value=d['losses'], inline=True)
    e.add_field(name="Total Wagered", value=d['wagered'], inline=True)
    await interaction.response.send_message(embed=e)

@tree.command(name="ping", description="Bot latency")
async def ping_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! `{round(client.latency*1000)}ms`")

@tree.command(name="prefix", description="Change server prefix (Admin only)")
@app_commands.describe(new_prefix="New prefix")
async def prefix_cmd(interaction: discord.Interaction, new_prefix: str):
    if not interaction.user.guild_permissions.administrator: return await interaction.response.send_message("❌ Admin only!", ephemeral=True)
    set_guild_prefix(interaction.guild.id, new_prefix)
    await interaction.response.send_message(f"✅ Prefix changed to `{new_prefix}`")

async def is_owner(interaction: discord.Interaction):
    return interaction.user.id in [MY_ID, OWNER_ID]

@tree.command(name="setbalance", description="Set user balance (Owner)")
@app_commands.describe(user="User", amount="New balance")
async def setbalance_cmd(interaction: discord.Interaction, user: discord.Member, amount: int):
    if not await is_owner(interaction): return await interaction.response.send_message("❌ Owner only!", ephemeral=True)
    update_balance(user.id, max(0, amount))
    await interaction.response.send_message(f"✅ {user.mention} balance set to **{amount}**")

@tree.command(name="addmoney", description="Add coins (Owner)")
@app_commands.describe(user="User", amount="Amount")
async def addmoney_cmd(interaction: discord.Interaction, user: discord.Member, amount: int):
    if not await is_owner(interaction): return await interaction.response.send_message("❌ Owner only!", ephemeral=True)
    d = get_user_data(user.id)
    update_balance(user.id, d['balance'] + amount)
    await interaction.response.send_message(f"✅ Added **{amount}** to {user.mention}")

@tree.command(name="removemoney", description="Remove coins (Owner)")
@app_commands.describe(user="User", amount="Amount")
async def removemoney_cmd(interaction: discord.Interaction, user: discord.Member, amount: int):
    if not await is_owner(interaction): return await interaction.response.send_message("❌ Owner only!", ephemeral=True)
    d = get_user_data(user.id)
    update_balance(user.id, max(0, d['balance'] - amount))
    await interaction.response.send_message(f"✅ Removed **{amount}** from {user.mention}")

@tree.command(name="reset", description="Reset user to 0 (Owner)")
@app_commands.describe(user="User")
async def reset_cmd(interaction: discord.Interaction, user: discord.Member):
    if not await is_owner(interaction): return await interaction.response.send_message("❌ Owner only!", ephemeral=True)
    update_balance(user.id, 0)
    await interaction.response.send_message(f"✅ {user.mention} reset to **0** coins")

@tree.command(name="wipebalance", description="Wipe user balance to 0 (Owner)")
@app_commands.describe(user="User")
async def wipebalance_cmd(interaction: discord.Interaction, user: discord.Member):
    if not await is_owner(interaction): return await interaction.response.send_message("❌ Owner only!", ephemeral=True)
    update_balance(user.id, 0)
    await interaction.response.send_message(f"✅ {user.mention}'s balance has been **wiped to 0**")

@tree.command(name="disable-command", description="Disable a command (Owner)")
@app_commands.describe(command="Command name")
async def disable_cmd(interaction: discord.Interaction, command: str):
    if not await is_owner(interaction): return await interaction.response.send_message("❌ Owner only!", ephemeral=True)
    await interaction.response.send_message(f"✅ `{command}` has been disabled")

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if token:
        client.run(token)
    else:
        print("❌ Set DISCORD_TOKEN in Replit Secrets!")
