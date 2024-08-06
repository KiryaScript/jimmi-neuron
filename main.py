import discord
from discord.ext import commands, tasks
import os
import random
import asyncio
import youtube_dl
import validators
import requests
import openai
from pydub import AudioSegment
import ffmpeg
import wave
import time
from pathlib import Path
import subprocess
from discord import app_commands
from characterai import pycai
import nacl
import json
from mutagen.mp3 import MP3
from mutagen.wave import WAVE
from mutagen.oggvorbis import OggVorbis
import psutil
import platform
import GPUtil
import sqlite3
import datetime
import random
import logging


intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# Подключение к базе данных
conn = sqlite3.connect('clicker.db')
cursor = conn.cursor()

# Создание таблиц
cursor.execute('''
    CREATE TABLE IF NOT EXISTS clicks
    (user_id TEXT PRIMARY KEY, clicks INTEGER, double_click INTEGER, auto_clicker INTEGER)
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS daily_rewards
    (user_id TEXT PRIMARY KEY, last_claim DATE)
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS achievements
    (user_id TEXT, achievement TEXT, PRIMARY KEY (user_id, achievement))
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS weekly_clicks
    (user_id TEXT, clicks INTEGER, week INTEGER, year INTEGER, PRIMARY KEY (user_id, week, year))
''')
conn.commit()

class ClickerBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        self.loop.create_task(self.create_clicker_button())
        logging.info("Setup hook called")

    async def create_clicker_button(self):
        await self.wait_until_ready()
        logging.info("Creating clicker button")
        channel_id = 123456789  # Замените на ID вашего канала
        channel = self.get_channel(channel_id)
        
        if channel:
            logging.info(f"Channel found: {channel.name}")
            view = discord.ui.View(timeout=None)
            button = ClickerButton(user_id=None)
            view.add_item(button)
            
            try:
                await channel.send("Click the button to play!", view=view)
                logging.info("Message with button sent successfully")
            except Exception as e:
                logging.error(f"Error sending message: {e}")
        else:
            logging.error(f"Channel with id {channel_id} not found")

bot = ClickerBot()

class ClickerButton(discord.ui.Button):
    def __init__(self, user_id):
        super().__init__(style=discord.ButtonStyle.primary, label="Click me!")
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        self.user_id = str(interaction.user.id)  # Устанавливаем user_id при первом нажатии
        
        cursor.execute('SELECT double_click FROM clicks WHERE user_id = ?', (self.user_id,))
        result = cursor.fetchone()
        double_click = result[0] if result else 0
        click_value = 2 if double_click else 1
        
        cursor.execute('INSERT OR REPLACE INTO clicks (user_id, clicks, double_click, auto_clicker) VALUES (?, COALESCE((SELECT clicks FROM clicks WHERE user_id = ?) + ?, 1), COALESCE((SELECT double_click FROM clicks WHERE user_id = ?), 0), COALESCE((SELECT auto_clicker FROM clicks WHERE user_id = ?), 0))', 
                       (self.user_id, self.user_id, click_value, self.user_id, self.user_id))
        conn.commit()
        
        cursor.execute('SELECT clicks FROM clicks WHERE user_id = ?', (self.user_id,))
        clicks = cursor.fetchone()[0]
        
        await check_achievements(self.user_id, clicks)
        
        await interaction.response.edit_message(content=f"Clicks: {clicks:,}", view=self.view)

@bot.command(name='create_button', help='Создать кнопку кликера')
async def create_button(ctx):
    view = discord.ui.View(timeout=None)
    button = ClickerButton(user_id=None)
    view.add_item(button)
    await ctx.send("Нажмите на кнопку, чтобы играть!", view=view)

class ClickerView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.add_item(ClickerButton(user_id))

@bot.command()
async def clicker(ctx):
    user_id = str(ctx.author.id)
    view = ClickerView(user_id)
    
    cursor.execute('SELECT clicks FROM clicks WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    clicks = result[0] if result else 0
    
    await ctx.send(f"Clicks: {clicks:,}", view=view)

@bot.command()
async def stats(ctx):
    user_id = str(ctx.author.id)
    cursor.execute('SELECT clicks FROM clicks WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    clicks = result[0] if result else 0
    await ctx.send(f"You have {clicks:,} clicks.")

@bot.command()
async def leaderboard(ctx):
    cursor.execute('SELECT user_id, clicks FROM clicks ORDER BY clicks DESC LIMIT 10')
    results = cursor.fetchall()
    
    embed = discord.Embed(title="🏆 Clicker Leaderboard 🏆", color=0x00ff00)
    embed.set_thumbnail(url="https://example.com/trophy_icon.png")  # Замените на URL иконки трофея
    
    for i, (user_id, clicks) in enumerate(results, start=1):
        user = await bot.fetch_user(int(user_id))
        medal = ""
        if i == 1:
            medal = "🥇"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        
        embed.add_field(
            name=f"{medal} Rank #{i}",
            value=f"**{user.name}**\n{clicks:,} clicks",
            inline=False
        )
    
    embed.set_footer(text="Keep clicking to climb the ranks!")
    
    await ctx.send(embed=embed)

@bot.command()
async def mystats(ctx):
    user_id = str(ctx.author.id)
    cursor.execute('SELECT clicks, double_click, auto_clicker FROM clicks WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    if result:
        clicks, double_click, auto_clicker = result
    else:
        clicks, double_click, auto_clicker = 0, 0, 0
    
    cursor.execute('SELECT COUNT(*) FROM clicks WHERE clicks > ?', (clicks,))
    rank = cursor.fetchone()[0] + 1
    
    embed = discord.Embed(title=f"📊 Stats for {ctx.author.name}", color=0x00ff00)
    embed.add_field(name="Total Clicks", value=f"{clicks:,}", inline=False)
    embed.add_field(name="Global Rank", value=f"#{rank}", inline=False)
    embed.add_field(name="Double Click", value="Activated" if double_click else "Not activated", inline=False)
    embed.add_field(name="Auto Clicker", value="Activated" if auto_clicker else "Not activated", inline=False)
    
    await ctx.send(embed=embed)

@bot.command()
async def shop(ctx):
    embed = discord.Embed(title="🛒 Clicker Shop", description="Upgrade your clicking power!", color=0x00ff00)
    embed.add_field(name="1. Double Click", value="Cost: 100 clicks\nYour clicks count twice", inline=False)
    embed.add_field(name="2. Auto Clicker", value="Cost: 500 clicks\nAutomatically clicks once every minute", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def buy(ctx, item: str):
    user_id = str(ctx.author.id)
    cursor.execute('SELECT clicks, double_click, auto_clicker FROM clicks WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if not result:
        await ctx.send("You haven't started clicking yet! Use the `click` command first.")
        return

    clicks, double_click, auto_clicker = result

    items = {
        "double": {"cost": 100, "check": not double_click, "column": "double_click"},
        "auto": {"cost": 500, "check": not auto_clicker, "column": "auto_clicker"}
    }

    if item not in items:
        await ctx.send("Invalid item. Available items: 'double' (Double Click) or 'auto' (Auto Clicker)")
        return

    selected_item = items[item]

    if clicks < selected_item["cost"]:
        await ctx.send(f"You don't have enough clicks. You need {selected_item['cost']} clicks.")
        return

    if not selected_item["check"]:
        await ctx.send(f"You already have the {item.capitalize()} upgrade.")
        return

    cursor.execute(f'UPDATE clicks SET clicks = clicks - ?, {selected_item["column"]} = 1 WHERE user_id = ?', 
                   (selected_item["cost"], user_id))
    conn.commit()

    await ctx.send(f"You've bought the {item.capitalize()} upgrade!")

@bot.command()
async def daily(ctx):
    user_id = str(ctx.author.id)
    today = datetime.date.today()
    
    cursor.execute('SELECT last_claim FROM daily_rewards WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if result and result[0] == str(today):
        await ctx.send("You've already claimed your daily reward today. Come back tomorrow!")
    else:
        reward = random.randint(50, 200)
        cursor.execute('INSERT OR REPLACE INTO daily_rewards (user_id, last_claim) VALUES (?, ?)', (user_id, str(today)))
        cursor.execute('UPDATE clicks SET clicks = clicks + ? WHERE user_id = ?', (reward, user_id))
        conn.commit()
        await ctx.send(f"You've claimed your daily reward of {reward} clicks!")

@bot.command()
async def achievements(ctx):
    user_id = str(ctx.author.id)
    cursor.execute('SELECT achievement FROM achievements WHERE user_id = ?', (user_id,))
    user_achievements = cursor.fetchall()
    
    embed = discord.Embed(title=f"🏅 Achievements for {ctx.author.name}", color=0xffd700)
    if user_achievements:
        for (achievement,) in user_achievements:
            embed.add_field(name=achievement, value="Unlocked! 🎉", inline=False)
    else:
        embed.description = "You haven't unlocked any achievements yet. Keep clicking!"
    
    await ctx.send(embed=embed)

@bot.command()
async def weekly_leaderboard(ctx):
    today = datetime.date.today()
    week = today.isocalendar()[1]
    year = today.year
    
    cursor.execute('''
        SELECT user_id, SUM(clicks) as total_clicks 
        FROM weekly_clicks 
        WHERE week = ? AND year = ? 
        GROUP BY user_id 
        ORDER BY total_clicks DESC 
        LIMIT 10
    ''', (week, year))
    results = cursor.fetchall()
    
    embed = discord.Embed(title=f"🏆 Weekly Leaderboard (Week {week})", color=0x00ff00)
    
    for i, (user_id, clicks) in enumerate(results, start=1):
        user = await bot.fetch_user(int(user_id))
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else ""
        embed.add_field(
            name=f"{medal} Rank #{i}",
            value=f"**{user.name}**\n{clicks:,} clicks",
            inline=False
        )
    
    embed.set_footer(text="Keep clicking to climb the weekly ranks!")
    await ctx.send(embed=embed)

async def auto_clicker():
    while True:
        cursor.execute('SELECT user_id FROM clicks WHERE auto_clicker = 1')
        auto_clicker_users = cursor.fetchall()
        for (user_id,) in auto_clicker_users:
            cursor.execute('UPDATE clicks SET clicks = clicks + 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        await asyncio.sleep(60)  # Wait for 1 minute

@tasks.loop(minutes=5)
async def update_weekly_clicks():
    today = datetime.date.today()
    week = today.isocalendar()[1]
    year = today.year
    
    cursor.execute('SELECT user_id, clicks FROM clicks')
    all_clicks = cursor.fetchall()
    
    for user_id, clicks in all_clicks:
        cursor.execute('''
            INSERT OR REPLACE INTO weekly_clicks (user_id, clicks, week, year)
            VALUES (?, ?, ?, ?)
        ''', (user_id, clicks, week, year))
    
    conn.commit()

@tasks.loop(minutes=30)
async def random_event():
    cursor.execute('SELECT user_id FROM clicks ORDER BY RANDOM() LIMIT 1')
    result = cursor.fetchone()
    if result:
        user_id = result[0]
        bonus_clicks = random.randint(100, 1000)
        cursor.execute('UPDATE clicks SET clicks = clicks + ? WHERE user_id = ?', (bonus_clicks, user_id))
        conn.commit()
        user = await bot.fetch_user(int(user_id))
        channel = bot.get_channel(int(os.getenv('ANNOUNCEMENT_CHANNEL_ID')))
        await channel.send(f"🎉 Random event! {user.mention} just received {bonus_clicks} bonus clicks!")

async def check_achievements(user_id, clicks):
    achievements = [
        ("Beginner Clicker", 100),
        ("Intermediate Clicker", 1000),
        ("Advanced Clicker", 10000),
        ("Expert Clicker", 100000),
        ("Master Clicker", 1000000)
    ]
    
    for achievement, required_clicks in achievements:
        if clicks >= required_clicks:
            cursor.execute('INSERT OR IGNORE INTO achievements (user_id, achievement) VALUES (?, ?)', (user_id, achievement))
            conn.commit()

recording = False
audio_filename = 'voice_recording.wav'

# Функция для записи голоса
async def record_audio(vc):
    global recording, audio_filename

    recording = True

    # Удалите файл, если он существует, чтобы избежать конфликтов
    audio_path = Path(audio_filename)
    if audio_path.exists():
        audio_path.unlink()

    # Настройте захват аудио с помощью FFmpeg
    command = [
        'ffmpeg',
        '-f', 'dshow',  # Для Windows. Для Linux используйте '-f', 'alsa'
        '-i', 'audio=CABLE Output (VB-Audio Virtual Cable)',  # Замените на название вашего микрофона
        '-t', '360000',  # Максимальная длительность записи в секундах
        audio_filename
    ]

    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    while recording:
        await asyncio.sleep(1)

    process.terminate()

    if audio_path.exists():
        print("Аудиофайл успешно создан.")
    else:
        stderr_output = process.stderr.read().decode()
        print(f"Ошибка: аудиофайл не был создан.\n{stderr_output}")

@bot.event
async def on_ready():
    print(f'Бот {bot.user} готов к работе!')

@bot.command(name='record', help='Начать запись голоса')
async def record(ctx):
    if ctx.author.voice and ctx.author.voice.channel:
        vc = await ctx.author.voice.channel.connect()
        asyncio.create_task(record_audio(vc))
        await ctx.send("Запись началась!")
    else:
        await ctx.send("Сначала присоединитесь к голосовому каналу.")

@bot.command(name='stoprecord', help='Остановить запись голоса')
async def stoprecord(ctx):
    global recording, audio_filename
    if recording:
        recording = False
        await ctx.voice_client.disconnect()

        audio_path = Path(audio_filename)
        if audio_path.exists():
            await ctx.send(f"Запись остановлена! Вот ваш файл: {audio_filename}")
            await ctx.send(file=discord.File(audio_filename))
        else:
            await ctx.send("Ошибка: аудиофайл не был создан.")
    else:
        await ctx.send("Запись не была начата.")

@bot.command(name='join', help='Присоединиться к голосовому каналу')
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f"Присоединился к каналу {channel}")
    else:
        await ctx.send("Вы должны находиться в голосовом канале!")

@bot.command(name='leave', help='Покинуть голосовой канал')
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Покинул голосовой канал")
    else:
        await ctx.send("Бот не находится в голосовом канале!")

UPLOAD_DIRECTORY = "user_audio"

if not os.path.exists(UPLOAD_DIRECTORY):
    os.makedirs(UPLOAD_DIRECTORY)

@bot.command(name='up', help='Загрузить аудиофайл')
async def upload(ctx):
    if len(ctx.message.attachments) == 0:
        embed = discord.Embed(title="Ошибка", description="Пожалуйста, прикрепите аудиофайл к сообщению.", color=discord.Color.red())
        await ctx.send(embed=embed)
        return
    
    attachment = ctx.message.attachments[0]
    if not attachment.filename.lower().endswith(('.mp3', '.wav', '.ogg')):
        embed = discord.Embed(title="Ошибка", description="Пожалуйста, загрузите аудиофайл в формате MP3, WAV или OGG.", color=discord.Color.red())
        await ctx.send(embed=embed)
        return

    file_path = os.path.join(UPLOAD_DIRECTORY, attachment.filename)
    await attachment.save(file_path)
    embed = discord.Embed(title="Успех", description=f"Файл {attachment.filename} успешно загружен!", color=discord.Color.green())
    await ctx.send(embed=embed)

@bot.command(name='playup', help='Воспроизвести загруженный аудиофайл')
async def play_local(ctx, *, filename=None):
    if not ctx.voice_client:
        embed = discord.Embed(title="Ошибка", description="Бот должен быть в голосовом канале!", color=discord.Color.red())
        await ctx.send(embed=embed)
        return

    if not filename:
        files = os.listdir(UPLOAD_DIRECTORY)
        if not files:
            embed = discord.Embed(title="Ошибка", description="Нет доступных аудиофайлов. Загрузите файл с помощью команды !up", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        file_list = "\n".join(files)
        embed = discord.Embed(title="Доступные аудиофайлы", description=file_list, color=discord.Color.blue())
        embed.set_footer(text="Используйте !playup <имя_файла> для воспроизведения.")
        await ctx.send(embed=embed)
        return
    
    # Ищем файл без учета расширения
    for file in os.listdir(UPLOAD_DIRECTORY):
        if file.lower().startswith(filename.lower()):
            file_path = os.path.join(UPLOAD_DIRECTORY, file)
            audio_source = discord.FFmpegPCMAudio(file_path)
            ctx.voice_client.play(audio_source, after=lambda e: print('Воспроизведение завершено', e))
            embed = discord.Embed(title="Воспроизведение", description=f"Начинаю воспроизведение {file}", color=discord.Color.green())
            await ctx.send(embed=embed)
            return

    embed = discord.Embed(title="Ошибка", description=f"Файл {filename} не найден.", color=discord.Color.red())
    await ctx.send(embed=embed)

    audio_source = discord.FFmpegPCMAudio(file_path)
    ctx.voice_client.play(audio_source, after=lambda e: print('Воспроизведение завершено', e))
    await ctx.send(f"Начинаю воспроизведение {filename}")

@bot.command(name='playyt', help='Воспроизведение музыки с YouTube')
async def play(ctx, *, url):
    if not validators.url(url):
        await ctx.send("Неверный URL!")
        return

    voice_channel = ctx.author.voice.channel
    if not voice_channel:
        await ctx.send("Сначала войдите в голосовой канал!")
        return

    vc = await voice_channel.connect()

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        url2 = info['formats'][0]['url']
        vc.play(discord.FFmpegPCMAudio(url2), after=lambda e: print('Песня закончилась'))

    await ctx.send(f"Сейчас играет: {info['title']}")

@bot.command(name='stop')
async def stop(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.send("Воспроизведение остановлено")

@bot.command(name='kick', help='Выгнать пользвателя с сервера')
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    await member.kick(reason=reason)
    await ctx.send(f"{member.mention} был исключен!")

@bot.command(name='ban', help='Забанить пользователя')
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    await member.ban(reason=reason)
    await ctx.send(f"{member.mention} был забанен!")

@bot.command(name='unban', help='Разбанить пользователя')
@commands.has_permissions(ban_members=True)
async def unban(ctx, *, member_name):
    banned_users = await ctx.guild.bans()
    member_name, _, member_discriminator = member_name.partition("#")
    for ban_entry in banned_users:
        user = ban_entry.user
        if user.name == member_name and user.discriminator == member_discriminator:
            await ctx.guild.unban(user)
            await ctx.send(f"{user.mention} был разбанен!")
            return
    await ctx.send(f"Пользователь {member_name}#{member_discriminator} не найден в бане.")

@bot.command(name='roll', help='Случайное число от 1 до 100')
async def roll(ctx):
    await ctx.send(f"Выпало число: {random.randint(1, 100)}")

@bot.command(name='flip', help='Подбрасывание монеты')
async def flip(ctx):
    await ctx.send(f"Выпало: {'Орел' if random.choice([True, False]) else 'Решка'}")

# Команды для получения погоды (используйте API OpenWeatherMap)
WEATHER_API_KEY = '83f08b9bc6627b6c938fb155f130cf3b'

@bot.command(name='weather', help='Получение погоды для заданного города')
async def weather(ctx, *, city: str):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        embed = discord.Embed(title=f"Погода в {data['name']}, {data['sys']['country']}", color=0x00AAFF)
        embed.add_field(name="Температура", value=f"{data['main']['temp']}°C", inline=True)
        embed.add_field(name="Ощущается как", value=f"{data['main']['feels_like']}°C", inline=True)
        embed.add_field(name="Влажность", value=f"{data['main']['humidity']}%", inline=True)
        embed.add_field(name="Ветер", value=f"{data['wind']['speed']} м/с", inline=True)
        embed.add_field(name="Описание", value=data['weather'][0]['description'].capitalize(), inline=False)
        embed.set_thumbnail(url=f"http://openweathermap.org/img/wn/{data['weather'][0]['icon']}@2x.png")
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(title="Ошибка", description="Не удалось найти город. Попробуйте еще раз.", color=discord.Color.red())
        await ctx.send(embed=embed)


# Задачи по расписанию (пример)
@tasks.loop(minutes=60)
async def scheduled_task():
    channel = discord.utils.get(bot.get_all_channels(), name='general')
    if channel:
        await channel.send("Ежечасное напоминание!")

@bot.command(name='start_tasks', help='Запустить периодические задачи')
async def start_tasks(ctx):
    if not scheduled_task.is_running():
        scheduled_task.start()
        await ctx.send("Периодические задачи запущены!")
    else:
        await ctx.send("Задачи уже запущены.")

@bot.command(name='stop_tasks', help='Остановить периодические задачи')
async def stop_tasks(ctx):
    if scheduled_task.is_running():
        scheduled_task.stop()
        await ctx.send("Периодические задачи остановлены!")
    else:
        await ctx.send("Задачи уже остановлены.")

# Обработка ошибок
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Команда не найдена. Используйте !help для списка команд.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Отсутствует обязательный аргумент. Проверьте синтаксис команды.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("У вас недостаточно прав для выполнения этой команды.")
    else:
        print(f'Unhandled error: {error}')
        await ctx.send("Произошла неизвестная ошибка. Пожалуйста, попробуйте позже.")

@bot.command(name='clear', help='Удалить указанное количество сообщений')
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    if amount <= 0:
        embed = discord.Embed(title="Ошибка", description="Укажите положительное число сообщений для удаления.", color=discord.Color.red())
        await ctx.send(embed=embed)
        return

import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import os
import random
import asyncio
import youtube_dl
import validators
import requests
import openai
from pydub import AudioSegment
import ffmpeg
import wave
import time
from pathlib import Path
import subprocess
from discord import app_commands
from characterai import pycai
import nacl
import json
from mutagen.mp3 import MP3
from mutagen.wave import WAVE
from mutagen.oggvorbis import OggVorbis

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

recording = False
audio_filename = 'voice_recording.wav'
UPLOAD_DIRECTORY = "user_audio"

if not os.path.exists(UPLOAD_DIRECTORY):
    os.makedirs(UPLOAD_DIRECTORY)

class MusicControls(discord.ui.View):
    def __init__(self, ctx, bot):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.bot = bot

    @discord.ui.button(label="⏯️", style=discord.ButtonStyle.primary)
    async def play_pause(self, button: discord.ui.Button, interaction: discord.Interaction):
        if not self.ctx.voice_client:
            await interaction.response.send_message("Бот не находится в голосовом канале.", ephemeral=True)
            return
        
        if self.ctx.voice_client.is_paused():
            self.ctx.voice_client.resume()
            await interaction.response.send_message("Воспроизведение возобновлено.", ephemeral=True)
        elif self.ctx.voice_client.is_playing():
            self.ctx.voice_client.pause()
            await interaction.response.send_message("Воспроизведение приостановлено.", ephemeral=True)
        else:
            await interaction.response.send_message("Нет активного воспроизведения.", ephemeral=True)

    @discord.ui.button(label="⏹️", style=discord.ButtonStyle.danger)
    async def stop(self, button: discord.ui.Button, interaction: discord.Interaction):
        if not self.ctx.voice_client:
            await interaction.response.send_message("Бот не находится в голосовом канале.", ephemeral=True)
            return
        
        self.ctx.voice_client.stop()
        await interaction.response.send_message("Воспроизведение остановлено.", ephemeral=True)

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.primary)
    async def next_track(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.bot.get_command('playup').callback(self.ctx)

def get_audio_duration(file_path):
    extension = os.path.splitext(file_path)[1].lower()
    if extension == '.mp3':
        audio = MP3(file_path)
    elif extension == '.wav':
        audio = WAVE(file_path)
    elif extension == '.ogg':
        audio = OggVorbis(file_path)
    else:
        return 0
    return audio.info.length

def format_duration(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes:02d}:{seconds:02d}"

async def record_audio(vc):
    global recording, audio_filename

    recording = True

    audio_path = Path(audio_filename)
    if audio_path.exists():
        audio_path.unlink()

    command = [
        'ffmpeg',
        '-f', 'dshow',
        '-i', 'audio=CABLE Output (VB-Audio Virtual Cable)',
        '-t', '360000',
        audio_filename
    ]

    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    while recording:
        await asyncio.sleep(1)

    process.terminate()

    if audio_path.exists():
        print("Аудиофайл успешно создан.")
    else:
        stderr_output = process.stderr.read().decode()
        print(f"Ошибка: аудиофайл не был создан.\n{stderr_output}")

@bot.event
async def on_ready():
    print(f'Бот {bot.user} готов к работе!')
    await bot.change_presence(activity=discord.Game(name="!help для списка команд"))

@bot.command(name='record', help='Начать запись голоса')
async def record(ctx):
    if ctx.author.voice and ctx.author.voice.channel:
        vc = await ctx.author.voice.channel.connect()
        asyncio.create_task(record_audio(vc))
        await ctx.send("Запись началась!")
    else:
        await ctx.send("Сначала присоединитесь к голосовому каналу.")

@bot.command(name='stoprecord', help='Остановить запись голоса')
async def stoprecord(ctx):
    global recording, audio_filename
    if recording:
        recording = False
        await ctx.voice_client.disconnect()

        audio_path = Path(audio_filename)
        if audio_path.exists():
            await ctx.send(f"Запись остановлена! Вот ваш файл: {audio_filename}")
            await ctx.send(file=discord.File(audio_filename))
        else:
            await ctx.send("Ошибка: аудиофайл не был создан.")
    else:
        await ctx.send("Запись не была начата.")

@bot.command(name='join', help='Присоединиться к голосовому каналу')
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f"Присоединился к каналу {channel}")
    else:
        await ctx.send("Вы должны находиться в голосовом канале!")

@bot.command(name='leave', help='Покинуть голосовой канал')
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Покинул голосовой канал")
    else:
        await ctx.send("Бот не находится в голосовом канале!")

@bot.command(name='up', help='Загрузить аудиофайл')
async def upload(ctx):
    if len(ctx.message.attachments) == 0:
        embed = discord.Embed(title="Ошибка", description="Пожалуйста, прикрепите аудиофайл к сообщению.", color=discord.Color.red())
        await ctx.send(embed=embed)
        return
    
    attachment = ctx.message.attachments[0]
    if not attachment.filename.lower().endswith(('.mp3', '.wav', '.ogg')):
        embed = discord.Embed(title="Ошибка", description="Пожалуйста, загрузите аудиофайл в формате MP3, WAV или OGG.", color=discord.Color.red())
        await ctx.send(embed=embed)
        return

    file_path = os.path.join(UPLOAD_DIRECTORY, attachment.filename)
    await attachment.save(file_path)
    embed = discord.Embed(title="Успех", description=f"Файл {attachment.filename} успешно загружен!", color=discord.Color.green())
    await ctx.send(embed=embed)

@bot.command(name='playup', help='Воспроизвести загруженный аудиофайл')
async def play_local(ctx, *, query=None):
    if not ctx.voice_client:
        embed = discord.Embed(title="Ошибка", description="Бот должен быть в голосовом канале!", color=discord.Color.red())
        await ctx.send(embed=embed)
        return

    if not query:
        files = os.listdir(UPLOAD_DIRECTORY)
        if not files:
            embed = discord.Embed(title="Ошибка", description="Нет доступных аудиофайлов. Загрузите файл с помощью команды !up", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        file_list = "\n".join(f"`{i+1}.` {file}" for i, file in enumerate(files))
        embed = discord.Embed(title="Доступные аудиофайлы", description=file_list, color=discord.Color.blue())
        embed.set_footer(text="Используйте !playup <номер> или !playup <название> для воспроизведения.")
        await ctx.send(embed=embed)
        return

    if query.isdigit():
        files = os.listdir(UPLOAD_DIRECTORY)
        index = int(query) - 1
        if 0 <= index < len(files):
            filename = files[index]
        else:
            embed = discord.Embed(title="Ошибка", description="Неверный номер трека.", color=discord.Color.red())
            await ctx.send(embed=embed)
            return
    else:
        filename = next((file for file in os.listdir(UPLOAD_DIRECTORY) 
                         if file.lower().startswith(query.lower())), None)
        
    if filename:
        file_path = os.path.join(UPLOAD_DIRECTORY, filename)
        
        duration = get_audio_duration(file_path)
        
        audio_source = discord.FFmpegPCMAudio(file_path)
        ctx.voice_client.play(audio_source, after=lambda e: print('Воспроизведение завершено', e))
        
        embed = discord.Embed(title="Сейчас играет", description=filename, color=discord.Color.green())
        embed.add_field(name="Длительность", value=format_duration(duration))
        
        view = MusicControls(ctx, bot)
        message = await ctx.send(embed=embed, view=view)
        
        start_time = asyncio.get_event_loop().time()
        while ctx.voice_client and ctx.voice_client.is_playing():
            current_time = asyncio.get_event_loop().time() - start_time
            if current_time > duration:
                break
            progress = int((current_time / duration) * 20)
            bar = "▓" * progress + "░" * (20 - progress)
            embed.set_field_at(0, name="Прогресс", value=f"{bar} {format_duration(current_time)}/{format_duration(duration)}")
            await message.edit(embed=embed)
            await asyncio.sleep(5)
    else:
        embed = discord.Embed(title="Ошибка", description=f"Файл '{query}' не найден.", color=discord.Color.red())
        await ctx.send(embed=embed)

@bot.command(name='playyt', help='Воспроизведение музыки с YouTube')
async def play(ctx, *, url):
    if not validators.url(url):
        await ctx.send("Неверный URL!")
        return

    voice_channel = ctx.author.voice.channel
    if not voice_channel:
        await ctx.send("Сначала войдите в голосовой канал!")
        return

    vc = await voice_channel.connect()

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        url2 = info['formats'][0]['url']
        vc.play(discord.FFmpegPCMAudio(url2), after=lambda e: print('Песня закончилась'))

    await ctx.send(f"Сейчас играет: {info['title']}")

@bot.command(name='stop')
async def stop(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.send("Воспроизведение остановлено")

@bot.command(name='kick', help='Выгнать пользвателя с сервера')
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    await member.kick(reason=reason)
    await ctx.send(f"{member.mention} был исключен!")

@bot.command(name='ban', help='Забанить пользователя')
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    await member.ban(reason=reason)
    await ctx.send(f"{member.mention} был забанен!")

@bot.command(name='unban', help='Разбанить пользователя')
@commands.has_permissions(ban_members=True)
async def unban(ctx, *, member_name):
    banned_users = await ctx.guild.bans()
    member_name, _, member_discriminator = member_name.partition("#")
    for ban_entry in banned_users:
        user = ban_entry.user
        if user.name == member_name and user.discriminator == member_discriminator:
            await ctx.guild.unban(user)
            await ctx.send(f"{user.mention} был разбанен!")
            return
    await ctx.send(f"Пользователь {member_name}#{member_discriminator} не найден в бане.")

@bot.command(name='roll', help='Случайное число от 1 до 100')
async def roll(ctx):
    await ctx.send(f"Выпало число: {random.randint(1, 100)}")

@bot.command(name='flip', help='Подбрасывание монеты')
async def flip(ctx):
    await ctx.send(f"Выпало: {'Орел' if random.choice([True, False]) else 'Решка'}")

WEATHER_API_KEY = '83f08b9bc6627b6c938fb155f130cf3b'

@bot.command(name='weather', help='Получение погоды для заданного города')
async def weather(ctx, *, city: str):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        embed = discord.Embed(title=f"Погода в {data['name']}, {data['sys']['country']}", color=0x00AAFF)
        embed.add_field(name="Температура", value=f"{data['main']['temp']}°C", inline=True)
        embed.add_field(name="Ощущается как", value=f"{data['main']['feels_like']}°C", inline=True)
        embed.add_field(name="Влажность", value=f"{data['main']['humidity']}%", inline=True)
        embed.add_field(name="Ветер", value=f"{data['wind']['speed']} м/с", inline=True)
        embed.add_field(name="Описание", value=data['weather'][0]['description'].capitalize(), inline=False)
        embed.set_thumbnail(url=f"http://openweathermap.org/img/wn/{data['weather'][0]['icon']}@2x.png")
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(title="Ошибка", description="Не удалось найти город. Попробуйте еще раз.", color=discord.Color.red())
        await ctx.send(embed=embed)

@tasks.loop(minutes=60)
async def scheduled_task():
    channel = discord.utils.get(bot.get_all_channels(), name='general')
    if channel:
        await channel.send("Ежечасное напоминание!")

@bot.command(name='start_tasks', help='Запустить периодические задачи')
async def start_tasks(ctx):
    if not scheduled_task.is_running():
        scheduled_task.start()
        await ctx.send("Периодические задачи запущены!")
    else:
        await ctx.send("Задачи уже запущены.")

@bot.command(name='stop_tasks', help='Остановить периодические задачи')
async def stop_tasks(ctx):
    if scheduled_task.is_running():
        scheduled_task.stop()
        await ctx.send("Периодические задачи остановлены!")
    else:
        await ctx.send("Задачи уже остановлены.")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Команда не найдена. Используйте !help для списка команд.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Отсутствует обязательный аргумент. Проверьте синтаксис команды.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("У вас недостаточно прав для выполнения этой команды.")
    else:
        print(f'Unhandled error: {error}')
        await ctx.send("Произошла неизвестная ошибка. Пожалуйста, попробуйте позже.")

@bot.command(name='clear', help='Удалить указанное количество сообщений')
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    if amount <= 0:
        embed = discord.Embed(title="Ошибка", description="Укажите положительное число сообщений для удаления.", color=discord.Color.red())
        await ctx.send(embed=embed)
        return

    deleted = await ctx.channel.purge(limit=amount + 1)
    
    embed = discord.Embed(title="Очистка сообщений", description=f"Удалено {len(deleted) - 1} сообщений.", color=discord.Color.green())
    confirmation = await ctx.send(embed=embed)
    await asyncio.sleep(5)
    await confirmation.delete()

@clear.error
async def clear_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Пожалуйста, укажите количество сообщений для удаления. Например: !clear 10")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Пожалуйста, укажите корректное число сообщений для удаления.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("У вас нет прав для выполнения этой команды.")
    else:
        await ctx.send(f"Произошла ошибка: {error}")

@bot.command(name='userinfo', help='Показать информацию о пользователе')
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author

    roles = [role.mention for role in member.roles[1:]]
    embed = discord.Embed(title="Информация о пользователе", color=member.color)
    embed.set_thumbnail(url=member.avatar.url)
    embed.add_field(name="Имя", value=member.name, inline=True)
    embed.add_field(name="Никнейм", value=member.nick or "Нет", inline=True)
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Статус", value=str(member.status).title(), inline=True)
    embed.add_field(name="Присоединился", value=member.joined_at.strftime("%d.%m.%Y"), inline=True)
    embed.add_field(name="Аккаунт создан", value=member.created_at.strftime("%d.%m.%Y"), inline=True)
    embed.add_field(name=f"Роли [{len(roles)}]", value=" ".join(roles) or "Нет", inline=False)

    await ctx.send(embed=embed)

@bot.command(name='serstats', help='Показать статистику сервера')
async def serstats(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=f"Статистика сервера {guild.name}", color=0x00ff00)
    embed.add_field(name="Участники", value=guild.member_count, inline=True)
    embed.add_field(name="Текстовые каналы", value=len(guild.text_channels), inline=True)
    embed.add_field(name="Голосовые каналы", value=len(guild.voice_channels), inline=True)
    embed.add_field(name="Роли", value=len(guild.roles), inline=True)
    embed.add_field(name="Владелец", value=guild.owner.mention, inline=True)
    embed.add_field(name="Дата создания", value=guild.created_at.strftime("%d.%m.%Y"), inline=True)
    embed.set_thumbnail(url=guild.icon.url)
    await ctx.send(embed=embed)

@bot.event
async def on_member_join(member):
    channel = discord.utils.get(member.guild.channels, name='welcome')
    if channel:
        embed = discord.Embed(title="Добро пожаловать!", description=f"{member.mention} присоединился к серверу!", color=0x00ff00)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        await channel.send(embed=embed)

    role = discord.utils.get(member.guild.roles, name='Новичок')
    if role:
        await member.add_roles(role)

@bot.command(name='ctv', help='Создать временный голосовой канал')
async def ctv(ctx, *, channel_name: str):
    category = discord.utils.get(ctx.guild.categories, name="Временные голосовые каналы")
    if not category:
        category = await ctx.guild.create_category("Временные голосовые каналы")

    channel = await ctx.guild.create_voice_channel(channel_name, category=category)
    await ctx.send(f"Создан временный голосовой канал: {channel.mention}")

    def check(x, y, z):
        return len(channel.members) == 0

    await bot.wait_for('voice_state_update', check=check)
    await channel.delete()
    await ctx.send(f"Временный голосовой канал '{channel_name}' был удален, так как все участники покинули его.")

@bot.command(name='sysinfo', help='Показать информацию о системе')
async def sysinfo(ctx):
    cpu_percent = psutil.cpu_percent()
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    embed = discord.Embed(title="Информация о системе", color=discord.Color.blue())
    
    embed.add_field(name="Система", value=platform.system(), inline=True)
    embed.add_field(name="Процессор", value=platform.processor(), inline=True)
    embed.add_field(name="Использование ЦП", value=f"{cpu_percent}%", inline=True)
    
    embed.add_field(name="Оперативная память", value=f"Всего: {memory.total / (1024**3):.2f} GB\n"
                                                     f"Использовано: {memory.used / (1024**3):.2f} GB ({memory.percent}%)", inline=False)
    
    embed.add_field(name="Диск", value=f"Всего: {disk.total / (1024**3):.2f} GB\n"
                                       f"Использовано: {disk.used / (1024**3):.2f} GB ({disk.percent}%)", inline=False)
    
    # Добавление информации о температуре (если доступно)
    try:
        temperatures = psutil.sensors_temperatures()
        if 'coretemp' in temperatures:
            cpu_temp = temperatures['coretemp'][0].current
            embed.add_field(name="Температура ЦП", value=f"{cpu_temp}°C", inline=True)
    except:
        pass  # Если информация о температуре недоступна, просто пропускаем

    # Добавление информации о GPU (если доступно)
    try:
        gpus = GPUtil.getGPUs()
        if gpus:
            gpu = gpus[0]
            embed.add_field(name="GPU", value=f"{gpu.name}\n"
                                              f"Использование: {gpu.load*100:.2f}%\n"
                                              f"Память: {gpu.memoryUsed}/{gpu.memoryTotal} MB", inline=False)
    except:
        pass  # Если информация о GPU недоступна, просто пропускаем

    await ctx.send(embed=embed)




TOKEN = 'TOKEN'

@bot.event
async def on_ready():
    print(f'Бот {bot.user} готов к работе!')
    await bot.change_presence(activity=discord.Game(name="!help для списка команд"))

if __name__ == '__main__':
    bot.run(TOKEN)