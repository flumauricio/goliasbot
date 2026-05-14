"""
Sistema de gerenciamento de contas Rockstar.
"""

import asyncio
import base64
import hashlib
import hmac
import logging
import struct
import time

import discord
from discord.ext import commands

from db import Database

LOGGER = logging.getLogger(__name__)


# ── helpers TOTP ──────────────────────────────────────────────────────────────

def _generate_totp(secret: str, digits: int = 6, interval: int = 30) -> str:
    secret = secret.replace(" ", "").replace("-", "").upper()
    remainder = len(secret) % 8
    if remainder:
        secret += "=" * (8 - remainder)
    try:
        key = base64.b32decode(secret, casefold=True)
    except Exception:
        return "ERRO_KEY"
    counter = int(time.time()) // interval
    counter_bytes = struct.pack(">Q", counter)
    hmac_hash = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = hmac_hash[-1] & 0x0F
    code_int = struct.unpack(">I", hmac_hash[offset: offset + 4])[0] & 0x7FFFFFFF
    return str(code_int % (10 ** digits)).zfill(digits)

def _seconds_remaining(interval: int = 30) -> int:
    return interval - (int(time.time()) % interval)

def _fmt_dt(value) -> str:
    """Converte UTC para horário de Brasília (UTC-3) e formata em dd/mm/aa HH:MM:SS."""
    if not value:
        return "—"
    from datetime import datetime, timezone, timedelta
    s = str(value).strip()
    # Normaliza separador T
    s = s.replace("T", " ")
    # Tenta parsear com e sem segundos
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt_utc = datetime.strptime(s[:len(fmt) + 2 if fmt == "%Y-%m-%d" else len(fmt)], fmt)
            break
        except ValueError:
            continue
    else:
        return s[:16]  # fallback sem conversão
    # Converte para BRT (UTC-3)
    brt = timezone(timedelta(hours=-3))
    dt_brt = dt_utc.replace(tzinfo=timezone.utc).astimezone(brt)
    return dt_brt.strftime("%d/%m/%y")


# ── Modals ────────────────────────────────────────────────────────────────────

class NoteModal(discord.ui.Modal, title="Editar Observação"):
    note = discord.ui.TextInput(
        label="Observação",
        style=discord.TextStyle.paragraph,
        placeholder="Digite uma observação sobre esta conta...",
        required=False,
        max_length=500,
    )

    def __init__(self, db: Database, account_id: int, manage_view):
        super().__init__()
        self.db = db
        self.account_id = account_id
        self.manage_view = manage_view

    async def on_submit(self, interaction: discord.Interaction):
        await self.db.rockstar_update_note(self.account_id, self.note.value)
        await interaction.response.defer()
        embed = await self.manage_view.build_embed()
        await interaction.message.edit(embeds=[embed], view=self.manage_view)


class ServerBanModal(discord.ui.Modal, title="Registrar Ban de Servidor"):
    server_name = discord.ui.TextInput(
        label="Nome do Servidor / Cidade",
        placeholder="Ex: Los Santos, Cidade Alta...",
        required=True,
        max_length=100,
    )

    def __init__(self, db: Database, account_id: int, manage_view):
        super().__init__()
        self.db = db
        self.account_id = account_id
        self.manage_view = manage_view

    async def on_submit(self, interaction: discord.Interaction):
        await self.db.rockstar_add_server_ban(self.account_id, self.server_name.value.strip())
        await interaction.response.defer()
        embed = await self.manage_view.build_embed()
        await interaction.message.edit(embeds=[embed], view=self.manage_view)

class FilterModal(discord.ui.Modal, title="Configurar Filtros"):
    filters = discord.ui.TextInput(
        label="Cidades / servidores",
        placeholder="Brasil, Cidade Alta, Santa",
        required=False,
        max_length=500,
        style=discord.TextStyle.paragraph,
    )

    def __init__(self, db: Database):
        super().__init__()
        self.db = db

    async def on_submit(self, interaction: discord.Interaction):
        value = self.filters.value.strip()

        await self.db.rockstar_save_filters(
            interaction.user.id,
            interaction.guild.id,
            value,
        )

        if value:
            msg = f"✅ Filtros salvos:\n```{value}```"
        else:
            msg = "🗑️ Filtros removidos."

        await interaction.response.send_message(
            msg,
            ephemeral=True,
            delete_after=10,
        )

# ── View: remover ban ─────────────────────────────────────────────────────────

class RemoveServerBanView(discord.ui.View):
    def __init__(self, db: Database, account_id: int, bans: list, manage_view):
        super().__init__(timeout=60)
        self.db = db
        self.account_id = account_id
        self.manage_view = manage_view
        self._message: discord.Message = None

        options = [
            discord.SelectOption(label=b["server_name"][:80], value=str(b["id"]))
            for b in bans[:25]
        ]
        select = discord.ui.Select(placeholder="Selecione o ban a remover...", options=options)
        select.callback = self.on_select
        self.add_item(select)

        back = discord.ui.Button(label="← Voltar", style=discord.ButtonStyle.secondary)
        back.callback = self.go_back
        self.add_item(back)

    async def on_timeout(self):
        try:
            if self._message:
                await self._message.delete()
        except Exception:
            pass

    async def on_select(self, interaction: discord.Interaction):
        ban_id = int(interaction.data["values"][0])
        await self.db.rockstar_remove_server_ban(ban_id)
        await interaction.response.defer()
        embed = await self.manage_view.build_embed()
        await interaction.message.edit(embeds=[embed], view=self.manage_view)

    async def go_back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = await self.manage_view.build_embed()
        await interaction.message.edit(embeds=[embed], view=self.manage_view)


# ── View: confirmação de delete ───────────────────────────────────────────────

class ConfirmDeleteView(discord.ui.View):
    def __init__(self, db: Database, account_id: int, list_view):
        super().__init__(timeout=30)
        self.db = db
        self.account_id = account_id
        self.list_view = list_view
        self._message: discord.Message = None

    async def on_timeout(self):
        try:
            if self._message:
                await self._message.delete()
        except Exception:
            pass

    @discord.ui.button(label="✅ Confirmar exclusão", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.db.rockstar_delete_account(self.account_id)
        await interaction.response.defer()
        embeds, view = await self.list_view.build_embed_and_view()
        view._message = interaction.message
        await interaction.message.edit(embeds=embeds, view=view)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embeds, view = await self.list_view.build_embed_and_view()
        view._message = interaction.message
        await interaction.message.edit(embeds=embeds, view=view)


# ── View: gerenciamento de uma conta ─────────────────────────────────────────

class AccountManageView(discord.ui.View):
    def __init__(self, db: Database, account_id: int, user_id: int, list_view):
        super().__init__(timeout=60)
        self.db = db
        self.account_id = account_id
        self.user_id = user_id
        self.list_view = list_view
        self._message: discord.Message = None

    async def on_timeout(self):
        try:
            if self._message:
                await self._message.delete()
        except Exception:
            pass

    async def build_embed(self) -> discord.Embed:
        acc = await self.db.rockstar_get_account(self.account_id)
        if not acc:
            return discord.Embed(title="Conta não encontrada", color=discord.Color.red())

        is_active = bool(acc.get("is_active"))
        global_ban = bool(acc.get("global_ban"))
        totp_secret = acc.get("totp_secret", "")
        totp_code = _generate_totp(totp_secret) if totp_secret else "N/A"
        secs = _seconds_remaining()

        color = (
            discord.Color.red() if global_ban
            else discord.Color.gold() if is_active
            else discord.Color.blurple()
        )

        title_prefix = ""
        if is_active:
            title_prefix += "🟢 "
        if global_ban:
            title_prefix += "🔴 BAN GLOBAL · "

        embed = discord.Embed(title=f"{title_prefix}📧 {acc['email']}", color=color)

        embed.add_field(name="📧 E-mail",  value=f"```{acc['email']}```",    inline=False)
        embed.add_field(name="🔑 Senha",   value=f"```{acc['password']}```", inline=False)
        embed.add_field(
            name=f"🔐 Código 2FA  *(expira em {secs}s)*",
            value=f"```{totp_code}```",
            inline=False,
        )

        # Status
        status_parts = []
        if is_active:
            activated = _fmt_dt(acc.get("activated_at"))
            status_parts.append(f"🟢 **Conta ativa** desde `{activated}`")
        if global_ban:
            gban_date = _fmt_dt(acc.get("global_ban_date"))
            status_parts.append(f"🔴 **Ban global** em `{gban_date}`")
        if not status_parts:
            status_parts.append("⚪ Sem status especial")
        embed.add_field(name="📊 Status", value="\n".join(status_parts), inline=False)

        # Bans de servidores
        bans = await self.db.rockstar_get_server_bans(self.account_id)
        if bans:
            ban_entries = [f"{b['server_name']} ({_fmt_dt(b['banned_at'])})" for b in bans]
            ban_value = "```" + ", ".join(ban_entries) + "```"
            embed.add_field(name="🗺️ Bans em servidores", value=ban_value, inline=False)
        else:
            embed.add_field(name="🗺️ Bans em servidores", value="Nenhum ban registrado", inline=False)

        # Observação
        note = acc.get("note") or ""
        embed.add_field(name="📝 Observação", value=note if note else "*Sem observação*", inline=False)

        # Datas
        embed.add_field(name="📅 Cadastrada em", value=f"`{_fmt_dt(acc.get('created_at'))}`", inline=True)
        if acc.get("activated_at"):
            embed.add_field(name="🟢 Ativada em", value=f"`{_fmt_dt(acc.get('activated_at'))}`", inline=True)

        embed.set_footer(text="⏱️ Esta janela fecha automaticamente em 60s sem interação.")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🔄 Atualizar 2FA", style=discord.ButtonStyle.success, row=0)
    async def refresh_totp(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await self.build_embed()
        await interaction.message.edit(embeds=[embed], view=self)

    @discord.ui.button(label="🚫 Ban servidor", style=discord.ButtonStyle.secondary, row=0)
    async def add_server_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ServerBanModal(self.db, self.account_id, self))

    @discord.ui.button(label="✅ Remover ban", style=discord.ButtonStyle.secondary, row=1)
    async def remove_server_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        bans = await self.db.rockstar_get_server_bans(self.account_id)
        if not bans:
            await interaction.response.send_message("Nenhum ban registrado.", ephemeral=True)
            return
        await interaction.response.defer()
        view = RemoveServerBanView(self.db, self.account_id, bans, self)
        view._message = interaction.message
        embed = discord.Embed(title="Selecione o ban para remover", color=discord.Color.orange())
        await interaction.message.edit(embeds=[embed], view=view)

    @discord.ui.button(label="🔴 Ban global", style=discord.ButtonStyle.danger, row=1)
    async def toggle_global_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        acc = await self.db.rockstar_get_account(self.account_id)
        new_state = not bool(acc.get("global_ban"))
        await self.db.rockstar_set_global_ban(self.account_id, new_state)
        await interaction.response.defer()
        embed = await self.build_embed()
        await interaction.message.edit(embeds=[embed], view=self)

    @discord.ui.button(label="📝 Observação", style=discord.ButtonStyle.secondary, row=1)
    async def edit_note(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NoteModal(self.db, self.account_id, self))

    @discord.ui.button(label="🗑️ Deletar conta", style=discord.ButtonStyle.danger, row=2)
    async def delete_account(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        confirm_view = ConfirmDeleteView(self.db, self.account_id, self.list_view)
        confirm_view._message = interaction.message
        embed = discord.Embed(
            title="⚠️ Confirmar exclusão",
            description="Tem certeza que deseja deletar esta conta? Esta ação é irreversível.",
            color=discord.Color.red(),
        )
        await interaction.message.edit(embeds=[embed], view=confirm_view)

    @discord.ui.button(label="← Voltar", style=discord.ButtonStyle.secondary, row=2)
    async def go_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embeds, view = await self.list_view.build_embed_and_view()
        view._message = interaction.message
        await interaction.message.edit(embeds=embeds, view=view)


# ── View: lista de contas ─────────────────────────────────────────────────────

class AccountListView(discord.ui.View):
    def __init__(self, db: Database, user_id: int, guild_id: int):
        super().__init__(timeout=60)
        self.db = db
        self.user_id = user_id
        self.guild_id = guild_id
        self._message: discord.Message = None

    async def on_timeout(self):
        try:
            if self._message:
                await self._message.delete()
        except Exception:
            pass

    async def build_embed_and_view(self, page: int = 0):
        """
        Retorna (embeds: list[discord.Embed], view: AccountListView).
        O primeiro embed é o cabeçalho; os seguintes são os cards das contas.
        Discord aceita até 10 embeds por mensagem — 1 header + até 4 cards = OK.
        """
        accounts = await self.db.rockstar_list_accounts(self.user_id, self.guild_id)
        # ── Aplica filtros ─────────────────────────────────────────────
        filters = await self.db.rockstar_get_filters(
            self.user_id,
            self.guild_id,
        )

        if filters:
            filtered_accounts = []

            for acc in accounts:
                bans = await self.db.rockstar_get_server_bans(acc["id"])

                blocked = False

                for ban in bans:
                    server_name = (ban["server_name"] or "").lower()

                    for flt in filters:
                        if flt in server_name:
                            blocked = True
                            break

                    if blocked:
                        break

                if not blocked:
                    filtered_accounts.append(acc)

            accounts = filtered_accounts
        self.clear_items()

        # ── Sem contas ────────────────────────────────────────────────────────
        if not accounts:
            header = discord.Embed(
                title="🎮 Suas contas Rockstar",
                description=(
                    "Você não tem contas cadastradas.\n\n"
                    "Digite `email:senha:chave2fa` no canal para cadastrar."
                ),
                color=0x5865F2,
            )
            if filters:
                header.description = (
                    "🔍 Filtros ativos: "
                    + ", ".join(filters)
                )
            header.set_footer(text="⏱️ Fecha em 60s sem interação")
            return [header], self

        # ── Ordena: ativa primeiro, depois por activated_at desc ──────────────
        accounts = sorted(
            accounts,
            key=lambda a: (1 if a.get("is_active") else 0, str(a.get("activated_at") or "0000")),
            reverse=True,
        )

        # ── Busca todos os bans de uma vez ────────────────────────────────────
        all_bans: dict[int, list] = {}
        for a in accounts:
            all_bans[a["id"]] = await self.db.rockstar_get_server_bans(a["id"])

        # ── Paginação: 4 contas por página (Discord max = 10 embeds/msg) ─────
        PAGE_SIZE = 4
        total_pages = max(1, -(-len(accounts) // PAGE_SIZE))
        page = max(0, min(page, total_pages - 1))
        page_accounts = accounts[page * PAGE_SIZE: page * PAGE_SIZE + PAGE_SIZE]

        # ── Embed cabeçalho ───────────────────────────────────────────────────
        active = next((a for a in accounts if a.get("is_active")), None)
        header = discord.Embed(
            title="🎮 Suas contas Rockstar",
            color=0x5865F2,  # azul Discord
        )
        if active:
            header.description = f"🟢 **Conta ativa:** `{active['email']}`  ·  ativada em {_fmt_dt(active.get('activated_at'))}"
        header.set_footer(
            text=(
                f"📋 {len(accounts)} conta(s)  ·  "
                f"Página {page + 1}/{total_pages}  ·  "
                f"⏱️ Fecha em 60s sem interação"
            )
        )

        embeds = [header]

        # ── Um embed por conta (barra lateral colorida) ───────────────────────
        #
        # Cores:  🟢 ativa  →  verde    0x57F287
        #         🔴 ban global → vermelho  0xED4245
        #         ⚪ normal     → cinza     0x4E5058  (cinza escuro Discord)
        #
        for a in page_accounts:
            is_active = bool(a.get("is_active"))
            global_ban = bool(a.get("global_ban"))
            bans = all_bans.get(a["id"], [])

            if is_active:
                side_color = 0x57F287   # verde
                status_line = "🟢  Ativa"
            elif global_ban:
                side_color = 0xED4245   # vermelho
                status_line = "🔴  Ban Global"
            else:
                side_color = 0x4E5058   # cinza
                status_line = "⚪  Normal"

            # Título do card = e-mail em destaque (aparece em azul claro no Discord
            # pois é o título do embed — não podemos forçar cor de texto, mas o
            # título nativo já tem aparência diferenciada)
            card = discord.Embed(
                title=a["email"],
                color=side_color,
            )

            # ── Linha 1: Status · Cadastro · Última ativação (3 colunas) ──────
            card.add_field(name="📊 Status",          value=status_line,                        inline=True)
            card.add_field(name="📅 Cadastro",         value=_fmt_dt(a.get("created_at")),      inline=True)
            card.add_field(name="🟢 Última ativação",  value=_fmt_dt(a.get("activated_at")),    inline=True)

            # ── Linha 2: bans (caixa de código, só se houver) ─────────────────
            ban_parts = []
            if global_ban:
                ban_parts.append(f"BAN GLOBAL ({_fmt_dt(a.get('global_ban_date'))})")
            for b in bans[:10]:
                ban_parts.append(f"{b['server_name']} ({_fmt_dt(b['banned_at'])})")
            if len(bans) > 10:
                ban_parts.append(f"+{len(bans) - 10} mais")
            if ban_parts:
                card.add_field(
                    name="🗺️ Bans em servidores",
                    value="```" + ", ".join(ban_parts) + "```",
                    inline=False,
                )

            embeds.append(card)

        # ── Botão de acesso rápido à conta ativa ──────────────────────────────
        if active:
            quick_btn = discord.ui.Button(
                label="⚡ Acessar conta ativa",
                style=discord.ButtonStyle.success,
                row=0,
            )
            active_id = active["id"]

            async def quick_callback(interaction: discord.Interaction, _aid=active_id):
                if interaction.user.id != self.user_id:
                    await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
                    return
                await interaction.response.defer()
                manage_view = AccountManageView(self.db, _aid, self.user_id, self)
                manage_view._message = interaction.message
                embed_m = await manage_view.build_embed()
                await interaction.message.edit(embeds=[embed_m], view=manage_view)

            quick_btn.callback = quick_callback
            self.add_item(quick_btn)

        # ── Botões de navegação (row=1) ───────────────────────────────────────
        if total_pages > 1:
            prev_btn = discord.ui.Button(
                label="◀ Anterior",
                style=discord.ButtonStyle.secondary,
                disabled=(page == 0),
                row=1,
            )
            next_btn = discord.ui.Button(
                label="Próxima ▶",
                style=discord.ButtonStyle.secondary,
                disabled=(page >= total_pages - 1),
                row=1,
            )

            async def prev_callback(interaction: discord.Interaction, _p=page):
                if interaction.user.id != self.user_id:
                    await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
                    return
                await interaction.response.defer()
                embeds_n, view_n = await self.build_embed_and_view(_p - 1)
                view_n._message = interaction.message
                await interaction.message.edit(embeds=embeds_n, view=view_n)

            async def next_callback(interaction: discord.Interaction, _p=page):
                if interaction.user.id != self.user_id:
                    await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
                    return
                await interaction.response.defer()
                embeds_n, view_n = await self.build_embed_and_view(_p + 1)
                view_n._message = interaction.message
                await interaction.message.edit(embeds=embeds_n, view=view_n)

            prev_btn.callback = prev_callback
            next_btn.callback = next_callback
            self.add_item(prev_btn)
            self.add_item(next_btn)

        # ── Select ────────────────────────────────────────────────────────────
        options = []
        for a in page_accounts:
            desc_parts = []
            if a.get("is_active"):
                desc_parts.append("Ativa")
            if a.get("global_ban"):
                desc_parts.append("Ban Global")
            bans = all_bans.get(a["id"], [])
            if bans:
                desc_parts.append(f"{len(bans)} ban(s)")
            options.append(discord.SelectOption(
                label=a["email"][:80],
                value=str(a["id"]),
                description=" · ".join(desc_parts) if desc_parts else "Clique para gerenciar",
                emoji="🟢" if a.get("is_active") else ("🔴" if a.get("global_ban") else "⚪"),
            ))

        select = discord.ui.Select(
            placeholder="Selecione uma conta para gerenciar...",
            options=options,
            row=2,
        )
        select.callback = self.on_select
        self.add_item(select)

        return embeds, self

    async def on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return
        account_id = int(interaction.data["values"][0])
        await interaction.response.defer()
        # Ativa automaticamente a conta selecionada
        await self.db.rockstar_set_active(account_id, self.user_id, interaction.guild.id)
        manage_view = AccountManageView(self.db, account_id, self.user_id, self)
        manage_view._message = interaction.message
        embed_m = await manage_view.build_embed()
        await interaction.message.edit(embeds=[embed_m], view=manage_view)


# ── View: painel fixo do canal ────────────────────────────────────────────────

class RockstarPanelView(discord.ui.View):
    """View persistente — nunca expira, fica fixada no canal."""

    def __init__(self, db: Database):
        super().__init__(timeout=None)
        self.db = db

    @discord.ui.button(
        label="🎮 Minhas Contas",
        style=discord.ButtonStyle.primary,
        custom_id="rockstar_panel:minhas_contas",
    )
    async def open_my_accounts(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=False)
        view = AccountListView(self.db, interaction.user.id, interaction.guild.id)
        embeds, view = await view.build_embed_and_view(page=0)
        msg = await interaction.followup.send(embeds=embeds, view=view, wait=True)
        view._message = msg

    @discord.ui.button(
        label="⚙️ Configurar filtros",
        style=discord.ButtonStyle.secondary,
        custom_id="rockstar_panel:config_filters",
    )
    async def configure_filters(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(FilterModal(self.db))

# ── helpers: embed do painel ─────────────────────────────────────────────────

async def build_panel_embed(db: Database, guild: discord.Guild) -> discord.Embed:
    try:
        async with db._conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(DISTINCT user_id) as users, COUNT(*) as total, "
                "SUM(global_ban) as global_bans "
                "FROM rockstar_accounts WHERE guild_id = ?",
                (str(guild.id),),
            )
            row = await cur.fetchone()
            total_users       = row["users"]                  if row else 0
            total_accounts    = row["total"]                  if row else 0
            total_global_bans = int(row["global_bans"] or 0) if row else 0

            await cur.execute(
                "SELECT COUNT(*) as server_bans FROM rockstar_server_bans rsb "
                "INNER JOIN rockstar_accounts ra ON rsb.account_id = ra.id "
                "WHERE ra.guild_id = ?",
                (str(guild.id),),
            )
            row2 = await cur.fetchone()
            total_server_bans = int(row2["server_bans"] or 0) if row2 else 0

        total_bans = total_global_bans + total_server_bans
    except Exception:
        total_users = 0
        total_accounts = 0
        total_bans = 0

    embed = discord.Embed(
        title="🎮 Gerenciador de Contas Rockstar",
        description=(
            "Gerencie suas contas de forma segura e organizada.\n"
            "Suas credenciais ficam protegidas e visíveis apenas para você."
        ),
        color=discord.Color.dark_gold(),
    )

    embed.add_field(
        name="📊 Estatísticas do servidor",
        value=(
            f"👥 **{total_users}** usuário(s) com contas cadastradas\n"
            f"🗂️ **{total_accounts}** conta(s) no total\n"
            f"🚫 **{total_bans}** ban(s) registrado(s)"
        ),
        inline=False,
    )

    embed.add_field(
        name="➕ Como cadastrar contas",
        value=(
            "Digite diretamente neste canal no formato:\n"
            "```email:senha:chave2fa```\n"
            "Você pode enviar várias contas de uma vez, uma por linha.\n"
            "A mensagem é apagada automaticamente por segurança."
        ),
        inline=False,
    )

    embed.add_field(
        name="🔐 Código 2FA",
        value=(
            "A chave 2FA é a **secret key** do seu autenticador\n"
            "(Google Authenticator, Authy, etc.), **não** o código de 6 dígitos.\n"
            "Exemplo de chave: `JBSWY3DPEHPK3PXP`"
        ),
        inline=False,
    )

    embed.add_field(
        name="📋 O que você pode gerenciar",
        value=(
            "• Visualizar e copiar e-mail, senha e código 2FA\n"
            "• Definir qual conta está ativa no momento\n"
            "• Registrar bans em servidores/cidades com data\n"
            "• Registrar e remover ban global da conta\n"
            "• Adicionar observações editáveis\n"
            "• Deletar contas"
        ),
        inline=False,
    )

    embed.set_footer(text="Clique em 'Minhas Contas' para acessar suas contas.")
    return embed


# ── Cog principal ─────────────────────────────────────────────────────────────

class RockstarCog(commands.Cog):
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db
        LOGGER.info("✅ RockstarCog carregado")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        try:
            settings = await self.db.get_settings(message.guild.id)
        except Exception as e:
            LOGGER.error("RockstarCog on_message erro settings: %s", e)
            return

        channel_id = settings.get("channel_rockstar")
        if not channel_id:
            return
        try:
            if message.channel.id != int(channel_id):
                return
        except (ValueError, TypeError):
            return

        content = message.content.strip()
        if not content or content.startswith("!"):
            return

        lines = [l.strip() for l in content.splitlines() if l.strip()]
        valid, invalid = [], []

        for line in lines:
            parts = line.split(":", 2)
            if len(parts) == 3 and all(p.strip() for p in parts):
                valid.append(parts)
            else:
                invalid.append(line)

        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        if not valid and not invalid:
            return

        added = 0
        duplicates = 0
        last_added_account_id = None

        for email, password, totp_secret in valid:
            try:
                result = await self.db.rockstar_add_account(
                    user_id=message.author.id,
                    guild_id=message.guild.id,
                    email=email.strip(),
                    password=password.strip(),
                    totp_secret=totp_secret.strip(),
                )

                if result == "duplicate":
                    duplicates += 1
                else:
                    added += 1

                    # Busca a conta recém cadastrada
                    async with self.db._conn.cursor() as cur:
                        await cur.execute(
                            """
                            SELECT id
                            FROM rockstar_accounts
                            WHERE user_id = ?
                            AND guild_id = ?
                            AND email = ?
                            ORDER BY id DESC
                            LIMIT 1
                            """,
                            (
                                str(message.author.id),
                                str(message.guild.id),
                                email.strip(),
                            ),
                        )

                        row = await cur.fetchone()

                    if row:
                        last_added_account_id = row["id"]

                        # Define automaticamente como conta ativa
                        await self.db.rockstar_set_active(
                            last_added_account_id,
                            message.author.id,
                            message.guild.id,
                        )

            except Exception as e:
                LOGGER.error("Erro ao cadastrar conta %s: %s", email, e)
                invalid.append(email)

        parts_msg = []
        if added:
            parts_msg.append(f"✅ **{added}** conta(s) cadastrada(s)")
        if duplicates:
            parts_msg.append(f"⚠️ **{duplicates}** já existia(m)")
        if invalid:
            parts_msg.append(f"❌ **{len(invalid)}** linha(s) inválida(s) — use `email:senha:chave2fa`")

        if parts_msg:
            await message.channel.send(
                f"{message.author.mention} — " + " · ".join(parts_msg),
                delete_after=8,
            )

        if added or duplicates:
            await self._refresh_panel(message.guild)

        # Abre automaticamente a conta recém cadastrada
        if last_added_account_id:
            try:
                list_view = AccountListView(
                    self.db,
                    message.author.id,
                    message.guild.id,
                )

                manage_view = AccountManageView(
                    self.db,
                    last_added_account_id,
                    message.author.id,
                    list_view,
                )

                embed = await manage_view.build_embed()

                msg = await message.channel.send(
                    content=f"{message.author.mention} — conta ativada automaticamente.",
                    embed=embed,
                    view=manage_view,
                    delete_after=60,
                )

                manage_view._message = msg

            except Exception as e:
                LOGGER.error("Erro ao abrir conta automaticamente: %s", e)

    async def _refresh_panel(self, guild: discord.Guild):
        try:
            settings = await self.db.get_settings(guild.id)
            channel_id = settings.get("channel_rockstar")
            panel_message_id = settings.get("rockstar_panel_message_id")
            if not channel_id or not panel_message_id:
                return
            channel = guild.get_channel(int(channel_id))
            if not channel:
                return
            msg = await channel.fetch_message(int(panel_message_id))
            embed = await build_panel_embed(self.db, guild)
            await msg.edit(embed=embed)
        except (discord.NotFound, discord.Forbidden):
            pass
        except Exception as e:
            LOGGER.warning("Erro ao atualizar painel rockstar: %s", e)

    @commands.command(name="rockstar_panel")
    @commands.has_permissions(administrator=True)
    async def publish_panel(self, ctx: commands.Context):
        """Publica ou atualiza o painel fixo de contas Rockstar no canal. (Apenas admin)"""
        if not ctx.guild:
            return

        settings = await self.db.get_settings(ctx.guild.id)
        channel_id = settings.get("channel_rockstar")

        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        if not channel_id:
            await ctx.send("❌ Canal Rockstar não configurado. Use `!setup` primeiro.", delete_after=10)
            return

        channel = ctx.guild.get_channel(int(channel_id))
        if not channel:
            await ctx.send("❌ Canal configurado não encontrado.", delete_after=10)
            return

        embed = await build_panel_embed(self.db, ctx.guild)
        view = RockstarPanelView(self.db)

        existing_id = settings.get("rockstar_panel_message_id")
        panel_msg = None

        if existing_id:
            try:
                panel_msg = await channel.fetch_message(int(existing_id))
                await panel_msg.edit(embed=embed, view=view)
            except (discord.NotFound, discord.Forbidden):
                panel_msg = None

        if not panel_msg:
            panel_msg = await channel.send(embed=embed, view=view)

        await self.db.rockstar_save_panel_message(ctx.guild.id, panel_msg.id)

        if ctx.channel.id != channel.id:
            await ctx.send(f"✅ Painel publicado em {channel.mention}!", delete_after=8)


async def setup(bot):
    cog = RockstarCog(bot, bot.db)
    await bot.add_cog(cog)
    bot.add_view(RockstarPanelView(bot.db))
