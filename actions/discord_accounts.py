"""
Sistema de gerenciamento de contas Discord.
"""

import io
import logging

import discord
from discord.ext import commands

from db import Database

LOGGER = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _fmt_dt(value) -> str:
    if not value:
        return "—"

    from datetime import datetime, timezone, timedelta

    s = str(value).strip()
    s = s.replace("T", " ")

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt_utc = datetime.strptime(s[:19], fmt)
            break
        except ValueError:
            continue
    else:
        return s

    brt = timezone(timedelta(hours=-3))
    dt_brt = dt_utc.replace(tzinfo=timezone.utc).astimezone(brt)

    return dt_brt.strftime("%d/%m/%y")


# ─────────────────────────────────────────────────────────────
# Modal observação
# ─────────────────────────────────────────────────────────────

class DiscordNoteModal(discord.ui.Modal, title="Editar Observação"):

    note = discord.ui.TextInput(
        label="Observação",
        required=False,
        max_length=500,
        style=discord.TextStyle.paragraph,
    )

    def __init__(self, db: Database, account_id: int, manage_view):
        super().__init__()

        self.db = db
        self.account_id = account_id
        self.manage_view = manage_view

    async def on_submit(self, interaction: discord.Interaction):

        await self.db.discord_update_note(
            self.account_id,
            self.note.value,
        )

        embed = await self.manage_view.build_embed()

        await interaction.response.edit_message(
            embed=embed,
            view=self.manage_view,
        )


class DiscordSteamModal(discord.ui.Modal, title="Editar Steam"):

    steam_user = discord.ui.TextInput(
        label="Usuário Steam",
        required=True,
        max_length=100,
    )
    steam_password = discord.ui.TextInput(
        label="Senha Steam",
        required=True,
        max_length=100,
        style=discord.TextStyle.short,
    )

    def __init__(self, db: Database, account_id: int, manage_view):
        super().__init__()

        self.db = db
        self.account_id = account_id
        self.manage_view = manage_view

    async def on_submit(self, interaction: discord.Interaction):

        await self.db.discord_update_steam(
            self.account_id,
            self.steam_user.value,
            self.steam_password.value,
        )

        embed = await self.manage_view.build_embed()

        await interaction.response.edit_message(
            embed=embed,
            view=self.manage_view,
        )


# ─────────────────────────────────────────────────────────────
# Vincular Rockstar
# ─────────────────────────────────────────────────────────────

class RockstarLinkView(discord.ui.View):

    def __init__(
        self,
        db: Database,
        discord_account_id: int,
        user_id: int,
        guild_id: int,
        manage_view,
    ):
        super().__init__(timeout=60)

        self.db = db
        self.discord_account_id = discord_account_id
        self.user_id = user_id
        self.guild_id = guild_id
        self.manage_view = manage_view

    async def setup(self):

        accounts = await self.db.rockstar_list_accounts(
            self.user_id,
            self.guild_id,
        )

        options = [
            discord.SelectOption(
                label="Remover vínculo",
                value="remove",
                emoji="❌",
            )
        ]

        for acc in accounts[:24]:
            options.append(
                discord.SelectOption(
                    label=acc["email"][:100],
                    value=str(acc["id"]),
                    emoji="🎮",
                )
            )

        select = discord.ui.Select(
            placeholder="Selecione a conta Rockstar",
            options=options,
        )

        async def callback(interaction: discord.Interaction):

            value = interaction.data["values"][0]

            if value == "remove":
                rockstar_id = None
            else:
                rockstar_id = int(value)

            await self.db.discord_link_rockstar(
                self.discord_account_id,
                rockstar_id,
            )

            embed = await self.manage_view.build_embed()

            await interaction.response.edit_message(
                embed=embed,
                view=self.manage_view,
            )

        select.callback = callback

        self.add_item(select)


# ─────────────────────────────────────────────────────────────
# Gerenciamento conta
# ─────────────────────────────────────────────────────────────

class DiscordManageView(discord.ui.View):

    def __init__(
        self,
        db: Database,
        account_id: int,
        user_id: int,
        guild_id: int,
        list_view,
    ):
        super().__init__(timeout=60)

        self.db = db
        self.account_id = account_id
        self.user_id = user_id
        self.guild_id = guild_id
        self.list_view = list_view

    async def interaction_check(self, interaction):

        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ Não autorizado.",
                ephemeral=True,
            )
            return False

        return True

    async def build_embed(self):

        acc = await self.db.discord_get_account(
            self.account_id
        )

        embed = discord.Embed(
            title=f"🎧 {acc['discord_user']}",
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name="👤 Discord",
            value=f"```{acc['discord_user']}```",
            inline=False,
        )

        embed.add_field(
            name="🔑 Senha Discord",
            value=f"```{acc['discord_password']}```",
            inline=False,
        )

        embed.add_field(
            name="📧 Email",
            value=f"```{acc['email']}```",
            inline=False,
        )

        embed.add_field(
            name="🔑 Senha Email",
            value=f"```{acc['email_password']}```",
            inline=False,
        )

        if acc.get("steam_user"):

            embed.add_field(
                name="🎮 Steam",
                value=f"```{acc['steam_user']}```",
                inline=False,
            )

            embed.add_field(
                name="🔑 Senha Steam",
                value=f"```{acc['steam_password']}```",
                inline=False,
            )

        # Rockstar vinculada
        if acc.get("rockstar_account_id"):

            rockstar = await self.db.rockstar_get_account(
                acc["rockstar_account_id"]
            )

            if rockstar:
                value = f"```{rockstar['email']}```"
            else:
                value = "Conta removida"

        else:
            value = "Nenhuma"
        
        embed.add_field(
            name="🎮 Rockstar vinculada",
            value=value,
            inline=False,
        )

        embed.add_field(
            name="📝 Observação",
            value=acc.get("note") or "*Sem observação*",
            inline=False,
        )

        embed.add_field(
            name="📅 Criada em",
            value=f"`{_fmt_dt(acc.get('created_at'))}`",
            inline=False,
        )

        return embed

    @discord.ui.button(
        label="🔗 Vincular Rockstar",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def link_rockstar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        view = RockstarLinkView(
            self.db,
            self.account_id,
            self.user_id,
            self.guild_id,
            self,
        )

        await view.setup()

        embed = discord.Embed(
            title="🔗 Vincular Rockstar",
            description="Selecione uma conta Rockstar.",
            color=discord.Color.gold(),
        )

        await interaction.response.edit_message(
            embed=embed,
            view=view,
        )

    @discord.ui.button(
        label="📝 Observação",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def note(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await interaction.response.send_modal(
            DiscordNoteModal(
                self.db,
                self.account_id,
                self,
            )
        )

    @discord.ui.button(
        label="�️ Steam",
        style=discord.ButtonStyle.secondary,
        row=2,
    )
    async def steam(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await interaction.response.send_modal(
            DiscordSteamModal(
                self.db,
                self.account_id,
                self,
            )
        )

    @discord.ui.button(
        label="�🗑️ Deletar",
        style=discord.ButtonStyle.danger,
        row=1,
    )
    async def delete(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await self.db.discord_delete_account(
            self.account_id
        )

        embeds, view = await self.list_view.build()
        await refresh_discord_accounts_panel(
            self.db,
            interaction.guild,
        )

        await interaction.response.edit_message(
            embeds=embeds,
            view=view,
        )

    @discord.ui.button(
        label="← Voltar",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def back(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        embeds, view = await self.list_view.build()

        await interaction.response.edit_message(
            embeds=embeds,
            view=view,
        )


# ─────────────────────────────────────────────────────────────
# Lista
# ─────────────────────────────────────────────────────────────

class DiscordAccountsView(discord.ui.View):

    def __init__(
        self,
        db: Database,
        user_id: int,
        guild_id: int,
    ):
        super().__init__(timeout=60)

        self.db = db
        self.user_id = user_id
        self.guild_id = guild_id

    async def build(self):

        accounts = await self.db.discord_list_accounts(
            self.user_id,
            self.guild_id,
        )

        if not accounts:

            embed = discord.Embed(
                title="🎧 Suas contas Discord",
                description=(
                    "Você não possui contas cadastradas.\n\n"
                    "Formato:\n"
                    "```"
                    "discord:senha:email:senhaemail\n"
                    "ou\n"
                    "discord:senha:email:senhaemail:steam:senhasteam"
                    "```\n\n"
                    "Esta mensagem será apagada automaticamente em 1 minuto."
                ),
                color=discord.Color.blurple(),
            )

            return [embed], self

        header = discord.Embed(
            title="🎧 Suas contas Discord",
            description=(
                f"📦 {len(accounts)} conta(s)\n"
                "⏱️ Esta mensagem será apagada automaticamente em 1 minuto."
            ),
            color=discord.Color.blurple(),
        )

        embeds = [header]

        options = []

        for acc in accounts[:24]:

            rockstar_text = ""

            if acc.get("rockstar_account_id"):

                rockstar = await self.db.rockstar_get_account(
                    acc["rockstar_account_id"]
                )

                if rockstar:
                    rockstar_text = f"\n🎮 {rockstar['email']}"

            embed = discord.Embed(
                title=acc["discord_user"],
                description=(
                    f"📧 {acc['email']}"
                    f"{rockstar_text}\n"
                    f"📅 {_fmt_dt(acc.get('created_at'))}"
                ),
                color=discord.Color.dark_blue(),
            )

            embeds.append(embed)

            options.append(
                discord.SelectOption(
                    label=acc["discord_user"][:100],
                    value=str(acc["id"]),
                    description=acc["email"][:100],
                    emoji="🎧",
                )
            )

        select = discord.ui.Select(
            placeholder="Selecione uma conta...",
            options=options,
        )

        async def callback(interaction):

            account_id = int(
                interaction.data["values"][0]
            )

            view = DiscordManageView(
                self.db,
                account_id,
                self.user_id,
                self.guild_id,
                self,
            )

            embed = await view.build_embed()

            await interaction.response.edit_message(
                embed=embed,
                view=view,
            )

        select.callback = callback

        self.clear_items()
        self.add_item(select)

        return embeds, self


# ─────────────────────────────────────────────────────────────
# Painel
# ─────────────────────────────────────────────────────────────

class DiscordPanelView(discord.ui.View):

    def __init__(self, db: Database):
        super().__init__(timeout=None)

        self.db = db

    @discord.ui.button(
        label="🎧 Minhas Contas Discord",
        style=discord.ButtonStyle.primary,
        custom_id="discord_accounts:open",
    )
    async def open_accounts(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        view = DiscordAccountsView(
            self.db,
            interaction.user.id,
            interaction.guild.id,
        )

        embeds, view = await view.build()

        await interaction.response.send_message(
            embeds=embeds,
            view=view,
            ephemeral=False,
            delete_after=60,
        )

    @discord.ui.button(
        label="💾 Backup",
        style=discord.ButtonStyle.secondary,
        custom_id="discord_accounts:backup",
        row=1,
    )
    async def backup_accounts(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await interaction.response.defer(ephemeral=True)
        backup_file = await create_discord_accounts_backup(
            self.db,
            interaction.guild.id,
        )
        if not backup_file:
            await interaction.followup.send(
                "❌ Não há contas Discord cadastradas para backup.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            "✅ Backup gerado com sucesso.",
            file=backup_file,
            ephemeral=True,
        )


# ─────────────────────────────────────────────────────────────
# Embed painel
# ─────────────────────────────────────────────────────────────

async def build_panel_embed(db: Database, guild: discord.Guild):
    total_users = 0
    total_accounts = 0

    try:
        async with db._conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(DISTINCT user_id) as users, COUNT(*) as total "
                "FROM discord_accounts WHERE guild_id = ?",
                (str(guild.id),),
            )
            row = await cur.fetchone()

        if row:
            total_users = int(row["users"] or 0)
            total_accounts = int(row["total"] or 0)
    except Exception:
        total_users = 0
        total_accounts = 0

    embed = discord.Embed(
        title="🎧 Gerenciador de Contas Discord",
        description=(
            "Gerencie contas Discord, Email e Steam.\n"
            "Suas credenciais são protegidas e esta mensagem é atualizada automaticamente."
        ),
        color=discord.Color.dark_blue(),
    )

    embed.add_field(
        name="📊 Estatísticas",
        value=(
            f"Contas cadastradas: **{total_accounts}**\n"
            f"Usuários com contas: **{total_users}**"
        ),
        inline=False,
    )

    embed.add_field(
        name="➕ Formato cadastro",
        value=(
            "```"
            "discord:senha:email:senhaemail\n"
            "ou\n"
            "discord:senha:email:senhaemail:steam:senhasteam"
            "```"
        ),
        inline=False,
    )

    embed.add_field(
        name="💾 Backup",
        value=(
            "Use o botão '💾 Backup' abaixo para exportar todas as contas Discord deste servidor em um arquivo .txt."
        ),
        inline=False,
    )

    embed.add_field(
        name="🔒 Segurança",
        value=(
            "As mensagens são apagadas automaticamente."
        ),
        inline=False,
    )

    return embed


async def create_discord_accounts_backup(db: Database, guild_id: int):
    accounts = await db.discord_list_guild_accounts(guild_id)
    if not accounts:
        return None

    lines = []
    for acc in accounts:
        base_line = (
            f"{acc['discord_user']}:{acc['discord_password']}:{acc['email']}:{acc['email_password']}"
        )
        if acc.get("steam_user") and acc.get("steam_password"):
            line = f"{base_line}:{acc['steam_user']}:{acc['steam_password']}"
        else:
            line = base_line
        lines.append(line)

    buffer = io.BytesIO("\n".join(lines).encode("utf-8"))
    buffer.seek(0)
    return discord.File(buffer, filename="discord_accounts_backup.txt")


async def refresh_discord_accounts_panel(db: Database, guild: discord.Guild):
    settings = await db.get_settings(guild.id)
    channel_id = settings.get("channel_discord_accounts")
    panel_msg_id = settings.get("discord_accounts_panel_message_id")

    if not channel_id or not panel_msg_id:
        return

    channel = guild.get_channel(int(channel_id))
    if not channel:
        return

    try:
        msg = await channel.fetch_message(int(panel_msg_id))
    except Exception:
        return

    embed = await build_panel_embed(db, guild)
    view = DiscordPanelView(db)

    try:
        await msg.edit(embed=embed, view=view)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# Cog
# ─────────────────────────────────────────────────────────────

class DiscordAccountsCog(commands.Cog):

    def __init__(
        self,
        bot: commands.Bot,
        db: Database,
    ):
        self.bot = bot
        self.db = db

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):

        if message.author.bot or not message.guild:
            return

        settings = await self.db.get_settings(
            message.guild.id
        )

        channel_id = settings.get(
            "channel_discord_accounts"
        )

        if not channel_id:
            return

        if message.channel.id != int(channel_id):
            return

        content = message.content.strip()

        if not content or content.startswith("!"):
            return

        lines = [
            x.strip()
            for x in content.splitlines()
            if x.strip()
        ]

        added = 0

        for line in lines:

            parts = line.split(":", 5)

            try:

                # Sem Steam
                if len(parts) == 4:

                    (
                        discord_user,
                        discord_password,
                        email,
                        email_password,
                    ) = parts

                    await self.db.discord_add_account(
                        message.author.id,
                        message.guild.id,
                        discord_user,
                        discord_password,
                        email,
                        email_password,
                    )

                    added += 1

                # Com Steam
                elif len(parts) == 6:

                    (
                        discord_user,
                        discord_password,
                        email,
                        email_password,
                        steam_user,
                        steam_password,
                    ) = parts

                    await self.db.discord_add_account(
                        message.author.id,
                        message.guild.id,
                        discord_user,
                        discord_password,
                        email,
                        email_password,
                        steam_user,
                        steam_password,
                    )

                    added += 1

            except Exception as e:
                LOGGER.error(
                    "Erro cadastro Discord account: %s",
                    e,
                )

        try:
            await message.delete()
        except Exception:
            pass

        if added:

            await message.channel.send(
                f"{message.author.mention} — "
                f"✅ {added} conta(s) cadastrada(s).",
                delete_after=8,
            )

            await self.refresh_panel_embed(message.guild)

    async def refresh_panel_embed(self, guild: discord.Guild):
        await refresh_discord_accounts_panel(self.db, guild)

    @commands.command(
        name="discord_accounts_panel"
    )
    @commands.has_permissions(administrator=True)
    async def publish_panel(
        self,
        ctx: commands.Context,
    ):

        settings = await self.db.get_settings(
            ctx.guild.id
        )

        channel_id = settings.get(
            "channel_discord_accounts"
        )

        if not channel_id:

            await ctx.send(
                "❌ Configure o canal no setup.",
                delete_after=8,
            )
            return

        channel = ctx.guild.get_channel(
            int(channel_id)
        )

        embed = await build_panel_embed(self.db, ctx.guild)

        view = DiscordPanelView(self.db)

        msg = await channel.send(
            embed=embed,
            view=view,
        )

        # Salva o ID da mensagem para restauração após reinicialização
        await self.db.upsert_settings(
            ctx.guild.id,
            discord_accounts_panel_message_id=msg.id,
        )

        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        if ctx.channel.id != channel.id:
            await ctx.send(
                "✅ Painel publicado.",
                delete_after=8,
            )


async def setup(bot):

    cog = DiscordAccountsCog(
        bot,
        bot.db,
    )

    await bot.add_cog(cog)

    bot.add_view(
        DiscordPanelView(bot.db)
    )