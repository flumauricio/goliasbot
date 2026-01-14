"""Modal para editar configurações de um cargo de hierarquia."""

import logging
from typing import Optional

import discord
from discord.ext import commands

from .repository import HierarchyRepository
from .models import HierarchyConfig
from .utils import apply_admin_permissions, position_role_hierarchically

LOGGER = logging.getLogger(__name__)


class EditRoleModal(discord.ui.Modal, title="Editar Cargo de Hierarquia"):
    """Modal para editar configurações de um cargo."""
    
    level_input = discord.ui.TextInput(
        label="Nível",
        placeholder="Ex: 1",
        required=True,
        max_length=3
    )
    
    max_vacancies_input = discord.ui.TextInput(
        label="Vagas Máximas (0 = ilimitadas)",
        placeholder="Ex: 10",
        required=False,
        max_length=5
    )
    
    auto_promote_input = discord.ui.TextInput(
        label="Auto-promover? (sim/não)",
        placeholder="sim",
        required=False,
        max_length=3
    )
    
    expiry_days_input = discord.ui.TextInput(
        label="Expira em (dias, 0 = nunca)",
        placeholder="Ex: 30",
        required=False,
        max_length=5
    )
    
    # Combina requires_approval e is_admin_rank em um único campo
    # Formato: "aprovação:sim admin:não" ou apenas "aprovação:sim"
    approval_and_admin_input = discord.ui.TextInput(
        label="Aprovação e Admin",
        placeholder="Formato: aprovação:sim admin:não",
        required=False,
        max_length=50
    )
    
    def __init__(
        self,
        config: HierarchyConfig,
        repository: HierarchyRepository,
        guild: discord.Guild,
        parent_view
    ):
        super().__init__()
        self.config = config
        self.repository = repository
        self.guild = guild
        self.parent_view = parent_view
        
        # Preenche valores atuais
        self.level_input.default = str(config.level_order)
        self.max_vacancies_input.default = str(config.max_vacancies) if config.max_vacancies > 0 else "0"
        self.auto_promote_input.default = "sim" if config.auto_promote else "não"
        self.expiry_days_input.default = str(config.expiry_days) if config.expiry_days > 0 else "0"
        # Formato: "aprovação:sim admin:não"
        approval_str = "sim" if config.requires_approval else "não"
        admin_str = "sim" if config.is_admin_rank else "não"
        self.approval_and_admin_input.default = f"aprovação:{approval_str} admin:{admin_str}"
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Parse valores
            level = int(self.level_input.value.strip())
            if level < 1:
                await interaction.followup.send("❌ Nível deve ser pelo menos 1.", ephemeral=True)
                return
            
            max_vacancies = int(self.max_vacancies_input.value.strip()) if self.max_vacancies_input.value and self.max_vacancies_input.value.strip().isdigit() else 0
            if max_vacancies < 0:
                max_vacancies = 0
            
            auto_promote = self.auto_promote_input.value.lower().strip() in ["sim", "s", "yes", "y"] if self.auto_promote_input.value else self.config.auto_promote
            
            # Parse approval_and_admin_input
            requires_approval = self.config.requires_approval
            is_admin_rank = self.config.is_admin_rank
            
            if self.approval_and_admin_input.value and self.approval_and_admin_input.value.strip():
                approval_admin_str = self.approval_and_admin_input.value.lower().strip()
                # Procura por "aprovação:sim" ou "aprovação:não"
                if "aprovação:" in approval_admin_str:
                    approval_part = approval_admin_str.split("aprovação:")[1].split()[0] if "aprovação:" in approval_admin_str else None
                    if approval_part:
                        requires_approval = approval_part in ["sim", "s", "yes", "y"]
                # Procura por "admin:sim" ou "admin:não"
                if "admin:" in approval_admin_str:
                    admin_part = approval_admin_str.split("admin:")[1].split()[0] if "admin:" in approval_admin_str else None
                    if admin_part:
                        is_admin_rank = admin_part in ["sim", "s", "yes", "y"]
            
            expiry_days = int(self.expiry_days_input.value.strip()) if self.expiry_days_input.value and self.expiry_days_input.value.strip().isdigit() else 0
            if expiry_days < 0:
                expiry_days = 0
            
            # Atualiza configuração
            updated_config = HierarchyConfig(
                guild_id=self.config.guild_id,
                role_id=self.config.role_id,
                role_name=self.config.role_name,
                level_order=level,
                role_color=self.config.role_color,
                max_vacancies=max_vacancies,
                is_admin_rank=is_admin_rank,
                auto_promote=auto_promote,
                requires_approval=requires_approval,
                expiry_days=expiry_days,
                req_messages=self.config.req_messages,
                req_call_time=self.config.req_call_time,
                req_reactions=self.config.req_reactions,
                req_min_days=self.config.req_min_days,
                req_min_any=self.config.req_min_any,
                auto_demote_on_lose_req=self.config.auto_demote_on_lose_req,
                auto_demote_inactive_days=self.config.auto_demote_inactive_days,
                vacancy_priority=self.config.vacancy_priority,
                check_frequency_hours=self.config.check_frequency_hours
            )
            
            await self.repository.upsert_config(updated_config)
            
            # Invalida cache
            self.repository.cache.invalidate_config(self.guild.id, self.config.role_id)
            
            # Obtém o cargo do Discord
            role = self.guild.get_role(self.config.role_id)
            if role:
                # Se is_admin_rank mudou, aplica/remove permissões de admin
                if is_admin_rank != self.config.is_admin_rank:
                    if is_admin_rank:
                        await apply_admin_permissions(self.guild, role)
                    else:
                        # Remove permissões de admin (volta para permissões padrão)
                        try:
                            await role.edit(permissions=discord.Permissions())
                        except Exception as e:
                            LOGGER.warning("Erro ao remover permissões de admin: %s", e)
                
                # Reposiciona cargo hierarquicamente se o nível mudou
                if level != self.config.level_order:
                    all_configs = await self.repository.get_all_configs(self.guild.id, order_by='level_order')
                    await position_role_hierarchically(self.guild, role, level, all_configs)
            
            # Atualiza view de detalhes (RoleDetailView)
            try:
                # Atualiza a configuração no objeto para refletir as mudanças
                self.parent_view.config = updated_config
                embed = await self.parent_view.build_embed()
                if interaction.message:
                    await interaction.message.edit(embed=embed, view=self.parent_view)
            except discord.NotFound:
                pass  # Mensagem foi deletada
            except Exception as e:
                LOGGER.warning("Erro ao atualizar mensagem de detalhes após editar cargo: %s", e)
            
            # Atualiza a view principal (ManageRolesView) se existir
            if self.parent_view and hasattr(self.parent_view, 'parent_view') and self.parent_view.parent_view:
                try:
                    manage_view = self.parent_view.parent_view
                    if hasattr(manage_view, 'update_embed'):
                        await manage_view.update_embed()
                    # Invalida cache para garantir que dados atualizados sejam buscados
                    self.repository.cache.invalidate_config(self.guild.id)
                except Exception as e:
                    LOGGER.warning("Erro ao atualizar view principal após editar cargo: %s", e)
            
            role = self.guild.get_role(self.config.role_id)
            await interaction.followup.send(
                f"✅ Configurações de {role.mention if role else 'cargo'} atualizadas!",
                ephemeral=True
            )
            
        except ValueError as e:
            await interaction.followup.send(
                f"❌ Valor inválido: {e}",
                ephemeral=True
            )
        except Exception as e:
            LOGGER.error("Erro ao editar cargo: %s", e, exc_info=True)
            await interaction.followup.send(
                "❌ Erro ao editar cargo. Tente novamente.",
                ephemeral=True
            )
