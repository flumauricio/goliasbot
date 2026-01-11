import asyncio
import logging
import re
from typing import Optional

import discord
from discord.ext import commands

from db import Database

LOGGER = logging.getLogger(__name__)


# Cores de botão do Discord
BUTTON_COLORS = {
    "verde": discord.ButtonStyle.success,
    "azul": discord.ButtonStyle.primary,
    "vermelho": discord.ButtonStyle.danger,
    "cinza": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "primary": discord.ButtonStyle.primary,
    "danger": discord.ButtonStyle.danger,
    "secondary": discord.ButtonStyle.secondary,
}


async def _ask(ctx: commands.Context, prompt: str, timeout: int = 120) -> str:
    """Helper para perguntar algo ao usuário."""
    await ctx.send(prompt)

    def check(msg: discord.Message) -> bool:
        return msg.author == ctx.author and msg.channel == ctx.channel

    try:
        msg = await ctx.bot.wait_for("message", check=check, timeout=timeout)
        return msg.content.strip()
    except asyncio.TimeoutError:
        raise TimeoutError("Tempo esgotado.")


async def _ask_yes_no(ctx: commands.Context, prompt: str) -> bool:
    """Pergunta sim/não e retorna True/False."""
    response = await _ask(ctx, f"{prompt} (sim/não)")
    return response.lower() in ("sim", "s", "yes", "y")


def parse_hex_color(color_str: str) -> Optional[discord.Color]:
    """Tenta parsear uma cor hexadecimal ou nome comum."""
    color_str = color_str.strip().lower()
    
    # Cores comuns
    color_map = {
        "vermelho": discord.Color.red(),
        "red": discord.Color.red(),
        "azul": discord.Color.blue(),
        "blue": discord.Color.blue(),
        "verde": discord.Color.green(),
        "green": discord.Color.green(),
        "amarelo": discord.Color.gold(),
        "yellow": discord.Color.gold(),
        "roxo": discord.Color.purple(),
        "purple": discord.Color.purple(),
        "laranja": discord.Color.orange(),
        "orange": discord.Color.orange(),
    }
    
    if color_str in color_map:
        return color_map[color_str]
    
    # Tenta hexadecimal
    if color_str.startswith("#"):
        color_str = color_str[1:]
    
    if re.match(r"^[0-9a-f]{6}$", color_str):
        try:
            return discord.Color(int(color_str, 16))
        except ValueError:
            pass
    
    return None


class TicketOpenView(discord.ui.View):
    """View persistente para abrir tickets."""
    
    def __init__(self, db: Database):
        super().__init__(timeout=None)
        self.db = db
    
    @discord.ui.button(
        label="Abrir Ticket",
        style=discord.ButtonStyle.primary,
        emoji="🎫",
        custom_id="btn_open_ticket_rota40"
    )
    async def open_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Botão que abre o menu de seleção de tópicos."""
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Este comando só funciona em servidores.", ephemeral=True)
            return
        
        topics = await self.db.get_ticket_topics(guild.id)
        if not topics:
            await interaction.response.send_message(
                "❌ Nenhum tópico de ticket configurado. Use `!ticket_setup` para configurar.",
                ephemeral=True
            )
            return
        
        # Cria um Select com os tópicos
        options = []
        for topic in topics[:25]:  # Limite do Discord
            emoji_str = topic.get("emoji", "🎫")
            name = topic.get("name", "Sem nome")
            description = topic.get("description", "")[:100]  # Limite de 100 chars
            
            options.append(
                discord.SelectOption(
                    label=name,
                    description=description,
                    emoji=emoji_str,
                    value=str(topic["id"]),
                )
            )
        
        view = TopicSelectView(self.db, options)
        await interaction.response.send_message(
            "Selecione o tipo de ticket que deseja abrir:",
            view=view,
            ephemeral=True
        )


class TopicSelectView(discord.ui.View):
    """View com Select para escolher tópico."""
    
    def __init__(self, db: Database, options: list):
        super().__init__(timeout=60)
        self.db = db
        self.select = discord.ui.Select(
            placeholder="Escolha um tópico...",
            options=options,
            min_values=1,
            max_values=1,
        )
        self.select.callback = self.on_select
        self.add_item(self.select)
    
    async def on_select(self, interaction: discord.Interaction):
        """Cria o ticket quando um tópico é selecionado."""
        topic_id = int(self.select.values[0])
        topic = await self.db.get_ticket_topic(topic_id)
        
        if not topic:
            await interaction.response.send_message("❌ Tópico não encontrado.", ephemeral=True)
            return
        
        guild = interaction.guild
        user = interaction.user
        
        if not guild:
            await interaction.response.send_message("Erro: servidor não encontrado.", ephemeral=True)
            return
        
        # Busca configurações
        settings = await self.db.get_ticket_settings(guild.id)
        category_id = settings.get("category_id")
        
        if not category_id:
            await interaction.response.send_message(
                "❌ Sistema de tickets não configurado. Use `!ticket_setup` primeiro.",
                ephemeral=True
            )
            return
        
        category = guild.get_channel(int(category_id))
        if not category or not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                "❌ Categoria de tickets não encontrada. Use `!ticket_setup` para reconfigurar.",
                ephemeral=True
            )
            return
        
        # Verifica limite de tickets abertos
        settings = await self.db.get_ticket_settings(guild.id)
        max_tickets = settings.get("max_tickets_per_user", 1) or 1
        
        open_count = await self.db.count_open_tickets_by_user(guild.id, user.id)
        if open_count >= max_tickets:
            await interaction.response.send_message(
                f"❌ Você já tem {open_count} ticket(s) aberto(s). O limite é {max_tickets} ticket(s) por usuário.\n"
                f"Por favor, feche seus tickets existentes antes de abrir um novo.",
                ephemeral=True
            )
            return
        
        # Cria o canal
        emoji_str = topic.get("emoji", "🎫")
        channel_name = f"{emoji_str}-{topic['name'].lower().replace(' ', '-')}-{user.name.lower()}"
        channel_name = channel_name[:100]  # Limite do Discord
        
        # Busca cargos do tópico
        role_ids = await self.db.get_topic_roles(topic_id)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_messages=True,
                read_message_history=True,
            ),
        }
        
        # Adiciona permissões para cargos de staff
        for role_id_str in role_ids:
            try:
                role = guild.get_role(int(role_id_str))
                if role:
                    overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                    )
            except (ValueError, TypeError):
                pass
        
        # Adiciona permissão para administradores
        overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
        
        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Ticket criado por {user}",
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Não tenho permissão para criar canais. Verifique as permissões do bot.",
                ephemeral=True
            )
            return
        except Exception as e:
            LOGGER.error("Erro ao criar canal de ticket: %s", e, exc_info=e)
            await interaction.response.send_message(
                "❌ Erro ao criar o canal de ticket. Tente novamente.",
                ephemeral=True
            )
            return
        
        # Cria registro no banco
        ticket_id = await self.db.create_ticket(guild.id, channel.id, user.id, topic_id)
        
        # Envia embed de boas-vindas
        embed = discord.Embed(
            title=f"{emoji_str} {topic['name']}",
            description=topic.get("description", "Bem-vindo ao seu ticket!"),
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="👤 Autor", value=user.mention, inline=True)
        embed.add_field(name="📅 Criado em", value=discord.utils.format_dt(discord.utils.utcnow(), style="R"), inline=True)
        embed.set_footer(text=f"Ticket #{ticket_id}")
        
        view = TicketControlView(self.db, ticket_id, user.id)
        await channel.send(embed=embed, view=view)
        
        # Notifica staff sobre novo ticket
        role_ids = await self.db.get_topic_roles(topic_id)
        if role_ids:
            mentions = []
            for role_id_str in role_ids:
                try:
                    role = guild.get_role(int(role_id_str))
                    if role:
                        mentions.append(role.mention)
                except (ValueError, TypeError):
                    pass
            
            if mentions:
                notification_embed = discord.Embed(
                    title="🔔 Novo Ticket Criado",
                    description=f"{user.mention} abriu um ticket: {channel.mention}",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow(),
                )
                notification_embed.add_field(name="Tópico", value=topic['name'], inline=True)
                notification_embed.add_field(name="Ticket ID", value=f"#{ticket_id}", inline=True)
                notification_embed.set_footer(text="Sistema de Tickets")
                
                await channel.send(
                    f"{' '.join(mentions)} - Novo ticket criado!",
                    embed=notification_embed
                )
        
        await interaction.response.send_message(
            f"✅ Ticket criado! Acesse {channel.mention}",
            ephemeral=True
        )


class TicketControlView(discord.ui.View):
    """View com botões de controle do ticket."""
    
    def __init__(self, db: Database, ticket_id: int, author_id: int, is_closed: bool = False):
        super().__init__(timeout=None)
        self.db = db
        self.ticket_id = ticket_id
        self.author_id = author_id
        self.is_closed = is_closed
        
        # Se o ticket estiver fechado, adiciona botão de reabertura
        if is_closed:
            self.add_item(ReopenButton(self.db, ticket_id, author_id))
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Verifica se o usuário pode interagir com os botões."""
        # Autor e administradores sempre podem
        if interaction.user.id == self.author_id or interaction.user.guild_permissions.administrator:
            return True
        
        # Verifica se é staff do tópico
        ticket = await self.db.get_ticket_by_channel(interaction.channel.id)
        if ticket and ticket.get("topic_id"):
            role_ids = await self.db.get_topic_roles(ticket["topic_id"])
            user_roles = [role.id for role in interaction.user.roles]
            for role_id_str in role_ids:
                try:
                    if int(role_id_str) in user_roles:
                        return True
                except (ValueError, TypeError):
                    pass
        
        return False
    
    async def on_timeout(self):
        """Remove botões quando a view expira (não deve acontecer com timeout=None, mas por segurança)."""
        pass
    
    @discord.ui.button(label="🔒 Fechar", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Fecha o ticket após confirmação."""
        # Verifica permissão (admin ou autor)
        if not interaction.user.guild_permissions.administrator and interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Apenas administradores ou o autor do ticket podem fechá-lo.",
                ephemeral=True
            )
            return
        
        # Confirmação
        view = ConfirmCloseView(self.db, self.ticket_id, interaction.channel)
        await interaction.response.send_message(
            "⚠️ Tem certeza que deseja fechar este ticket? Uma transcrição será gerada.",
            view=view,
            ephemeral=True
        )
    
    @discord.ui.button(label="🙋‍♂️ Assumir", style=discord.ButtonStyle.primary, custom_id="ticket_claim")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Marca o ticket como assumido."""
        ticket = await self.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message("❌ Ticket não encontrado.", ephemeral=True)
            return
        
        if ticket.get("claimed_by"):
            claimed_user = interaction.guild.get_member(int(ticket["claimed_by"]))
            if claimed_user:
                await interaction.response.send_message(
                    f"ℹ️ Este ticket já está sendo atendido por {claimed_user.mention}.",
                    ephemeral=True
                )
                return
        
        await self.db.claim_ticket(self.ticket_id, interaction.user.id)
        await interaction.response.send_message(
            f"✅ {interaction.user.mention} assumiu este ticket.",
            allowed_mentions=discord.AllowedMentions(users=[interaction.user])
        )
    
    @discord.ui.button(label="📝 Transcrição", style=discord.ButtonStyle.secondary, custom_id="ticket_transcript")
    async def generate_transcript(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Gera transcrição do ticket."""
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("❌ Erro ao gerar transcrição.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Coleta mensagens
        messages = []
        async for msg in channel.history(limit=None, oldest_first=True):
            content = msg.content or "(sem texto)"
            if msg.embeds:
                content += " [Embed]"
            if msg.attachments:
                content += f" [Anexos: {', '.join(a.filename for a in msg.attachments)}]"
            messages.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author} ({msg.author.id}): {content}")
        
        transcript = "\n".join(messages)
        
        # Envia como arquivo
        file = discord.File(
            fp=transcript.encode("utf-8"),
            filename=f"transcript-{channel.name}-{discord.utils.utcnow().strftime('%Y%m%d-%H%M%S')}.txt"
        )
        
        await interaction.followup.send(
            "📝 Transcrição gerada:",
            file=file,
            ephemeral=True
        )
    


class ReopenButton(discord.ui.Button):
    """Botão para reabrir ticket fechado."""
    
    def __init__(self, db: Database, ticket_id: int, author_id: int):
        super().__init__(
            label="🔓 Reabrir",
            style=discord.ButtonStyle.success,
            custom_id=f"ticket_reopen_{ticket_id}"
        )
        self.db = db
        self.ticket_id = ticket_id
        self.author_id = author_id
    
    async def callback(self, interaction: discord.Interaction):
        """Reabre um ticket fechado."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Apenas administradores podem reabrir tickets.",
                ephemeral=True
            )
            return
        
        ticket = await self.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message("❌ Ticket não encontrado.", ephemeral=True)
            return
        
        if ticket.get("status") != "closed":
            await interaction.response.send_message(
                "ℹ️ Este ticket já está aberto.",
                ephemeral=True
            )
            return
        
        await self.db.reopen_ticket(self.ticket_id)
        
        embed = discord.Embed(
            title="🔓 Ticket Reaberto",
            description=f"Este ticket foi reaberto por {interaction.user.mention}",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        
        await interaction.response.send_message(embed=embed)
        
        # Atualiza a view para remover o botão de reabertura
        author_id = int(ticket["user_id"])
        view = TicketControlView(self.db, self.ticket_id, author_id, is_closed=False)
        try:
            # Tenta encontrar a mensagem original com os botões
            async for msg in interaction.channel.history(limit=50):
                if msg.embeds and msg.embeds[0].footer and f"Ticket #{self.ticket_id}" in str(msg.embeds[0].footer.text):
                    await msg.edit(view=view)
                    break
        except Exception as e:
            LOGGER.warning("Erro ao atualizar view após reabertura: %s", e)


class ConfirmCloseView(discord.ui.View):
    """View de confirmação para fechar ticket."""
    
    def __init__(self, db: Database, ticket_id: int, channel: discord.TextChannel):
        super().__init__(timeout=30)
        self.db = db
        self.ticket_id = ticket_id
        self.channel = channel
    
    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirma e fecha o ticket."""
        # Gera transcrição antes de fechar
        messages = []
        async for msg in self.channel.history(limit=None, oldest_first=True):
            messages.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author}: {msg.content}")
        
        transcript = "\n".join(messages)
        
        # Busca canal de logs
        ticket = await self.db.get_ticket_by_channel(self.channel.id)
        if ticket:
            settings = await self.db.get_ticket_settings(int(ticket["guild_id"]))
            log_channel_id = settings.get("log_channel_id")
            
            if log_channel_id:
                log_channel = interaction.guild.get_channel(int(log_channel_id))
                if log_channel:
                    file = discord.File(
                        fp=transcript.encode("utf-8"),
                        filename=f"transcript-{self.channel.name}-{discord.utils.utcnow().strftime('%Y%m%d-%H%M%S')}.txt"
                    )
                    embed = discord.Embed(
                        title="🎫 Ticket Fechado",
                        description=f"Ticket `{self.channel.name}` foi fechado por {interaction.user.mention}",
                        color=discord.Color.red(),
                        timestamp=discord.utils.utcnow(),
                    )
                    await log_channel.send(embed=embed, file=file)
        
        # Fecha no banco
        await self.db.close_ticket(self.ticket_id)
        
        # Deleta o canal
        try:
            await self.channel.delete(reason=f"Ticket fechado por {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message(
                "✅ Ticket marcado como fechado, mas não tenho permissão para deletar o canal.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "✅ Ticket fechado e canal deletado.",
                ephemeral=True
            )
    
    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancela o fechamento."""
        await interaction.response.send_message("❌ Fechamento cancelado.", ephemeral=True)
        self.stop()


class TicketCog(commands.Cog):
    """Cog para sistema de tickets."""
    
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db
    
    @commands.command(name="ticket_setup")
    @commands.has_permissions(administrator=True)
    async def ticket_setup(self, ctx: commands.Context):
        """Wizard interativo para configurar o sistema de tickets."""
        guild = ctx.guild
        if not guild:
            await ctx.reply("Este comando só funciona em servidores.")
            return
        
        # Verifica permissões do bot
        bot_member = guild.me
        if not bot_member.guild_permissions.manage_channels:
            await ctx.reply(
                "❌ Eu preciso da permissão **Gerenciar Canais** para configurar tickets.",
                delete_after=15
            )
            return
        
        if not bot_member.guild_permissions.manage_roles:
            await ctx.reply(
                "❌ Eu preciso da permissão **Gerenciar Cargos** para configurar tickets.",
                delete_after=15
            )
            return
        
        await ctx.reply("🎫 Iniciando configuração do sistema de tickets...")
        
        try:
            # 1. Categoria
            create_category = await _ask_yes_no(
                ctx,
                "Deseja que eu crie uma nova categoria para os tickets ou usar uma existente? (responda 'sim' para criar nova)"
            )
            
            if create_category:
                category_name = await _ask(ctx, "Informe o nome da categoria (ex: 🎫 Tickets):")
                category = await guild.create_category(category_name)
                await ctx.reply(f"✅ Categoria `{category.name}` criada!")
            else:
                category_id_str = await _ask(ctx, "Informe o ID da categoria existente:")
                try:
                    category_id = int(category_id_str)
                    category = guild.get_channel(category_id)
                    if not category or not isinstance(category, discord.CategoryChannel):
                        await ctx.reply("❌ Categoria não encontrada. Cancelando setup.")
                        return
                except ValueError:
                    await ctx.reply("❌ ID inválido. Cancelando setup.")
                    return
            
            await self.db.upsert_ticket_settings(guild.id, category_id=category.id)
            
            # 2. Canal de tickets (painel)
            create_ticket_channel = await _ask_yes_no(
                ctx,
                "Deseja criar um canal específico para o painel de tickets? (responda 'sim' para criar)"
            )
            
            if create_ticket_channel:
                ticket_channel = await guild.create_text_channel("🎫-suporte")
                await ctx.reply(f"✅ Canal de tickets `{ticket_channel.name}` criado!")
            else:
                ticket_channel_id_str = await _ask(ctx, "Informe o ID do canal onde deseja enviar o painel de tickets (ou 'pular' para configurar depois):")
                if ticket_channel_id_str.lower() != "pular":
                    try:
                        ticket_channel_id = int(ticket_channel_id_str)
                        ticket_channel = guild.get_channel(ticket_channel_id)
                        if not ticket_channel or not isinstance(ticket_channel, discord.TextChannel):
                            await ctx.reply("❌ Canal não encontrado. Você pode configurar depois com !ticket.")
                            ticket_channel = None
                    except ValueError:
                        await ctx.reply("❌ ID inválido. Você pode configurar depois com !ticket.")
                        ticket_channel = None
                else:
                    ticket_channel = None
            
            if ticket_channel:
                await self.db.upsert_ticket_settings(guild.id, ticket_channel_id=ticket_channel.id)
            
            # 3. Limite de tickets por usuário
            limit_response = await _ask(ctx, "Quantos tickets cada usuário pode ter abertos simultaneamente? (padrão: 1)")
            try:
                max_tickets = int(limit_response.strip())
                if max_tickets < 1:
                    max_tickets = 1
            except ValueError:
                max_tickets = 1
                await ctx.reply("⚠️ Valor inválido, usando padrão: 1")
            
            await self.db.upsert_ticket_settings(guild.id, max_tickets_per_user=max_tickets)
            
            # 4. Canal de logs
            create_log_channel = await _ask_yes_no(
                ctx,
                "Deseja criar um canal de logs para transcrições de tickets? (responda 'sim' para criar)"
            )
            
            if create_log_channel:
                log_channel = await guild.create_text_channel("🎫-logs-tickets")
                await ctx.reply(f"✅ Canal de logs `{log_channel.name}` criado!")
            else:
                log_channel_id_str = await _ask(ctx, "Informe o ID do canal de logs existente:")
                try:
                    log_channel_id = int(log_channel_id_str)
                    log_channel = guild.get_channel(log_channel_id)
                    if not log_channel or not isinstance(log_channel, discord.TextChannel):
                        await ctx.reply("❌ Canal não encontrado. Continuando sem logs...")
                        log_channel = None
                except ValueError:
                    await ctx.reply("❌ ID inválido. Continuando sem logs...")
                    log_channel = None
            
            if log_channel:
                await self.db.upsert_ticket_settings(guild.id, log_channel_id=log_channel.id)
            
            # 5. Criar tópicos
            topics = []
            while True:
                create_topic = await _ask_yes_no(ctx, "Deseja adicionar um novo tópico de ticket?")
                if not create_topic:
                    break
                
                topic_name = await _ask(ctx, "Nome do tópico (ex: Suporte, Denúncia):")
                topic_description = await _ask(ctx, "Descrição do tópico:")
                topic_emoji = await _ask(ctx, "Emoji do tópico (ex: 🎫, 💬):")
                
                # Cor do botão
                color_response = await _ask(
                    ctx,
                    "Cor do botão (verde/azul/vermelho/cinza ou primary/success/danger/secondary):"
                )
                button_color = color_response.lower()
                if button_color not in BUTTON_COLORS:
                    button_color = "primary"
                
                topic_id = await self.db.create_ticket_topic(
                    guild.id,
                    topic_name,
                    topic_description,
                    topic_emoji,
                    button_color,
                )
                
                # Cargos do tópico
                create_role = await _ask_yes_no(
                    ctx,
                    "Deseja criar um novo cargo de Staff para este tópico ou usar um existente? (responda 'sim' para criar novo)"
                )
                
                if create_role:
                    role_name = await _ask(ctx, "Nome do cargo (ex: Staff Suporte):")
                    color_response = await _ask(
                        ctx,
                        "Cor do cargo (hexadecimal como #FF0000 ou nome como 'vermelho'):"
                    )
                    role_color = parse_hex_color(color_response) or discord.Color.blue()
                    
                    try:
                        role = await guild.create_role(
                            name=role_name,
                            color=role_color,
                            reason="Cargo criado para sistema de tickets",
                        )
                        await self.db.add_topic_role(topic_id, role.id)
                        await ctx.reply(f"✅ Cargo `{role.name}` criado e vinculado ao tópico!")
                    except discord.Forbidden:
                        await ctx.reply("❌ Não tenho permissão para criar cargos. Pulando...")
                else:
                    role_id_str = await _ask(ctx, "Informe o ID do cargo existente:")
                    try:
                        role_id = int(role_id_str)
                        role = guild.get_role(role_id)
                        if role:
                            await self.db.add_topic_role(topic_id, role.id)
                            await ctx.reply(f"✅ Cargo `{role.name}` vinculado ao tópico!")
                        else:
                            await ctx.reply("❌ Cargo não encontrado. Pulando...")
                    except ValueError:
                        await ctx.reply("❌ ID inválido. Pulando...")
                
                topics.append({"id": topic_id, "name": topic_name})
                await ctx.reply(f"✅ Tópico '{topic_name}' criado!")
            
            if not topics:
                await ctx.reply("⚠️ Nenhum tópico criado. Use `!ticket_setup` novamente para adicionar.")
                return
            
            await ctx.reply("✅ Configuração de tickets concluída!")
            
        except TimeoutError:
            await ctx.reply("⏰ Tempo esgotado. Use `!ticket_setup` novamente.")
        except Exception as e:
            LOGGER.error("Erro no ticket_setup: %s", e, exc_info=e)
            await ctx.reply(f"❌ Erro durante configuração: {str(e)}")
    
    @commands.command(name="ticket")
    @commands.has_permissions(administrator=True)
    async def create_ticket_panel(self, ctx: commands.Context):
        """Cria o painel de tickets no canal configurado."""
        guild = ctx.guild
        if not guild:
            await ctx.reply("Este comando só funciona em servidores.")
            return
        
        topics = await self.db.get_ticket_topics(guild.id)
        if not topics:
            await ctx.reply(
                "❌ Nenhum tópico configurado. Use `!ticket_setup` primeiro.",
                delete_after=15
            )
            return
        
        # Busca canal configurado
        settings = await self.db.get_ticket_settings(guild.id)
        ticket_channel_id = settings.get("ticket_channel_id")
        
        if ticket_channel_id:
            channel = guild.get_channel(int(ticket_channel_id))
            if not channel or not isinstance(channel, discord.TextChannel):
                await ctx.reply(
                    "❌ Canal de tickets configurado não encontrado. Use `!ticket_setup` para reconfigurar.",
                    delete_after=15
                )
                return
        else:
            # Se não estiver configurado, pergunta
            use_current = await _ask_yes_no(
                ctx,
                "Nenhum canal de tickets configurado. Deseja usar o canal atual? (responda 'sim' para usar o canal atual, 'não' para criar um novo)"
            )
            
            if use_current:
                channel = ctx.channel
            else:
                try:
                    channel = await guild.create_text_channel(
                        "🎫-suporte",
                        reason="Canal criado para painel de tickets",
                    )
                    await ctx.reply(f"✅ Canal `{channel.name}` criado!")
                except discord.Forbidden:
                    await ctx.reply("❌ Não tenho permissão para criar canais.")
                    return
            
            # Salva o canal
            await self.db.upsert_ticket_settings(guild.id, ticket_channel_id=channel.id)
        
        # Verifica se já existe um painel e deleta a mensagem antiga se necessário
        panel_message_id = settings.get("panel_message_id")
        if panel_message_id:
            try:
                old_message = await channel.fetch_message(int(panel_message_id))
                if old_message:
                    try:
                        await old_message.delete()
                    except discord.NotFound:
                        pass
            except (discord.NotFound, ValueError, discord.Forbidden):
                pass
        
        # Cria embed do painel
        embed = discord.Embed(
            title="🎫 Sistema de Tickets",
            description=(
                "Clique no botão abaixo para abrir um ticket.\n\n"
                "Selecione o tipo de atendimento que você precisa e nossa equipe irá ajudá-lo!"
            ),
            color=discord.Color.blue(),
        )
        
        # Lista tópicos
        topics_text = "\n".join([
            f"{topic.get('emoji', '🎫')} **{topic['name']}** - {topic.get('description', '')}"
            for topic in topics[:10]  # Limite visual
        ])
        if topics_text:
            embed.add_field(name="Tipos de Tickets Disponíveis", value=topics_text, inline=False)
        
        # Adiciona informações sobre limite
        max_tickets = settings.get("max_tickets_per_user", 1) or 1
        embed.add_field(
            name="ℹ️ Informações",
            value=f"Limite: {max_tickets} ticket(s) aberto(s) por usuário",
            inline=False
        )
        
        view = TicketOpenView(self.db)
        message = await channel.send(embed=embed, view=view)
        
        # Salva message_id
        await self.db.upsert_ticket_settings(guild.id, panel_message_id=message.id)
        
        await ctx.reply(f"✅ Painel de tickets criado/atualizado em {channel.mention}!")
    
    @commands.command(name="ticket_stats")
    @commands.has_permissions(administrator=True)
    async def ticket_stats(self, ctx: commands.Context):
        """Exibe estatísticas de tickets do servidor."""
        guild = ctx.guild
        if not guild:
            await ctx.reply("Este comando só funciona em servidores.")
            return
        
        stats = await self.db.get_ticket_stats(guild.id)
        
        embed = discord.Embed(
            title="📊 Estatísticas de Tickets",
            description=f"Estatísticas do sistema de tickets de **{guild.name}**",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        )
        
        embed.add_field(name="📈 Total de Tickets", value=str(stats["total"]), inline=True)
        embed.add_field(name="🟢 Tickets Abertos", value=str(stats["open"]), inline=True)
        embed.add_field(name="🔴 Tickets Fechados", value=str(stats["closed"]), inline=True)
        
        if stats["total"] > 0:
            embed.add_field(
                name="⏱️ Tempo Médio de Resolução",
                value=f"{stats['avg_resolution_hours']:.2f} horas" if stats["avg_resolution_hours"] > 0 else "N/A",
                inline=True
            )
            embed.add_field(
                name="📊 Taxa de Resolução",
                value=f"{stats['resolution_rate']:.1f}%",
                inline=True
            )
        
        embed.set_footer(text="Sistema de Tickets")
        
        await ctx.reply(embed=embed)
