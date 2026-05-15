import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from typing import Dict, List, Optional, Tuple

import discord
from discord.ext import commands, tasks

from db import Database

LOGGER = logging.getLogger(__name__)


class AnalyticsCog(commands.Cog):
    """Cog para rastreamento de analytics de membros (mensagens, reações, menções)."""
    
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db
        
        # Buffer em memória: {(guild_id, user_id): {contadores acumulados}}
        self._buffer: Dict[Tuple[int, int], Dict[str, int]] = defaultdict(
            lambda: {
                "msg_count": 0,
                "img_count": 0,
                "mentions_sent": 0,
                "mentions_received": 0,
                "reactions_given": 0,
                "reactions_received": 0,
            }
        )
        
        # Proteção contra flood: deque com (message_id, timestamp)
        self._processed_messages: deque = deque(maxlen=100)
        
        # Cache de canais ignorados por guild
        self._ignored_channels_cache: Dict[int, List[int]] = {}
    
    async def cog_load(self):
        """Inicializa tarefa periódica ao carregar o cog."""
        self.save_buffer_task.start()
        
    
    async def cog_unload(self):
        """Salva buffer pendente antes de desligar."""
        self.save_buffer_task.cancel()
        try:
            await self._flush_buffer()
            LOGGER.info("AnalyticsCog descarregado - buffer salvo")
        except Exception as e:
            LOGGER.error("Erro ao salvar buffer no unload: %s", e, exc_info=True)
    
    def _add_to_buffer(self, guild_id: int, user_id: int, **updates):
        """Acumula valores no buffer em memória."""
        key = (guild_id, user_id)
        for field, delta in updates.items():
            if field in self._buffer[key]:
                self._buffer[key][field] += delta
    
    async def _flush_buffer(self):
        """Salva todos os dados do buffer no banco usando batch_upsert."""
        if not self._buffer:
            return
        
        updates_list = []
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        
        for (guild_id, user_id), counts in self._buffer.items():
            # Só adiciona se houver mudanças
            if any(count != 0 for count in counts.values()):
                update = {
                    "guild_id": guild_id,
                    "user_id": user_id,
                    **counts,
                    "last_active": current_time
                }
                updates_list.append(update)
        
        if updates_list:
            try:
                await self.db.batch_upsert_user_analytics(updates_list)
                LOGGER.debug("Buffer salvo: %d atualizações", len(updates_list))
            except Exception as e:
                LOGGER.error("Erro ao salvar buffer: %s", e, exc_info=True)
        
        # Limpa o buffer
        self._buffer.clear()
    
    @tasks.loop(seconds=60)
    async def save_buffer_task(self):
        """Tarefa periódica que salva o buffer a cada 60 segundos."""
        await self._flush_buffer()
    
    @save_buffer_task.before_loop
    async def before_save_buffer_task(self):
        """Aguarda bot estar pronto antes de iniciar tarefa."""
        await self.bot.wait_until_ready()
    
    async def _get_ignored_channels(self, guild_id: int) -> List[int]:
        """Busca lista de canais ignorados para um guild (com cache)."""
        if guild_id in self._ignored_channels_cache:
            return self._ignored_channels_cache[guild_id]
        
        try:
            settings = await self.db.get_settings(guild_id)
            ignored_str = settings.get("analytics_ignored_channels")
            
            if ignored_str:
                try:
                    # Tenta parsear como JSON
                    ignored_list = json.loads(ignored_str)
                    if isinstance(ignored_list, list):
                        ignored_ids = [int(cid) for cid in ignored_list]
                    else:
                        # Fallback: separado por vírgula
                        ignored_ids = [int(cid.strip()) for cid in ignored_str.split(",") if cid.strip()]
                except (json.JSONDecodeError, ValueError):
                    # Fallback: separado por vírgula
                    ignored_ids = [int(cid.strip()) for cid in ignored_str.split(",") if cid.strip()]
            else:
                ignored_ids = []
            
            self._ignored_channels_cache[guild_id] = ignored_ids
            return ignored_ids
        except Exception as e:
            LOGGER.warning("Erro ao buscar canais ignorados para %s: %s", guild_id, e)
            return []
    
    def _is_message_processed(self, message_id: int) -> bool:
        """Verifica se mensagem já foi processada recentemente (últimos 5 segundos)."""
        current_time = time.time()
        for msg_id, timestamp in self._processed_messages:
            if msg_id == message_id and (current_time - timestamp) < 5:
                return True
        return False
    
    def _mark_message_processed(self, message_id: int):
        """Marca mensagem como processada."""
        self._processed_messages.append((message_id, time.time()))
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Rastreia mensagens para analytics."""
        # Ignorar bots
        if message.author.bot:
            return
        
        # Ignorar comandos
        if message.content and message.content.startswith("!"):
            return
        
        # Ignorar DMs
        if not message.guild:
            return
        
        # Verificar proteção contra flood
        if self._is_message_processed(message.id):
            return
        
        # Verificar canais ignorados
        ignored_channels = await self._get_ignored_channels(message.guild.id)
        if message.channel.id in ignored_channels:
            return
        
        guild_id = message.guild.id
        user_id = message.author.id
        
        # Adicionar ao buffer
        self._add_to_buffer(guild_id, user_id, msg_count=1)
        
        # Contar imagens/anexos
        if message.attachments:
            self._add_to_buffer(guild_id, user_id, img_count=len(message.attachments))
        
        # Processar menções (apenas membros, não bots)
        if message.mentions:
            for mentioned in message.mentions:
                if not mentioned.bot and mentioned.id != user_id:
                    # Autor mencionou alguém
                    self._add_to_buffer(guild_id, user_id, mentions_sent=1)
                    # Mencionado recebeu menção
                    self._add_to_buffer(guild_id, mentioned.id, mentions_received=1)
        
        # Marcar como processada
        self._mark_message_processed(message.id)
    
    @commands.Cog.listener()
    async def on_reaction_add(
        self, reaction: discord.Reaction, user: discord.User
    ):
        """Rastreia reações para analytics."""
        # Ignorar bots
        if user.bot:
            return
        
        # Ignorar se autor da mensagem for bot
        if reaction.message.author.bot:
            return
        
        # Ignorar DMs
        if not reaction.message.guild:
            return
        
        # Verificar canais ignorados
        ignored_channels = await self._get_ignored_channels(reaction.message.guild.id)
        if reaction.message.channel.id in ignored_channels:
            return
        
        guild_id = reaction.message.guild.id
        reactor_id = user.id
        author_id = reaction.message.author.id
        
        # Ignorar se usuário reagiu na própria mensagem (opcional)
        # if reactor_id == author_id:
        #     return
        
        # Adicionar ao buffer
        self._add_to_buffer(guild_id, reactor_id, reactions_given=1)
        self._add_to_buffer(guild_id, author_id, reactions_received=1)
    
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """Subtrai contadores quando mensagem é deletada (integridade dos dados)."""
        # Ignorar bots
        if message.author.bot:
            return
        
        # Ignorar comandos
        if message.content and message.content.startswith("!"):
            return
        
        # Ignorar DMs
        if not message.guild:
            return
        
        # Verificar canais ignorados
        ignored_channels = await self._get_ignored_channels(message.guild.id)
        if message.channel.id in ignored_channels:
            return
        
        guild_id = message.guild.id
        user_id = message.author.id
        
        # Buscar dados do autor no banco
        analytics = await self.db.get_user_analytics(guild_id, user_id)
        
        # Se existir e tiver mensagens, subtrai
        if analytics and analytics.get("msg_count", 0) > 0:
            self._add_to_buffer(guild_id, user_id, msg_count=-1)
            
            # Se tinha anexos, subtrai também
            if message.attachments:
                img_count = min(len(message.attachments), analytics.get("img_count", 0))
                if img_count > 0:
                    self._add_to_buffer(guild_id, user_id, img_count=-img_count)
            
            # Nota: Para menções em mensagens deletadas, seria necessário cache
            # de mensagens recentes. Por simplicidade, ignoramos essa parte.
    
    @commands.command(name="top_stats")
    @commands.has_permissions(administrator=True)
    async def top_stats(self, ctx: commands.Context):
        """Exibe ranking dos membros mais ativos do servidor baseado em mensagens enviadas.

Uso: !top_stats

Exemplos:
- !top_stats
"""
        if not ctx.guild:
            await ctx.send("❌ Use este comando em um servidor.")
            return
        
        view = TopStatsView(self.bot, self.db, ctx.guild, ctx.author)
        embed = await view.build_embed()
        await ctx.send(embed=embed, view=view)


class TopStatsView(discord.ui.View):
    """View paginada para ranking de membros mais ativos."""
    
    def __init__(self, bot: commands.Bot, db: Database, guild: discord.Guild, author: discord.Member):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = db
        self.guild = guild
        self.author = author
        self.page = 0
        self.per_page = 10
    
    async def build_embed(self) -> discord.Embed:
        """Constrói embed com ranking da página atual."""
        offset = self.page * self.per_page
        top_users = await self.db.get_top_users_by_messages(
            self.guild.id, limit=self.per_page, offset=offset
        )
        
        embed = discord.Embed(
            title="🏆 Top Membros Mais Ativos",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )
        
        if not top_users:
            embed.description = "Nenhum dado de analytics disponível ainda."
            return embed
        
        # Emojis de medalha para top 3
        medal_emojis = {0: "🥇", 1: "🥈", 2: "🥉"}
        
        stats_text = []
        for idx, user_data in enumerate(top_users):
            rank = offset + idx + 1
            user_id = int(user_data["user_id"])
            member = self.guild.get_member(user_id)
            
            if member:
                mention = member.mention
                display_name = member.display_name
            else:
                mention = f"<@{user_id}>"
                display_name = f"ID: {user_id}"
            
            medal = medal_emojis.get(idx, "")
            msg_count = user_data.get("msg_count", 0)
            img_count = user_data.get("img_count", 0)
            reactions = user_data.get("reactions_given", 0) + user_data.get("reactions_received", 0)
            
            stats_text.append(
                f"{medal} **#{rank}** {mention}\n"
                f"   📝 Mensagens: {msg_count:,} | 🖼️ Imagens: {img_count:,} | ⭐ Reações: {reactions:,}"
            )
        
        embed.description = "\n\n".join(stats_text)
        embed.set_footer(text=f"Página {self.page + 1} • Use os botões para navegar")
        
        return embed
    
    async def update_view(self):
        """Atualiza botões de navegação."""
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
            row=0
        )
        next_button.callback = self.next_page
        self.add_item(next_button)
    
    async def previous_page(self, interaction: discord.Interaction):
        """Navega para página anterior."""
        if self.page > 0:
            self.page -= 1
            await self.update_view()
            embed = await self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    async def next_page(self, interaction: discord.Interaction):
        """Navega para próxima página."""
        self.page += 1
        await self.update_view()
        embed = await self.build_embed()
        
        # Verifica se há dados na próxima página
        offset = self.page * self.per_page
        next_users = await self.db.get_top_users_by_messages(
            self.guild.id, limit=self.per_page, offset=offset
        )
        
        if not next_users:
            # Volta uma página se não houver dados
            self.page -= 1
            await self.update_view()
            embed = await self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Verifica se o autor do comando é quem está interagindo."""
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ Apenas quem executou o comando pode navegar.",
                ephemeral=True
            )
            return False
        return True


async def setup(bot):
    """Função de setup para carregamento da extensão."""
    db = bot.db
    await bot.add_cog(AnalyticsCog(bot, db))
