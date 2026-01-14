"""View para configurar requisitos de cargos de hierarquia."""

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


class RequirementsConfigModal(discord.ui.Modal, title="Configurar Requisitos"):
    """Modal para configurar requisitos de um cargo."""
    
    def __init__(self, config: HierarchyConfig, repository: HierarchyRepository, guild: discord.Guild, parent_view):
        super().__init__()
        self.config = config
        self.repository = repository
        self.guild = guild
        self.parent_view = parent_view
        
        # Limpa qualquer item existente (por segurança)
        self.clear_items()
        
        # Adiciona campos manualmente para garantir controle total (máximo 5 campos)
        self.req_messages = discord.ui.TextInput(
            label="Mensagens Necessárias",
            placeholder="Ex: 1000 (0 para desabilitar)",
            required=False,
            max_length=10
        )
        self.req_messages.default = str(config.req_messages) if config.req_messages > 0 else ""
        self.add_item(self.req_messages)
        
        self.req_call_time = discord.ui.TextInput(
            label="Tempo em Call (horas)",
            placeholder="Ex: 50 (0 para desabilitar)",
            required=False,
            max_length=10
        )
        self.req_call_time.default = str(config.req_call_time // 3600) if config.req_call_time > 0 else ""
        self.add_item(self.req_call_time)
        
        self.req_reactions = discord.ui.TextInput(
            label="Reações Necessárias",
            placeholder="Ex: 500 (0 para desabilitar)",
            required=False,
            max_length=10
        )
        self.req_reactions.default = str(config.req_reactions) if config.req_reactions > 0 else ""
        self.add_item(self.req_reactions)
        
        # Combina req_min_days (dias no servidor) e min_days_in_role (dias no cargo)
        # Formato: "servidor:30 cargo:15"
        self.min_days_combined = discord.ui.TextInput(
            label="Dias Mínimos (Servidor/Cargo)",
            placeholder="Formato: servidor:30 cargo:15",
            required=False,
            max_length=30
        )
        servidor_str = str(config.req_min_days) if config.req_min_days > 0 else "0"
        cargo_str = str(config.min_days_in_role) if config.min_days_in_role > 0 else "0"
        self.min_days_combined.default = f"servidor:{servidor_str} cargo:{cargo_str}"
        self.add_item(self.min_days_combined)
        
        # Combina requires_approval e req_min_any em um único campo
        # Formato: "aprovação:sim mínimo:2" ou apenas "aprovação:sim"
        self.approval_and_min_input = discord.ui.TextInput(
            label="Aprovação e Mínimo",
            placeholder="Formato: aprovação:sim mínimo:2",
            required=False,
            max_length=30
        )
        approval_str = "sim" if config.requires_approval else "não"
        min_str = str(config.req_min_any) if config.req_min_any > 0 else "1"
        self.approval_and_min_input.default = f"aprovação:{approval_str} mínimo:{min_str}"
        self.add_item(self.approval_and_min_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Parse valores
            req_messages = int(self.req_messages.value) if self.req_messages.value and self.req_messages.value.strip().isdigit() else 0
            req_call_hours = int(self.req_call_time.value) if self.req_call_time.value and self.req_call_time.value.strip().isdigit() else 0
            req_call_time = req_call_hours * 3600  # Converte horas para segundos
            req_reactions = int(self.req_reactions.value) if self.req_reactions.value and self.req_reactions.value.strip().isdigit() else 0
            
            # Parse min_days_combined (formato: "servidor:30 cargo:15")
            req_min_days = self.config.req_min_days  # Valor padrão
            min_days_in_role = self.config.min_days_in_role  # Valor padrão
            
            if self.min_days_combined.value and self.min_days_combined.value.strip():
                days_str = self.min_days_combined.value.lower().strip()
                # Procura por "servidor:"
                if "servidor:" in days_str:
                    servidor_part = days_str.split("servidor:")[1].split()[0] if "servidor:" in days_str else None
                    if servidor_part and servidor_part.isdigit():
                        req_min_days = int(servidor_part)
                # Procura por "cargo:"
                if "cargo:" in days_str:
                    cargo_part = days_str.split("cargo:")[1].split()[0] if "cargo:" in days_str else None
                    if cargo_part and cargo_part.isdigit():
                        min_days_in_role = int(cargo_part)
            
            # Parse approval_and_min_input
            requires_approval = self.config.requires_approval
            req_min_any = self.config.req_min_any
            
            if self.approval_and_min_input.value and self.approval_and_min_input.value.strip():
                approval_min_str = self.approval_and_min_input.value.lower().strip()
                # Procura por "aprovação:sim" ou "aprovação:não"
                if "aprovação:" in approval_min_str:
                    approval_part = approval_min_str.split("aprovação:")[1].split()[0] if "aprovação:" in approval_min_str else None
                    if approval_part:
                        requires_approval = approval_part in ["sim", "s", "yes", "y"]
                # Procura por "mínimo:" ou "minimo:"
                if "mínimo:" in approval_min_str or "minimo:" in approval_min_str:
                    min_key = "mínimo:" if "mínimo:" in approval_min_str else "minimo:"
                    min_part = approval_min_str.split(min_key)[1].split()[0] if min_key in approval_min_str else None
                    if min_part and min_part.isdigit():
                        req_min_any = int(min_part)
            
            # Fallback: se req_min_any não foi definido, usa o valor padrão
            if req_min_any < 1:
                req_min_any = 1
            
            # Validações
            if req_min_any < 1:
                req_min_any = 1
            
            # Atualiza configuração
            updated_config = HierarchyConfig(
                guild_id=self.config.guild_id,
                role_id=self.config.role_id,
                role_name=self.config.role_name,
                level_order=self.config.level_order,
                role_color=self.config.role_color,
                max_vacancies=self.config.max_vacancies,
                is_admin_rank=self.config.is_admin_rank,
                auto_promote=self.config.auto_promote,
                requires_approval=requires_approval,
                expiry_days=self.config.expiry_days,
                req_messages=req_messages,
                req_call_time=req_call_time,
                req_reactions=req_reactions,
                req_min_days=req_min_days,
                min_days_in_role=min_days_in_role,
                req_min_any=req_min_any,
                auto_demote_on_lose_req=self.config.auto_demote_on_lose_req,
                auto_demote_inactive_days=self.config.auto_demote_inactive_days,
                vacancy_priority=self.config.vacancy_priority,
                check_frequency_hours=self.config.check_frequency_hours
            )
            
            await self.repository.upsert_config(updated_config)
            
            # Invalida cache
            self.repository.cache.invalidate_config(self.guild.id, self.config.role_id)
            
            # Atualiza embed (se a mensagem ainda existir)
            try:
                embed = await self.parent_view.build_embed()
                if interaction.message:
                    await interaction.message.edit(embed=embed, view=self.parent_view)
            except discord.NotFound:
                pass  # Mensagem foi deletada
            except Exception as e:
                LOGGER.warning("Erro ao atualizar mensagem após configurar requisitos: %s", e)
            
            await interaction.followup.send(
                f"✅ Requisitos atualizados para {self.guild.get_role(self.config.role_id).mention if self.guild.get_role(self.config.role_id) else 'cargo'}!",
                ephemeral=True
            )
            
        except ValueError as e:
            await interaction.followup.send(
                f"❌ Valor inválido: {e}",
                ephemeral=True
            )
        except Exception as e:
            LOGGER.error("Erro ao atualizar requisitos: %s", e, exc_info=True)
            await interaction.followup.send(
                "❌ Erro ao atualizar requisitos. Tente novamente.",
                ephemeral=True
            )


class RequirementsView(discord.ui.View):
    """View para configurar requisitos de cargos de hierarquia."""
    
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
        
        # RoleSelect para escolher cargo (será populado dinamicamente apenas com cargos de hierarquia)
        self.role_select = None  # Será criado dinamicamente em build_embed se houver cargos
        
        # Botão Voltar
        if self.parent_view:
            self.add_item(BackButton(self.parent_view, row=4))
    
    async def on_role_select_custom(self, interaction: discord.Interaction):
        """Callback quando um cargo é selecionado via Select customizado."""
        selected_values = interaction.data.get("values", [])
        if not selected_values:
            await interaction.response.send_message("❌ Nenhum cargo selecionado.", ephemeral=True)
            return
        
        role_id = int(selected_values[0])
        role = self.guild.get_role(role_id)
        
        if not role:
            await interaction.response.send_message("❌ Cargo não encontrado.", ephemeral=True)
            return
        
        # Busca configuração do cargo (já sabemos que está na hierarquia pelo select)
        config = await self.repository.get_config(self.guild.id, role_id)
        if not config:
            await interaction.response.send_message(
                f"❌ Erro: Cargo {role.mention} não encontrado na configuração.",
                ephemeral=True
            )
            return
        
        # Abre modal para configurar requisitos (modals só podem ser enviados via response, não followup)
        modal = RequirementsConfigModal(config, self.repository, self.guild, self.parent_view)
        await interaction.response.send_modal(modal)
    
    async def build_embed(self) -> discord.Embed:
        """Constrói embed com lista de cargos e seus requisitos."""
        configs = await self.repository.get_all_configs(self.guild.id, order_by='level_order')
        
        if not configs:
            embed = discord.Embed(
                title="⚙️ Configurar Requisitos de Hierarquia",
                description="❌ **Nenhum cargo de hierarquia configurado.**\n\n"
                          "Você precisa criar ou adicionar cargos à hierarquia primeiro.\n"
                          "Use os botões de criação no menu principal.",
                color=discord.Color.orange()
            )
            return embed
        
        # Cria RoleSelect dinamicamente apenas com cargos de hierarquia
        # Limpa select anterior se existir
        if self.role_select:
            self.remove_item(self.role_select)
        
        # Cria novo select com apenas os cargos de hierarquia
        hierarchy_role_ids = [config.role_id for config in configs]
        
        # Cria um select customizado que filtra apenas cargos de hierarquia
        # Como RoleSelect não suporta filtro direto, vamos usar um Select menu customizado
        from discord.ui import Select
        
        options = []
        for config in configs:
            role = self.guild.get_role(config.role_id)
            if role:
                options.append(discord.SelectOption(
                    label=f"Nível {config.level_order}: {role.name}",
                    value=str(config.role_id),
                    description=f"Configurar requisitos deste cargo"
                ))
        
        if options:
            self.role_select = Select(
                placeholder="Selecione o cargo para configurar requisitos...",
                min_values=1,
                max_values=1,
                options=options[:25],  # Discord limita a 25 opções
                row=0
            )
            self.role_select.callback = self.on_role_select_custom
            self.add_item(self.role_select)
        
        # Lista cargos com requisitos
        roles_list = []
        for config in configs:
            role = self.guild.get_role(config.role_id)
            if role:
                reqs = []
                if config.req_messages > 0:
                    reqs.append(f"💬 {config.req_messages:,} msgs")
                if config.req_call_time > 0:
                    reqs.append(f"📞 {config.req_call_time // 3600}h call")
                if config.req_reactions > 0:
                    reqs.append(f"⭐ {config.req_reactions:,} reações")
                if config.req_min_days > 0:
                    reqs.append(f"📅 {config.req_min_days} dias servidor")
                if config.min_days_in_role > 0:
                    reqs.append(f"⏳ {config.min_days_in_role} dias cargo")
                
                req_text = " | ".join(reqs) if reqs else "Sem requisitos"
                min_any_text = f" (mín. {config.req_min_any})" if config.req_min_any > 1 else ""
                
                roles_list.append(
                    f"**Nível {config.level_order}:** {role.mention}\n"
                    f"• Requisitos: {req_text}{min_any_text}\n"
                    f"• Aprovação: {'✅ Sim' if config.requires_approval else '❌ Não'}\n"
                    f"• Vagas: {config.max_vacancies if config.max_vacancies > 0 else 'Ilimitadas'}"
                )
        
        embed = await build_standard_config_embed(
            title="⚙️ Configurar Requisitos de Hierarquia",
            description="Configure os requisitos necessários para cada cargo da hierarquia.",
            current_config={
                "Cargos Configurados": f"{len(configs)} cargo(s)"
            },
            guild=self.guild,
            footer_text="Selecione um cargo acima para configurar seus requisitos"
        )
        
        embed.add_field(
            name="📋 Cargos e Requisitos Atuais",
            value="\n\n".join(roles_list) if roles_list else "Nenhum cargo configurado",
            inline=False
        )
        
        return embed
