import logging
from typing import Optional

import discord
from discord.ext import commands

from config_manager import ConfigManager
from db import Database


LOGGER = logging.getLogger(__name__)


def _is_digits(value: str) -> bool:
    return value.isdigit()


async def _get_settings(db: Database, guild_id: int):
    """Obtém configurações do servidor apenas do banco de dados (fonte única de verdade).
    
    Retorna: (channels_dict, roles_dict, messages_dict)
    """
    stored = await db.get_settings(guild_id)
    
    # Converte as configurações do banco para o formato esperado
    channels = {}
    roles = {}
    messages = {}
    
    # Canais
    if stored.get("channel_registration_embed"):
        channels["registration_embed"] = stored["channel_registration_embed"]
        channels["channel_registration_embed"] = stored["channel_registration_embed"]
    if stored.get("channel_welcome"):
        channels["welcome"] = stored["channel_welcome"]
        channels["channel_welcome"] = stored["channel_welcome"]
    if stored.get("channel_warnings"):
        channels["warnings"] = stored["channel_warnings"]
        channels["channel_warnings"] = stored["channel_warnings"]
    if stored.get("channel_leaves"):
        channels["leaves"] = stored["channel_leaves"]
        channels["channel_leaves"] = stored["channel_leaves"]
    if stored.get("channel_approval"):
        channels["approval"] = stored["channel_approval"]
        channels["channel_approval"] = stored["channel_approval"]
    if stored.get("channel_records"):
        channels["records"] = stored["channel_records"]
        channels["channel_records"] = stored["channel_records"]
    
    # Cargos
    if stored.get("role_set"):
        roles["set"] = stored["role_set"]
        roles["role_set"] = stored["role_set"]
    if stored.get("role_member"):
        roles["member"] = stored["role_member"]
        roles["role_member"] = stored["role_member"]
    if stored.get("role_adv1"):
        roles["adv1"] = stored["role_adv1"]
        roles["role_adv1"] = stored["role_adv1"]
    if stored.get("role_adv2"):
        roles["adv2"] = stored["role_adv2"]
        roles["role_adv2"] = stored["role_adv2"]
    
    # Mensagens
    if stored.get("message_set_embed"):
        messages["set_embed"] = stored["message_set_embed"]
    
    return channels, roles, messages


class RegistrationModal(discord.ui.Modal, title="Cadastro de Membro"):
    nome = discord.ui.TextInput(label="Nome", placeholder="Seu nome", max_length=80)
    server_id = discord.ui.TextInput(
        label="ID no servidor",
        placeholder="Somente números",
        max_length=32,
    )
    recruiter_id = discord.ui.TextInput(
        label="ID de quem recrutou",
        placeholder="Somente números",
        max_length=32,
    )

    def __init__(self, db: Database, config: ConfigManager):
        super().__init__(timeout=None)
        self.db = db
        self.config = config

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message(
                "Ação permitida apenas em servidores.", ephemeral=True
            )
            return

        if not (_is_digits(self.server_id.value) and _is_digits(self.recruiter_id.value)):
            await interaction.response.send_message(
                "IDs devem conter apenas números.", ephemeral=True
            )
            return

        channels, _, _ = await _get_settings(self.db, guild.id)
        approval_id = channels.get("approval") or channels.get("channel_approval")
        if not approval_id:
            await interaction.response.send_message(
                "Canal de aprovação não configurado. Peça a um admin para rodar !setup.",
                ephemeral=True,
            )
            return

        approval_channel = guild.get_channel(int(approval_id))
        if not approval_channel:
            await interaction.response.send_message(
                "Não encontrei o canal de aprovação configurado.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📝 Cadastro pendente",
            description="Revise os dados antes de aprovar ou recusar.",
            color=discord.Color.orange(),
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="Nome", value=self.nome.value, inline=False)
        embed.add_field(name="ID no servidor", value=self.server_id.value, inline=True)
        embed.add_field(name="ID do recrutador", value=self.recruiter_id.value, inline=True)
        embed.add_field(name="Usuário", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
        embed.add_field(
            name="Conta criada",
            value=discord.utils.format_dt(interaction.user.created_at, style="R"),
            inline=True,
        )

        view = ApprovalView(self.db, self.config, interaction.user.id)
        approval_message = await approval_channel.send(embed=embed, view=view)

        registration_id = await self.db.create_registration(
            guild_id=guild.id,
            user_id=interaction.user.id,
            user_name=self.nome.value,
            server_id=self.server_id.value,
            recruiter_id=self.recruiter_id.value,
            approval_message_id=approval_message.id,
        )

        # Atualiza view com ID salvo para persistência
        view.registration_id = registration_id

        await interaction.response.send_message(
            "Cadastro enviado para aprovação. Aguarde um administrador.",
            ephemeral=True,
        )
        LOGGER.info(
            "Cadastro pendente criado: guild=%s user=%s registration_id=%s",
            guild.id,
            interaction.user.id,
            registration_id,
        )


class RegistrationView(discord.ui.View):
    def __init__(self, db: Database, config: ConfigManager):
        super().__init__(timeout=None)
        self.db = db
        self.config = config

    @discord.ui.button(
        label="Cadastrar",
        style=discord.ButtonStyle.primary,
        custom_id="registration:start",
    )
    async def handle_register(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(RegistrationModal(self.db, self.config))


class ApprovalView(discord.ui.View):
    def __init__(self, db: Database, config: ConfigManager, requester_id: int):
        super().__init__(timeout=None)
        self.db = db
        self.config = config
        self.requester_id = requester_id
        self.registration_id: Optional[int] = None

    async def _check_admin(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Apenas administradores podem aprovar.", ephemeral=True
            )
            return False
        return True

    async def _apply_roles(
        self,
        member: discord.Member,
        roles: dict,
    ) -> None:
        role_member_id = roles.get("member") or roles.get("role_member")
        role_set_id = roles.get("set") or roles.get("role_set")
        add_role = member.guild.get_role(int(role_member_id)) if role_member_id else None
        set_role = member.guild.get_role(int(role_set_id)) if role_set_id else None

        if add_role:
            await member.add_roles(add_role, reason="Cadastro aprovado")
        if set_role and set_role in member.roles:
            await member.remove_roles(set_role, reason="Cadastro aprovado")

    async def _send_record(
        self,
        guild: discord.Guild,
        channels: dict,
        data: dict,
        approver: discord.Member,
    ) -> None:
        record_id = channels.get("records") or channels.get("channel_records")
        if not record_id:
            return
        ch = guild.get_channel(int(record_id))
        if not ch:
            return
        embed = discord.Embed(
            title="✅ Cadastro aprovado",
            color=discord.Color.green(),
        )
        user_id = int(data["user_id"])
        member = guild.get_member(user_id)
        if member:
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(
                name="Conta criada",
                value=discord.utils.format_dt(member.created_at, style="R"),
                inline=True,
            )
            if member.joined_at:
                embed.add_field(
                    name="Entrou no servidor",
                    value=discord.utils.format_dt(member.joined_at, style="R"),
                    inline=True,
                )
        embed.add_field(name="Nome (cadastro)", value=data["user_name"], inline=False)
        embed.add_field(name="ID no servidor", value=data["server_id"], inline=True)
        embed.add_field(name="ID do recrutador", value=data["recruiter_id"], inline=True)
        embed.add_field(name="Usuário", value=f"<@{data['user_id']}>", inline=False)
        embed.add_field(name="Aprovado por", value=approver.mention, inline=False)
        embed.set_footer(text="Golias Bot • Registros")
        await ch.send(embed=embed)

    @discord.ui.button(
        label="Aprovar",
        style=discord.ButtonStyle.success,
        custom_id="registration:approve",
    )
    async def approve(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        if not await self._check_admin(interaction):
            return
        guild = interaction.guild
        if not guild or self.registration_id is None:
            await interaction.response.send_message(
                "Registro não encontrado.", ephemeral=True
            )
            return

        data = await self.db.get_registration(self.registration_id)
        if not data:
            await interaction.response.send_message(
                "Registro não encontrado ou já processado.", ephemeral=True
            )
            return

        channels, roles, _ = await _get_settings(self.db, guild.id)

        member = guild.get_member(int(data["user_id"]))
        if not member:
            await interaction.response.send_message(
                "Usuário não encontrado no servidor.", ephemeral=True
            )
            return

        await self._apply_roles(member, roles)

        # Atualiza apelido: Nome | IDServidor
        new_nick = f"{data['user_name']} | {data['server_id']}"
        try:
            await member.edit(nick=new_nick, reason="Cadastro aprovado - atualização de apelido")
            # Armazena mapeamento server_id -> discord_id para busca otimizada
            await self.db.set_member_server_id(guild.id, member.id, data['server_id'])
        except discord.Forbidden:
            LOGGER.warning("Não consegui alterar apelido de %s em %s", member.id, guild.id)

        await self._send_record(guild, channels, data, approver=interaction.user)

        await self.db.update_registration_status(self.registration_id, "approved")

        await interaction.response.send_message(
            f"Cadastro aprovado para {member.mention}.", ephemeral=True
        )
        await interaction.message.edit(
            content="✅ Aprovado", view=None
        )

        try:
            await member.send("Seu cadastro foi aprovado. Bem-vindo!")
        except discord.Forbidden:
            LOGGER.warning("Não consegui enviar DM para %s", member.id)

    @discord.ui.button(
        label="Recusar",
        style=discord.ButtonStyle.danger,
        custom_id="registration:reject",
    )
    async def reject(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        if not await self._check_admin(interaction):
            return
        if self.registration_id is None:
            await interaction.response.send_message(
                "Registro não encontrado.", ephemeral=True
            )
            return
        data = await self.db.get_registration(self.registration_id)
        if not data:
            await interaction.response.send_message(
                "Registro não encontrado ou já processado.", ephemeral=True
            )
            return
        guild = interaction.guild
        member = guild.get_member(int(data["user_id"])) if guild else None

        await self.db.update_registration_status(self.registration_id, "rejected")
        await interaction.response.send_message("Cadastro recusado.", ephemeral=True)
        await interaction.message.edit(content="❌ Recusado", view=None)

        if member:
            try:
                await member.send("Seu cadastro foi recusado. Procure um administrador.")
            except discord.Forbidden:
                LOGGER.warning("Não consegui enviar DM para %s", member.id)


class RegistrationCog(commands.Cog):
    def __init__(self, bot: commands.Bot, db: Database, config: ConfigManager):
        self.bot = bot
        self.db = db
        self.config = config

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channels, roles, _ = await _get_settings(self.db, member.guild.id)
        role_id = roles.get("set") or roles.get("role_set")
        role_member_id = roles.get("member") or roles.get("role_member")
        if not role_id:
            return
        role = member.guild.get_role(int(role_id))
        if not role:
            return
        try:
            # Remove eventual cargo de membro se já veio atribuído por engano.
            if role_member_id:
                member_role = member.guild.get_role(int(role_member_id))
                if member_role and member_role in member.roles:
                    await member.remove_roles(member_role, reason="Ajuste: manter apenas cargo SET na entrada")
            await member.add_roles(role, reason="Novo membro - cargo SET automático")
            LOGGER.info("Cargo SET atribuído a %s no guild %s", member.id, member.guild.id)
        except discord.Forbidden:
            LOGGER.warning("Permissão insuficiente para atribuir cargo SET em %s", member.guild.id)

        # Envia boas-vindas detalhadas
        welcome_id = channels.get("welcome") or channels.get("channel_welcome")
        if welcome_id:
            channel = member.guild.get_channel(int(welcome_id))
            if channel and isinstance(channel, discord.TextChannel):
                embed = discord.Embed(
                    title="🎉 Bem-vindo!",
                    description=f"{member.mention}, bem-vindo ao servidor!",
                    color=discord.Color.green(),
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.add_field(name="ID", value=str(member.id), inline=True)
                embed.add_field(
                    name="Conta criada em",
                    value=discord.utils.format_dt(member.created_at, style="R"),
                    inline=True,
                )
                embed.add_field(
                    name="Entrou em",
                    value=discord.utils.format_dt(member.joined_at or member.created_at, style="R"),
                    inline=True,
                )
                await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Monitora saídas de membros e envia relatório completo."""
        guild = member.guild
        channels, roles, _ = await _get_settings(self.db, guild.id)
        
        # Remove mapeamento server_id do banco quando membro sai
        try:
            await self.db.remove_member_server_id(guild.id, member.id)
        except Exception as exc:
            LOGGER.warning("Erro ao remover mapeamento server_id de %s: %s", member.id, exc)
        
        leave_id = channels.get("leaves") or channels.get("channel_leaves")
        if not leave_id:
            return
        channel = guild.get_channel(int(leave_id))
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        # Constrói embed completo
        embed = discord.Embed(
            title="🚪 Relatório de Saída de Membro",
            description=f"{member.mention} (`{member.id}`) deixou o servidor.",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        
        # Informações básicas
        embed.add_field(
            name="👤 Informações Básicas",
            value=(
                f"**Nome:** {member.display_name}\n"
                f"**Conta criada:** {discord.utils.format_dt(member.created_at, style='R')}\n"
                f"**Entrou no servidor:** {discord.utils.format_dt(member.joined_at, style='R') if member.joined_at else 'Desconhecido'}"
            ),
            inline=False
        )
        
        # Cargos
        if member.roles:
            role_names = [r.name for r in member.roles if not r.is_default()]
            if role_names:
                embed.add_field(
                    name="🎭 Cargos",
                    value=", ".join(role_names)[:1000],
                    inline=False,
                )
        
        # Dados de cadastro
        try:
            registration_data = await self.db.get_user_registration(guild.id, member.id, status="approved")
            if registration_data:
                server_id = registration_data.get("server_id", "")
                recruiter_id = registration_data.get("recruiter_id", "")
                
                registration_info = []
                if server_id:
                    registration_info.append(f"**ID no servidor:** {server_id}")
                if recruiter_id:
                    try:
                        recruiter = guild.get_member(int(recruiter_id))
                        if recruiter:
                            registration_info.append(f"**Recrutador:** {recruiter.display_name}")
                        else:
                            registration_info.append(f"**Recrutador ID:** {recruiter_id}")
                    except (ValueError, TypeError):
                        pass
                
                if registration_info:
                    embed.add_field(
                        name="📝 Dados de Cadastro",
                        value="\n".join(registration_info),
                        inline=True
                    )
        except Exception as exc:
            LOGGER.warning("Erro ao buscar dados de cadastro de %s: %s", member.id, exc)
        
        # Tempo de voz
        try:
            from .voice_utils import format_time
            total_seconds = await self.db.get_total_voice_time(guild.id, member.id)
            if total_seconds > 0:
                time_str = format_time(total_seconds)
                embed.add_field(
                    name="⏱️ Tempo em Call",
                    value=time_str,
                    inline=True
                )
        except Exception as exc:
            LOGGER.warning("Erro ao buscar tempo de voz de %s: %s", member.id, exc)
        
        # Histórico de ações
        try:
            stats = await self.db.get_user_stats(guild.id, member.id)
            if stats:
                participations = stats.get("participations", 0)
                total_earned = stats.get("total_earned", 0.0)
                if participations > 0 or total_earned > 0:
                    embed.add_field(
                        name="📊 Histórico de Ações",
                        value=(
                            f"**Participações:** {participations}\n"
                            f"**Total ganho:** R$ {total_earned:,.2f}"
                        ),
                        inline=True
                    )
        except Exception as exc:
            LOGGER.warning("Erro ao buscar estatísticas de ações de %s: %s", member.id, exc)
        
        # Advertências
        try:
            role_adv1_id = roles.get("adv1") or roles.get("role_adv1")
            role_adv2_id = roles.get("adv2") or roles.get("role_adv2")
            
            adv_count = 0
            if role_adv1_id:
                role_adv1 = guild.get_role(int(role_adv1_id))
                if role_adv1 and role_adv1 in member.roles:
                    adv_count = 1
            if role_adv2_id:
                role_adv2 = guild.get_role(int(role_adv2_id))
                if role_adv2 and role_adv2 in member.roles:
                    adv_count = 2
            
            if adv_count > 0:
                embed.add_field(
                    name="⚠️ Advertências",
                    value=f"ADV {adv_count}",
                    inline=True
                )
        except Exception as exc:
            LOGGER.warning("Erro ao verificar advertências de %s: %s", member.id, exc)
        
        # Logs recentes (últimos 3)
        try:
            logs = await self.db.get_member_logs(guild.id, member.id, limit=3)
            if logs:
                from datetime import datetime
                logs_text = []
                for log in logs:
                    log_type = log.get("type", "unknown")
                    content = log.get("content", "")[:50]
                    timestamp = log.get("timestamp", "")
                    logs_text.append(f"• {log_type}: {content}...")
                
                if logs_text:
                    embed.add_field(
                        name="📝 Últimos Registros",
                        value="\n".join(logs_text),
                        inline=False
                    )
        except Exception as exc:
            LOGGER.warning("Erro ao buscar logs de %s: %s", member.id, exc)
        
        embed.set_footer(text=f"ID: {member.id} • Relatório de Saída")
        
        await channel.send(embed=embed)


async def setup(bot):
    """Função de setup para carregamento da extensão."""
    from config_manager import ConfigManager
    from db import Database
    
    await bot.add_cog(RegistrationCog(bot, bot.db, bot.config_manager))
