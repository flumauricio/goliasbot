"""Comandos administrativos do sistema de hierarquia."""

import logging
from typing import Optional

import discord
from discord.ext import commands

from db import Database
from permissions import command_guard
from .repository import HierarchyRepository
from .cache import HierarchyCache
from .promotion_engine import HierarchyPromotionCog
from .utils import check_bot_hierarchy

LOGGER = logging.getLogger(__name__)


class HierarchyCommandsCog(commands.Cog):
    """Cog com comandos administrativos de hierarquia."""
    
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db
        
        cache = HierarchyCache()
        self.repository = HierarchyRepository(db, cache)
    
    @commands.command(name="promover", aliases=["promote"])
    @command_guard("promover")
    async def promote_command(
        self,
        ctx: commands.Context,
        member: Optional[discord.Member] = None,
        *,
        motivo: str = "Promoção manual"
    ):
        """
        Promove um membro manualmente na hierarquia.
        
        Uso: !promover @membro [motivo]
        Exemplo: !promover @usuario Promoção por mérito
        """
        if not member:
            await ctx.send("❌ Mencione o membro a ser promovido.\nUso: `!promover @membro [motivo]`")
            return
        
        if member.bot:
            await ctx.send("❌ Não é possível promover bots.")
            return
        
        try:
            # Busca status atual
            user_status = await self.repository.get_user_status(ctx.guild.id, member.id)
            if not user_status or not user_status.current_role_id:
                await ctx.send(f"❌ {member.mention} não possui cargo de hierarquia configurado.")
                return
            
            # Busca configuração do cargo atual
            current_config = await self.repository.get_config(
                ctx.guild.id, user_status.current_role_id
            )
            if not current_config:
                await ctx.send("❌ Cargo atual não encontrado na hierarquia.")
                return
            
            # Busca próximo cargo
            next_config = await self.repository.get_config_by_level(
                ctx.guild.id, current_config.level_order + 1
            )
            if not next_config:
                await ctx.send("❌ Não há cargo superior disponível.")
                return
            
            # Usa motor de promoção
            temp_cog = HierarchyPromotionCog(self.bot, self.db)
            result = await temp_cog._promote_user(
                ctx.guild,
                member.id,
                user_status.current_role_id,
                next_config,
                f"Promoção manual por {ctx.author}: {motivo}",
                str(ctx.author.id)
            )
            
            if "error" in result:
                await ctx.send(f"❌ Erro ao promover: {result['error']}")
                return
            
            # Ignora promoção automática por 7 dias
            from datetime import datetime, timedelta
            ignore_until = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            await self.repository.update_user_status(
                ctx.guild.id,
                member.id,
                ignore_auto_promote_until=ignore_until
            )
            
            next_role = ctx.guild.get_role(next_config.role_id)
            await ctx.send(
                f"✅ {member.mention} foi promovido para {next_role.mention if next_role else 'cargo desconhecido'}!"
            )
            
        except Exception as e:
            LOGGER.error("Erro ao promover membro: %s", e, exc_info=True)
            await ctx.send("❌ Erro ao promover membro. Tente novamente.")
    
    @commands.command(name="rebaixar", aliases=["demote"])
    @command_guard("rebaixar")
    async def demote_command(
        self,
        ctx: commands.Context,
        member: Optional[discord.Member] = None,
        *,
        motivo: str = "Rebaixamento manual"
    ):
        """
        Rebaixa um membro manualmente na hierarquia.
        
        Uso: !rebaixar @membro [motivo]
        Exemplo: !rebaixar @usuario Rebaixamento por inatividade
        """
        if not member:
            await ctx.send("❌ Mencione o membro a ser rebaixado.\nUso: `!rebaixar @membro [motivo]`")
            return
        
        if member.bot:
            await ctx.send("❌ Não é possível rebaixar bots.")
            return
        
        try:
            # Busca status atual
            user_status = await self.repository.get_user_status(ctx.guild.id, member.id)
            if not user_status or not user_status.current_role_id:
                await ctx.send(f"❌ {member.mention} não possui cargo de hierarquia configurado.")
                return
            
            # Busca configuração do cargo atual
            current_config = await self.repository.get_config(
                ctx.guild.id, user_status.current_role_id
            )
            if not current_config:
                await ctx.send("❌ Cargo atual não encontrado na hierarquia.")
                return
            
            # Busca cargo anterior (inferior)
            prev_config = await self.repository.get_config_by_level(
                ctx.guild.id, current_config.level_order - 1
            )
            if not prev_config:
                await ctx.send("❌ Não há cargo inferior disponível.")
                return
            
            # Remove cargo atual e adiciona cargo anterior
            current_role = ctx.guild.get_role(current_config.role_id)
            prev_role = ctx.guild.get_role(prev_config.role_id)
            
            if not current_role or not prev_role:
                await ctx.send("❌ Cargos não encontrados no servidor.")
                return
            
            # Verifica hierarquia do bot
            can_manage, error_msg = check_bot_hierarchy(ctx.guild, prev_role)
            if not can_manage:
                await ctx.send(f"❌ {error_msg}")
                return
            
            # Remove cargo atual e adiciona anterior
            await member.remove_roles(
                current_role,
                reason=f"Rebaixamento manual por {ctx.author}: {motivo}"
            )
            await member.add_roles(
                prev_role,
                reason=f"Rebaixamento manual por {ctx.author}: {motivo}"
            )
            
            # Atualiza status no banco
            from datetime import datetime, timedelta
            now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            ignore_until = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            
            await self.repository.update_user_status(
                ctx.guild.id,
                member.id,
                current_role_id=prev_config.role_id,
                ignore_auto_promote_until=ignore_until,
                ignore_auto_demote_until=ignore_until
            )
            
            # Adiciona ao histórico
            await self.repository.add_history(
                ctx.guild.id,
                member.id,
                "manual_demotion",
                prev_config.role_id,
                from_role_id=current_config.role_id,
                reason=f"Rebaixamento manual por {ctx.author}: {motivo}",
                performed_by=ctx.author.id
            )
            
            await ctx.send(
                f"✅ {member.mention} foi rebaixado para {prev_role.mention}!"
            )
            
        except Exception as e:
            LOGGER.error("Erro ao rebaixar membro: %s", e, exc_info=True)
            await ctx.send("❌ Erro ao rebaixar membro. Tente novamente.")
    
    @commands.command(name="hierarquia", aliases=["hierarchy", "ranks"])
    @command_guard("hierarquia")
    async def hierarchy_command(self, ctx: commands.Context):
        """
        Lista todos os cargos da hierarquia configurados.
        
        Uso: !hierarquia
        """
        try:
            configs = await self.repository.get_all_configs(ctx.guild.id, order_by='level_order')
            
            if not configs:
                await ctx.send("❌ Nenhum cargo de hierarquia configurado. Use `!setup` para configurar.")
                return
            
            embed = discord.Embed(
                title="🎖️ Hierarquia do Servidor",
                description="Lista de cargos configurados na hierarquia:",
                color=discord.Color.blue()
            )
            
            hierarchy_text = []
            for config in configs:
                role = ctx.guild.get_role(config.role_id)
                if role:
                    role_mention = role.mention
                else:
                    role_mention = f"`{config.role_name}` (não encontrado)"
                
                # Conta membros com o cargo
                if role:
                    member_count = len([m for m in role.members if not m.bot])
                else:
                    member_count = 0
                
                vacancy_text = ""
                if config.max_vacancies > 0:
                    vacancy_text = f" ({member_count}/{config.max_vacancies} vagas)"
                else:
                    vacancy_text = f" ({member_count} membros)"
                
                hierarchy_text.append(
                    f"**Nível {config.level_order}:** {role_mention}{vacancy_text}"
                )
            
            embed.add_field(
                name="📋 Cargos",
                value="\n".join(hierarchy_text) if hierarchy_text else "Nenhum cargo",
                inline=False
            )
            
            embed.set_footer(text="Use !setup para configurar a hierarquia")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            LOGGER.error("Erro ao listar hierarquia: %s", e, exc_info=True)
            await ctx.send("❌ Erro ao listar hierarquia. Tente novamente.")


async def setup(bot: commands.Bot):
    """Função de setup para carregar o cog."""
    db = bot.db
    await bot.add_cog(HierarchyCommandsCog(bot, db))
