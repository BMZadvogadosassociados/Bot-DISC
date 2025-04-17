import discord
from discord.ext import commands, tasks
from discord.ui import View, Modal, TextInput, Button, Select
from discord import SelectOption
from math import ceil
import asyncio
from datetime import datetime

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Armazenamento por servidor (guild_id)
auto_roles = {}
ticket_response_channels = {}
mention_roles = {}  # guild_id: cargo que será mencionado nos tickets
sugestao_channels = {}  # guild_id: canal para sugestões/reclamações
test_channels = {}  # guild_id: canal para mensagens de teste

import json
import os

def salvar_dados():
    dados = {
        "auto_roles": auto_roles,
        "ticket_response_channels": ticket_response_channels,
        "mention_roles": mention_roles,
        "sugestao_channels": sugestao_channels,
        "test_channels": test_channels,
    }
    temp_file = "dados_servidor_temp.json"
    final_file = "dados_servidor.json"
    with open(temp_file, "w") as f:
        json.dump(dados, f, indent=4)  # indent deixa bonito e organizado
    os.replace(temp_file, final_file)


def carregar_dados():
    if os.path.exists("dados_servidor.json"):
        with open("dados_servidor.json", "r") as f:
            conteudo = f.read().strip()
            if conteudo:  # Só tenta carregar se não estiver vazio
                dados = json.loads(conteudo)
                auto_roles.update(dados.get("auto_roles", {}))
                ticket_response_channels.update(dados.get("ticket_response_channels", {}))
                mention_roles.update(dados.get("mention_roles", {}))
                sugestao_channels.update(dados.get("sugestao_channels", {}))
                test_channels.update(dados.get("test_channels", {}))


@bot.event
async def on_member_join(member):
    role_id = auto_roles.get(member.guild.id)
    if role_id:
        role = member.guild.get_role(role_id)
        if role:
            await member.add_roles(role)
            print(f"✅ Cargo {role.name} atribuído a {member.name}")

# Comando: define o cargo automático
@bot.command(aliases=["cargos"])
@commands.has_permissions(administrator=True)
async def cargo(ctx):
    roles = [r for r in ctx.guild.roles if not r.is_bot_managed() and r.name != "@everyone"]
    options = [SelectOption(label=r.name[:100], value=str(r.id)) for r in roles[:25] if r.name.strip()]

    if not options:
        await ctx.send("⚠️ Nenhum cargo válido encontrado.")
        return

    class RoleSelect(Select):
        def __init__(self):
            super().__init__(placeholder="Selecione o cargo automático", options=options)

        async def callback(self, interaction: discord.Interaction):
            selected_role_id = int(self.values[0])
            auto_roles[ctx.guild.id] = selected_role_id
            salvar_dados()  # <<< Aqui salva IMEDIATAMENTE!
            role = ctx.guild.get_role(selected_role_id)
            await interaction.response.send_message(f"✅ Cargo automático configurado para: **{role.name}**", ephemeral=True)

    view = View()
    view.add_item(RoleSelect())
    await ctx.send("👥 Selecione o cargo automático:", view=view)


@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    bot.add_view(TicketButtonView())
    bot.add_view(SugestaoView())



# Comando: define o cargo a ser mencionado nos tickets
@bot.command()
@commands.has_permissions(administrator=True)
async def setcargo(ctx):
    roles = [r for r in ctx.guild.roles if not r.is_bot_managed() and r.name != "@everyone"]
    options = [SelectOption(label=r.name[:100], value=str(r.id)) for r in roles[:25] if r.name.strip()]

    if not options:
        await ctx.send("⚠️ Nenhum cargo válido encontrado.")
        return

    class MentionRoleSelect(Select):
        def __init__(self):
            super().__init__(placeholder="Selecione o cargo para mencionar nos tickets", options=options)

        async def callback(self, interaction: discord.Interaction):
            selected = int(self.values[0])
            mention_roles[ctx.guild.id] = selected
            salvar_dados()  # <<< E aqui também!
            role = ctx.guild.get_role(selected)
            await interaction.response.send_message(f"📌 Cargo a ser mencionado nos tickets definido como: **{role.mention}**", ephemeral=True)

    view = View()
    view.add_item(MentionRoleSelect())
    await ctx.send("🔣 Selecione o cargo que será mencionado nos tickets:", view=view)


# Modal que abre com o botão dos tickets
class TicketModal(Modal, title="Solicitar Cargo"):
    nome = TextInput(label="Nome", placeholder="Digite seu nome completo", style=discord.TextStyle.short)
    cargo = TextInput(label="Setor / Cargo desejado", placeholder="Ex: Financeiro, RH...", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        mod_channel_id = ticket_response_channels.get(interaction.guild.id)
        mod_channel = bot.get_channel(mod_channel_id)
        cargo_id = mention_roles.get(interaction.guild.id)

        try:
            await interaction.user.edit(nick=self.nome.value)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Não consegui alterar seu apelido (permite o bot modificar nicknames?)", ephemeral=True)
            return

        if not mod_channel:
            await interaction.response.send_message("❌ Nenhum canal configurado para envio de tickets.", ephemeral=True)
            return

        embed = discord.Embed(title="📉 Novo Pedido de Cargo", color=discord.Color.blurple())
        embed.add_field(name="Usuário", value=interaction.user.mention, inline=False)
        embed.add_field(name="Cargo desejado", value=self.cargo.value, inline=False)
        embed.set_footer(text=f"ID: {interaction.user.id}")

        mention = f"<@&{cargo_id}>" if cargo_id else ""

        await mod_channel.send(content=mention, embed=embed)
        await interaction.response.send_message("✅ Pedido enviado com sucesso! Seu apelido foi atualizado.", ephemeral=True)

class TicketButton(Button):
    def __init__(self):
        super().__init__(label="Solicitar cargo", emoji="📬", style=discord.ButtonStyle.secondary, custom_id="ticket_button")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketModal())

class TicketButtonView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketButton())

# Comando: configura o canal onde os tickets serão enviados
@bot.command()
@commands.has_permissions(administrator=True)
async def ticket(ctx):
    all_channels = [c for c in ctx.guild.text_channels if c.permissions_for(ctx.guild.me).send_messages]
    if not all_channels:
        await ctx.send("❌ Não há canais disponíveis para seleção.")
        return

    per_page = 25
    total_pages = ceil(len(all_channels) / per_page)

    class ChannelSelect(Select):
        def __init__(self, page=0):
            self.page = page
            start = page * per_page
            end = start + per_page
            options = [SelectOption(label=c.name[:100], value=str(c.id)) for c in all_channels[start:end]]
            super().__init__(placeholder=f"Página {page + 1} de {total_pages}", options=options)

        async def callback(self, interaction: discord.Interaction):
            selected_channel_id = int(self.values[0])
            ticket_response_channels[ctx.guild.id] = selected_channel_id
            await interaction.response.send_message(f"✅ Canal de envio configurado para <#{selected_channel_id}>.", ephemeral=True)
            await ctx.send("📉 Solicite seu cargo abaixo:", view=TicketButtonView())

    class ChannelSelectionView(View):
        def __init__(self):
            super().__init__(timeout=60)
            self.page = 0
            self.select = ChannelSelect(self.page)
            self.add_item(self.select)

            if total_pages > 1:
                self.prev = Button(label="⏪ Anterior", style=discord.ButtonStyle.secondary)
                self.next = Button(label="⏩ Próximo", style=discord.ButtonStyle.secondary)
                self.prev.callback = self.go_prev
                self.next.callback = self.go_next
                self.add_item(self.prev)
                self.add_item(self.next)

        async def go_prev(self, interaction):
            if self.page > 0:
                self.page -= 1
                await self.update(interaction)

        async def go_next(self, interaction):
            if self.page < total_pages - 1:
                self.page += 1
                await self.update(interaction)

        async def update(self, interaction):
            self.clear_items()
            self.select = ChannelSelect(self.page)
            self.add_item(self.select)
            if total_pages > 1:
                self.add_item(self.prev)
                self.add_item(self.next)
            await interaction.response.edit_message(view=self)

    await ctx.send("📌 Selecione o canal para onde os tickets serão enviados:", view=ChannelSelectionView())

# Comando: define o canal para sugestões/reclamações anônimas
@bot.command()
@commands.has_permissions(administrator=True)
async def reclamacao(ctx):
    canais = [c for c in ctx.guild.text_channels if c.permissions_for(ctx.guild.me).send_messages]
    options = [SelectOption(label=c.name[:100], value=str(c.id)) for c in canais[:25]]

    class CanalSelect(Select):
        def __init__(self):
            super().__init__(placeholder="Escolha onde as mensagens anônimas serão enviadas", options=options)

        async def callback(self, interaction):
            canal_id = int(self.values[0])
            sugestao_channels[ctx.guild.id] = canal_id
            await interaction.response.send_message("✅ Canal de destino configurado!", ephemeral=True)
            await ctx.send(
                "**📜 Envie sua sugestão ou reclamação de forma anônima. Ninguém saberá que foi você.**",
                view=SugestaoView()
            )

    view = View()
    view.add_item(CanalSelect())
    await ctx.send("🔹 Escolha o canal que vai receber as sugestões/reclamações:", view=view)

class SugestaoModal(Modal, title="Envie sua sugestão ou reclamação"):
    mensagem = TextInput(label="Escreva aqui", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction):
        canal_id = sugestao_channels.get(interaction.guild.id)
        canal = bot.get_channel(canal_id)
        if canal:
            embed = discord.Embed(title="📢 Sugestão/Reclamação Anônima", description=self.mensagem.value, color=discord.Color.orange())
            embed.set_footer(text="Enviado anonimamente")
            await canal.send(embed=embed)
        await interaction.response.send_message("✅ Sua mensagem foi enviada de forma anônima!", ephemeral=True)

class SugestaoButton(Button):
    def __init__(self):
        super().__init__(label="Enviar sugestão/reclamação", emoji="💡", style=discord.ButtonStyle.secondary, custom_id="sugestao_button")

    async def callback(self, interaction):
        await interaction.response.send_modal(SugestaoModal())

class SugestaoView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(SugestaoButton())

@bot.command()
@commands.has_permissions(administrator=True)
async def clear(ctx):
    class ConfirmarLimpeza(Button):
        def __init__(self):
            super().__init__(label="Sim, limpar!", style=discord.ButtonStyle.danger)

        async def callback(self, interaction: discord.Interaction):
            if interaction.user != ctx.author:
                await interaction.response.send_message("❌ Apenas o autor do comando pode confirmar.", ephemeral=True)
                return

            for i in range(5, 0, -1):
                await mensagem.edit(content=f"🧹 Limpando em {i} segundos...")
                await asyncio.sleep(1)

            await ctx.channel.purge()
            aviso = await ctx.send("✅ Todas as mensagens foram limpas com sucesso!")
            await asyncio.sleep(3)
            await aviso.delete()

    view = View()
    view.add_item(ConfirmarLimpeza())
    mensagem = await ctx.send("⚠️ Tem certeza que deseja limpar todas as mensagens deste canal?", view=view)


@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 PONG! O bot está funcional.\n📶 Ping atual: `{latency}ms`")


# Comando de ajuda
@bot.command(name="ajuda")
async def ajuda(ctx):
    embed = discord.Embed(
        title="📖 Comandos disponíveis",
        color=discord.Color.green(),
        description="Veja abaixo os comandos que você pode usar:"
    )
    embed.add_field(name="!cargo", value="Define o cargo automático para novos membros.", inline=False)
    embed.add_field(name="!ticket", value="Escolhe o canal para os pedidos de cargo e exibe o botão.", inline=False)
    embed.add_field(name="!setcargo", value="Define qual cargo será mencionado nas mensagens do ticket.", inline=False)
    embed.add_field(name="!reclamacao", value="Cria botão para sugestões/reclamações anônimas.", inline=False)
    embed.add_field(name="!ajuda", value="Mostra esta mensagem com todos os comandos.", inline=False)
    embed.add_field(name="!ping", value="Verifica se o bot está funcional e mostra o ping.", inline=False)

    await ctx.send(embed=embed)



@bot.event
async def on_command_completion(ctx):
    salvar_dados()

@bot.event
async def on_guild_join(guild):
    salvar_dados()

@bot.event
async def on_guild_remove(guild):
    auto_roles.pop(str(guild.id), None)
    ticket_response_channels.pop(str(guild.id), None)
    mention_roles.pop(str(guild.id), None)
    sugestao_channels.pop(str(guild.id), None)
    test_channels.pop(str(guild.id), None)
    salvar_dados()


from dotenv import load_dotenv

load_dotenv()
carregar_dados()  # <<< ADICIONE ESTA LINHA AQUI

TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)

