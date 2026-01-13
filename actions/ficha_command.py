import asyncio
import logging
import math
from datetime import timedelta
from typing import Optional, Dict, Any, Tuple

import discord
from discord.ext import commands

from db import Database
from permissions import command_guard, check_command_permission
from .registration import _get_settings

LOGGER = logging.getLogger(__name__)

# Usa o set global do bot para prevenir execução duplicada


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
    
    async def build_embed(self) -> discord.Embed:
        """Constrói embed com logs da página atual."""
        total_logs = await self.ficha_cog.db.count_member_logs(self.guild.id, self.member.id)
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
        total_logs = await self.ficha_cog.db.count_member_logs(self.guild.id, self.member.id)
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
        total_logs = await self.ficha_cog.db.count_member_logs(self.guild.id, self.member.id)
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
            
            # Editar Tempo de Voz
            voice_time_button = discord.ui.Button(
                label="⏱️ Editar Tempo",
                style=discord.ButtonStyle.primary,
                row=1
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
        
        # ===== TEMPO TOTAL EM CALL =====
        try:
            from .voice_utils import format_time
            total_seconds = await self.db.get_total_voice_time(guild.id, member.id)
            time_str = format_time(total_seconds)
            embed.add_field(
                name="⏱️ Tempo Total em Call",
                value=time_str,
                inline=True
            )
        except Exception as exc:
            LOGGER.warning("Erro ao buscar tempo em call: %s", exc)
            embed.add_field(
                name="⏱️ Tempo Total em Call",
                value="0h 0min 0seg",
                inline=True
            )
        
        # ===== ADVERTÊNCIAS =====
        try:
            adv_count = await self._get_member_adv_count(member, guild)
            adv_text = "Nenhuma" if adv_count == 0 else f"{adv_count} ADV(s)"
            embed.add_field(
                name="⚠️ Advertências",
                value=adv_text,
                inline=True
            )
        except Exception as exc:
            LOGGER.warning("Erro ao contar ADVs: %s", exc)
            embed.add_field(
                name="⚠️ Advertências",
                value="Nenhuma",
                inline=True
            )
        
        # ===== ÚLTIMOS LOGS =====
        try:
            logs = await self.db.get_member_logs(guild.id, member.id, limit=3)
            is_staff = await self._check_staff_permissions(viewer, guild) if viewer else False
            
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
                    
                    # Pula staff_note se viewer não for staff
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
                    embed.add_field(
                        name="📝 Últimos Registros",
                        value="\n".join(logs_text),
                        inline=False
                    )
        except Exception as exc:
            LOGGER.warning("Erro ao buscar logs: %s", exc)
        
        # ===== STAFF NOTES (apenas para Staff) =====
        if viewer and await self._check_staff_permissions(viewer, guild):
            try:
                staff_notes = await self.db.get_member_logs(
                    guild.id,
                    member.id,
                    limit=5,
                    log_type="staff_note"
                )
                if staff_notes:
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
                        embed.add_field(
                            name="🕵️ Notas Internas",
                            value="\n".join(notes_text),
                            inline=False
                        )
            except Exception as exc:
                LOGGER.warning("Erro ao buscar staff notes: %s", exc)
        
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
            
            # Constrói embed e view
            embed = await self._build_user_ficha_embed(guild, member, registration_data, ctx.author)
            view = await self._create_ficha_view(guild, member, ctx.author)
            
            # Envia embed com view (sem delete_after para permitir interações)
            await ctx.send(embed=embed, view=view)
        finally:
            # Remove do set de processamento após 2 segundos
            await asyncio.sleep(2)
            with self.bot._processing_lock:
                self.bot._processing_messages.discard(msg_id)


async def setup(bot):
    """Função de setup para carregamento da extensão."""
    from db import Database
    
    await bot.add_cog(FichaCog(bot, bot.db))

