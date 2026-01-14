"""Views de configuração do sistema de hierarquia."""

import asyncio
import logging
from typing import Optional, Dict, Any, List

import discord
from discord.ext import commands

from db import Database
from .repository import HierarchyRepository
from .rate_limiter import HierarchyRateLimiter
from .utils import (
    generate_color_gradient, 
    check_bot_hierarchy,
    apply_admin_permissions,
    position_role_hierarchically
)
from .models import HierarchyConfig
from ..ui_commons import (
    BackButton, CreateRoleModal, build_standard_config_embed,
    check_bot_permissions
)

LOGGER = logging.getLogger(__name__)


class AddExistingRoleLevelModal(discord.ui.Modal, title="Adicionar Cargo à Hierarquia"):
    """Modal para perguntar o nível ao adicionar cargo existente."""
    
    def __init__(
        self,
        role: discord.Role,
        repository: HierarchyRepository,
        setup_view
    ):
        super().__init__()
        self.role = role
        self.repository = repository
        self.setup_view = setup_view
        
        # Busca próximo nível disponível para sugerir
        # (será atualizado no on_submit se necessário)
        self.suggested_level = 1
    
    level_input = discord.ui.TextInput(
        label="Nível",
        placeholder="Ex: 1 (deixe vazio para usar próximo nível)",
        required=False,
        max_length=3
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Parse nível
            if self.level_input.value and self.level_input.value.strip():
                try:
                    level = int(self.level_input.value.strip())
                    if level < 1:
                        await interaction.followup.send("❌ Nível deve ser pelo menos 1.", ephemeral=True)
                        return
                except ValueError:
                    await interaction.followup.send("❌ Nível deve ser um número válido.", ephemeral=True)
                    return
            else:
                # Busca próximo nível disponível
                existing_configs = await self.repository.get_all_configs(self.role.guild.id, order_by='level_order')
                level = max(c.level_order for c in existing_configs) + 1 if existing_configs else 1
            
            # Reorganiza níveis se necessário (desloca cargos existentes)
            await self.setup_view._reorganize_levels(self.role.guild.id, level, self.role.id)
            
            # Busca todos os configs para posicionamento hierárquico
            all_configs = await self.repository.get_all_configs(self.role.guild.id, order_by='level_order')
            
            # Posiciona cargo hierarquicamente
            await position_role_hierarchically(self.role.guild, self.role, level, all_configs)
            
            # Cria configuração
            config = HierarchyConfig(
                guild_id=self.role.guild.id,
                role_id=self.role.id,
                role_name=self.role.name,
                level_order=level,
                role_color=f"#{self.role.color.value:06x}" if self.role.color.value != 0 else "#000000"
            )
            await self.repository.upsert_config(config)
            
            # Se for cargo admin, aplica permissões
            if config.is_admin_rank:
                await apply_admin_permissions(self.role.guild, self.role)
            
            # Invalida cache
            self.repository.cache.invalidate_config(self.role.guild.id)
            
            # Atualiza embed (se a mensagem ainda existir)
            try:
                embed = await self.setup_view.build_embed()
                if interaction.message:
                    await interaction.message.edit(embed=embed, view=self.setup_view)
            except discord.NotFound:
                pass  # Mensagem foi deletada
            except Exception as e:
                LOGGER.warning("Erro ao atualizar mensagem após adicionar cargo existente: %s", e)
            
            await interaction.followup.send(
                f"✅ Cargo {self.role.mention} adicionado à hierarquia (Nível {level})!",
                ephemeral=True
            )
            
        except Exception as e:
            LOGGER.error("Erro ao adicionar cargo existente: %s", e, exc_info=True)
            await interaction.followup.send(
                "❌ Erro ao adicionar cargo. Tente novamente.",
                ephemeral=True
            )


class CreateSingleRoleModal(discord.ui.Modal, title="Criar Cargo Individual"):
    """Modal para criar um único cargo de hierarquia."""
    
    def __init__(
        self,
        guild: discord.Guild,
        repository: HierarchyRepository,
        rate_limiter: HierarchyRateLimiter,
        setup_view
    ):
        super().__init__()
        self.guild = guild
        self.repository = repository
        self.rate_limiter = rate_limiter
        self.setup_view = setup_view
    
    role_name_input = discord.ui.TextInput(
        label="Nome do Cargo",
        placeholder="Ex: Soldado",
        required=True,
        max_length=100
    )
    
    level_input = discord.ui.TextInput(
        label="Nível (opcional)",
        placeholder="Deixe vazio para usar próximo nível",
        required=False,
        max_length=3
    )
    
    color_input = discord.ui.TextInput(
        label="Cor (Hex, opcional)",
        placeholder="#0000FF",
        required=False,
        max_length=7
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Cria um único cargo de hierarquia."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            role_name = self.role_name_input.value.strip()
            if not role_name:
                await interaction.followup.send("❌ O nome do cargo não pode estar vazio.", ephemeral=True)
                return
            
            # Verifica se já existe
            existing_role = discord.utils.get(self.guild.roles, name=role_name)
            if existing_role:
                await interaction.followup.send(
                    f"⚠️ Cargo '{role_name}' já existe: {existing_role.mention}\n"
                    f"Use o seletor de cargos existentes para adicioná-lo à hierarquia.",
                    ephemeral=True
                )
                return
            
            # Nível (opcional)
            if self.level_input.value and self.level_input.value.strip():
                try:
                    level = int(self.level_input.value.strip())
                    if level < 1:
                        await interaction.followup.send("❌ Nível deve ser pelo menos 1.", ephemeral=True)
                        return
                except ValueError:
                    await interaction.followup.send("❌ Nível deve ser um número válido.", ephemeral=True)
                    return
            else:
                # Busca próximo nível disponível
                existing_configs = await self.repository.get_all_configs(self.guild.id, order_by='level_order')
                level = max(c.level_order for c in existing_configs) + 1 if existing_configs else 1
            
            # Cor (opcional)
            color_value = None
            if self.color_input.value and self.color_input.value.strip():
                color_str = self.color_input.value.strip()
                if not color_str.startswith('#'):
                    color_str = '#' + color_str
                try:
                    color_value = discord.Color.from_str(color_str)
                except ValueError:
                    await interaction.followup.send("❌ Cor inválida. Use formato hex (ex: #0000FF).", ephemeral=True)
                    return
            
            # Verifica rate limit
            can_create, count_48h, remaining = await self.rate_limiter.can_create_role(self.guild.id)
            if not can_create:
                await interaction.followup.send(
                    f"❌ **Rate Limit Atingido!**\n"
                    f"Você já criou {count_48h} cargos nas últimas 48h.\n"
                    f"Limite do Discord: 250 cargos/48h.",
                    ephemeral=True
                )
                return
            
            # Verifica permissões
            has_perm, missing = await check_bot_permissions(self.guild, ["manage_roles"])
            if not has_perm:
                await interaction.followup.send(
                    f"❌ Bot não tem permissão 'Gerenciar Cargos'. Faltando: {', '.join(missing)}",
                    ephemeral=True
                )
                return
            
            # Cria o cargo
            try:
                role = await self.guild.create_role(
                    name=role_name,
                    color=color_value,
                    mentionable=False
                )
                
                # Verifica hierarquia
                can_manage, error_msg = check_bot_hierarchy(self.guild, role)
                if not can_manage:
                    await role.delete()
                    await interaction.followup.send(f"❌ {error_msg}", ephemeral=True)
                    return
                
                # Registra rate limit
                await self.rate_limiter.track_action(self.guild.id, 'role_create')
                
                # Reorganiza níveis se necessário (desloca cargos existentes)
                await self.setup_view._reorganize_levels(self.guild.id, level, role.id)
                
                # Busca todos os configs para posicionamento hierárquico
                all_configs = await self.repository.get_all_configs(self.guild.id, order_by='level_order')
                
                # Posiciona cargo hierarquicamente
                await position_role_hierarchically(self.guild, role, level, all_configs)
                
                # Salva configuração
                config = HierarchyConfig(
                    guild_id=self.guild.id,
                    role_id=role.id,
                    role_name=role_name,
                    level_order=level,
                    role_color=f"#{role.color.value:06x}" if role.color.value != 0 else "#000000"
                )
                await self.repository.upsert_config(config)
                
                # Se for cargo admin, aplica permissões
                if config.is_admin_rank:
                    await apply_admin_permissions(self.guild, role)
                
                # Atualiza embed (se a mensagem ainda existir)
                try:
                    embed = await self.setup_view.build_embed()
                    if interaction.message:
                        await interaction.message.edit(embed=embed, view=self.setup_view)
                except discord.NotFound:
                    pass  # Mensagem foi deletada
                except Exception as e:
                    LOGGER.warning("Erro ao atualizar mensagem após criar cargo: %s", e)
                
                await interaction.followup.send(
                    f"✅ Cargo {role.mention} criado e adicionado à hierarquia (Nível {level})!",
                    ephemeral=True
                )
                
            except discord.Forbidden:
                await interaction.followup.send("❌ Não foi possível criar o cargo. Verifique as permissões do bot.", ephemeral=True)
            except Exception as e:
                LOGGER.error("Erro ao criar cargo individual: %s", e, exc_info=True)
                await interaction.followup.send("❌ Erro ao criar cargo. Tente novamente.", ephemeral=True)
                
        except Exception as e:
            LOGGER.error("Erro no modal de criação individual: %s", e, exc_info=True)
            await interaction.followup.send("❌ Erro ao processar. Tente novamente.", ephemeral=True)


class CreateBulkRolesModal(discord.ui.Modal, title="Criar Cargos em Massa"):
    """Modal para criar múltiplos cargos de hierarquia de uma vez."""
    
    def __init__(
        self,
        guild: discord.Guild,
        repository: HierarchyRepository,
        rate_limiter: HierarchyRateLimiter,
        setup_view
    ):
        super().__init__()
        self.guild = guild
        self.repository = repository
        self.rate_limiter = rate_limiter
        self.setup_view = setup_view
        
        # Adiciona campos manualmente para garantir controle total
        self.quantity_input = discord.ui.TextInput(
            label="Quantidade de Cargos",
            placeholder="Ex: 10",
            required=True,
            max_length=3
        )
        self.add_item(self.quantity_input)
        
        self.prefix_input = discord.ui.TextInput(
            label="Prefix do Nome",
            placeholder="Ex: Patente",
            required=True,
            max_length=50
        )
        self.add_item(self.prefix_input)
        
        self.start_color_input = discord.ui.TextInput(
            label="Cor Inicial (Hex)",
            placeholder="#0000FF",
            required=True,
            max_length=7
        )
        self.add_item(self.start_color_input)
        
        self.end_color_input = discord.ui.TextInput(
            label="Cor Final (Hex) - Opcional",
            placeholder="#00FFFF (deixe vazio para mesma cor)",
            required=False,
            max_length=7
        )
        self.add_item(self.end_color_input)
        
        self.start_level_input = discord.ui.TextInput(
            label="Nível Inicial (opcional)",
            placeholder="Deixe vazio para usar próximo nível",
            required=False,
            max_length=3
        )
        self.add_item(self.start_level_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Cria cargos em massa com rate limiting inteligente."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Validação de entrada
            try:
                quantity = int(self.quantity_input.value)
            except ValueError:
                await interaction.followup.send(
                    "❌ Quantidade deve ser um número válido.",
                    ephemeral=True
                )
                return
            
            if quantity < 1 or quantity > 50:
                await interaction.followup.send(
                    "❌ Quantidade deve estar entre 1 e 50.",
                    ephemeral=True
                )
                return
            
            # Nível inicial (opcional - usa próximo nível disponível se não informado)
            if self.start_level_input.value and self.start_level_input.value.strip():
                try:
                    start_level = int(self.start_level_input.value.strip())
                    if start_level < 1:
                        await interaction.followup.send(
                            "❌ Nível inicial deve ser pelo menos 1.",
                            ephemeral=True
                        )
                        return
                except ValueError:
                    await interaction.followup.send(
                        "❌ Nível inicial deve ser um número válido.",
                        ephemeral=True
                    )
                    return
            else:
                # Busca próximo nível disponível
                existing_configs = await self.repository.get_all_configs(self.guild.id, order_by='level_order')
                if existing_configs:
                    start_level = max(c.level_order for c in existing_configs) + 1
                else:
                    start_level = 1
            
            # Validação de cores
            start_color = self.start_color_input.value.strip()
            end_color = self.end_color_input.value.strip() if self.end_color_input.value else ""
            
            if not start_color.startswith('#'):
                start_color = '#' + start_color
            if end_color and not end_color.startswith('#'):
                end_color = '#' + end_color
            
            # Se não tiver cor final, usa mesma cor (sem gradiente)
            use_gradient = bool(end_color and end_color != start_color)
            if not end_color:
                end_color = start_color
            
            # Verifica rate limit ANTES de começar
            can_create, count_48h, remaining = await self.rate_limiter.can_create_role(self.guild.id)
            
            if not can_create:
                await interaction.followup.send(
                    f"❌ **Rate Limit Atingido!**\n"
                    f"Você já criou {count_48h} cargos nas últimas 48h.\n"
                    f"Limite do Discord: 250 cargos/48h.\n"
                    f"Tente novamente mais tarde.",
                    ephemeral=True
                )
                return
            
            if remaining < quantity:
                await interaction.followup.send(
                    f"⚠️ **Atenção:** Você só pode criar {remaining} cargos restantes nas próximas 48h.\n"
                    f"Quantidade solicitada: {quantity}.\n"
                    f"Reduza a quantidade ou aguarde.",
                    ephemeral=True
                )
                return
            
            # Gera gradiente de cores se solicitado
            if use_gradient:
                colors = generate_color_gradient(start_color, end_color, quantity)
            else:
                colors = [start_color] * quantity
            
            prefix = self.prefix_input.value.strip()
            
            # Verifica permissões do bot
            has_perm, missing = await check_bot_permissions(
                self.guild,
                ["manage_roles"]
            )
            if not has_perm:
                await interaction.followup.send(
                    f"❌ Bot não tem permissão 'Gerenciar Cargos'. Faltando: {', '.join(missing)}",
                    ephemeral=True
                )
                return
            
            # Cria cargos sequencialmente com rate limiting
            created_roles = []
            failed = []
            
            status_msg = await interaction.followup.send(
                f"⏳ Criando cargos... (0/{quantity})\n"
                f"{await self.rate_limiter.get_status_message(self.guild.id, 'role_create')}",
                ephemeral=True
            )
            
            for i in range(quantity):
                role_name = f"{prefix} {i + 1}"
                level_order = start_level + i
                color = discord.Color.from_str(colors[i])
                
                try:
                    # Delay adaptativo baseado em ações recentes
                    delay = await self.rate_limiter.get_adaptive_delay(
                        self.guild.id, 'role_create'
                    )
                    if i > 0:  # Não espera antes do primeiro
                        await asyncio.sleep(delay)
                    
                    # Verifica rate limit novamente antes de cada criação
                    can_create, count_48h, _ = await self.rate_limiter.can_create_role(self.guild.id)
                    if not can_create:
                        failed.append(f"{role_name} (rate limit atingido)")
                        break
                    
                    # Cria o cargo
                    role = await self.guild.create_role(
                        name=role_name,
                        color=color,
                        mentionable=False
                    )
                    
                    # Verifica hierarquia
                    can_manage, error_msg = check_bot_hierarchy(self.guild, role)
                    if not can_manage:
                        await role.delete()
                        failed.append(f"{role_name} ({error_msg})")
                        continue
                    
                    # Registra rate limit
                    await self.rate_limiter.track_action(self.guild.id, 'role_create')
                    
                    # Busca todos os configs para posicionamento hierárquico
                    all_configs = await self.repository.get_all_configs(self.guild.id, order_by='level_order')
                    
                    # Posiciona cargo hierarquicamente
                    await position_role_hierarchically(self.guild, role, level_order, all_configs)
                    
                    # Salva configuração no banco
                    config = HierarchyConfig(
                        guild_id=self.guild.id,
                        role_id=role.id,
                        role_name=role_name,
                        level_order=level_order,
                        role_color=colors[i]
                    )
                    await self.repository.upsert_config(config)
                    
                    # Se for cargo admin, aplica permissões
                    if config.is_admin_rank:
                        await apply_admin_permissions(self.guild, role)
                    
                    created_roles.append(role)
                    
                    # Atualiza mensagem de progresso com feedback visual
                    progress_pct = int((i + 1) / quantity * 100)
                    progress_bar = "🟩" * int(progress_pct / 10) + "⬜" * (10 - int(progress_pct / 10))
                    
                    rate_status = await self.rate_limiter.get_status_message(self.guild.id, 'role_create')
                    
                    # Calcula tempo restante estimado
                    remaining = quantity - (i + 1)
                    estimated_remaining = int(remaining * 1.5)
                    time_str = f"{estimated_remaining // 60}min {estimated_remaining % 60}seg" if estimated_remaining >= 60 else f"{estimated_remaining}seg"
                    
                    await status_msg.edit(
                        content=(
                            f"⏳ **Criando cargos...**\n"
                            f"📊 Progresso: {i + 1}/{quantity} ({progress_pct}%)\n"
                            f"{progress_bar}\n"
                            f"⏱️ Tempo restante estimado: ~{time_str}\n\n"
                            f"{rate_status}"
                        )
                    )
                    
                except discord.Forbidden:
                    failed.append(f"{role_name} (sem permissão)")
                except discord.HTTPException as e:
                    if e.status == 429:  # Rate limit do Discord
                        await asyncio.sleep(15 * 60)  # Espera 15 minutos
                        failed.append(f"{role_name} (rate limit do Discord)")
                        break
                    else:
                        failed.append(f"{role_name} (erro: {e})")
                except Exception as e:
                    LOGGER.error("Erro ao criar cargo %s: %s", role_name, e, exc_info=True)
                    failed.append(f"{role_name} (erro desconhecido)")
            
            # Mensagem final
            success_count = len(created_roles)
            if success_count > 0:
                result_msg = f"✅ **{success_count} cargo(s) criado(s) com sucesso!**\n"
                if failed:
                    result_msg += f"❌ {len(failed)} falha(s): {', '.join(failed[:5])}"
                if len(failed) > 5:
                    result_msg += f"\n... e mais {len(failed) - 5} falha(s)"
            else:
                result_msg = f"❌ **Nenhum cargo foi criado.**\n"
                if failed:
                    result_msg += f"Erros: {', '.join(failed[:5])}"
            
            await status_msg.edit(content=result_msg)
            
            # Atualiza embed do setup
            await self.setup_view.update_embed()
            
        except Exception as e:
            LOGGER.error("Erro ao criar cargos em massa: %s", e, exc_info=True)
            await interaction.followup.send(
                "❌ Erro ao criar cargos. Tente novamente.",
                ephemeral=True
            )


class HierarchySetupView(discord.ui.View):
    """View principal para configurar o sistema de hierarquia."""
    
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
        
        # Inicializa repository e rate limiter
        from .repository import HierarchyRepository
        from .cache import HierarchyCache
        from .rate_limiter import HierarchyRateLimiter
        
        cache = HierarchyCache()
        self.repository = HierarchyRepository(db, cache)
        self.rate_limiter = HierarchyRateLimiter(db)
        
        # ChannelSelect para Canal de Logs de Hierarquia (row 0 - ocupa linha inteira)
        self.log_channel_select = discord.ui.ChannelSelect(
            placeholder="Selecione o canal para logs de hierarquia...",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            row=0
        )
        self.log_channel_select.callback = self.on_log_channel_select
        self.add_item(self.log_channel_select)
        
        # RoleSelect para adicionar cargos existentes (row 1 - ocupa linha inteira)
        self.existing_role_select = discord.ui.RoleSelect(
            placeholder="Selecione cargo existente para adicionar à hierarquia...",
            min_values=0,
            max_values=1,
            row=1
        )
        self.existing_role_select.callback = self.on_existing_role_select
        self.add_item(self.existing_role_select)
        
        # Botão Criar Cargo Individual (row 2)
        self.create_single_btn = discord.ui.Button(
            label="➕ Criar Cargo Individual",
            style=discord.ButtonStyle.success,
            row=2
        )
        self.create_single_btn.callback = self.create_single_role
        self.add_item(self.create_single_btn)
        
        # Botão Criar em Massa (row 2)
        self.bulk_create_btn = discord.ui.Button(
            label="➕ Criar Cargos em Massa",
            style=discord.ButtonStyle.success,
            row=2
        )
        self.bulk_create_btn.callback = self.create_bulk_roles
        self.add_item(self.bulk_create_btn)
        
        # Botão Criar Novo Canal de Logs (row 2)
        self.create_log_channel_btn = discord.ui.Button(
            label="➕ Criar Canal de Logs",
            style=discord.ButtonStyle.success,
            row=2
        )
        self.create_log_channel_btn.callback = self.create_log_channel
        self.add_item(self.create_log_channel_btn)
        
        # Botão Gerenciar Cargos (row 3)
        self.manage_roles_btn = discord.ui.Button(
            label="⚙️ Gerenciar Cargos",
            style=discord.ButtonStyle.primary,
            row=3
        )
        self.manage_roles_btn.callback = self.manage_roles
        self.add_item(self.manage_roles_btn)
        
        # Botão Sincronizar Ordem (row 3)
        self.sync_order_btn = discord.ui.Button(
            label="🔄 Sincronizar Ordem",
            style=discord.ButtonStyle.secondary,
            row=3
        )
        self.sync_order_btn.callback = self.sync_role_order
        self.add_item(self.sync_order_btn)
        
        # Botão Configurar Requisitos (row 3)
        self.requirements_btn = discord.ui.Button(
            label="⚙️ Configurar Requisitos",
            style=discord.ButtonStyle.primary,
            row=3
        )
        self.requirements_btn.callback = self.open_requirements
        self.add_item(self.requirements_btn)
        
        # Botão Criar Canal de Aprovação (row 3)
        self.create_approval_channel_btn = discord.ui.Button(
            label="➕ Criar Canal de Aprovação",
            style=discord.ButtonStyle.success,
            row=3
        )
        self.create_approval_channel_btn.callback = self.create_approval_channel
        self.add_item(self.create_approval_channel_btn)
        
        # Botão Configurar Intervalo (row 4)
        self.interval_btn = discord.ui.Button(
            label="⏱️ Intervalo de Verificação",
            style=discord.ButtonStyle.secondary,
            row=4
        )
        self.interval_btn.callback = self.configure_interval
        self.add_item(self.interval_btn)
        
        # Botão Verificar Agora (row 4)
        self.check_now_btn = discord.ui.Button(
            label="🔄 Verificar Agora",
            style=discord.ButtonStyle.success,
            row=4
        )
        self.check_now_btn.callback = self.check_promotions_now
        self.add_item(self.check_now_btn)
        
        # Botão Voltar (row 4)
        if self.parent_view:
            self.add_item(BackButton(self.parent_view, row=4))
    
    async def _reorganize_levels(self, guild_id: int, target_level: int, new_role_id: int) -> None:
        """
        Reorganiza níveis quando um cargo é inserido em um nível ocupado.
        Desloca todos os cargos com level_order >= target_level para baixo (+1).
        
        Args:
            guild_id: ID do servidor
            target_level: Nível onde o novo cargo será inserido
            new_role_id: ID do novo cargo (será ignorado na reorganização)
        """
        # Busca todos os cargos configurados
        existing_configs = await self.repository.get_all_configs(guild_id, order_by='level_order')
        
        # Filtra cargos que precisam ser deslocados (level_order >= target_level)
        # e que não são o novo cargo sendo inserido
        configs_to_shift = [
            c for c in existing_configs 
            if c.level_order >= target_level and c.role_id != new_role_id
        ]
        
        if not configs_to_shift:
            return  # Nenhum cargo precisa ser deslocado
        
        # Atualiza cada cargo deslocando +1
        for config in reversed(configs_to_shift):  # Reverso para evitar conflitos
            updated_config = HierarchyConfig(
                guild_id=config.guild_id,
                role_id=config.role_id,
                role_name=config.role_name,
                level_order=config.level_order + 1,  # Desloca para baixo
                role_color=config.role_color,
                max_vacancies=config.max_vacancies,
                is_admin_rank=config.is_admin_rank,
                auto_promote=config.auto_promote,
                requires_approval=config.requires_approval,
                expiry_days=config.expiry_days,
                req_messages=config.req_messages,
                req_call_time=config.req_call_time,
                req_reactions=config.req_reactions,
                req_min_days=config.req_min_days,
                req_min_any=config.req_min_any,
                auto_demote_on_lose_req=config.auto_demote_on_lose_req,
                auto_demote_inactive_days=config.auto_demote_inactive_days,
                vacancy_priority=config.vacancy_priority,
                check_frequency_hours=config.check_frequency_hours
            )
            await self.repository.upsert_config(updated_config)
        
        # Invalida cache
        self.repository.cache.invalidate_config(guild_id)
    
    async def build_embed(self) -> discord.Embed:
        """Constrói a embed com as configurações atuais."""
        configs = await self.repository.get_all_configs(self.guild.id)
        
        # Alerta de segurança
        bot_member = self.guild.get_member(self.guild.me.id)
        bot_warning = ""
        if bot_member and bot_member.top_role:
            bot_warning = (
                f"⚠️ **IMPORTANTE:** O cargo do Bot ({bot_member.top_role.mention}) "
                f"DEVE estar no topo da hierarquia do servidor para gerenciar estes cargos.\n\n"
            )
        
        # Lista de cargos configurados
        if configs:
            roles_text = []
            for config in configs[:10]:  # Limita a 10 para não sobrecarregar
                role = self.guild.get_role(config.role_id)
                if role:
                    roles_text.append(
                        f"• {role.mention} (Nível {config.level_order})"
                    )
                else:
                    roles_text.append(
                        f"• `{config.role_name}` (Nível {config.level_order}) - Cargo não encontrado"
                    )
            if len(configs) > 10:
                roles_text.append(f"\n... e mais {len(configs) - 10} cargo(s)")
            roles_list = "\n".join(roles_text)
        else:
            roles_list = "Nenhum cargo configurado"
        
        # Busca canal de log configurado
        settings = await self.db.get_settings(self.guild.id)
        log_channel_id = settings.get("rank_log_channel")
        approval_channel_id = settings.get("hierarchy_approval_channel")
        log_channel_text = None
        if log_channel_id:
            log_channel = self.guild.get_channel(int(log_channel_id))
            if log_channel:
                log_channel_text = f"{log_channel.mention} (`{log_channel.id}`)"
            else:
                log_channel_text = f"`{log_channel_id}` (canal não encontrado)"
        
        # Busca canal de aprovação configurado
        approval_channel_text = None
        if approval_channel_id:
            approval_channel = self.guild.get_channel(int(approval_channel_id))
            if approval_channel:
                approval_channel_text = f"{approval_channel.mention} (`{approval_channel.id}`)"
            else:
                approval_channel_text = f"`{approval_channel_id}` (canal não encontrado)"
        
        # Busca intervalo configurado
        interval = settings.get("hierarchy_check_interval_hours", 1)
        if isinstance(interval, str):
            try:
                interval = int(interval)
            except ValueError:
                interval = 1
        
        current_config = {
            "Canal de Logs": log_channel_text or "Não configurado",
            "Canal de Aprovação": approval_channel_text or "Não configurado",
            "Cargos Configurados": f"{len(configs)} cargo(s)" if configs else "Nenhum",
            "Intervalo de Verificação": f"{interval} hora(s)"
        }
        
        embed = await build_standard_config_embed(
            title="🎖️ Configuração do Sistema de Hierarquia",
            description=(
                bot_warning +
                "Configure os cargos de hierarquia do servidor, requisitos de promoção, "
                "vagas limitadas e sistema de aprovação."
            ),
            current_config=current_config,
            guild=self.guild,
            footer_text="Use os botões abaixo para gerenciar cargos"
        )
        
        embed.add_field(
            name="📋 Cargos da Hierarquia",
            value=roles_list,
            inline=False
        )
        
        # Status de rate limit
        status_msg = await self.rate_limiter.get_status_message(
            self.guild.id, 'role_create'
        )
        embed.add_field(
            name="📊 Status de Rate Limit",
            value=status_msg,
            inline=False
        )
        
        return embed
    
    async def update_embed(self):
        """Atualiza a embed da mensagem."""
        # Esta função será chamada após mudanças
        # A implementação completa requer acesso à mensagem original
        pass
    
    async def create_single_role(self, interaction: discord.Interaction):
        """Abre modal para criar cargo individual."""
        modal = CreateSingleRoleModal(
            self.guild,
            self.repository,
            self.rate_limiter,
            self
        )
        await interaction.response.send_modal(modal)
    
    async def create_bulk_roles(self, interaction: discord.Interaction):
        """Abre modal para criar cargos em massa."""
        modal = CreateBulkRolesModal(
            self.guild,
            self.repository,
            self.rate_limiter,
            self
        )
        await interaction.response.send_modal(modal)
    
    async def on_existing_role_select(self, interaction: discord.Interaction):
        """Callback quando um cargo existente é selecionado para adicionar à hierarquia."""
        selected_roles = interaction.data.get("values", [])
        if not selected_roles:
            await interaction.response.send_message("❌ Nenhum cargo selecionado.", ephemeral=True)
            return
        
        role_id = int(selected_roles[0])
        role = self.guild.get_role(role_id)
        
        if not role:
            await interaction.response.send_message("❌ Cargo não encontrado.", ephemeral=True)
            return
        
        # Verifica se já está na hierarquia
        existing_config = await self.repository.get_config(self.guild.id, role_id)
        if existing_config:
            await interaction.response.send_message(
                f"⚠️ Cargo {role.mention} já está configurado na hierarquia (Nível {existing_config.level_order}).",
                ephemeral=True
            )
            return
        
        # Abre modal para perguntar o nível (modals só podem ser enviados via response, não followup)
        modal = AddExistingRoleLevelModal(role, self.repository, self)
        await interaction.response.send_modal(modal)
    
    async def on_log_channel_select(self, interaction: discord.Interaction):
        """Callback quando um canal de log é selecionado - salvamento automático."""
        await interaction.response.defer(ephemeral=True)
        
        selected_channels = interaction.data.get("values", [])
        if not selected_channels:
            await interaction.followup.send("❌ Nenhum canal selecionado.", ephemeral=True)
            return
        
        channel_id = int(selected_channels[0])
        channel = self.guild.get_channel(channel_id)
        
        if not channel:
            await interaction.followup.send("❌ Canal não encontrado.", ephemeral=True)
            return
        
        # Salva no banco
        await self.db.upsert_settings(
            self.guild.id,
            rank_log_channel=channel_id
        )
        
        # Atualiza embed (se a mensagem ainda existir)
        try:
            embed = await self.build_embed()
            if interaction.message:
                await interaction.message.edit(embed=embed, view=self)
        except discord.NotFound:
            pass  # Mensagem foi deletada
        except Exception as e:
            LOGGER.warning("Erro ao atualizar mensagem após configurar canal: %s", e)
        
        await interaction.followup.send(
            f"✅ Canal de logs de hierarquia configurado: {channel.mention}",
            ephemeral=True
        )
    
    async def create_log_channel(self, interaction: discord.Interaction):
        """Abre modal para criar canal de logs."""
        from ..ui_commons import CreateChannelModal
        
        # Busca cargos de staff para permissões automáticas
        settings = await self.db.get_settings(self.guild.id)
        staff_roles = []
        
        # Busca cargo de moderador de hierarquia se configurado
        mod_role_id = settings.get("hierarchy_mod_role_id")
        if mod_role_id:
            mod_role = self.guild.get_role(int(mod_role_id))
            if mod_role:
                staff_roles.append(mod_role)
        
        # Busca cargos de staff via command_permissions (ficha, warn, etc)
        # Tenta buscar qualquer cargo que tenha permissão de moderação
        try:
            ficha_perms = await self.db.get_command_permissions(self.guild.id, "ficha")
            if ficha_perms:
                role_ids = [int(rid.strip()) for rid in ficha_perms.split(",") if rid.strip().isdigit()]
                for role_id in role_ids:
                    role = self.guild.get_role(role_id)
                    if role and role not in staff_roles:
                        staff_roles.append(role)
        except Exception:
            pass
        
        modal = CreateChannelModal(
            self.guild,
            title="Criar Canal de Logs de Hierarquia",
            channel_name_label="Nome do Canal",
            channel_type=discord.ChannelType.text,
            is_sensitive=True,  # Canal sensível, oculta de @everyone automaticamente
            staff_roles=staff_roles,
            on_success=self._on_log_channel_created
        )
        await interaction.response.send_modal(modal)
    
    async def _on_log_channel_created(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Callback quando canal de log é criado."""
        # Salva no banco
        await self.db.upsert_settings(
            self.guild.id,
            rank_log_channel=channel.id
        )
        
        # Atualiza embed (se a mensagem ainda existir)
        try:
            embed = await self.build_embed()
            if interaction.message:
                await interaction.message.edit(embed=embed, view=self)
        except discord.NotFound:
            pass  # Mensagem foi deletada
        except Exception as e:
            LOGGER.warning("Erro ao atualizar mensagem após criar canal de log: %s", e)
    
    async def create_approval_channel(self, interaction: discord.Interaction):
        """Abre modal para criar canal de aprovação de hierarquia."""
        from ..ui_commons import CreateChannelModal
        
        # Busca cargos de staff para permissões automáticas
        settings = await self.db.get_settings(self.guild.id)
        staff_roles = []
        
        # Busca cargo de moderador de hierarquia se configurado
        mod_role_id = settings.get("hierarchy_mod_role_id")
        if mod_role_id:
            mod_role = self.guild.get_role(int(mod_role_id))
            if mod_role:
                staff_roles.append(mod_role)
        
        # Busca cargos de staff via command_permissions
        try:
            ficha_perms = await self.db.get_command_permissions(self.guild.id, "ficha")
            if ficha_perms:
                role_ids = [int(rid.strip()) for rid in ficha_perms.split(",") if rid.strip().isdigit()]
                for role_id in role_ids:
                    role = self.guild.get_role(role_id)
                    if role and role not in staff_roles:
                        staff_roles.append(role)
        except Exception:
            pass
        
        modal = CreateChannelModal(
            self.guild,
            title="Criar Canal de Aprovação de Hierarquia",
            channel_name_label="Nome do Canal",
            channel_type=discord.ChannelType.text,
            is_sensitive=True,  # Canal sensível, oculta de @everyone automaticamente
            staff_roles=staff_roles,
            on_success=self._on_approval_channel_created
        )
        await interaction.response.send_modal(modal)
    
    async def _on_approval_channel_created(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Callback quando canal de aprovação é criado."""
        # Salva no banco
        await self.db.upsert_settings(
            self.guild.id,
            hierarchy_approval_channel=channel.id
        )
        
        # Atualiza embed (se a mensagem ainda existir)
        try:
            embed = await self.build_embed()
            if interaction.message:
                await interaction.message.edit(embed=embed, view=self)
        except discord.NotFound:
            pass  # Mensagem foi deletada
        except Exception as e:
            LOGGER.warning("Erro ao atualizar mensagem após criar canal de aprovação: %s", e)
        
        await interaction.followup.send(
            f"✅ Canal de aprovação de hierarquia criado e configurado: {channel.mention}",
            ephemeral=True
        )
    
    async def open_requirements(self, interaction: discord.Interaction):
        """Abre view para configurar requisitos de cargos."""
        from .requirements_view import RequirementsView
        
        # Verifica se há cargos configurados antes de abrir
        configs = await self.repository.get_all_configs(self.guild.id)
        if not configs:
            await interaction.response.send_message(
                "❌ **Nenhum cargo de hierarquia configurado.**\n\n"
                "Você precisa criar ou adicionar cargos à hierarquia primeiro.\n"
                "Use os botões de criação acima.",
                ephemeral=True
            )
            return
        
        view = RequirementsView(self.bot, self.db, self.guild, parent_view=self)
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def manage_roles(self, interaction: discord.Interaction):
        """Abre view para gerenciar cargos individuais."""
        from .manage_roles_view import ManageRolesView
        
        view = ManageRolesView(self.bot, self.db, self.guild, parent_view=self)
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)
        # Armazena referência à mensagem para atualização futura
        if interaction.message:
            view._message = interaction.message
    
    async def sync_role_order(self, interaction: discord.Interaction):
        """Sincroniza level_order do banco com as posições reais dos cargos no Discord."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Busca todos os cargos configurados
            configs = await self.repository.get_all_configs(self.guild.id, order_by='level_order')
            
            if not configs:
                await interaction.followup.send(
                    "❌ Nenhum cargo de hierarquia configurado.",
                    ephemeral=True
                )
                return
            
            # Mapeia role_id -> role.position atual no Discord
            role_positions = {}
            missing_roles = []
            for config in configs:
                role = self.guild.get_role(config.role_id)
                if role:
                    role_positions[config.role_id] = role.position
                else:
                    missing_roles.append(config.role_name)
            
            if missing_roles:
                await interaction.followup.send(
                    f"⚠️ Os seguintes cargos não foram encontrados: {', '.join(missing_roles)}",
                    ephemeral=True
                )
                return
            
            # Ordena por posição (maior = mais alto na hierarquia)
            sorted_roles = sorted(role_positions.items(), key=lambda x: x[1], reverse=True)
            
            # Atualiza level_order no banco (1 = mais alto, 2 = segundo, etc.)
            updates = []
            for idx, (role_id, position) in enumerate(sorted_roles, start=1):
                # Busca config correspondente
                config = next((c for c in configs if c.role_id == role_id), None)
                if config and config.level_order != idx:
                    # Cria nova instância com level_order atualizado
                    from .models import HierarchyConfig
                    updated_config = HierarchyConfig(
                        guild_id=config.guild_id,
                        role_id=config.role_id,
                        role_name=config.role_name,
                        level_order=idx,  # Novo level_order baseado na posição do Discord
                        role_color=config.role_color,
                        max_vacancies=config.max_vacancies,
                        is_admin_rank=config.is_admin_rank,
                        auto_promote=config.auto_promote,
                        requires_approval=config.requires_approval,
                        expiry_days=config.expiry_days,
                        req_messages=config.req_messages,
                        req_call_time=config.req_call_time,
                        req_reactions=config.req_reactions,
                        req_min_days=config.req_min_days,
                        req_min_any=config.req_min_any,
                        auto_demote_on_lose_req=config.auto_demote_on_lose_req,
                        auto_demote_inactive_days=config.auto_demote_inactive_days,
                        vacancy_priority=config.vacancy_priority,
                        check_frequency_hours=config.check_frequency_hours
                    )
                    # Atualiza no banco
                    await self.repository.upsert_config(updated_config)
                    updates.append(f"`{config.role_name}`: Nível {config.level_order} → {idx}")
            
            if updates:
                # Invalida cache
                self.repository.cache.invalidate_config(self.guild.id)
                
                # Atualiza embed (se a mensagem ainda existir)
                try:
                    embed = await self.build_embed()
                    if interaction.message:
                        await interaction.message.edit(embed=embed, view=self)
                except discord.NotFound:
                    # Mensagem foi deletada, não há o que atualizar
                    pass
                except Exception as e:
                    LOGGER.warning("Erro ao atualizar mensagem após sincronizar ordem: %s", e)
                
                await interaction.followup.send(
                    f"✅ **Ordem sincronizada com sucesso!**\n\n" +
                    "\n".join(updates),
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "ℹ️ A ordem já está sincronizada.",
                    ephemeral=True
                )
                
        except Exception as e:
            LOGGER.error("Erro ao sincronizar ordem: %s", e, exc_info=True)
            await interaction.followup.send(
                "❌ Erro ao sincronizar ordem. Tente novamente.",
                ephemeral=True
            )
    
    async def configure_interval(self, interaction: discord.Interaction):
        """Abre modal para configurar intervalo de verificação."""
        from .interval_config_modal import IntervalConfigModal
        
        # Busca intervalo atual
        settings = await self.db.get_settings(self.guild.id)
        current_interval = settings.get("hierarchy_check_interval_hours", 1)
        if isinstance(current_interval, str):
            try:
                current_interval = int(current_interval)
            except ValueError:
                current_interval = 1
        
        modal = IntervalConfigModal(current_interval, self.db, self.guild, self)
        await interaction.response.send_modal(modal)
    
    async def check_promotions_now(self, interaction: discord.Interaction):
        """Executa verificação de promoções imediatamente."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Busca o cog de promoção
            promotion_cog = self.bot.get_cog("HierarchyPromotionCog")
            if not promotion_cog:
                await interaction.followup.send(
                    "❌ Sistema de promoção não está carregado.",
                    ephemeral=True
                )
                return
            
            # Executa verificação (check_all_members=True para verificar TODOS os membros)
            result = await promotion_cog.check_promotions_now(self.guild.id, check_all_members=True)
            
            # Monta mensagem de resultado
            message_parts = [
                f"✅ Verificação executada!",
                f"👥 Usuários verificados: {result.get('checked_users', 0)}",
                f"🎖️ Promoções realizadas: {result.get('promotions', 0)}"
            ]
            
            # Adiciona pedidos de aprovação se houver
            approval_count = result.get('approval_requests', 0)
            if approval_count > 0:
                message_parts.append(f"🔔 Pedidos de aprovação criados: {approval_count}")
            
            if result.get("errors"):
                message_parts.append(f"\n⚠️ Erros: {len(result['errors'])}")
                message_parts.extend(result["errors"][:3])
            
            await interaction.followup.send(
                "\n".join(message_parts),
                ephemeral=True
            )
        except Exception as e:
            LOGGER.error("Erro ao executar verificação imediata: %s", e, exc_info=True)
            await interaction.followup.send(
                "❌ Erro ao executar verificação. Tente novamente.",
                ephemeral=True
            )
