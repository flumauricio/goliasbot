"""View para gerenciar cargos individuais da hierarquia."""

import logging
from typing import Optional

import discord
from discord.ext import commands

from db import Database
from .repository import HierarchyRepository
from .cache import HierarchyCache
from .models import HierarchyConfig
from ..ui_commons import BackButton, build_standard_config_embed

LOGGER = logging.getLogger(__name__)


class ManageRolesView(discord.ui.View):
    """View para gerenciar cargos individuais da hierarquia."""
    
    def __init__(
        self,
        bot: commands.Bot,
        db: Database,
        guild: discord.Guild,
        parent_view=None
    ):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = db
        self.guild = guild
        self.parent_view = parent_view
        
        cache = HierarchyCache()
        self.repository = HierarchyRepository(db, cache)
        
        # Select customizado para escolher cargo (será populado dinamicamente)
        self.role_select = discord.ui.Select(
            placeholder="Selecione o cargo para gerenciar...",
            min_values=0,
            max_values=1,
            row=0
        )
        self.role_select.callback = self.on_role_select
        self.add_item(self.role_select)
        
        # Botão Voltar
        if self.parent_view:
            self.add_item(BackButton(self.parent_view, row=4))
    
    async def _update_role_select(self):
        """Atualiza as opções do select com apenas os cargos da hierarquia."""
        configs = await self.repository.get_all_configs(self.guild.id, order_by='level_order')
        
        if not configs:
            self.role_select.options = [
                discord.SelectOption(
                    label="Nenhum cargo configurado",
                    value="none",
                    description="Configure cargos primeiro",
                    emoji="⚠️"
                )
            ]
            self.role_select.disabled = True
            return
        
        # Limpa opções anteriores
        self.role_select.options = []
        
        # Adiciona apenas cargos da hierarquia
        for config in configs:
            role = self.guild.get_role(config.role_id)
            if role:
                self.role_select.options.append(
                    discord.SelectOption(
                        label=f"Nível {config.level_order}: {role.name}",
                        value=str(config.role_id),
                        description=f"Gerenciar {role.name}",
                        emoji="🎖️"
                    )
                )
        
        # Limita a 25 opções (limite do Discord)
        if len(self.role_select.options) > 25:
            self.role_select.options = self.role_select.options[:25]
            self.role_select.options.append(
                discord.SelectOption(
                    label="... (mais cargos disponíveis)",
                    value="more",
                    description="Use o comando !hierarquia para ver todos",
                    emoji="📋"
                )
            )
        
        self.role_select.disabled = False
    
    async def on_role_select(self, interaction: discord.Interaction):
        """Callback quando um cargo é selecionado."""
        await interaction.response.defer(ephemeral=True)
        
        selected_values = interaction.data.get("values", [])
        if not selected_values:
            await interaction.followup.send("❌ Nenhum cargo selecionado.", ephemeral=True)
            return
        
        role_id_str = selected_values[0]
        
        # Verifica se é uma opção especial
        if role_id_str == "none" or role_id_str == "more":
            await interaction.followup.send(
                "⚠️ Selecione um cargo válido da hierarquia.",
                ephemeral=True
            )
            return
        
        role_id = int(role_id_str)
        role = self.guild.get_role(role_id)
        
        if not role:
            await interaction.followup.send("❌ Cargo não encontrado.", ephemeral=True)
            return
        
        # Busca configuração
        config = await self.repository.get_config(self.guild.id, role_id)
        if not config:
            await interaction.followup.send(
                f"❌ Cargo {role.mention} não está configurado na hierarquia.",
                ephemeral=True
            )
            return
        
        # Abre view de detalhes/edição
        detail_view = RoleDetailView(self.bot, self.db, self.guild, config, parent_view=self)
        embed = await detail_view.build_embed()
        await interaction.followup.send(embed=embed, view=detail_view, ephemeral=True)
    
    async def build_embed(self) -> discord.Embed:
        """Constrói embed com lista de cargos."""
        # Atualiza o select com cargos da hierarquia
        await self._update_role_select()
        
        configs = await self.repository.get_all_configs(self.guild.id, order_by='level_order')
        
        if not configs:
            embed = discord.Embed(
                title="⚙️ Gerenciar Cargos da Hierarquia",
                description="Nenhum cargo de hierarquia configurado.\n\nUse os botões de criação primeiro.",
                color=discord.Color.orange()
            )
            return embed
        
        # Lista cargos
        roles_list = []
        for config in configs:
            role = self.guild.get_role(config.role_id)
            if role:
                roles_list.append(
                    f"**Nível {config.level_order}:** {role.mention}\n"
                    f"• Nome: `{config.role_name}`\n"
                    f"• Vagas: {config.max_vacancies if config.max_vacancies > 0 else 'Ilimitadas'}\n"
                    f"• Auto-promover: {'✅' if config.auto_promote else '❌'}\n"
                    f"• Requer aprovação: {'✅' if config.requires_approval else '❌'}\n"
                    f"• Cargo Admin: {'✅' if config.is_admin_rank else '❌'}"
                )
            else:
                roles_list.append(
                    f"**Nível {config.level_order}:** `{config.role_name}` (cargo não encontrado)"
                )
        
        embed = await build_standard_config_embed(
            title="⚙️ Gerenciar Cargos da Hierarquia",
            description="Selecione um cargo acima para ver detalhes e editar configurações.",
            current_config={
                "Total de Cargos": f"{len(configs)} cargo(s)"
            },
            guild=self.guild,
            footer_text="Selecione um cargo para gerenciar"
        )
        
        embed.add_field(
            name="📋 Cargos Configurados",
            value="\n\n".join(roles_list) if roles_list else "Nenhum cargo",
            inline=False
        )
        
        return embed


class RoleDetailView(discord.ui.View):
    """View de detalhes e edição de um cargo específico."""
    
    def __init__(
        self,
        bot: commands.Bot,
        db: Database,
        guild: discord.Guild,
        config: HierarchyConfig,
        parent_view=None
    ):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = db
        self.guild = guild
        self.config = config
        self.parent_view = parent_view
        
        cache = HierarchyCache()
        self.repository = HierarchyRepository(db, cache)
        
        # Botão Voltar
        if self.parent_view:
            self.add_item(BackButton(self.parent_view, row=4))
        
        # Botão Editar
        self.edit_btn = discord.ui.Button(
            label="✏️ Editar",
            style=discord.ButtonStyle.primary,
            row=1
        )
        self.edit_btn.callback = self.edit_role
        self.add_item(self.edit_btn)
        
        # Botão Remover da Hierarquia
        self.remove_btn = discord.ui.Button(
            label="🗑️ Remover da Hierarquia",
            style=discord.ButtonStyle.danger,
            row=1
        )
        self.remove_btn.callback = self.remove_role
        self.add_item(self.remove_btn)
    
    async def build_embed(self) -> discord.Embed:
        """Constrói embed com detalhes do cargo."""
        role = self.guild.get_role(self.config.role_id)
        
        if not role:
            embed = discord.Embed(
                title="❌ Cargo Não Encontrado",
                description=f"O cargo `{self.config.role_name}` não existe mais no servidor.",
                color=discord.Color.red()
            )
            return embed
        
        # Conta membros
        member_count = len([m for m in role.members if not m.bot])
        
        # Requisitos
        reqs = []
        if self.config.req_messages > 0:
            reqs.append(f"💬 {self.config.req_messages:,} mensagens")
        if self.config.req_call_time > 0:
            reqs.append(f"📞 {self.config.req_call_time // 3600}h em call")
        if self.config.req_reactions > 0:
            reqs.append(f"⭐ {self.config.req_reactions:,} reações")
        if self.config.req_min_days > 0:
            reqs.append(f"📅 {self.config.req_min_days} dias")
        
        req_text = "\n".join(reqs) if reqs else "Nenhum requisito configurado"
        
        embed = discord.Embed(
            title=f"⚙️ Detalhes: {role.name}",
            description=f"Cargo de hierarquia - Nível {self.config.level_order}",
            color=role.color if role.color.value != 0 else discord.Color.blue()
        )
        
        embed.add_field(
            name="📊 Informações Básicas",
            value=(
                f"**Cargo:** {role.mention}\n"
                f"**Nível:** {self.config.level_order}\n"
                f"**Membros:** {member_count}\n"
                f"**Vagas:** {self.config.max_vacancies if self.config.max_vacancies > 0 else 'Ilimitadas'}\n"
                f"**Cargo Admin:** {'✅ Sim' if self.config.is_admin_rank else '❌ Não'}\n"
                f"**Requer Aprovação:** {'✅ Sim' if self.config.requires_approval else '❌ Não'}"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚙️ Configurações",
            value=(
                f"**Auto-promover:** {'✅ Sim' if self.config.auto_promote else '❌ Não'}\n"
                f"**Requer aprovação:** {'✅ Sim' if self.config.requires_approval else '❌ Não'}\n"
                f"**Cargo admin:** {'✅ Sim' if self.config.is_admin_rank else '❌ Não'}\n"
                f"**Expira em:** {self.config.expiry_days} dias" if self.config.expiry_days > 0 else "**Expira em:** Nunca"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📋 Requisitos",
            value=req_text,
            inline=False
        )
        
        embed.set_footer(text="Use os botões abaixo para editar ou remover")
        
        return embed
    
    async def update_embed(self):
        """Atualiza a embed do ManageRolesView se a mensagem estiver disponível."""
        try:
            # Atualiza o select com cargos da hierarquia
            await self._update_role_select()
            
            # Reconstrói a embed
            embed = await self.build_embed()
            
            # Tenta atualizar a mensagem se estiver disponível
            if self._message:
                try:
                    await self._message.edit(embed=embed, view=self)
                except discord.NotFound:
                    self._message = None  # Mensagem foi deletada
                except Exception as e:
                    LOGGER.warning("Erro ao atualizar mensagem do ManageRolesView: %s", e)
        except Exception as e:
            LOGGER.warning("Erro ao atualizar embed do ManageRolesView: %s", e)
    
    async def edit_role(self, interaction: discord.Interaction):
        """Abre modal para editar cargo."""
        from .edit_role_modal import EditRoleModal
        
        modal = EditRoleModal(self.config, self.repository, self.guild, self)
        await interaction.response.send_modal(modal)
    
    async def remove_role(self, interaction: discord.Interaction):
        """Remove cargo da hierarquia (não deleta o cargo do Discord)."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Remove do banco
            await self.repository.delete_config(self.guild.id, self.config.role_id)
            
            # Invalida cache
            self.repository.cache.invalidate_config(self.guild.id, self.config.role_id)
            
            role = self.guild.get_role(self.config.role_id)
            role_mention = role.mention if role else f"`{self.config.role_name}`"
            
            await interaction.followup.send(
                f"✅ Cargo {role_mention} removido da hierarquia.\n"
                f"⚠️ O cargo ainda existe no Discord, mas não será mais gerenciado pelo sistema.",
                ephemeral=True
            )
            
            # Atualiza view pai (se a mensagem ainda existir)
            if self.parent_view:
                try:
                    embed = await self.parent_view.build_embed()
                    if interaction.message:
                        await interaction.message.edit(embed=embed, view=self.parent_view)
                except discord.NotFound:
                    # Mensagem foi deletada, não há o que atualizar
                    pass
                except Exception as e:
                    LOGGER.warning("Erro ao atualizar mensagem pai após remover cargo: %s", e)
                
        except Exception as e:
            LOGGER.error("Erro ao remover cargo da hierarquia: %s", e, exc_info=True)
            await interaction.followup.send(
                "❌ Erro ao remover cargo. Tente novamente.",
                ephemeral=True
            )
