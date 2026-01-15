import asyncio
import logging
import math
import time
from dataclasses import dataclass
from datetime import timedelta, datetime
from typing import Optional, Dict, Any, Tuple, List, TYPE_CHECKING

import discord
from discord.ext import commands

from db import Database
from permissions import command_guard, check_command_permission
from .registration import _get_settings

# Importações de hierarchy movidas para o topo (evita importações dentro de métodos)
if TYPE_CHECKING:
    from .hierarchy.repository import HierarchyRepository
    from .hierarchy.cache import HierarchyCache
    from .hierarchy.promotion_engine import HierarchyPromotionCog
    from .hierarchy.utils import check_bot_hierarchy
else:
    try:
        from .hierarchy.repository import HierarchyRepository
        from .hierarchy.cache import HierarchyCache
        from .hierarchy.promotion_engine import HierarchyPromotionCog
        from .hierarchy.utils import check_bot_hierarchy
    except ImportError:
        # Módulo de hierarquia não disponível
        HierarchyRepository = None
        HierarchyCache = None
        HierarchyPromotionCog = None
        check_bot_hierarchy = None

LOGGER = logging.getLogger(__name__)

# Usa o set global do bot para prevenir execução duplicada


# ===== HELPERS =====

class EmbedBuilder:
    """Helper para construir embeds com validação automática de limites do Discord."""
    
    MAX_EMBED_LENGTH = 6000
    MAX_FIELD_LENGTH = 1024
    MAX_FIELDS = 25
    
    def __init__(self, title: str = "", color: discord.Color = discord.Color.blue()):
        self.embed = discord.Embed(title=title, color=color)
        self.total_length = len(title)
        self.field_count = 0
    
    def add_field_safe(
        self,
        name: str,
        value: str,
        inline: bool = False,
        truncate: bool = True
    ) -> bool:
        """
        Adiciona field validando limites do Discord.
        
        Returns:
            True se adicionado com sucesso, False se excedeu limites
        """
        if self.field_count >= self.MAX_FIELDS:
            LOGGER.warning(f"Embed excedeu limite de {self.MAX_FIELDS} fields")
            return False
        
        if len(value) > self.MAX_FIELD_LENGTH:
            if truncate:
                value = value[:self.MAX_FIELD_LENGTH - 20] + "\n\n*(truncado)*"
            else:
                LOGGER.warning(f"Field '{name}' excedeu {self.MAX_FIELD_LENGTH} chars")
                return False
        
        field_length = len(name) + len(value)
        if self.total_length + field_length > self.MAX_EMBED_LENGTH:
            LOGGER.warning(f"Embed excedeu limite de {self.MAX_EMBED_LENGTH} chars")
            return False
        
        self.embed.add_field(name=name, value=value, inline=inline)
        self.total_length += field_length
        self.field_count += 1
        return True
    
    def set_description_safe(self, description: str, truncate: bool = True):
        """Define descrição validando limite de 4096 chars."""
        if len(description) > 4096:
            if truncate:
                description = description[:4090] + "..."
            else:
                raise ValueError("Description excede 4096 chars")
        
        self.embed.description = description
        self.total_length += len(description)


@dataclass
class AdvStatus:
    """Status de advertências de um membro."""
    has_adv1: bool
    has_adv2: bool
    is_banned: bool
    recent_warnings: List[Dict[str, Any]]
    total_warnings: int


# ===== MODAIS =====

class CommentModal(discord.ui.Modal, title="Adicionar Comentário"):
    """Modal para adicionar comentário público na ficha."""
    
    comment = discord.ui.TextInput(
        label="Comentário",
        placeholder="Digite o comentário público...",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )
    
    def __init__(self, ficha_cog, member: discord.Member):
        super().__init__()
        self.ficha_cog = ficha_cog
        self.member = member
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Salva log
        await self.ficha_cog.db.add_member_log(
            interaction.guild.id,
            self.member.id,
            interaction.user.id,
            "comentario",
            self.comment.value
        )
        
        # Atualiza ficha
        registration_data = await self.ficha_cog._get_user_registration_data(interaction.guild.id, self.member.id)
        embed = await self.ficha_cog._build_user_ficha_embed(interaction.guild, self.member, registration_data, interaction.user)
        view = await self.ficha_cog._create_ficha_view(interaction.guild, self.member, interaction.user)
        
        await interaction.message.edit(embed=embed, view=view)
        await interaction.followup.send("✅ Comentário adicionado com sucesso!", ephemeral=True)


class WarnModal(discord.ui.Modal, title="Aplicar Advertência"):
    """Modal para aplicar advertência."""
    
    motivo = discord.ui.TextInput(
        label="Motivo da Advertência",
        placeholder="Digite o motivo da advertência...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True
    )
    
    def __init__(self, ficha_cog, member: discord.Member):
        super().__init__()
        self.ficha_cog = ficha_cog
        self.member = member
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Aplica advertência usando mesma lógica do warn_command.py
            channels, roles, _ = await _get_settings(self.ficha_cog.db, interaction.guild.id)
            warn_channel_id = channels.get("warnings") or channels.get("channel_warnings")
            role_adv1_id = roles.get("adv1") or roles.get("role_adv1")
            role_adv2_id = roles.get("adv2") or roles.get("role_adv2")
            
            if not (role_adv1_id and role_adv2_id):
                await interaction.followup.send("❌ Cargos de advertência não configurados.", ephemeral=True)
                return
            
            role_adv1 = interaction.guild.get_role(int(role_adv1_id))
            role_adv2 = interaction.guild.get_role(int(role_adv2_id))
            
            if not (role_adv1 and role_adv2):
                await interaction.followup.send("❌ Cargos de advertência não encontrados.", ephemeral=True)
                return
            
            has_adv1 = role_adv1 in self.member.roles
            has_adv2 = role_adv2 in self.member.roles
            
            action = ""
            if not has_adv1:
                await self.member.add_roles(role_adv1, reason=f"ADV 1 aplicada por {interaction.user}: {self.motivo.value}")
                action = "ADV 1 aplicada"
            elif not has_adv2:
                await self.member.add_roles(role_adv2, reason=f"ADV 2 aplicada por {interaction.user}: {self.motivo.value}")
                action = "ADV 2 aplicada"
            else:
                # Terceira vez: banimento
                action = "Banimento após ADV 2"
                try:
                    await self.member.send(
                        f"Você já possuía duas advertências (ADV 2) e foi banido do servidor.\n"
                        f"Motivo: {self.motivo.value}"
                    )
                except discord.Forbidden:
                    pass
                await interaction.guild.ban(self.member, reason=f"Banido após ADV 2 por {interaction.user}: {self.motivo.value}")
                
                # Envia embed para canal de advertências (se configurado)
                if warn_channel_id:
                    warn_channel = interaction.guild.get_channel(int(warn_channel_id))
                    if isinstance(warn_channel, discord.TextChannel):
                        # Busca server_id para o embed
                        server_id = ""
                        registration_data = await self.ficha_cog._get_user_registration_data(interaction.guild.id, self.member.id)
                        if registration_data:
                            server_id = registration_data.get("server_id", "")
                        else:
                            # Tenta extrair do apelido
                            name = self.member.nick or self.member.name
                            if "|" in name:
                                try:
                                    _, right = name.split("|", 1)
                                    server_id = right.strip()
                                except ValueError:
                                    pass
                        
                        embed_log = discord.Embed(
                            title="🚫 Usuário banido por advertências",
                            color=discord.Color.dark_red(),
                        )
                        embed_log.add_field(name="Usuário", value=f"{self.member.mention} ({self.member.id})", inline=False)
                        if server_id:
                            embed_log.add_field(name="ID no servidor", value=server_id, inline=True)
                        embed_log.add_field(name="Ação", value=action, inline=True)
                        embed_log.add_field(name="Motivo", value=self.motivo.value, inline=False)
                        embed_log.add_field(name="Executor", value=interaction.user.mention, inline=False)
                        
                        await warn_channel.send(embed=embed_log)
                
                # Salva log
                await self.ficha_cog.db.add_member_log(
                    interaction.guild.id,
                    self.member.id,
                    interaction.user.id,
                    "adv",
                    f"{action}: {self.motivo.value}"
                )
                
                await interaction.followup.send(f"✅ {self.member.mention} foi banido após ADV 2.", ephemeral=True)
                
                # Atualiza ficha
                registration_data = await self.ficha_cog._get_user_registration_data(interaction.guild.id, self.member.id)
                embed = await self.ficha_cog._build_user_ficha_embed(interaction.guild, self.member, registration_data, interaction.user)
                view = await self.ficha_cog._create_ficha_view(interaction.guild, self.member, interaction.user)
                await interaction.message.edit(embed=embed, view=view)
                return
            
            # Envia embed para canal de advertências (se configurado)
            if warn_channel_id:
                warn_channel = interaction.guild.get_channel(int(warn_channel_id))
                if isinstance(warn_channel, discord.TextChannel):
                    # Busca server_id para o embed
                    server_id = ""
                    registration_data = await self.ficha_cog._get_user_registration_data(interaction.guild.id, self.member.id)
                    if registration_data:
                        server_id = registration_data.get("server_id", "")
                    else:
                        # Tenta extrair do apelido
                        name = self.member.nick or self.member.name
                        if "|" in name:
                            try:
                                _, right = name.split("|", 1)
                                server_id = right.strip()
                            except ValueError:
                                pass
                    
                    embed_log = discord.Embed(
                        title="⚠️ Advertência aplicada",
                        color=discord.Color.orange(),
                    )
                    embed_log.add_field(name="Usuário", value=f"{self.member.mention} ({self.member.id})", inline=False)
                    if server_id:
                        embed_log.add_field(name="ID no servidor", value=server_id, inline=True)
                    embed_log.add_field(name="Ação", value=action, inline=True)
                    embed_log.add_field(name="Motivo", value=self.motivo.value, inline=False)
                    embed_log.add_field(name="Executor", value=interaction.user.mention, inline=False)
                    embed_log.set_thumbnail(url=self.member.display_avatar.url)
                    
                    await warn_channel.send(embed=embed_log)
            
            # Salva log
            await self.ficha_cog.db.add_member_log(
                interaction.guild.id,
                self.member.id,
                interaction.user.id,
                "adv",
                f"{action}: {self.motivo.value}"
            )
            
            # Envia DM se possível
            try:
                await self.member.send(
                    f"Você recebeu uma **{action.lower()}** no servidor.\n"
                    f"Motivo: {self.motivo.value}"
                )
            except discord.Forbidden:
                pass
            
            # Atualiza ficha
            registration_data = await self.ficha_cog._get_user_registration_data(interaction.guild.id, self.member.id)
            embed = await self.ficha_cog._build_user_ficha_embed(interaction.guild, self.member, registration_data, interaction.user)
            view = await self.ficha_cog._create_ficha_view(interaction.guild, self.member, interaction.user)
            
            await interaction.message.edit(embed=embed, view=view)
            # Não envia mensagem de confirmação - a atualização da ficha já é feedback suficiente
            
        except discord.Forbidden:
            await interaction.followup.send("❌ Não tenho permissão para aplicar advertência.", ephemeral=True)
        except Exception as e:
            LOGGER.error("Erro ao aplicar advertência: %s", e, exc_info=True)
            await interaction.followup.send("❌ Erro ao aplicar advertência.", ephemeral=True)


class TimeoutModal(discord.ui.Modal, title="Aplicar Timeout"):
    """Modal para aplicar timeout."""
    
    duration = discord.ui.TextInput(
        label="Duração",
        placeholder="10m, 1h ou 24h",
        max_length=10,
        required=True
    )
    
    motivo = discord.ui.TextInput(
        label="Motivo",
        placeholder="Digite o motivo do timeout...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True
    )
    
    def __init__(self, ficha_cog, member: discord.Member):
        super().__init__()
        self.ficha_cog = ficha_cog
        self.member = member
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Parse duração
            duration_str = self.duration.value.strip().lower()
            if duration_str == "10m":
                duration = timedelta(minutes=10)
            elif duration_str == "1h":
                duration = timedelta(hours=1)
            elif duration_str == "24h":
                duration = timedelta(hours=24)
            else:
                await interaction.followup.send("❌ Duração inválida. Use: 10m, 1h ou 24h", ephemeral=True)
                return
            
            # Aplica timeout
            until = discord.utils.utcnow() + duration
            await self.member.timeout(until, reason=f"Timeout aplicado por {interaction.user}: {self.motivo.value}")
            
            # Salva log
            await self.ficha_cog.db.add_member_log(
                interaction.guild.id,
                self.member.id,
                interaction.user.id,
                "timeout",
                f"{duration_str}: {self.motivo.value}"
            )
            
            # Atualiza ficha
            registration_data = await self.ficha_cog._get_user_registration_data(interaction.guild.id, self.member.id)
            embed = await self.ficha_cog._build_user_ficha_embed(interaction.guild, self.member, registration_data, interaction.user)
            view = await self.ficha_cog._create_ficha_view(interaction.guild, self.member, interaction.user)
            
            await interaction.message.edit(embed=embed, view=view)
            await interaction.followup.send(f"✅ Timeout de {duration_str} aplicado com sucesso!", ephemeral=True)
            
        except discord.Forbidden:
            await interaction.followup.send("❌ Não tenho permissão para aplicar timeout.", ephemeral=True)
        except Exception as e:
            LOGGER.error("Erro ao aplicar timeout: %s", e, exc_info=True)
            await interaction.followup.send("❌ Erro ao aplicar timeout.", ephemeral=True)


class KickModal(discord.ui.Modal, title="Expulsar Membro"):
    """Modal para confirmar expulsão."""
    
    confirmacao = discord.ui.TextInput(
        label="Digite CONFIRMAR para expulsar",
        placeholder="CONFIRMAR",
        max_length=20,
        required=True
    )
    
    motivo = discord.ui.TextInput(
        label="Motivo",
        placeholder="Digite o motivo da expulsão...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True
    )
    
    def __init__(self, ficha_cog, member: discord.Member):
        super().__init__()
        self.ficha_cog = ficha_cog
        self.member = member
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        if self.confirmacao.value.upper() != "CONFIRMAR":
            await interaction.followup.send("❌ Confirmação inválida. Operação cancelada.", ephemeral=True)
            return
        
        try:
            # Expulsa membro
            await self.member.kick(reason=f"Expulso por {interaction.user}: {self.motivo.value}")
            
            # Salva log
            await self.ficha_cog.db.add_member_log(
                interaction.guild.id,
                self.member.id,
                interaction.user.id,
                "kick",
                self.motivo.value
            )
            
            await interaction.followup.send(f"✅ {self.member.mention} foi expulso do servidor.", ephemeral=True)
            
        except discord.Forbidden:
            await interaction.followup.send("❌ Não tenho permissão para expulsar membros.", ephemeral=True)
        except Exception as e:
            LOGGER.error("Erro ao expulsar membro: %s", e, exc_info=True)
            await interaction.followup.send("❌ Erro ao expulsar membro.", ephemeral=True)


class NicknameModal(discord.ui.Modal, title="Alterar Apelido"):
    """Modal para alterar apelido do membro."""
    
    nickname = discord.ui.TextInput(
        label="Novo Apelido",
        placeholder="Digite o novo apelido (ou deixe vazio para remover)...",
        max_length=32,
        required=False
    )
    
    def __init__(self, ficha_cog, member: discord.Member):
        super().__init__()
        self.ficha_cog = ficha_cog
        self.member = member
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            new_nick = self.nickname.value.strip() if self.nickname.value else None
            
            # Altera apelido
            await self.member.edit(nick=new_nick, reason=f"Apelido alterado por {interaction.user}")
            
            # Salva log
            await self.ficha_cog.db.add_member_log(
                interaction.guild.id,
                self.member.id,
                interaction.user.id,
                "nickname",
                f"Alterado para: {new_nick or '(removido)'}"
            )
            
            # Atualiza ficha
            registration_data = await self.ficha_cog._get_user_registration_data(interaction.guild.id, self.member.id)
            embed = await self.ficha_cog._build_user_ficha_embed(interaction.guild, self.member, registration_data, interaction.user)
            view = await self.ficha_cog._create_ficha_view(interaction.guild, self.member, interaction.user)
            
            await interaction.message.edit(embed=embed, view=view)
            await interaction.followup.send("✅ Apelido alterado com sucesso!", ephemeral=True)
            
        except discord.Forbidden:
            await interaction.followup.send("❌ Não tenho permissão para alterar apelidos.", ephemeral=True)
        except Exception as e:
            LOGGER.error("Erro ao alterar apelido: %s", e, exc_info=True)
            await interaction.followup.send("❌ Erro ao alterar apelido.", ephemeral=True)


class VoiceTimeModal(discord.ui.Modal, title="Editar Tempo de Voz"):
    """Modal para adicionar ou remover tempo de voz."""
    
    tempo = discord.ui.TextInput(
        label="Tempo",
        placeholder="Ex: 2h 30m, -1h, 150m, -30m, 0 (zerar)",
        max_length=20,
        required=True
    )
    
    motivo = discord.ui.TextInput(
        label="Motivo",
        placeholder="Digite o motivo da alteração...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True
    )
    
    def __init__(self, ficha_cog, member: discord.Member):
        super().__init__()
        self.ficha_cog = ficha_cog
        self.member = member
    
    def _parse_time(self, time_str: str) -> Optional[int]:
        """Converte string de tempo para segundos.
        
        Formatos aceitos:
        - "2h 30m" -> 9000 segundos
        - "1h" -> 3600 segundos
        - "30m" -> 1800 segundos
        - "150m" -> 9000 segundos
        - "0" -> 0 (zerar)
        - "-1h" -> -3600 segundos
        """
        time_str = time_str.strip().lower()
        
        # Se for "0", retorna None para indicar zerar
        if time_str == "0":
            return None
        
        # Verifica se é negativo
        is_negative = time_str.startswith("-")
        if is_negative:
            time_str = time_str[1:].strip()
        
        total_seconds = 0
        
        # Parse horas
        if "h" in time_str:
            parts = time_str.split("h", 1)
            try:
                hours = int(parts[0].strip())
                total_seconds += hours * 3600
                time_str = parts[1].strip() if len(parts) > 1 else ""
            except ValueError:
                return None
        
        # Parse minutos
        if "m" in time_str:
            parts = time_str.split("m", 1)
            try:
                minutes = int(parts[0].strip())
                total_seconds += minutes * 60
            except ValueError:
                return None
        
        # Se não tem h nem m, tenta como minutos
        if "h" not in time_str and "m" not in time_str and time_str:
            try:
                minutes = int(time_str)
                total_seconds = minutes * 60
            except ValueError:
                return None
        
        return -total_seconds if is_negative else total_seconds
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Parse tempo
            time_str = self.tempo.value.strip()
            seconds_delta = self._parse_time(time_str)
            
            if seconds_delta is None and time_str != "0":
                await interaction.followup.send(
                    "❌ Formato inválido. Use: 2h 30m, 1h, 30m, -1h, ou 0 para zerar",
                    ephemeral=True
                )
                return
            
            # Busca tempo atual
            current_total = await self.ficha_cog.db.get_total_voice_time(interaction.guild.id, self.member.id)
            
            # Se for zerar (time_str == "0")
            if time_str == "0":
                seconds_delta = -current_total  # Remove todo o tempo
            elif seconds_delta is None:
                await interaction.followup.send(
                    "❌ Formato inválido. Use: 2h 30m, 1h, 30m, -1h, ou 0 para zerar",
                    ephemeral=True
                )
                return
            
            # Limite razoável: máximo 1000 horas (3,600,000 segundos)
            if abs(seconds_delta) > 3600000:
                await interaction.followup.send("❌ Valor muito grande. Máximo: ±1000 horas", ephemeral=True)
                return
            
            # Ajusta tempo de voz
            new_total = await self.ficha_cog.db.adjust_voice_time(interaction.guild.id, self.member.id, seconds_delta)
            
            # Formata para exibição
            from .voice_utils import format_time
            time_delta_str = format_time(abs(seconds_delta))
            new_total_str = format_time(new_total)
            
            # Salva log
            await self.ficha_cog.db.add_member_log(
                interaction.guild.id,
                self.member.id,
                interaction.user.id,
                "voice_time",
                f"{self.motivo.value}",
                points_delta=seconds_delta  # Reutiliza points_delta para segundos
            )
            
            # Atualiza ficha
            registration_data = await self.ficha_cog._get_user_registration_data(interaction.guild.id, self.member.id)
            embed = await self.ficha_cog._build_user_ficha_embed(interaction.guild, self.member, registration_data, interaction.user)
            view = await self.ficha_cog._create_ficha_view(interaction.guild, self.member, interaction.user)
            
            await interaction.message.edit(embed=embed, view=view)
            
            action_text = "zerado" if time_str == "0" else ("adicionado" if seconds_delta > 0 else "removido")
            await interaction.followup.send(
                f"✅ Tempo {action_text}: {time_delta_str}\n"
                f"Novo total: {new_total_str}",
                ephemeral=True
            )
            
        except Exception as e:
            LOGGER.error("Erro ao editar tempo de voz: %s", e, exc_info=True)
            await interaction.followup.send("❌ Erro ao editar tempo de voz.", ephemeral=True)


class PromoteModal(discord.ui.Modal, title="Promover Membro"):
    """Modal para promover membro manualmente."""
    
    motivo = discord.ui.TextInput(
        label="Motivo da Promoção",
        placeholder="Digite o motivo da promoção...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True
    )
    
    def __init__(self, ficha_cog, member: discord.Member):
        super().__init__()
        self.ficha_cog = ficha_cog
        self.member = member
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Usa importações do topo do arquivo
            if not HierarchyRepository or not HierarchyCache or not HierarchyPromotionCog:
                await interaction.followup.send(
                    "❌ Sistema de hierarquia não disponível.",
                    ephemeral=True
                )
                return
            
            cache = HierarchyCache()
            repository = HierarchyRepository(self.ficha_cog.db, cache)
            
            # Busca status atual
            user_status = await repository.get_user_status(interaction.guild.id, self.member.id)
            if not user_status or not user_status.current_role_id:
                await interaction.followup.send(
                    "❌ Membro não possui cargo de hierarquia configurado.",
                    ephemeral=True
                )
                return
            
            # Busca configuração do cargo atual
            current_config = await repository.get_config(
                interaction.guild.id, user_status.current_role_id
            )
            if not current_config:
                await interaction.followup.send(
                    "❌ Cargo atual não encontrado na hierarquia.",
                    ephemeral=True
                )
                return
            
            # Busca próximo cargo
            next_config = await repository.get_config_by_level(
                interaction.guild.id, current_config.level_order + 1
            )
            if not next_config:
                await interaction.followup.send(
                    "❌ Não há cargo superior disponível.",
                    ephemeral=True
                )
                return
            
            # Usa motor de promoção para promover
            temp_cog = HierarchyPromotionCog(self.ficha_cog.bot, self.ficha_cog.db)
            result = await temp_cog._promote_user(
                interaction.guild,
                self.member.id,
                user_status.current_role_id,
                next_config,
                f"Promoção manual por {interaction.user}: {self.motivo.value}",
                str(interaction.user.id)
            )
            
            if "error" in result:
                await interaction.followup.send(
                    f"❌ Erro ao promover: {result['error']}",
                    ephemeral=True
                )
                return
            
            # Ignora promoção automática por 7 dias após promoção manual
            ignore_until = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            await repository.update_user_status(
                interaction.guild.id,
                self.member.id,
                ignore_auto_promote_until=ignore_until
            )
            
            # Atualiza ficha
            registration_data = await self.ficha_cog._get_user_registration_data(
                interaction.guild.id, self.member.id
            )
            embed = await self.ficha_cog._build_user_ficha_embed(
                interaction.guild, self.member, registration_data, interaction.user
            )
            view = await self.ficha_cog._create_ficha_view(
                interaction.guild, self.member, interaction.user
            )
            
            await interaction.message.edit(embed=embed, view=view)
            await interaction.followup.send(
                f"✅ {self.member.mention} foi promovido para {interaction.guild.get_role(next_config.role_id).mention}!",
                ephemeral=True
            )
            
        except Exception as e:
            LOGGER.error("Erro ao promover membro: %s", e, exc_info=True)
            await interaction.followup.send(
                "❌ Erro ao promover membro. Tente novamente.",
                ephemeral=True
            )


class DemoteModal(discord.ui.Modal, title="Rebaixar Membro"):
    """Modal para rebaixar membro manualmente."""
    
    motivo = discord.ui.TextInput(
        label="Motivo do Rebaixamento",
        placeholder="Digite o motivo do rebaixamento...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True
    )
    
    def __init__(self, ficha_cog, member: discord.Member):
        super().__init__()
        self.ficha_cog = ficha_cog
        self.member = member
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Usa importações do topo do arquivo
            if not HierarchyRepository or not HierarchyCache:
                await interaction.followup.send(
                    "❌ Sistema de hierarquia não disponível.",
                    ephemeral=True
                )
                return
            
            cache = HierarchyCache()
            repository = HierarchyRepository(self.ficha_cog.db, cache)
            
            # Busca status atual
            user_status = await repository.get_user_status(interaction.guild.id, self.member.id)
            if not user_status or not user_status.current_role_id:
                await interaction.followup.send(
                    "❌ Membro não possui cargo de hierarquia configurado.",
                    ephemeral=True
                )
                return
            
            # Busca configuração do cargo atual
            current_config = await repository.get_config(
                interaction.guild.id, user_status.current_role_id
            )
            if not current_config:
                await interaction.followup.send(
                    "❌ Cargo atual não encontrado na hierarquia.",
                    ephemeral=True
                )
                return
            
            # Busca cargo anterior (inferior)
            prev_config = await repository.get_config_by_level(
                interaction.guild.id, current_config.level_order - 1
            )
            if not prev_config:
                await interaction.followup.send(
                    "❌ Não há cargo inferior disponível.",
                    ephemeral=True
                )
                return
            
            # Remove cargo atual e adiciona cargo anterior
            current_role = interaction.guild.get_role(current_config.role_id)
            prev_role = interaction.guild.get_role(prev_config.role_id)
            
            if not current_role or not prev_role:
                await interaction.followup.send(
                    "❌ Cargos não encontrados no servidor.",
                    ephemeral=True
                )
                return
            
            # Verifica hierarquia do bot (usa importação do topo)
            if not check_bot_hierarchy:
                await interaction.followup.send(
                    "❌ Função de verificação de hierarquia não disponível.",
                    ephemeral=True
                )
                return
            
            can_manage, error_msg = check_bot_hierarchy(interaction.guild, prev_role)
            if not can_manage:
                await interaction.followup.send(
                    f"❌ {error_msg}",
                    ephemeral=True
                )
                return
            
            # Remove cargo atual e adiciona anterior
            await self.member.remove_roles(
                current_role,
                reason=f"Rebaixamento manual por {interaction.user}: {self.motivo.value}"
            )
            await self.member.add_roles(
                prev_role,
                reason=f"Rebaixamento manual por {interaction.user}: {self.motivo.value}"
            )
            
            # Atualiza status no banco
            now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            ignore_until = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            
            await repository.update_user_status(
                interaction.guild.id,
                self.member.id,
                current_role_id=prev_config.role_id,
                ignore_auto_promote_until=ignore_until,
                ignore_auto_demote_until=ignore_until
            )
            
            # Adiciona ao histórico
            await repository.add_history(
                interaction.guild.id,
                self.member.id,
                "manual_demotion",
                prev_config.role_id,
                from_role_id=current_config.role_id,
                reason=f"Rebaixamento manual por {interaction.user}: {self.motivo.value}",
                performed_by=interaction.user.id
            )
            
            # Atualiza ficha
            registration_data = await self.ficha_cog._get_user_registration_data(
                interaction.guild.id, self.member.id
            )
            embed = await self.ficha_cog._build_user_ficha_embed(
                interaction.guild, self.member, registration_data, interaction.user
            )
            view = await self.ficha_cog._create_ficha_view(
                interaction.guild, self.member, interaction.user
            )
            
            await interaction.message.edit(embed=embed, view=view)
            await interaction.followup.send(
                f"✅ {self.member.mention} foi rebaixado para {prev_role.mention}!",
                ephemeral=True
            )
            
        except Exception as e:
            LOGGER.error("Erro ao rebaixar membro: %s", e, exc_info=True)
            await interaction.followup.send(
                "❌ Erro ao rebaixar membro. Tente novamente.",
                ephemeral=True
            )


class StaffNoteModal(discord.ui.Modal, title="Adicionar Nota Interna"):
    """Modal para adicionar nota interna (apenas para Staff)."""
    
    nota = discord.ui.TextInput(
        label="Nota Interna",
        placeholder="Digite a nota interna (visível apenas para Staff)...",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )
    
    def __init__(self, ficha_cog, member: discord.Member):
        super().__init__()
        self.ficha_cog = ficha_cog
        self.member = member
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Salva log
        await self.ficha_cog.db.add_member_log(
            interaction.guild.id,
            self.member.id,
            interaction.user.id,
            "staff_note",
            self.nota.value
        )
        
        # Atualiza ficha
        registration_data = await self.ficha_cog._get_user_registration_data(interaction.guild.id, self.member.id)
        embed = await self.ficha_cog._build_user_ficha_embed(interaction.guild, self.member, registration_data, interaction.user)
        view = await self.ficha_cog._create_ficha_view(interaction.guild, self.member, interaction.user)
        
        await interaction.message.edit(embed=embed, view=view)
        await interaction.followup.send("✅ Nota interna adicionada com sucesso!", ephemeral=True)


# ===== VIEWS =====

class LogHistoryView(discord.ui.View):
    """View para histórico paginado de logs."""
    
    def __init__(self, ficha_cog, guild: discord.Guild, member: discord.Member, viewer: discord.Member, page: int = 0):
        super().__init__(timeout=300)
        self.ficha_cog = ficha_cog
        self.guild = guild
        self.member = member
        self.viewer = viewer
        self.page = page
        self.logs_per_page = 5
        self._total_logs_cache: Optional[int] = None  # Cache para evitar recontagem
    
    async def get_total_logs(self) -> int:
        """Busca total de logs com cache."""
        if self._total_logs_cache is None:
            self._total_logs_cache = await self.ficha_cog.db.count_member_logs(
                self.guild.id, self.member.id
            )
        return self._total_logs_cache
    
    async def build_embed(self) -> discord.Embed:
        """Constrói embed com logs da página atual."""
        total_logs = await self.get_total_logs()  # Usa cache
        total_pages = math.ceil(total_logs / self.logs_per_page) if total_logs > 0 else 1
        
        # Ajusta página se necessário
        if self.page >= total_pages:
            self.page = total_pages - 1
        if self.page < 0:
            self.page = 0
        
        offset = self.page * self.logs_per_page
        logs = await self.ficha_cog.db.get_member_logs(
            self.guild.id,
            self.member.id,
            limit=self.logs_per_page,
            offset=offset
        )
        
        embed = discord.Embed(
            title=f"📜 Histórico de {self.member.display_name}",
            description=f"Página {self.page + 1} de {total_pages}",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=self.member.display_avatar.url)
        embed.set_footer(text=f"Total de {total_logs} registros")
        
        if not logs:
            embed.add_field(
                name="📝 Logs",
                value="Nenhum registro encontrado.",
                inline=False
            )
        else:
            logs_text = []
            type_emojis = {
                "comentario": "💬",
                "adv": "⚠️",
                "timeout": "🔇",
                "kick": "🚫",
                "nickname": "🏷️",
                "voice_time": "⏱️",
                "staff_note": "🕵️"
            }
            
            for log in logs:
                log_type = log.get("type", "unknown")
                emoji = type_emojis.get(log_type, "📝")
                author_id = int(log.get("author_id", 0))
                author = self.guild.get_member(author_id)
                author_name = author.display_name if author else f"ID: {author_id}"
                timestamp = log.get("timestamp", "")
                
                content = log.get("content", "")
                if log_type == "voice_time":
                    from .voice_utils import format_time
                    delta = log.get("points_delta", 0)  # Reutiliza points_delta para segundos
                    if delta != 0:
                        time_str = format_time(abs(delta))
                        sign = "+" if delta > 0 else "-"
                        content = f"{sign}{time_str} - {content}"
                    else:
                        content = f"Zerado - {content}"
                elif log_type == "staff_note":
                    # Só mostra se viewer for staff
                    if not await self.ficha_cog._check_staff_permissions(self.viewer, self.guild):
                        continue
                
                logs_text.append(
                    f"{emoji} **{log_type.title()}** por {author_name}\n"
                    f"   {content[:200]}\n"
                    f"   *{timestamp}*"
                )
            
            if logs_text:
                embed.add_field(
                    name="📝 Logs",
                    value="\n\n".join(logs_text),
                    inline=False
                )
            else:
                embed.add_field(
                    name="📝 Logs",
                    value="Nenhum registro visível.",
                    inline=False
                )
        
        return embed
    
    async def update_view(self):
        """Atualiza botões de navegação."""
        total_logs = await self.get_total_logs()  # Usa cache
        total_pages = math.ceil(total_logs / self.logs_per_page) if total_logs > 0 else 1
        
        # Remove botões antigos
        self.clear_items()
        
        # Botão Anterior
        prev_button = discord.ui.Button(
            label="⬅️ Anterior",
            style=discord.ButtonStyle.secondary,
            disabled=self.page <= 0,
            row=0
        )
        prev_button.callback = self.previous_page
        self.add_item(prev_button)
        
        # Botão Próxima
        next_button = discord.ui.Button(
            label="➡️ Próxima",
            style=discord.ButtonStyle.secondary,
            disabled=self.page >= total_pages - 1,
            row=0
        )
        next_button.callback = self.next_page
        self.add_item(next_button)
        
        # Botão Voltar
        back_button = discord.ui.Button(
            label="⬅️ Voltar à Ficha",
            style=discord.ButtonStyle.primary,
            row=0
        )
        back_button.callback = self.back_to_ficha
        self.add_item(back_button)
    
    async def previous_page(self, interaction: discord.Interaction):
        """Navega para página anterior."""
        if self.page > 0:
            self.page -= 1
            await self.update_view()
            embed = await self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)
    
    async def next_page(self, interaction: discord.Interaction):
        """Navega para próxima página."""
        total_logs = await self.get_total_logs()  # Usa cache
        total_pages = math.ceil(total_logs / self.logs_per_page) if total_logs > 0 else 1
        if self.page < total_pages - 1:
            self.page += 1
            await self.update_view()
            embed = await self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)
    
    async def back_to_ficha(self, interaction: discord.Interaction):
        """Volta para a ficha principal."""
        registration_data = await self.ficha_cog._get_user_registration_data(self.guild.id, self.member.id)
        embed = await self.ficha_cog._build_user_ficha_embed(self.guild, self.member, registration_data, self.viewer)
        view = await self.ficha_cog._create_ficha_view(self.guild, self.member, self.viewer)
        await interaction.response.edit_message(embed=embed, view=view)


class MemberFichaView(discord.ui.View):
    """View principal da ficha com botões de ação."""
    
    def __init__(self, ficha_cog, guild: discord.Guild, member: discord.Member, viewer: discord.Member):
        super().__init__(timeout=300)
        self.ficha_cog = ficha_cog
        self.guild = guild
        self.member = member
        self.viewer = viewer
        self.is_staff = False
    
    async def initialize(self):
        """Inicializa a view e adiciona botões apropriados."""
        self.is_staff = await self.ficha_cog._check_staff_permissions(self.viewer, self.guild)
        
        # Botão Ver Histórico (sempre visível se houver logs)
        total_logs = await self.ficha_cog.db.count_member_logs(self.guild.id, self.member.id)
        if total_logs > 3:
            history_button = discord.ui.Button(
                label="📜 Ver Histórico",
                style=discord.ButtonStyle.secondary,
                row=0
            )
            history_button.callback = self.view_history
            self.add_item(history_button)
        
        # Botões apenas para Staff
        if self.is_staff:
            # Comentar
            comment_button = discord.ui.Button(
                label="📝 Comentar",
                style=discord.ButtonStyle.primary,
                row=0
            )
            comment_button.callback = self.add_comment
            self.add_item(comment_button)
            
            # Moderação (submenu)
            moderation_button = discord.ui.Button(
                label="🛡️ Moderação",
                style=discord.ButtonStyle.danger,
                row=0
            )
            moderation_button.callback = self.show_moderation_menu
            self.add_item(moderation_button)
            
            # Progressão de Carreira (se houver hierarquia configurada)
            try:
                # Usa importações do topo do arquivo
                if not HierarchyRepository or not HierarchyCache:
                    raise ImportError("Hierarquia não disponível")
                
                cache = HierarchyCache()
                repository = HierarchyRepository(self.ficha_cog.db, cache)
                user_status = await repository.get_user_status(self.guild.id, self.member.id)
                
                if user_status and user_status.current_role_id:
                    # Botão Promover
                    promote_button = discord.ui.Button(
                        label="⬆️ Promover",
                        style=discord.ButtonStyle.success,
                        row=1
                    )
                    promote_button.callback = self.promote_member
                    self.add_item(promote_button)
                    
                    # Botão Rebaixar
                    demote_button = discord.ui.Button(
                        label="⬇️ Rebaixar",
                        style=discord.ButtonStyle.danger,
                        row=1
                    )
                    demote_button.callback = self.demote_member
                    self.add_item(demote_button)
            except Exception:
                pass  # Ignora se hierarquia não estiver configurada
            
            # Editar Tempo de Voz
            voice_time_button = discord.ui.Button(
                label="⏱️ Editar Tempo",
                style=discord.ButtonStyle.primary,
                row=2
            )
            voice_time_button.callback = self.edit_voice_time
            self.add_item(voice_time_button)
            
            # Staff Note
            staff_note_button = discord.ui.Button(
                label="🕵️ Staff Note",
                style=discord.ButtonStyle.secondary,
                row=1
            )
            staff_note_button.callback = self.add_staff_note
            self.add_item(staff_note_button)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Verifica permissões antes de processar interações."""
        if not interaction.guild or not interaction.user:
            return False
        
        # Verifica se é staff para botões de moderação
        if not await self.ficha_cog._check_staff_permissions(interaction.user, interaction.guild):
            await interaction.response.send_message(
                "❌ Você não tem permissão para usar este botão.",
                ephemeral=True
            )
            return False
        
        return True
    
    async def view_history(self, interaction: discord.Interaction):
        """Abre histórico paginado."""
        view = LogHistoryView(self.ficha_cog, self.guild, self.member, self.viewer, page=0)
        await view.update_view()
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def add_comment(self, interaction: discord.Interaction):
        """Abre modal para adicionar comentário."""
        modal = CommentModal(self.ficha_cog, self.member)
        await interaction.response.send_modal(modal)
    
    async def show_moderation_menu(self, interaction: discord.Interaction):
        """Mostra menu de moderação."""
        view = ModerationMenuView(self.ficha_cog, self.guild, self.member, self.viewer)
        embed = discord.Embed(
            title="🛡️ Menu de Moderação",
            description="Selecione uma ação:",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def edit_voice_time(self, interaction: discord.Interaction):
        """Abre modal para editar tempo de voz."""
        modal = VoiceTimeModal(self.ficha_cog, self.member)
        await interaction.response.send_modal(modal)
    
    async def add_staff_note(self, interaction: discord.Interaction):
        """Abre modal para adicionar nota interna."""
        modal = StaffNoteModal(self.ficha_cog, self.member)
        await interaction.response.send_modal(modal)
    
    async def promote_member(self, interaction: discord.Interaction):
        """Abre modal para promover membro manualmente."""
        modal = PromoteModal(self.ficha_cog, self.member)
        await interaction.response.send_modal(modal)
    
    async def demote_member(self, interaction: discord.Interaction):
        """Abre modal para rebaixar membro manualmente."""
        modal = DemoteModal(self.ficha_cog, self.member)
        await interaction.response.send_modal(modal)


class ModerationMenuView(discord.ui.View):
    """View com menu de moderação."""
    
    def __init__(self, ficha_cog, guild: discord.Guild, member: discord.Member, viewer: discord.Member):
        super().__init__(timeout=300)
        self.ficha_cog = ficha_cog
        self.guild = guild
        self.member = member
        self.viewer = viewer
    
    @discord.ui.button(label="⚠️ Advertir", style=discord.ButtonStyle.danger, row=0)
    async def warn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = WarnModal(self.ficha_cog, self.member)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🔇 Timeout", style=discord.ButtonStyle.danger, row=0)
    async def apply_timeout(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = TimeoutModal(self.ficha_cog, self.member)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🚫 Expulsar", style=discord.ButtonStyle.danger, row=0)
    async def kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = KickModal(self.ficha_cog, self.member)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🏷️ Apelido", style=discord.ButtonStyle.primary, row=1)
    async def nickname(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = NicknameModal(self.ficha_cog, self.member)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="⬅️ Voltar", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        registration_data = await self.ficha_cog._get_user_registration_data(self.guild.id, self.member.id)
        embed = await self.ficha_cog._build_user_ficha_embed(self.guild, self.member, registration_data, self.viewer)
        view = await self.ficha_cog._create_ficha_view(self.guild, self.member, self.viewer)
        await interaction.response.edit_message(embed=embed, view=view)


class FichaCog(commands.Cog):
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db
        
        # Cache compartilhado de hierarquia (usa importações do topo)
        if HierarchyRepository and HierarchyCache:
            self._hierarchy_cache = HierarchyCache()
            self._repository = HierarchyRepository(self.db, self._hierarchy_cache)
        else:
            # Módulo de hierarquia não está disponível
            self._hierarchy_cache = None
            self._repository = None
        
        # Cache de settings (TTL: 5 minutos)
        self._settings_cache: Dict[int, Tuple[Dict, float]] = {}
        self._settings_ttl = 300  # segundos
    
    async def _get_cached_settings(self, guild_id: int) -> Dict:
        """Retorna settings com cache de 5 minutos."""
        import time
        now = time.time()
        
        if guild_id in self._settings_cache:
            settings, cached_at = self._settings_cache[guild_id]
            if now - cached_at < self._settings_ttl:
                return settings
        
        # Buscar do banco
        settings = await self.db.get_settings(guild_id)
        self._settings_cache[guild_id] = (settings, now)
        return settings
    
    async def _get_adv_status(
        self,
        guild: discord.Guild,
        member: discord.Member
    ) -> Optional[AdvStatus]:
        """Busca status completo de advertências do membro."""
        try:
            settings = await self._get_cached_settings(guild.id)
            
            role_adv1_id = settings.get("role_adv1")
            role_adv2_id = settings.get("role_adv2")
            
            if not (role_adv1_id or role_adv2_id):
                return None
            
            role_adv1 = guild.get_role(int(role_adv1_id)) if role_adv1_id else None
            role_adv2 = guild.get_role(int(role_adv2_id)) if role_adv2_id else None
            
            has_adv1 = role_adv1 in member.roles if role_adv1 else False
            has_adv2 = role_adv2 in member.roles if role_adv2 else False
            
            all_warnings = await self.db.get_member_logs(
                guild.id,
                member.id,
                log_type="adv",
                limit=50
            )
            
            ban_log = None
            warnings_only = []
            
            for log in all_warnings:
                content = log.get("content", "")
                if "Banimento" in content or "banido" in content.lower():
                    ban_log = log
                else:
                    warnings_only.append(log)
            
            return AdvStatus(
                has_adv1=has_adv1,
                has_adv2=has_adv2,
                is_banned=ban_log is not None,
                recent_warnings=warnings_only[:5],
                total_warnings=len(warnings_only)
            )
        except Exception as e:
            LOGGER.error(f"Erro ao buscar status de ADV: {e}", exc_info=True)
            return None
    
    async def _get_next_config(self, guild_id: int, current_role_id: int):
        """Helper para buscar próximo cargo na hierarquia."""
        if not self._repository:
            return None
        
        current = await self._repository.get_config(guild_id, current_role_id)
        if not current:
            return None
        # Próximo cargo = level_order - 1 (Nível 1 é o mais alto, então progredimos diminuindo)
        return await self._repository.get_config_by_level(guild_id, current.level_order - 1)
    
    async def _build_hierarchy_section(
        self,
        guild: discord.Guild,
        member: discord.Member
    ) -> Optional[str]:
        """Constrói seção de hierarquia com progresso detalhado."""
        try:
            if not self._repository:
                return None
            
            user_status = await self._repository.get_user_status(guild.id, member.id)
            
            if not user_status or not user_status.current_role_id:
                return None
            
            current_role = guild.get_role(user_status.current_role_id)
            if not current_role:
                return None
            
            # Queries paralelas
            current_config, next_config = await asyncio.gather(
                self._repository.get_config(guild.id, user_status.current_role_id),
                self._get_next_config(guild.id, user_status.current_role_id),
                return_exceptions=True
            )
            
            if isinstance(current_config, Exception) or not current_config:
                return "⚠️ *Erro ao carregar dados de hierarquia*"
            
            text = f"**Cargo Atual:** {current_role.mention} (Nível {current_config.level_order})\n"
            
            if isinstance(next_config, Exception) or not next_config:
                text += "\n*Nível máximo atingido*"
                return text
            
            next_role = guild.get_role(next_config.role_id)
            if not next_role:
                return text
            
            text += f"**Próximo Cargo:** {next_role.mention} (Nível {next_config.level_order})\n\n"
            
            # Usa método estruturado (usa importação do topo)
            if not HierarchyPromotionCog:
                text += "⚠️ *Sistema de verificação de requisitos não disponível*"
                return text
            
            temp_cog = HierarchyPromotionCog(self.bot, self.db)
            eligibility = await temp_cog.check_requirements_structured(guild, member.id, next_config)
            
            # Requisitos
            text += "**📋 Requisitos:**\n"
            for req in eligibility.requirements:
                status = "✅" if req.met else "❌"
                if req.name == "Call":
                    text += f"• {req.emoji} {req.name}: {req.current}h/{req.required}h {status}\n"
                elif req.name == "Tempo no Cargo":
                    text += f"• {req.emoji} {req.name}: {req.current}/{req.required} dias {status}\n"
                else:
                    text += f"• {req.emoji} {req.name}: {req.current:,}/{req.required:,} {status}\n"
            
            # Barra de progresso
            progress = eligibility.overall_progress
            filled = progress // 10
            bar = "▰" * filled + "▱" * (10 - filled)
            text += f"\n**📊 Progresso:** {bar} {progress}%\n"
            
            # Vagas (se limitado)
            if next_config.max_vacancies > 0:
                occupied = len([m for m in guild.members if next_role in m.roles])
                text += f"\n**Vagas:** {occupied}/{next_config.max_vacancies}"
            
            text += f"\n\n{eligibility.summary}"
            
            return text
            
        except ImportError:
            return "⚠️ *Sistema de hierarquia não configurado*"
        except asyncio.TimeoutError:
            LOGGER.error(f"Timeout ao buscar hierarquia para {member.id}")
            return "⏱️ *Timeout ao carregar hierarquia*"
        except Exception as e:
            LOGGER.error(f"Erro ao construir seção de hierarquia: {e}", exc_info=True)
            return "❌ *Erro ao carregar dados de hierarquia*"
    
    async def _build_adv_section(
        self,
        guild: discord.Guild,
        member: discord.Member
    ) -> Optional[str]:
        """Constrói seção de advertências com cargos e histórico."""
        status = await self._get_adv_status(guild, member)
        
        if not status or not (status.has_adv1 or status.has_adv2 or status.recent_warnings):
            return None
        
        text = ""
        
        if status.has_adv1 or status.has_adv2:
            roles_text = []
            settings = await self._get_cached_settings(guild.id)
            
            if status.has_adv1 and settings.get("role_adv1"):
                role = guild.get_role(int(settings["role_adv1"]))
                if role:
                    roles_text.append(role.mention)
            
            if status.has_adv2 and settings.get("role_adv2"):
                role = guild.get_role(int(settings["role_adv2"]))
                if role:
                    roles_text.append(role.mention)
            
            if roles_text:
                text += f"**Cargos Ativos:** {', '.join(roles_text)}\n"
        
        if status.recent_warnings:
            text += f"\n**Histórico** ({status.total_warnings} total):\n"
            
            for warning in status.recent_warnings[:3]:
                timestamp = warning.get("timestamp", "")
                content = warning.get("content", "")
                author_id = int(warning.get("author_id", 0))
                author = guild.get_member(author_id)
                author_name = author.display_name if author else f"ID:{author_id}"
                
                if len(content) > 80:
                    content = content[:77] + "..."
                
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    date_str = dt.strftime("%d/%m/%Y")
                except:
                    date_str = "N/A"
                
                text += f"• {date_str} - {content} (@{author_name})\n"
            
            if status.total_warnings > 3:
                remaining = status.total_warnings - 3
                text += f"\n*...e mais {remaining} advertência(s)*"
        
        if status.is_banned:
            text += "\n\n🚫 **Membro foi banido após ADV2**"
        
        return text if text else None
    
    async def _build_other_roles_section(
        self,
        guild: discord.Guild,
        member: discord.Member,
        exclude_role_ids: List[int]
    ) -> str:
        """Lista outros cargos excluindo hierarquia e advertências."""
        other_roles = [
            role for role in member.roles
            if role.id not in exclude_role_ids and role.name != "@everyone"
        ]
        
        if not other_roles:
            return "Nenhum"
        
        # Ordena por posição
        other_roles.sort(key=lambda r: r.position, reverse=True)
        
        roles_text = ", ".join([role.mention for role in other_roles])
        
        # Trunca se muito longo
        if len(roles_text) > 900:
            visible_roles = []
            total_length = 0
            remaining = 0
            
            for role in other_roles:
                role_mention = role.mention + ", "
                if total_length + len(role_mention) <= 900:
                    visible_roles.append(role.mention)
                    total_length += len(role_mention)
                else:
                    remaining += 1
            
            roles_text = ", ".join(visible_roles)
            if remaining > 0:
                roles_text += f"\n*...e mais {remaining} cargo(s)*"
        
        return roles_text
    
    async def _check_staff_permissions(self, member: discord.Member, guild: discord.Guild) -> bool:
        """Verifica se o membro é Staff (admin ou tem cargo configurado)."""
        # Admin sempre tem permissão
        if member.guild_permissions.administrator:
            return True
        
        # Verifica cargos configurados via command_permissions
        role_ids = await self.db.get_command_permissions(guild.id, "ficha")
        if role_ids:
            role_ids = role_ids.strip()
            if role_ids and role_ids != "0":
                try:
                    allowed_ids = {int(rid) for rid in role_ids.split(",") if rid.strip()}
                    member_role_ids = {role.id for role in member.roles}
                    return bool(allowed_ids & member_role_ids)
                except ValueError:
                    pass
        
        return False
    
    async def _get_member_adv_count(self, member: discord.Member, guild: discord.Guild) -> int:
        """Conta quantas advertências (ADV1 + ADV2) um membro tem baseado nos cargos."""
        try:
            channels, roles, _ = await _get_settings(self.db, guild.id)
            role_adv1_id = roles.get("adv1") or roles.get("role_adv1")
            role_adv2_id = roles.get("adv2") or roles.get("role_adv2")
            
            if not (role_adv1_id and role_adv2_id):
                return 0
            
            role_adv1 = guild.get_role(int(role_adv1_id))
            role_adv2 = guild.get_role(int(role_adv2_id))
            
            if not (role_adv1 and role_adv2):
                return 0
            
            count = 0
            if role_adv1 in member.roles:
                count += 1
            if role_adv2 in member.roles:
                count += 1
            
            return count
        except Exception as exc:
            LOGGER.warning("Erro ao contar ADVs: %s", exc)
            return 0
    
    async def _create_ficha_view(
        self,
        guild: discord.Guild,
        member: discord.Member,
        viewer: discord.Member
    ) -> MemberFichaView:
        """Cria e inicializa a view da ficha."""
        view = MemberFichaView(self, guild, member, viewer)
        await view.initialize()
        return view

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

    def _generate_activity_thermometer(self, msg_count: int, max_or_avg_count: float) -> str:
        """Gera barra de temperatura de atividade usando emojis de blocos.
        
        Args:
            msg_count: Número de mensagens do usuário
            max_or_avg_count: Média ou máximo de mensagens do servidor
            
        Returns:
            String com 5 emojis representando nível de atividade
        """
        if max_or_avg_count == 0:
            return "⬜⬜⬜⬜⬜"
        
        # Calcula percentil (limita a 100%)
        percentil = min(100, (msg_count / max_or_avg_count) * 100)
        
        # Mapeia percentil para número de blocos verdes (0-5)
        filled = int((percentil / 100) * 5)
        filled = max(0, min(5, filled))  # Garante entre 0 e 5
        
        # Se filled == 0, usa vermelho no primeiro bloco
        if filled == 0:
            return "🟥⬜⬜⬜⬜"
        
        # Caso contrário, usa blocos verdes e cinzas
        return "🟩" * filled + "⬜" * (5 - filled)

    async def _build_user_ficha_embed(
        self,
        guild: discord.Guild,
        member: discord.Member,
        registration_data: Optional[dict] = None,
        viewer: Optional[discord.Member] = None
    ) -> discord.Embed:
        """Constrói a embed com todas as informações do usuário.
        
        Esta função foi estruturada para ser facilmente extensível.
        """
        # Inicia medição de performance
        start_time = time.perf_counter()
        
        guild = member.guild
        
        # Calcula permissões de staff uma única vez
        is_staff = await self._check_staff_permissions(viewer, guild) if viewer else False
        
        # OTIMIZAÇÃO: Paraleliza todas as queries independentes
        gather_results = await asyncio.gather(
            self._get_cached_settings(guild.id),
            self.db.get_user_stats(guild.id, member.id),
            self.db.get_total_voice_time(guild.id, member.id),
            self.db.get_user_analytics(guild.id, member.id),
            self.db.get_member_logs(guild.id, member.id, limit=3),
            self.db.get_member_logs(guild.id, member.id, limit=5, log_type="staff_note") if is_staff else asyncio.sleep(0, result=[]),
            self._build_hierarchy_section(guild, member),
            self._build_adv_section(guild, member),
            return_exceptions=True
        )
        
        # Valida cada resultado do gather
        settings = gather_results[0] if not isinstance(gather_results[0], Exception) else {}
        if isinstance(gather_results[0], Exception):
            LOGGER.error("Erro ao buscar settings: %s", gather_results[0], exc_info=gather_results[0])
        
        user_stats = gather_results[1] if not isinstance(gather_results[1], Exception) else None
        if isinstance(gather_results[1], Exception):
            LOGGER.error("Erro ao buscar user_stats: %s", gather_results[1], exc_info=gather_results[1])
        
        total_voice_seconds = gather_results[2] if not isinstance(gather_results[2], Exception) else 0
        if isinstance(gather_results[2], Exception):
            LOGGER.error("Erro ao buscar voice_time: %s", gather_results[2], exc_info=gather_results[2])
        
        analytics = gather_results[3] if not isinstance(gather_results[3], Exception) else None
        if isinstance(gather_results[3], Exception):
            LOGGER.error("Erro ao buscar analytics: %s", gather_results[3], exc_info=gather_results[3])
        
        logs = gather_results[4] if not isinstance(gather_results[4], Exception) else []
        if isinstance(gather_results[4], Exception):
            LOGGER.error("Erro ao buscar logs: %s", gather_results[4], exc_info=gather_results[4])
        
        staff_notes = gather_results[5] if not isinstance(gather_results[5], Exception) else []
        if isinstance(gather_results[5], Exception):
            LOGGER.error("Erro ao buscar staff_notes: %s", gather_results[5], exc_info=gather_results[5])
        
        hierarchy_text = gather_results[6] if not isinstance(gather_results[6], Exception) else None
        if isinstance(gather_results[6], Exception):
            LOGGER.error("Erro ao buscar hierarchy: %s", gather_results[6], exc_info=gather_results[6])
            hierarchy_text = "❌ *Erro ao carregar dados de hierarquia*"
        
        adv_text = gather_results[7] if not isinstance(gather_results[7], Exception) else None
        if isinstance(gather_results[7], Exception):
            LOGGER.error("Erro ao buscar adv_status: %s", gather_results[7], exc_info=gather_results[7])
            adv_text = "❌ *Erro ao carregar advertências*"
        
        # Usa EmbedBuilder para validação automática de limites
        builder = EmbedBuilder(
            title=f"📋 Ficha de {member.display_name}",
            color=member.color if member.color != discord.Color.default() else discord.Color.blue()
        )
        
        # Avatar e footer
        builder.embed.set_thumbnail(url=member.display_avatar.url)
        builder.embed.set_footer(text="Golias Bot • Ficha do Membro")
        builder.embed.timestamp = discord.utils.utcnow()
        
        # ===== INFORMAÇÕES BÁSICAS DO DISCORD =====
        builder.add_field_safe(
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
        
        builder.add_field_safe(
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
            
            builder.add_field_safe(
                name="🏠 Servidor",
                value=f"**Entrou em:** {discord.utils.format_dt(member.joined_at, style='R')}\n"
                      f"**Tempo no servidor:** {server_age_str}",
                inline=True
            )
        else:
            builder.add_field_safe(
                name="🏠 Servidor",
                value="*Data de entrada não disponível*",
                inline=True
            )
        
        # ===== INFORMAÇÕES DE CADASTRO (se disponível) =====
        if registration_data:
            server_id = registration_data.get("server_id", "")
            recruiter_id = registration_data.get("recruiter_id", "")
            
            if server_id:
                builder.add_field_safe(
                    name="🎮 ID no Servidor",
                    value=f"`{server_id}`",
                    inline=True
                )
            
            if recruiter_id:
                recruiter = guild.get_member(int(recruiter_id)) if recruiter_id.isdigit() else None
                recruiter_mention = recruiter.mention if recruiter else f"`{recruiter_id}`"
                builder.add_field_safe(
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
                        builder.add_field_safe(
                            name="🎮 ID no Servidor",
                            value=f"`{server_id}`",
                            inline=True
                        )
                except ValueError:
                    pass
        
        # ===== CARGOS (SERÃO ADICIONADOS POR SEÇÃO MAIS ABAIXO) =====
        
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
        
        builder.add_field_safe(
            name="📊 Status",
            value=f"**Status:** {status_str} {str(member.status).title()}\n"
                  f"**Atividade:** {activity_str}",
            inline=True
        )
        
        # ===== HISTÓRICO DE AÇÕES ===== (já carregado no gather)
        if user_stats:
            participations = user_stats.get("participations", 0)
            total_earned = user_stats.get("total_earned", 0.0)
            builder.add_field_safe(
                name="📊 Histórico de Ações",
                value=(
                    f"**Participações:** {participations}\n"
                    f"**Total Ganho:** R$ {total_earned:,.2f}"
                ),
                inline=True
            )
        else:
            builder.add_field_safe(
                name="📊 Histórico de Ações",
                value="Nenhuma participação registrada",
                inline=True
            )
        
        # ===== TEMPO TOTAL EM CALL ===== (já carregado no gather)
        try:
            from .voice_utils import format_time
            time_str = format_time(total_voice_seconds)
            builder.add_field_safe(
                name="⏱️ Tempo Total em Call",
                value=time_str,
                inline=True
            )
        except Exception as exc:
            LOGGER.warning("Erro ao formatar tempo em call: %s", exc)
            builder.add_field_safe(
                name="⏱️ Tempo Total em Call",
                value="0h 0min 0seg",
                inline=True
            )
        
        # ===== ESTATÍSTICAS DE ENGAJAMENTO ===== (já carregado no gather)
        if analytics:
            msg_count = analytics.get("msg_count", 0)
            img_count = analytics.get("img_count", 0)
            reactions_given = analytics.get("reactions_given", 0)
            reactions_received = analytics.get("reactions_received", 0)
            mentions_sent = analytics.get("mentions_sent", 0)
            mentions_received = analytics.get("mentions_received", 0)
            
            # Buscar ranking e média (paraleliza as 2 queries restantes)
            rank, avg_messages = await asyncio.gather(
                self.db.get_user_rank(guild.id, member.id),
                self.db.get_server_avg_messages(guild.id),
                return_exceptions=True
            )
            
            # Valida resultados
            if isinstance(rank, Exception):
                LOGGER.warning("Erro ao buscar rank: %s", rank)
                rank = None
            if isinstance(avg_messages, Exception):
                LOGGER.warning("Erro ao buscar avg_messages: %s", avg_messages)
                avg_messages = 1
            
            rank_text = f"#{rank}" if rank else "N/A"
            if avg_messages is None or avg_messages == 0:
                avg_messages = 1  # Evita divisão por zero
            
            # Gerar barra de temperatura
            thermometer = self._generate_activity_thermometer(msg_count, avg_messages)
            
            builder.add_field_safe(
                name="📊 Estatísticas de Engajamento",
                value=(
                    f"**Mensagens:** {msg_count:,}\n"
                    f"**Imagens:** {img_count:,}\n"
                    f"**Reações:** {reactions_given:,} dadas | {reactions_received:,} recebidas\n"
                    f"**Menções:** {mentions_sent:,} enviadas | {mentions_received:,} recebidas\n"
                    f"**Ranking:** {rank_text}º membro mais ativo\n"
                    f"**Atividade:** {thermometer}"
                ),
                inline=False
            )
        else:
            builder.add_field_safe(
                name="📊 Estatísticas de Engajamento",
                value="Nenhum dado disponível ainda.",
                inline=False
            )
        
        # ===== SEÇÃO 1: HIERARQUIA E PROGRESSÃO ===== (já carregado no gather)
        if hierarchy_text:
            builder.add_field_safe(
                name="🎖️ Hierarquia e Progressão",
                value=hierarchy_text,
                inline=False
            )
        
        # ===== SEÇÃO 2: ADVERTÊNCIAS ===== (já carregado no gather)
        if adv_text:
            builder.add_field_safe(
                name="⚠️ Advertências",
                value=adv_text,
                inline=False
            )
        
        # ===== SEÇÃO 3: OUTROS CARGOS ===== (usa settings já carregado)
        # Coleta IDs para excluir (hierarquia + advertências)
        hierarchy_role_ids = []
        try:
            if self._repository:
                all_configs = await self._repository.get_all_configs(guild.id)
                hierarchy_role_ids = [cfg.role_id for cfg in all_configs]
        except Exception:
            pass
        
        adv_role_ids = []
        if settings.get("role_adv1"):
            adv_role_ids.append(int(settings["role_adv1"]))
        if settings.get("role_adv2"):
            adv_role_ids.append(int(settings["role_adv2"]))
        
        exclude_ids = hierarchy_role_ids + adv_role_ids
        other_roles_text = await self._build_other_roles_section(guild, member, exclude_ids)
        
        builder.add_field_safe(
            name="🏷️ Outros Cargos",
            value=other_roles_text,
            inline=False
        )
        
        # ===== ÚLTIMOS LOGS ===== (já carregado no gather)
        if logs:
            logs_text = []
            type_emojis = {
                "comentario": "💬",
                "adv": "⚠️",
                "timeout": "🔇",
                "kick": "🚫",
                "nickname": "🏷️",
                "voice_time": "⏱️",
                "staff_note": "🕵️"
            }
            
            for log in logs[:3]:
                log_type = log.get("type", "unknown")
                
                # Pula staff_note se viewer não for staff (usa is_staff já calculado)
                if log_type == "staff_note" and not is_staff:
                    continue
                
                emoji = type_emojis.get(log_type, "📝")
                author_id = int(log.get("author_id", 0))
                author = guild.get_member(author_id)
                author_name = author.display_name if author else f"ID: {author_id}"
                
                content = log.get("content", "")
                if log_type == "voice_time":
                    from .voice_utils import format_time
                    delta = log.get("points_delta", 0)  # Reutiliza points_delta para segundos
                    if delta != 0:
                        time_str = format_time(abs(delta))
                        sign = "+" if delta > 0 else "-"
                        content = f"{sign}{time_str} - {content}"
                    else:
                        content = f"Zerado - {content}"
                
                # Trunca conteúdo muito longo
                if len(content) > 100:
                    content = content[:97] + "..."
                
                logs_text.append(f"{emoji} {author_name}: {content}")
            
            if logs_text:
                builder.add_field_safe(
                    name="📝 Últimos Registros",
                    value="\n".join(logs_text),
                    inline=False
                )
        
        # ===== STAFF NOTES (apenas para Staff) ===== (já carregado no gather)
        if is_staff and staff_notes:
            notes_text = []
            for note in staff_notes[:3]:
                author_id = int(note.get("author_id", 0))
                author = guild.get_member(author_id)
                author_name = author.display_name if author else f"ID: {author_id}"
                content = note.get("content", "")
                if len(content) > 80:
                    content = content[:77] + "..."
                notes_text.append(f"🕵️ {author_name}: {content}")
            
            if notes_text:
                builder.add_field_safe(
                    name="🕵️ Notas Internas",
                    value="\n".join(notes_text),
                    inline=False
                )
        
        # Log de performance com detalhamento
        elapsed = time.perf_counter() - start_time
        elapsed_ms = elapsed * 1000
        
        LOGGER.info(
            "Ficha construída em %.2fms para usuário %s (guild: %s)",
            elapsed_ms, member.id, guild.id
        )
        
        if elapsed > 0.8:  # Aviso se demorar >800ms
            # Detalhamento dos campos processados
            fields_processed = []
            if user_stats:
                fields_processed.append("user_stats")
            if total_voice_seconds > 0:
                fields_processed.append("voice_time")
            if analytics:
                fields_processed.append("analytics")
            if logs:
                fields_processed.append(f"logs({len(logs)})")
            if staff_notes:
                fields_processed.append(f"staff_notes({len(staff_notes)})")
            if hierarchy_text:
                fields_processed.append("hierarchy")
            if adv_text:
                fields_processed.append("adv_status")
            
            LOGGER.warning(
                "⚠️ PERFORMANCE: Ficha demorou %.2fms (acima de 800ms esperado)\n"
                "   Usuário: %s | Guild: %s\n"
                "   Campos processados: %s\n"
                "   Total de fields no embed: %d",
                elapsed_ms, member.id, guild.id,
                ", ".join(fields_processed) if fields_processed else "nenhum",
                len(builder.embed.fields)
            )
        
        return builder.embed

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
        # Verifica se já está sendo processado (prevenção de duplicação) - thread-safe
        msg_id = ctx.message.id
        with self.bot._processing_lock:
            if msg_id in self.bot._processing_messages:
                return
            
            # Marca como em processamento
            self.bot._processing_messages.add(msg_id)
        
        try:
            guild = ctx.guild
            if not guild:
                await ctx.send("❌ Use este comando em um servidor.")
                return
            
            # Busca o membro
            member = await self._find_member_flexible(guild, identifier)
            if not member:
                await ctx.send(f"❌ Não encontrei membro com identificador `{identifier}` no servidor.")
                return
            
            # Busca dados de cadastro (se disponível)
            registration_data = await self._get_user_registration_data(guild.id, member.id)
            
            # Constrói embed com timeout de 10s
            try:
                embed = await asyncio.wait_for(
                    self._build_user_ficha_embed(guild, member, registration_data, ctx.author),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                LOGGER.error(
                    "Timeout ao construir ficha para usuário %s no servidor %s",
                    member.id, guild.id
                )
                await ctx.send(
                    "⏱️ Timeout ao carregar ficha (>10s). Por favor, tente novamente.\n"
                    "Se o problema persistir, contate um administrador."
                )
                return
            
            # Cria view com tratamento de erro isolado
            view = None
            try:
                view = await self._create_ficha_view(guild, member, ctx.author)
            except Exception as e:
                LOGGER.error(
                    "Erro ao criar view da ficha para usuário %s: %s",
                    member.id, e, exc_info=True
                )
                # Continua sem a view - pelo menos o embed será enviado
            
            # Envia embed (com ou sem view)
            await ctx.send(embed=embed, view=view)
            
        finally:
            # Remove do set de processamento imediatamente após envio
            with self.bot._processing_lock:
                self.bot._processing_messages.discard(msg_id)


async def setup(bot):
    """Função de setup para carregamento da extensão."""
    from db import Database
    
    await bot.add_cog(FichaCog(bot, bot.db))

