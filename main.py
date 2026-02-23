import discord
from discord.ext import commands
import io
import asyncio
from groq import AsyncGroq

# --- AYARLAR (BURALARI KENDİNE GÖRE DOLDUR) ---
DISCORD_TOKEN = "BURAYA_DISCORD_BOT_TOKEN_GELECEK"
GROQ_API_KEY = "BURAYA_GROQ_API_KEY_GELECEK"

YETKILI_ROL_ID = 123456789012345678 # Yetkili rolünün ID'si (Sayısal)
LOG_KANAL_ID = 123456789012345678   # Ticket loglarının düşeceği kanalın ID'si (Sayısal)
KATEGORI_ID = 123456789012345678    # Ticketların açılacağı kategorinin ID'si (Sayısal)
# ---------------------------------------------

# Bot ayarları
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Groq istemcisini başlatıyoruz
groq_client = AsyncGroq(api_key=GROQ_API_KEY)

# Hafıza sözlükleri
ticket_durumlari = {} 
chat_gecmisleri = {}  

# MAX.AI KİŞİLİĞİ
SISTEM_MESAJI = """Senin adın Max.Ai. Bu Discord sunucusunun ilk kademe yapay zeka destek asistanısın. 
Amacın kullanıcılara kodlama, sunucu kuralları, teknik hatalar veya genel konularda hızlıca yardımcı olmak. 
Çok nazik, profesyonel ve çözüm odaklı bir dil kullan. Destan yazma, cevapların discord mesajı formatında kısa ve öz olsun. 
Eğer kullanıcının sorununu çözemezsen veya yetkili talep ederlerse, onlara "Canlı Desteğe Bağlan" butonuna tıklayabileceklerini hatırlat."""

# 4. AŞAMA: TİCKET KAPATMA
class TicketKapatView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Ticketi Kapat", style=discord.ButtonStyle.danger, custom_id="kapat_btn")
    async def kapat(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Ticket 5 saniye içinde kapatılıyor ve loglanıyor...")
        
        kanal_id = interaction.channel.id
        
        # Geçmiş mesajları çekip txt dosyası yapma
        messages = [message async for message in interaction.channel.history(limit=200, oldest_first=True)]
        log_metni = f"--- {interaction.channel.name} Log Kaydı ---\n\n"
        for msg in messages:
            log_metni += f"[{msg.author.name}]: {msg.content}\n"
            
        dosya = discord.File(io.BytesIO(log_metni.encode('utf-8')), filename=f"{interaction.channel.name}-log.txt")
        
        log_kanali = bot.get_channel(LOG_KANAL_ID)
        if log_kanali:
            await log_kanali.send(f"Biten Destek Logu: {interaction.channel.name}", file=dosya)
            
        # Hafızayı temizle
        if kanal_id in ticket_durumlari:
            del ticket_durumlari[kanal_id]
        if kanal_id in chat_gecmisleri:
            del chat_gecmisleri[kanal_id]
            
        await asyncio.sleep(5)
        await interaction.channel.delete()

# 3. AŞAMA: TİCKETİ DEVRALMA
class TicketiDevralView(discord.ui.View):
    def __init__(self, ticket_sahibi):
        super().__init__(timeout=None)
        self.ticket_sahibi = ticket_sahibi

    @discord.ui.button(label="✋ Ticketi Devral", style=discord.ButtonStyle.success, custom_id="devral_btn")
    async def devral(self, interaction: discord.Interaction, button: discord.ui.Button):
        if YETKILI_ROL_ID not in [role.id for role in interaction.user.roles]:
            return await interaction.response.send_message("Bu butonu sadece yetkililer kullanabilir!", ephemeral=True)

        ticket_durumlari[interaction.channel.id] = "DEVRALINDI"

        overwrites = interaction.channel.overwrites
        yetkili_rol = interaction.guild.get_role(YETKILI_ROL_ID)
        
        overwrites[yetkili_rol] = discord.PermissionOverwrite(read_messages=False)
        overwrites[interaction.user] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        await interaction.channel.edit(overwrites=overwrites)
        
        await interaction.response.send_message(
            f"✅ Bu ticket {interaction.user.mention} tarafından devralındı. Diğer yetkililere gizlendi.\nDestek bittiğinde kapatabilirsiniz.",
            view=TicketKapatView()
        )
        self.stop()

# 2. AŞAMA: CANLI DESTEĞE BAĞLAN
class CanliDestekView(discord.ui.View):
    def __init__(self, ticket_sahibi):
        super().__init__(timeout=None)
        self.ticket_sahibi = ticket_sahibi

    @discord.ui.button(label="🎧 Canlı Desteğe Bağlan", style=discord.ButtonStyle.primary, custom_id="canli_destek_btn")
    async def canli_destek(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ticket_sahibi:
            return await interaction.response.send_message("Bunu sadece ticketi açan kişi yapabilir!", ephemeral=True)

        ticket_durumlari[interaction.channel.id] = "BEKLIYOR"

        kategori = interaction.channel.category
        sira_no = len(kategori.channels) if kategori else 1

        yetkili_rol = interaction.guild.get_role(YETKILI_ROL_ID)
        mesaj = f"{yetkili_rol.mention} Yeni bir destek talebi var!\n" \
                f"Sıra Numaranız: **{sira_no}**\n" \
                f"En kısa sürede sizinle ilgileneceğiz."

        await interaction.response.send_message(mesaj, view=TicketiDevralView(self.ticket_sahibi))
        self.stop()

# 1. AŞAMA: TİCKET OLUŞTURMA
@bot.command()
async def ticket_kur(ctx):
    class TicketAcView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="📩 Destek Talebi Aç", style=discord.ButtonStyle.secondary, custom_id="ticket_ac_btn")
        async def ticket_ac(self, interaction: discord.Interaction, button: discord.ui.Button):
            guild = interaction.guild
            kategori = discord.utils.get(guild.categories, id=KATEGORI_ID)
            
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.get_role(YETKILI_ROL_ID): discord.PermissionOverwrite(read_messages=True)
            }
            
            kanal = await guild.create_text_channel(f"destek-{interaction.user.name}", category=kategori, overwrites=overwrites)
            
            kanal_id = kanal.id
            ticket_durumlari[kanal_id] = "AI_MODU"
            
            chat_gecmisleri[kanal_id] = [
                {"role": "system", "content": SISTEM_MESAJI}
            ]
            
            await interaction.response.send_message(f"Ticket açıldı: {kanal.mention}", ephemeral=True)
            
            ai_mesaji = f"Merhaba {interaction.user.mention}, ben **Max.Ai**. Sana yetkililerden önce yardımcı olmak için buradayım.\n" \
                        f"Ne konuda yardım arıyorsun? (Kodlama dilleri, sunucu sorunları vb.)"
            
            await kanal.send(ai_mesaji, view=CanliDestekView(interaction.user))

    await ctx.send("Destek talebi oluşturmak için aşağıdaki butona tıklayın.", view=TicketAcView())

# YAPAY ZEKA MESAJ DİNLEME SİSTEMİ
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    kanal_id = message.channel.id

    if kanal_id in ticket_durumlari and ticket_durumlari[kanal_id] == "AI_MODU":
        async with message.channel.typing():
            
            if kanal_id not in chat_gecmisleri:
                chat_gecmisleri[kanal_id] = [{"role": "system", "content": SISTEM_MESAJI}]
            
            chat_gecmisleri[kanal_id].append({"role": "user", "content": message.content})

            try:
                chat_completion = await groq_client.chat.completions.create(
                    messages=chat_gecmisleri[kanal_id],
                    model="llama3-8b-8192", 
                    temperature=0.7,
                    max_tokens=512,
                )

                ai_cevabi = chat_completion.choices[0].message.content
                chat_gecmisleri[kanal_id].append({"role": "assistant", "content": ai_cevabi})

                await message.channel.send(f"**Max.Ai:** {ai_cevabi}")

            except Exception as e:
                print(f"Groq API Hatası: {e}")
                await message.channel.send("Tüh, sistemsel bir yoğunluk var sanırım kanka! İstersen aşağıdaki butondan canlı desteğe bağlanabilirsin.")

    await bot.process_commands(message)

# Botu çalıştırıyoruz
bot.run(DISCORD_TOKEN)
          
