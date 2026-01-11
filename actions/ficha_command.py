import logging
from typing import Optional

import discord
from discord.ext import commands

from db import Database
from permissions import command_guard
from .registration import _get_settings

LOGGER = logging.getLogger(__name__)


class FichaCog(commands.Cog):
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db

    async def _find_member_flexible(
        self, guild: discord.Guild, identifier: str
    ) -> Optional[discord.Member]:
        """Busca membro por server_id, discord_id ou menção.
        
        Args:
            guild: Servidor onde buscar
            identifier: server_id, discord_id, menção (@user) ou user_id
            
        Returns:
            Member se encontrado, None caso contrário
        """
        identifier = identifier.strip()
        
        # Remove menções <@!id> ou <@id>
        if identifier.startswith("<@") and identifier.endswith(">"):
            identifier = identifier[2:-1]
            if identifier.startswith("!"):
                identifier = identifier[1:]
        
        # Tenta como discord_id primeiro (mais comum em menções)
        if identifier.isdigit():
            try:
                user_id = int(identifier)
                member = guild.get_member(user_id)
                if member:
                    return member
            except (ValueError, OverflowError):
                pass
        
        # Tenta buscar por server_id no banco (otimizado)
        try:
            discord_id = await self.db.get_member_by_server_id(guild.id, identifier)
            if discord_id:
                member = guild.get_member(discord_id)
                if member:
                    return member
        except Exception as exc:
            LOGGER.debug("Erro ao buscar por server_id: %s", exc)
        
        # Fallback: busca manual por server_id no apelido
        for member in guild.members:
            name = member.nick or member.name
            if "|" not in name:
                continue
            left, right = name.split("|", 1)
            if right.strip() == identifier:
                return member
        
        return None

    async def _get_user_registration_data(
        self, guild_id: int, user_id: int
    ) -> Optional[dict]:
        """Busca dados de cadastro do usuário no banco.
        
        Returns:
            Dict com dados da última registration aprovada, ou None
        """
        try:
            registration = await self.db.get_user_registration(guild_id, user_id, status="approved")
            return registration
        except Exception as exc:
            LOGGER.warning("Erro ao buscar dados de cadastro: %s", exc)
            return None

    async def _build_user_ficha_embed(
        self, member: discord.Member, registration_data: Optional[dict] = None
    ) -> discord.Embed:
        """Constrói a embed com todas as informações do usuário.
        
        Esta função foi estruturada para ser facilmente extensível.
        """
        guild = member.guild
        embed = discord.Embed(
            title=f"📋 Ficha de {member.display_name}",
            color=member.color if member.color != discord.Color.default() else discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        # Avatar
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Golias Bot • Ficha do Membro")
        
        # ===== INFORMAÇÕES BÁSICAS DO DISCORD =====
        embed.add_field(
            name="👤 Identificação",
            value=f"**Nome:** {member.name}\n"
                  f"**Apelido:** {member.display_name}\n"
                  f"**ID Discord:** `{member.id}`",
            inline=False
        )
        
        # ===== TEMPO NO DISCORD =====
        account_age = discord.utils.utcnow() - member.created_at
        account_days = account_age.days
        account_years = account_days // 365
        account_months = (account_days % 365) // 30
        
        account_age_str = f"{account_years} anos, {account_months} meses" if account_years > 0 else f"{account_months} meses"
        
        embed.add_field(
            name="⏰ Conta Discord",
            value=f"**Criada em:** {discord.utils.format_dt(member.created_at, style='R')}\n"
                  f"**Idade da conta:** {account_age_str}",
            inline=True
        )
        
        # ===== TEMPO NO SERVIDOR =====
        if member.joined_at:
            server_age = discord.utils.utcnow() - member.joined_at
            server_days = server_age.days
            server_years = server_days // 365
            server_months = (server_days % 365) // 30
            
            server_age_str = f"{server_years} anos, {server_months} meses" if server_years > 0 else f"{server_months} meses"
            
            embed.add_field(
                name="🏠 Servidor",
                value=f"**Entrou em:** {discord.utils.format_dt(member.joined_at, style='R')}\n"
                      f"**Tempo no servidor:** {server_age_str}",
                inline=True
            )
        else:
            embed.add_field(
                name="🏠 Servidor",
                value="*Data de entrada não disponível*",
                inline=True
            )
        
        # ===== INFORMAÇÕES DE CADASTRO (se disponível) =====
        if registration_data:
            server_id = registration_data.get("server_id", "")
            recruiter_id = registration_data.get("recruiter_id", "")
            
            if server_id:
                embed.add_field(
                    name="🎮 ID no Servidor",
                    value=f"`{server_id}`",
                    inline=True
                )
            
            if recruiter_id:
                recruiter = guild.get_member(int(recruiter_id)) if recruiter_id.isdigit() else None
                recruiter_mention = recruiter.mention if recruiter else f"`{recruiter_id}`"
                embed.add_field(
                    name="👥 Recrutado por",
                    value=recruiter_mention,
                    inline=True
                )
        else:
            # Tenta extrair server_id do apelido
            name = member.nick or member.name
            if "|" in name:
                try:
                    left, right = name.split("|", 1)
                    server_id = right.strip()
                    if server_id:
                        embed.add_field(
                            name="🎮 ID no Servidor",
                            value=f"`{server_id}`",
                            inline=True
                        )
                except ValueError:
                    pass
        
        # ===== CARGOS =====
        roles = [role for role in member.roles if not role.is_default()]
        if roles:
            # Ordena por posição (hierarquia)
            roles_sorted = sorted(roles, key=lambda r: r.position, reverse=True)
            roles_str = " ".join([role.mention for role in roles_sorted[:10]])  # Limite de 10 cargos
            if len(roles_sorted) > 10:
                roles_str += f"\n*+ {len(roles_sorted) - 10} cargo(s) adicional(is)*"
            
            embed.add_field(
                name=f"🎭 Cargos ({len(roles_sorted)})",
                value=roles_str if roles_str else "Nenhum cargo",
                inline=False
            )
        else:
            embed.add_field(
                name="🎭 Cargos",
                value="*Sem cargos atribuídos*",
                inline=False
            )
        
        # ===== STATUS E ATIVIDADE =====
        status_emoji = {
            discord.Status.online: "🟢",
            discord.Status.idle: "🟡",
            discord.Status.dnd: "🔴",
            discord.Status.offline: "⚫"
        }
        status_str = status_emoji.get(member.raw_status, "⚫")
        
        activity_str = "Nenhuma"
        if member.activities:
            for activity in member.activities:
                if isinstance(activity, discord.Game):
                    activity_str = f"🎮 {activity.name}"
                    break
                elif isinstance(activity, discord.Streaming):
                    activity_str = f"📺 Transmitindo: {activity.name}"
                    break
                elif isinstance(activity, discord.Spotify):
                    activity_str = f"🎵 {activity.title} - {activity.artist}"
                    break
        
        embed.add_field(
            name="📊 Status",
            value=f"**Status:** {status_str} {str(member.status).title()}\n"
                  f"**Atividade:** {activity_str}",
            inline=True
        )
        
        # ===== HISTÓRICO DE AÇÕES =====
        try:
            stats = await self.db.get_user_stats(guild.id, member.id)
            if stats:
                participations = stats.get("participations", 0)
                total_earned = stats.get("total_earned", 0.0)
                embed.add_field(
                    name="📊 Histórico de Ações",
                    value=(
                        f"**Participações:** {participations}\n"
                        f"**Total Ganho:** R$ {total_earned:,.2f}"
                    ),
                    inline=True
                )
            else:
                embed.add_field(
                    name="📊 Histórico de Ações",
                    value="Nenhuma participação registrada",
                    inline=True
                )
        except Exception as exc:
            LOGGER.warning("Erro ao buscar estatísticas de ações: %s", exc)
            embed.add_field(
                name="📊 Histórico de Ações",
                value="Erro ao carregar dados",
                inline=True
            )
        
        # ===== PONTOS (FUTURO) =====
        # Estrutura preparada para quando implementarmos sistema de pontos
        # embed.add_field(
        #     name="⭐ Pontos",
        #     value=f"**Total:** {points}\n**Rank:** #{rank}",
        #     inline=True
        # )
        
        # ===== CURSOS (FUTURO) =====
        # Estrutura preparada para quando implementarmos sistema de cursos
        # course_roles = [r for r in roles if r.name.startswith("Curso:")]
        # if course_roles:
        #     embed.add_field(
        #         name="📚 Cursos Concluídos",
        #         value="\n".join([r.name.replace("Curso:", "") for r in course_roles]),
        #         inline=False
        #     )
        
        # ===== HIERARQUIA (FUTURO) =====
        # Estrutura preparada para quando implementarmos sistema de hierarquia
        # hierarchy_role = next((r for r in roles if r.name in HIERARCHY_LEVELS), None)
        # if hierarchy_role:
        #     embed.add_field(
        #         name="🏆 Hierarquia",
        #         value=hierarchy_role.name,
        #         inline=True
        #     )
        
        return embed

    @commands.command(name="ficha")
    @command_guard("ficha")
    async def show_user_ficha(self, ctx: commands.Context, identifier: str):
        """Exibe a ficha completa de um membro.
        
        Uso: !ficha <server_id> | !ficha <discord_id> | !ficha <@menção>
        
        Exemplos:
        - !ficha 2525 (ID no servidor)
        - !ficha @Usuario (menção)
        - !ficha 1215226146421262 (ID do Discord)
        """
        guild = ctx.guild
        if not guild:
            await ctx.reply("❌ Use este comando em um servidor.")
            return
        
        # Busca o membro
        member = await self._find_member_flexible(guild, identifier)
        if not member:
            await ctx.reply(f"❌ Não encontrei membro com identificador `{identifier}` no servidor.")
            return
        
        # Busca dados de cadastro (se disponível)
        registration_data = await self._get_user_registration_data(guild.id, member.id)
        
        # Constrói e envia a embed
        embed = await self._build_user_ficha_embed(member, registration_data)
        await ctx.reply(embed=embed)

