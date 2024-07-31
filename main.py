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


intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)


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
        await ctx.send("Пожалуйста, прикрепите аудиофайл к сообщению.")
        return
    
    attachment = ctx.message.attachments[0]
    if not attachment.filename.lower().endswith(('.mp3', '.wav', '.ogg')):
        await ctx.send("Пожалуйста, загрузите аудиофайл в формате MP3, WAV или OGG.")
        return

    file_path = os.path.join(UPLOAD_DIRECTORY, attachment.filename)
    await attachment.save(file_path)
    await ctx.send(f"Файл {attachment.filename} успешно загружен!")

@bot.command(name='playup', help='Воспроизвести загруженный аудиофайл')
async def play_local(ctx, *, filename=None):
    if not ctx.voice_client:
        await ctx.send("Бот должен быть в голосовом канале!")
        return

    if not filename:
        # Показать список доступных файлов
        files = os.listdir(UPLOAD_DIRECTORY)
        if not files:
            await ctx.send("Нет доступных аудиофайлов. Загрузите файл с помощью команды !up")
            return
        file_list = "\n".join(files)
        await ctx.send(f"Доступные аудиофайлы:\n{file_list}\n\nИспользуйте !playup <имя_файла> для воспроизведения.")
        return

    file_path = os.path.join(UPLOAD_DIRECTORY, filename)
    if not os.path.exists(file_path):
        await ctx.send(f"Файл {filename} не найден.")
        return

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
        city_name = data['name']
        temperature = data['main']['temp']
        weather_desc = data['weather'][0]['description']
        await ctx.send(f"Погода в {city_name}: {temperature}°C, {weather_desc}")
    else:
        await ctx.send("Не удалось найти город. Попробуйте еще раз.")


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
        await ctx.send("Пожалуйста, укажите положительное число сообщений для удаления.")
        return

    await ctx.channel.purge(limit=amount + 1)  # +1 чтобы удалить и команду тоже
    
    # Отправляем сообщение о выполнении и удаляем его через 5 секунд
    confirmation_message = await ctx.send(f"Удалено {amount} сообщений.")
    await asyncio.sleep(5)
    await confirmation_message.delete()

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
        embed.set_thumbnail(url=member.avatar.url)
        await channel.send(embed=embed)

    # Автоматическая выдача роли новому пользователю
    role = discord.utils.get(member.guild.roles, name='Ккакой то НН')
    if role:
        await member.add_roles(role)

# В обработчике события on_member_join:
@bot.event
async def on_member_join(member):
    channel = discord.utils.get(member.guild.channels, name='welcome')
    if channel:
        embed = discord.Embed(title="Добро пожаловать!", description=f"{member.mention} присоединился к серверу!", color=0x00ff00)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        await channel.send(embed=embed)

    # Автоматическая выдача роли новому пользователю
    role = discord.utils.get(member.guild.roles, name='Новичок')
    if role:
        await member.add_roles(role)

# Добавим команду для создания временных голосовых каналов
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

TOKEN = 'YOUR TOKEN'

@bot.event
async def on_ready():
    print(f'Бот {bot.user} готов к работе!')
    await bot.change_presence(activity=discord.Game(name="!help для списка команд"))

if __name__ == '__main__':
    bot.run(TOKEN)