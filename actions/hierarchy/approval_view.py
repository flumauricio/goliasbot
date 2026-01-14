"""View de aprovação de promoções de hierarquia."""

import logging
from datetime import datetime, timedelta
from typing import Optional

import discord
from discord.ext import commands

from db import Database
from .repository import HierarchyRepository
from .cache import HierarchyCache
from .promotion_engine import HierarchyPromotionCog
from .models import PromotionRequest

LOGGER = logging.getLogger(__name__)


class PromotionApprovalView(discord.ui.View):
    """View para aprovar/rejeitar pedidos de promoção."""
    
    def __init__(
        self,
        bot: commands.Bot,
        db: Database,
        request: PromotionRequest,
        detailed_reason: str
    ):
        super().__init__(timeout=None)  # Persistente
        self.bot = bot
        self.db = db
        self.request = request
        self.detailed_reason = detailed_reason
        
        cache = HierarchyCache()
        self.repository = HierarchyRepository(db, cache)
        
        # Define custom_id único para cada botão (permite processar cliques mesmo após reinício)
        if self.request.id:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    if item.label == "✅ Aprovar":
                        item.custom_id = f"hierarchy:approve:{self.request.id}"
                    elif item.label == "❌ Rejeitar":
                        item.custom_id = f"hierarchy:reject:{self.request.id}"
    
    async def _check_mod_permissions(self, member: discord.Member, guild: discord.Guild) -> bool:
        """Verifica se membro tem permissão para aprovar promoções."""
        # Admin sempre tem permissão
        if member.guild_permissions.administrator:
            return True
        
        # Busca cargo de moderador configurado (será adicionado ao settings)
        settings = await self.db.get_settings(guild.id)
        mod_role_id = settings.get("hierarchy_mod_role_id")
        
        if mod_role_id:
            mod_role = guild.get_role(int(mod_role_id))
            if mod_role and mod_role in member.roles:
                return True
        
        return False
    
    @discord.ui.button(
        label="✅ Aprovar",
        style=discord.ButtonStyle.success,
        custom_id=None  # Será definido dinamicamente
    )
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Aprova pedido de promoção."""
        await interaction.response.defer(ephemeral=True)
        
        # Verifica permissões
        if not await self._check_mod_permissions(interaction.user, interaction.guild):
            await interaction.followup.send(
                "❌ Você não tem permissão para aprovar promoções.",
                ephemeral=True
            )
            return
        
        # Verifica se pedido ainda está pendente
        if self.request.status != 'pending':
            await interaction.followup.send(
                f"❌ Este pedido já foi {self.request.status}.",
                ephemeral=True
            )
            return
        
        try:
            guild = interaction.guild
            member = guild.get_member(self.request.user_id)
            if not member:
                await interaction.followup.send(
                    "❌ Membro não encontrado no servidor.",
                    ephemeral=True
                )
                return
            
            # Busca configuração do cargo alvo
            target_config = await self.repository.get_config(
                guild.id, self.request.target_role_id
            )
            if not target_config:
                await interaction.followup.send(
                    "❌ Cargo alvo não encontrado na hierarquia.",
                    ephemeral=True
                )
                return
            
            # Usa motor de promoção para promover
            temp_cog = HierarchyPromotionCog(self.bot, self.db)
            result = await temp_cog._promote_user(
                guild,
                self.request.user_id,
                int(self.request.current_role_id) if self.request.current_role_id else None,
                target_config,
                f"Promoção aprovada por {interaction.user}: {self.detailed_reason}",
                str(interaction.user.id)
            )
            
            if "error" in result:
                await interaction.followup.send(
                    f"❌ Erro ao promover: {result['error']}",
                    ephemeral=True
                )
                return
            
            # Resolve pedido no banco
            await self.repository.resolve_request(
                self.request.id,
                'approved',
                interaction.user.id
            )
            
            # Atualiza embed para mostrar como aprovado
            embed = interaction.message.embeds[0] if interaction.message.embeds else None
            if embed:
                embed.color = discord.Color.green()
                embed.add_field(
                    name="✅ Status",
                    value=f"Aprovado por {interaction.user.mention}",
                    inline=False
                )
                
                # Remove botões
                view = discord.ui.View()
                await interaction.message.edit(embed=embed, view=view)
            
            await interaction.followup.send(
                f"✅ Promoção aprovada! {member.mention} foi promovido.",
                ephemeral=True
            )
            
        except Exception as e:
            LOGGER.error("Erro ao aprovar promoção: %s", e, exc_info=True)
            await interaction.followup.send(
                "❌ Erro ao aprovar promoção. Tente novamente.",
                ephemeral=True
            )
    
    @discord.ui.button(
        label="❌ Rejeitar",
        style=discord.ButtonStyle.danger,
        custom_id=None  # Será definido dinamicamente
    )
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Rejeita pedido de promoção."""
        await interaction.response.defer(ephemeral=True)
        
        # Verifica permissões
        if not await self._check_mod_permissions(interaction.user, interaction.guild):
            await interaction.followup.send(
                "❌ Você não tem permissão para rejeitar promoções.",
                ephemeral=True
            )
            return
        
        # Verifica se pedido ainda está pendente
        if self.request.status != 'pending':
            await interaction.followup.send(
                f"❌ Este pedido já foi {self.request.status}.",
                ephemeral=True
            )
            return
        
        # Abre modal para motivo da rejeição
        modal = RejectReasonModal(self, interaction.user)
        await interaction.followup.send(
            "Digite o motivo da rejeição no modal que foi aberto.",
            ephemeral=True
        )
        await interaction.followup.send_modal(modal)
    
    async def reject_with_reason(self, interaction: discord.Interaction, reason: str):
        """Rejeita pedido com motivo."""
        try:
            # Resolve pedido no banco
            await self.repository.resolve_request(
                self.request.id,
                'rejected',
                interaction.user.id
            )
            
            # Atualiza embed para mostrar como rejeitado
            embed = interaction.message.embeds[0] if interaction.message.embeds else None
            if embed:
                embed.color = discord.Color.red()
                embed.add_field(
                    name="❌ Status",
                    value=f"Rejeitado por {interaction.user.mention}\n**Motivo:** {reason}",
                    inline=False
                )
                
                # Remove botões
                view = discord.ui.View()
                await interaction.message.edit(embed=embed, view=view)
            
            # Adiciona ao histórico
            await self.repository.add_history(
                interaction.guild.id,
                self.request.user_id,
                "promotion_rejected",
                self.request.target_role_id,
                from_role_id=int(self.request.current_role_id) if self.request.current_role_id else None,
                reason=f"Rejeitado por {interaction.user}: {reason}",
                performed_by=interaction.user.id
            )
            
            await interaction.response.send_message(
                f"✅ Pedido rejeitado.",
                ephemeral=True
            )
            
        except Exception as e:
            LOGGER.error("Erro ao rejeitar promoção: %s", e, exc_info=True)
            await interaction.response.send_message(
                "❌ Erro ao rejeitar promoção. Tente novamente.",
                ephemeral=True
            )


class RejectReasonModal(discord.ui.Modal, title="Motivo da Rejeição"):
    """Modal para motivo da rejeição."""
    
    motivo = discord.ui.TextInput(
        label="Motivo da Rejeição",
        placeholder="Digite o motivo da rejeição...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True
    )
    
    def __init__(self, approval_view: PromotionApprovalView, moderator: discord.Member):
        super().__init__()
        self.approval_view = approval_view
        self.moderator = moderator
    
    async def on_submit(self, interaction: discord.Interaction):
        await self.approval_view.reject_with_reason(interaction, self.motivo.value)


def build_approval_embed(
    guild: discord.Guild,
    request: PromotionRequest,
    detailed_reason: str
) -> discord.Embed:
    """Constrói embed de pedido de aprovação."""
    member = guild.get_member(request.user_id)
    current_role = guild.get_role(int(request.current_role_id)) if request.current_role_id else None
    target_role = guild.get_role(request.target_role_id)
    
    embed = discord.Embed(
        title="📋 Pedido de Promoção - Aguardando Aprovação",
        description=f"Um membro atende todos os requisitos para promoção.",
        color=discord.Color.orange(),
        timestamp=discord.utils.utcnow()
    )
    
    if member:
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(
            name="👤 Usuário",
            value=f"{member.mention} (`{member.id}`)",
            inline=False
        )
    else:
        embed.add_field(
            name="👤 Usuário",
            value=f"`{request.user_id}` (não encontrado)",
            inline=False
        )
    
    if current_role:
        embed.add_field(
            name="📈 De → Para",
            value=f"{current_role.mention} → {target_role.mention if target_role else 'Cargo não encontrado'}",
            inline=False
        )
    else:
        embed.add_field(
            name="📈 Para",
            value=target_role.mention if target_role else "Cargo não encontrado",
            inline=False
        )
    
    embed.add_field(
        name="📋 Razão Detalhada",
        value=detailed_reason[:1024] if len(detailed_reason) <= 1024 else detailed_reason[:1021] + "...",
        inline=False
    )
    
    embed.set_footer(text="Use os botões abaixo para aprovar ou rejeitar")
    
    return embed
