import logging
from typing import Optional

import discord
from discord.ext import commands

from db import Database
from permissions import command_guard
from .voice_utils import format_time

LOGGER = logging.getLogger(__name__)


class VoiceCommandsCog(commands.Cog):
    """Cog para comandos de visualização de pontos por voz."""
    
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db
    
    async def _find_member(self, guild: discord.Guild, identifier: Optional[str]) -> Optional[discord.Member]:
        """Busca um membro por menção ou retorna o autor se identifier for None."""
        if not identifier:
            return None
        
        identifier = identifier.strip()
        
        # Remove menções <@!id> ou <@id>
        if identifier.startswith("<@") and identifier.endswith(">"):
            identifier = identifier[2:-1]
            if identifier.startswith("!"):
                identifier = identifier[1:]
        
        # Tenta como discord_id
        if identifier.isdigit():
            try:
                user_id = int(identifier)
                member = guild.get_member(user_id)
                if member:
                    return member
            except (ValueError, OverflowError):
                pass
        
        return None
    
    @commands.command(name="ponto")
    @command_guard("ponto")
    async def ponto(self, ctx: commands.Context, member_mention: Optional[str] = None):
        """Mostra os pontos de tempo em call de um usuário.
        
        Uso: !ponto [@usuario]
        Se nenhum usuário for mencionado, mostra os pontos do próprio autor.
        Apenas Staff/Admin pode usar este comando.
        """
        if not ctx.guild:
            await ctx.reply("❌ Use este comando em um servidor.")
            return
        
        # Determina qual membro mostrar
        if member_mention:
            target_member = await self._find_member(ctx.guild, member_mention)
            if not target_member:
                await ctx.reply(f"❌ Não encontrei o membro `{member_mention}`.")
                return
        else:
            target_member = ctx.author
        
        # Busca estatísticas
        stats = await self.db.get_voice_stats(ctx.guild.id, target_member.id)
        total_seconds = await self.db.get_total_voice_time(ctx.guild.id, target_member.id)
        
        # Constrói embed
        embed = discord.Embed(
            title=f"⏱️ Pontos de {target_member.display_name}",
            color=target_member.color if target_member.color != discord.Color.default() else discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        embed.set_thumbnail(url=target_member.display_avatar.url)
        embed.set_footer(text="Golias Bot • Sistema de Pontos")
        
        # Adiciona estatísticas por canal
        if stats:
            for stat in stats[:10]:  # Limite de 10 canais
                channel_id = int(stat.get("channel_id", 0))
                channel = ctx.guild.get_channel(channel_id)
                channel_name = channel.mention if channel else f"`{channel_id}` (canal não encontrado)"
                seconds = stat.get("total_seconds", 0)
                time_str = format_time(seconds)
                embed.add_field(
                    name=f"📢 {channel_name}",
                    value=time_str,
                    inline=True
                )
            
            if len(stats) > 10:
                embed.add_field(
                    name="...",
                    value=f"*+ {len(stats) - 10} canal(is) adicional(is)*",
                    inline=False
                )
        else:
            embed.add_field(
                name="📢 Canais",
                value="Nenhum tempo registrado",
                inline=False
            )
        
        # Adiciona total
        embed.add_field(
            name="📊 Total",
            value=format_time(total_seconds),
            inline=False
        )
        
        await ctx.reply(embed=embed)
        
        # Deleta o comando após execução
        try:
            await ctx.message.delete()
        except:
            pass
    
    @commands.command(name="ponto_relatorio")
    @command_guard("ponto_relatorio")
    async def ponto_relatorio(self, ctx: commands.Context):
        """Gera um ranking dos 10 membros com mais tempo acumulado.
        
        Apenas Staff/Admin pode usar este comando.
        """
        if not ctx.guild:
            await ctx.reply("❌ Use este comando em um servidor.")
            return
        
        # Busca ranking
        ranking = await self.db.get_voice_ranking(ctx.guild.id, limit=10)
        
        if not ranking:
            await ctx.reply("❌ Nenhum dado de pontos encontrado no servidor.")
            return
        
        # Constrói embed
        embed = discord.Embed(
            title="📊 Ranking de Pontos por Voz",
            description="Top 10 membros com mais tempo acumulado",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )
        
        embed.set_footer(text="Golias Bot • Sistema de Pontos")
        
        # Adiciona membros ao ranking
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        
        ranking_text = []
        for idx, entry in enumerate(ranking):
            user_id = int(entry.get("user_id", 0))
            total_seconds = entry.get("total_seconds", 0)
            time_str = format_time(total_seconds)
            
            member = ctx.guild.get_member(user_id)
            if member:
                mention = member.mention
            else:
                mention = f"`{user_id}` (usuário não encontrado)"
            
            medal = medals[idx] if idx < len(medals) else f"{idx + 1}."
            ranking_text.append(f"{medal} {mention}: {time_str}")
        
        embed.description = "\n".join(ranking_text)
        
        await ctx.reply(embed=embed)
        
        # Deleta o comando após execução
        try:
            await ctx.message.delete()
        except:
            pass
