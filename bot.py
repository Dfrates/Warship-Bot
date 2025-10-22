# TODO: add chat activity tracking for bonus scrap.
# TODO: add fleet management (rename ships, set active ships, etc).
# TODO: add ship trading between users.
# TODO: add dueling between users.
# TODO: add boss events.
# TODO: add rare currency types.
# TODO: add abiltiy to sell ships for scrap.
# TODO: max fleet size based on rank.
# TODO: possibly add logic to level up ships if rolled duplicates.
# TODO: add leaderboards.
# TODO: add more ship/passive variety.
# TODO: add more detailed help command.


import discord, random, time, math, json, os
from discord.ext import commands
from tinydb import TinyDB, Query

# ---------- Setup ----------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

db = TinyDB('data/fleet_data.json')
User = Query()

# Load pets dynamically
with open(os.path.join("data", "pets.json"), "r", encoding="utf-8") as f:
    PET_POOL = json.load(f)

RARITY_WEIGHTS = {"common": 0.6, "rare": 0.25, "epic": 0.1, "legendary": 0.05, "mythic": 0.01, "relic": 0.005}

# ---------- Helpers ----------
def get_scrap(uid):
    user = db.get(User.id == uid)
    return user['scrap'] if user else 0

def add_scrap(uid, amt):
    user = db.get(User.id == uid)
    if user:
        db.update({'scrap': user['scrap'] + amt}, User.id == uid)
    else:
        db.insert({'id': uid, 'scrap': amt, 'last_mission': 0, 'last_daily': 0, 'streak': 0, 'pets': []})

def update_user(uid, field, value):
    db.update({field: value}, User.id == uid)

def fmt_time(seconds):
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{m}m {s}s"

def get_rank(streak):
    if streak < 3: return "Deckhand"
    if streak < 7: return "Boatswain"
    if streak < 14: return "First Mate"
    if streak < 30: return "Captain"
    if streak < 60: return "Commodore"
    return "Admiral"

def get_rank_bonus(rank):
    bonuses = {
        "Deckhand": 1.0, "Boatswain": 1.1, "First Mate": 1.25,
        "Captain": 1.5, "Commodore": 1.75, "Admiral": 2.0
    }
    return bonuses.get(rank, 1.0)

def get_fleet_power(user):
    pets = user.get('pets', [])
    return sum(p.get('attack', 0) + p.get('defense', 0) for p in pets)

def get_fleet_tier(power):
    if power < 20: return "Ragtag Fleet"
    if power < 50: return "Seasoned Squadron"
    if power < 100: return "Iron Armada"
    if power < 200: return "Storm Vanguard"
    return "Leviathan Armada"

# ---------- Passive Effect Handling ----------
def calculate_passive_effects(pets):
    effects = {
        "loot_boost": 0.0,
        "mission_success": 0.0,
        "defense_boost": 0.0,
        "attack_boost": 0.0,
        "daily_bonus": 0.0
    }
    for pet in pets:
        p = pet.get("passive", {})
        if p and p["type"] in effects:
            effects[p["type"]] += p["value"]
    return effects

# ---------- Commands ----------
@bot.event
async def on_ready():
    print(f"⚓ Bot deployed as {bot.user}")

# @bot.command()
# async def help(ctx):
#     help_text = (
#         "🛠️ **Warship Bot Commands** 🛠️\n\n"
#         "`!balance` - Check your Scrap balance.\n"
#         "`!daily` - Claim your daily Dock Pay.\n"
#         "`!mission` - Send your fleet on a mission for Scrap.\n"
#         "`!roll` - Spend 200 Scrap to recover a new ship.\n"
#         "`!fleet` - View your current fleet and its stats.\n"
#     )
#     await ctx.send(help_text)

@bot.command()
async def odds(ctx):
    odds_text = "🎲 **Ship Rarity Odds** 🎲\n\n"
    for rarity, weight in RARITY_WEIGHTS.items():
        # make rarity names colored based on tier
        odds_text += f"**{rarity.capitalize()}**: {weight*100:.2f}%\n"
    await ctx.send(odds_text)

@bot.command()
async def balance(ctx):
    scrap = get_scrap(ctx.author.id)
    await ctx.send(f"🧰 {ctx.author.display_name}, you have ⚙️ {scrap} Scrap.")

# 💰 Daily
@bot.command()
async def daily(ctx):
    uid = ctx.author.id
    user = db.get(User.id == uid)
    now = time.time()
    if not user:
        add_scrap(uid, 0)
        user = db.get(User.id == uid)

    cooldown = 86400
    remaining = cooldown - (now - user.get('last_daily', 0))
    if remaining > 0:
        await ctx.send(f"⏳ Come back in {fmt_time(remaining)} for your next payout.")
        return

    streak = user.get('streak', 0)
    last = user.get('last_daily', 0)
    if now - last < (86400 * 2):
        streak += 1
    else:
        streak = 1

    rank = get_rank(streak)
    rank_mult = get_rank_bonus(rank)
    pets = user.get('pets', [])
    passives = calculate_passive_effects(pets)
    daily_bonus = passives["daily_bonus"]

    base = random.randint(120, 300)
    reward = int(base * rank_mult * (1 + daily_bonus))
    add_scrap(uid, reward)
    db.update({'last_daily': now, 'streak': streak}, User.id == uid)

    bar = "🔥" * (streak % 10) + "⚫" * (10 - (streak % 10))
    embed = discord.Embed(
        title="💰 Dock Pay Received!",
        description=(
            f"**Rank:** {rank}\n"
            f"**Streak:** {bar} ({streak} days)\n\n"
            f"**Base Pay:** ⚙️ {base}\n"
            f"**Rank Multiplier:** x{rank_mult}\n"
            f"**Passive Bonus:** +{int(daily_bonus*100)}%\n"
            f"**Total:** ⚙️ {reward}"
        ),
        color=0x3B82F6
    )
    await ctx.send(embed=embed)

# ⚔️ Mission
@bot.command()
async def mission(ctx):
    uid = ctx.author.id
    user = db.get(User.id == uid)
    now = time.time()
    if not user:
        add_scrap(uid, 0)
        user = db.get(User.id == uid)

    cooldown = 60
    remaining = cooldown - (now - user.get('last_mission', 0))
    if remaining > 0:
        await ctx.send(f"🕐 Fleet still returning — {fmt_time(remaining)} remaining.")
        return

    pets = user.get('pets', [])
    passives = calculate_passive_effects(pets)
    fleet_power = get_fleet_power(user)
    rank = get_rank(user.get('streak', 0))
    rank_mult = get_rank_bonus(rank)

    base_chance = 0.5 + (fleet_power * 0.002) + passives["mission_success"]
    base_chance = min(base_chance, 0.95)

    roll = random.random()
    if roll < base_chance:
        outcome = "success"
    elif roll < base_chance + 0.25:
        outcome = "partial"
    else:
        outcome = "failure"

    loot_mult = 1 + passives["loot_boost"]
    if outcome == "success":
        base = random.randint(60, 150)
        reward = int(base * rank_mult * loot_mult)
        desc = f"⚓ Your fleet triumphed! Gained ⚙️ {reward} Scrap."
        color = 0x3B82F6
    elif outcome == "partial":
        base = random.randint(20, 70)
        reward = int(base * rank_mult * loot_mult * 0.5)
        desc = f"🛠️ Fleet returned damaged but recovered ⚙️ {reward} Scrap."
        color = 0xA855F7
    else:
        reward = 0
        desc = f"💥 The seas claimed your prize — no Scrap gained."
        color = 0xF87171

    add_scrap(uid, reward)
    update_user(uid, 'last_mission', now)

    embed = discord.Embed(title="🌊 Mission Report", description=desc, color=color)
    embed.add_field(name="🏅 Rank", value=f"{rank} (x{rank_mult})", inline=True)
    embed.add_field(name="⚔️ Fleet Power", value=f"{fleet_power}", inline=True)
    embed.add_field(name="🧭 Passives", value=f"Loot +{int(passives['loot_boost']*100)}%, Success +{int(passives['mission_success']*100)}%", inline=False)
    await ctx.send(embed=embed)

# 🎲 Roll
@bot.command()
async def roll(ctx):
    uid = ctx.author.id
    user = db.get(User.id == uid)
    if not user or user['scrap'] < 200:
        await ctx.send("⚙️ You need at least 200 Scrap to roll for a new ship.")
        return

    db.update({'scrap': user['scrap'] - 200}, User.id == uid)
    rank = get_rank(user.get('streak', 0))
    rank_mult = get_rank_bonus(rank)

    rarity = random.choices(
        list(RARITY_WEIGHTS.keys()), weights=list(RARITY_WEIGHTS.values())
    )[0]
    pet = random.choice([p for p in PET_POOL if p['rarity'] == rarity])
    pets = user.get('pets', [])
    pets.append(pet)
    db.update({'pets': pets}, User.id == uid)

    rarity_color = 0x3B82F6
    if rarity == "epic":
        rarity_color = 0xFFD700
    elif rarity == "legendary":
        rarity_color = 0xA855F7
    elif rarity == "mythic":
        rarity_color = 0xEF4444

    embed = discord.Embed(
        title="🚢 New Ship Recovered!",
        description=(
            f"{pet['emoji']} **{pet['name']}** ({pet['rarity'].capitalize()})\n"
            f"⚔️ {pet['attack']}  🛡️ {pet['defense']}\n"
            f"Passive: {pet['passive']['description']}\n\n"
            f"⚙️ -200 Scrap"
        ),
        color=rarity_color
    )
    await ctx.send(embed=embed)

# ⚓ Fleet
@bot.command()
async def fleet(ctx):
    user = db.get(User.id == ctx.author.id)
    if not user or not user.get('pets'):
        await ctx.send("🚫 You don’t have any ships yet. Use `!roll` to acquire one!")
        return

    pets = user['pets']
    fleet_power = get_fleet_power(user)
    tier = get_fleet_tier(fleet_power)

    desc = "\n".join(
        [f"{p['emoji']} **{p['name']}** ({p['rarity']}) ⚔️{p['attack']} 🛡️{p['defense']} — {p['passive']['description']}" for p in pets]
    )
    embed = discord.Embed(
        title=f"⚓ {ctx.author.display_name}'s Fleet",
        description=f"{desc}\n\n**Fleet Power:** {fleet_power}\n**Tier:** {tier}",
        color=0x3B82F6
    )
    await ctx.send(embed=embed)

bot.run("token")
