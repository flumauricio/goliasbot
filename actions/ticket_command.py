import asyncio
import io
import logging
import re
from typing import Optional, Dict, Any, List, Callable, Awaitable
import html

import discord
from discord.ext import commands

from db import Database

LOGGER = logging.getLogger(__name__)


class CreateChannelModal(discord.ui.Modal):
    """Modal genérico para criar canais de texto."""
    
    def __init__(self, guild: discord.Guild, title: str = "Criar Novo Canal",
                 channel_name_label: str = "Nome do Canal", 
                 on_success: Optional[Callable[[discord.Interaction, discord.TextChannel], Awaitable[None]]] = None):
        super().__init__(title=title)
        self.guild = guild
        self.on_success = on_success
        self.channel_name_input = discord.ui.TextInput(
            label=channel_name_label,
            placeholder="Ex: canal-exemplo",
            required=True,
            max_length=100
        )
        self.add_item(self.channel_name_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Cria o canal e chama o callback de sucesso."""
        try:
            channel_name = self.channel_name_input.value.strip()
            if not channel_name:
                await interaction.response.send_message(
                    "❌ O nome do canal não pode estar vazio.",
                    ephemeral=True
                )
                return
            
            try:
                channel = await self.guild.create_text_channel(
                    name=channel_name,
                    reason=f"Canal criado via Dashboard por {interaction.user}"
                )
                
                LOGGER.info(f"Canal '{channel.name}' criado no guild {self.guild.id} por {interaction.user.id}")
                
                await interaction.response.send_message(
                    f"✅ Canal **{channel.name}** criado! {channel.mention}",
                    ephemeral=True
                )
                
                # Chama callback de sucesso se fornecido
                if self.on_success:
                    await self.on_success(interaction, channel)
                    
            except discord.Forbidden:
                await interaction.response.send_message(
                    "❌ Não tenho permissão para criar canais. Verifique as permissões do bot.",
                    ephemeral=True
                )
            except Exception as exc:
                LOGGER.error("Erro ao criar canal: %s", exc, exc_info=True)
                await interaction.response.send_message(
                    "❌ Erro ao criar canal. Tente novamente.",
                    ephemeral=True
                )
        except Exception as exc:
            LOGGER.error("Erro no modal de criar canal: %s", exc, exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Erro ao processar. Tente novamente.",
                    ephemeral=True
                )


class CreateCategoryModal(discord.ui.Modal):
    """Modal para criar categorias."""
    
    def __init__(self, guild: discord.Guild, 
                 on_success: Optional[Callable[[discord.Interaction, discord.CategoryChannel], Awaitable[None]]] = None):
        super().__init__(title="Criar Nova Categoria")
        self.guild = guild
        self.on_success = on_success
        self.category_name_input = discord.ui.TextInput(
            label="Nome da Categoria",
            placeholder="Ex: Tickets",
            required=True,
            max_length=100
        )
        self.add_item(self.category_name_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Cria a categoria e chama o callback de sucesso."""
        try:
            category_name = self.category_name_input.value.strip()
            if not category_name:
                await interaction.response.send_message(
                    "❌ O nome da categoria não pode estar vazio.",
                    ephemeral=True
                )
                return
            
            try:
                category = await self.guild.create_category(
                    name=category_name,
                    reason=f"Categoria criada via Dashboard por {interaction.user}"
                )
                
                LOGGER.info(f"Categoria '{category.name}' criada no guild {self.guild.id} por {interaction.user.id}")
                
                await interaction.response.send_message(
                    f"✅ Categoria **{category.name}** criada! {category.mention}",
                    ephemeral=True
                )
                
                # Chama callback de sucesso se fornecido
                if self.on_success:
                    await self.on_success(interaction, category)
                    
            except discord.Forbidden:
                await interaction.response.send_message(
                    "❌ Não tenho permissão para criar categorias. Verifique as permissões do bot.",
                    ephemeral=True
                )
            except Exception as exc:
                LOGGER.error("Erro ao criar categoria: %s", exc, exc_info=True)
                await interaction.response.send_message(
                    "❌ Erro ao criar categoria. Tente novamente.",
                    ephemeral=True
                )
        except Exception as exc:
            LOGGER.error("Erro no modal de criar categoria: %s", exc, exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Erro ao processar. Tente novamente.",
                    ephemeral=True
                )


class CreateRoleModal(discord.ui.Modal):
    """Modal genérico para criar cargos."""
    
    def __init__(self, guild: discord.Guild, 
                 on_success: Optional[Callable[[discord.Interaction, discord.Role], Awaitable[None]]] = None):
        super().__init__(title="Criar Novo Cargo")
        self.guild = guild
        self.on_success = on_success
        self.role_name_input = discord.ui.TextInput(
            label="Nome do Cargo",
            placeholder="Ex: Cargo Exemplo",
            required=True,
            max_length=100
        )
        self.role_color_input = discord.ui.TextInput(
            label="Cor (Hex, opcional)",
            placeholder="Ex: #3498db ou deixe em branco",
            required=False,
            max_length=7
        )
        self.add_item(self.role_name_input)
        self.add_item(self.role_color_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Cria o cargo e chama o callback de sucesso."""
        try:
            role_name = self.role_name_input.value.strip()
            if not role_name:
                await interaction.response.send_message(
                    "❌ O nome do cargo não pode estar vazio.",
                    ephemeral=True
                )
                return
            
            # Processa cor
            color = discord.Color.default()
            color_str = self.role_color_input.value.strip()
            if color_str:
                try:
                    # Remove # se presente
                    if color_str.startswith("#"):
                        color_str = color_str[1:]
                    # Converte hex para int
                    color_value = int(color_str, 16)
                    color = discord.Color(color_value)
                except (ValueError, OverflowError):
                    await interaction.response.send_message(
                        "⚠️ Cor inválida. Usando cor padrão.",
                        ephemeral=True
                    )
            
            # Cria o cargo
            try:
                role = await self.guild.create_role(
                    name=role_name,
                    color=color,
                    reason=f"Cargo criado via Dashboard por {interaction.user}"
                )
                
                LOGGER.info(f"Cargo '{role.name}' criado no guild {self.guild.id} por {interaction.user.id}")
                
                await interaction.response.send_message(
                    f"✅ Cargo **{role.name}** criado! {role.mention}",
                    ephemeral=True
                )
                
                # Chama callback de sucesso se fornecido
                if self.on_success:
                    await self.on_success(interaction, role)
                    
            except discord.Forbidden:
                await interaction.response.send_message(
                    "❌ Não tenho permissão para criar cargos. Verifique as permissões do bot.",
                    ephemeral=True
                )
            except Exception as exc:
                LOGGER.error("Erro ao criar cargo: %s", exc, exc_info=True)
                await interaction.response.send_message(
                    "❌ Erro ao criar cargo. Tente novamente.",
                    ephemeral=True
                )
        except Exception as exc:
            LOGGER.error("Erro no modal de criar cargo: %s", exc, exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Erro ao processar. Tente novamente.",
                    ephemeral=True
                )


class BackButton(discord.ui.Button):
    """Botão para voltar ao dashboard principal."""
    
    def __init__(self, parent_view):
        super().__init__(label="⬅️ Voltar ao Dashboard", style=discord.ButtonStyle.secondary, row=4)
        self.parent_view = parent_view
    
    async def callback(self, interaction: discord.Interaction):
        """Retorna ao dashboard principal."""
        embed = await self.parent_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


# Cores de botão do Discord
BUTTON_COLORS = {
    "verde": discord.ButtonStyle.success,
    "azul": discord.ButtonStyle.primary,
    "vermelho": discord.ButtonStyle.danger,
    "cinza": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "primary": discord.ButtonStyle.primary,
    "danger": discord.ButtonStyle.danger,
    "secondary": discord.ButtonStyle.secondary,
}


# Métodos _ask e _ask_yes_no removidos - substituídos por interface interativa


def generate_html_transcript(
    ticket_id: int,
    channel_name: str,
    guild_name: str,
    user_id: str,
    closed_by: str,
    created_at: str,
    closed_at: str,
    topic_name: str,
    claimed_by: Optional[str],
    messages_data: List[Dict[str, Any]],
) -> str:
    """Gera uma transcrição HTML moderna e estilizada do ticket."""
    
    # Escapa HTML para segurança
    def escape_html(text: str) -> str:
        return html.escape(str(text))
    
    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transcrição de Ticket #{ticket_id}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            color: #333;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 28px;
            margin-bottom: 10px;
        }}
        .header p {{
            opacity: 0.9;
            font-size: 14px;
        }}
        .info-section {{
            padding: 25px;
            background: #f8f9fa;
            border-bottom: 2px solid #e9ecef;
        }}
        .info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
        }}
        .info-item {{
            background: white;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}
        .info-item strong {{
            display: block;
            color: #667eea;
            font-size: 12px;
            text-transform: uppercase;
            margin-bottom: 5px;
        }}
        .info-item span {{
            color: #333;
            font-size: 14px;
        }}
        .messages-section {{
            padding: 25px;
        }}
        .messages-section h2 {{
            color: #667eea;
            margin-bottom: 20px;
            font-size: 20px;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }}
        .message {{
            background: #f8f9fa;
            border-left: 4px solid #667eea;
            padding: 15px;
            margin-bottom: 15px;
            border-radius: 8px;
            transition: transform 0.2s;
        }}
        .message:hover {{
            transform: translateX(5px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}
        .message-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            flex-wrap: wrap;
        }}
        .message-author {{
            font-weight: bold;
            color: #667eea;
            font-size: 16px;
        }}
        .message-time {{
            color: #6c757d;
            font-size: 12px;
        }}
        .message-content {{
            color: #333;
            line-height: 1.6;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        .message-embed {{
            background: #e9ecef;
            padding: 10px;
            border-radius: 6px;
            margin-top: 10px;
            font-size: 13px;
            color: #495057;
        }}
        .message-attachments {{
            background: #fff3cd;
            padding: 10px;
            border-radius: 6px;
            margin-top: 10px;
            font-size: 13px;
            color: #856404;
        }}
        .footer {{
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #6c757d;
            font-size: 12px;
            border-top: 2px solid #e9ecef;
        }}
        @media (max-width: 768px) {{
            .info-grid {{
                grid-template-columns: 1fr;
            }}
            .message-header {{
                flex-direction: column;
                align-items: flex-start;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎫 Transcrição de Ticket</h1>
            <p>Ticket #{ticket_id} • {escape_html(channel_name)}</p>
        </div>
        
        <div class="info-section">
            <div class="info-grid">
                <div class="info-item">
                    <strong>🆔 Ticket ID</strong>
                    <span>#{ticket_id}</span>
                </div>
                <div class="info-item">
                    <strong>🎯 Tópico</strong>
                    <span>{escape_html(topic_name)}</span>
                </div>
                <div class="info-item">
                    <strong>👤 Autor</strong>
                    <span>User ID: {escape_html(user_id)}</span>
                </div>
                <div class="info-item">
                    <strong>🔒 Fechado por</strong>
                    <span>{escape_html(closed_by)}</span>
                </div>
                <div class="info-item">
                    <strong>📅 Criado em</strong>
                    <span>{escape_html(created_at)}</span>
                </div>
                <div class="info-item">
                    <strong>⏰ Fechado em</strong>
                    <span>{escape_html(closed_at)}</span>
                </div>
                {f'<div class="info-item"><strong>👨‍💼 Atendido por</strong><span>User ID: {escape_html(claimed_by)}</span></div>' if claimed_by else ''}
            </div>
        </div>
        
        <div class="messages-section">
            <h2>💬 Histórico de Mensagens ({len(messages_data)} mensagens)</h2>
"""
    
    # Adiciona cada mensagem
    for msg_data in messages_data:
        author = escape_html(msg_data.get('author', 'Unknown'))
        timestamp = escape_html(msg_data.get('timestamp', ''))
        content = escape_html(msg_data.get('content', ''))
        embed_info = msg_data.get('embed_info', [])
        attachments_info = msg_data.get('attachments_info', [])
        
        html_content += f"""
            <div class="message">
                <div class="message-header">
                    <span class="message-author">{author}</span>
                    <span class="message-time">{timestamp}</span>
                </div>
                <div class="message-content">{content if content else '<em>(sem texto)</em>'}</div>
"""
        
        if embed_info:
            html_content += f"""
                <div class="message-embed">
                    <strong>📎 Embed:</strong> {escape_html('; '.join(embed_info))}
                </div>
"""
        
        if attachments_info:
            html_content += f"""
                <div class="message-attachments">
                    <strong>📎 Anexos:</strong> {escape_html(', '.join(attachments_info))}
                </div>
"""
        
        html_content += """
            </div>
"""
    
    html_content += f"""
        </div>
        
        <div class="footer">
            <p>💼 Sistema de Tickets • Gerado em {escape_html(closed_at)}</p>
            <p>Total de mensagens: {len(messages_data)}</p>
        </div>
    </div>
</body>
</html>
"""
    
    return html_content


def parse_hex_color(color_str: str) -> Optional[discord.Color]:
    """Tenta parsear uma cor hexadecimal ou nome comum."""
    color_str = color_str.strip().lower()
    
    # Cores comuns
    color_map = {
        "vermelho": discord.Color.red(),
        "red": discord.Color.red(),
        "azul": discord.Color.blue(),
        "blue": discord.Color.blue(),
        "verde": discord.Color.green(),
        "green": discord.Color.green(),
        "amarelo": discord.Color.gold(),
        "yellow": discord.Color.gold(),
        "roxo": discord.Color.purple(),
        "purple": discord.Color.purple(),
        "laranja": discord.Color.orange(),
        "orange": discord.Color.orange(),
    }
    
    if color_str in color_map:
        return color_map[color_str]
    
    # Tenta hexadecimal
    if color_str.startswith("#"):
        color_str = color_str[1:]
    
    if re.match(r"^[0-9a-f]{6}$", color_str):
        try:
            return discord.Color(int(color_str, 16))
        except ValueError:
            pass
    
    return None


class TicketOpenView(discord.ui.View):
    """View persistente para abrir tickets."""
    
    def __init__(self, db: Database):
        super().__init__(timeout=None)
        self.db = db
    
    @discord.ui.button(
        label="Abrir Ticket",
        style=discord.ButtonStyle.primary,
        emoji="🎫",
        custom_id="btn_open_ticket_rota40"
    )
    async def open_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Botão que abre o menu de seleção de tópicos."""
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Este comando só funciona em servidores.", ephemeral=True)
            return
        
        topics = await self.db.get_ticket_topics(guild.id)
        if not topics:
            await interaction.response.send_message(
                "❌ Nenhum tópico de ticket configurado. Use `!ticket_setup` para configurar.",
                ephemeral=True
            )
            return
        
        # Cria um Select com os tópicos
        options = []
        for topic in topics[:25]:  # Limite do Discord
            emoji_str = topic.get("emoji", "🎫")
            name = topic.get("name", "Sem nome")
            description = topic.get("description", "")[:100]  # Limite de 100 chars
            
            options.append(
                discord.SelectOption(
                    label=name,
                    description=description,
                    emoji=emoji_str,
                    value=str(topic["id"]),
                )
            )
        
        view = TopicSelectView(self.db, options)
        await interaction.response.send_message(
            "Selecione o tipo de ticket que deseja abrir:",
            view=view,
            ephemeral=True
        )


class TopicSelectView(discord.ui.View):
    """View com Select para escolher tópico."""
    
    def __init__(self, db: Database, options: list):
        super().__init__(timeout=60)
        self.db = db
        self.select = discord.ui.Select(
            placeholder="Escolha um tópico...",
            options=options,
            min_values=1,
            max_values=1,
        )
        self.select.callback = self.on_select
        self.add_item(self.select)
    
    async def on_select(self, interaction: discord.Interaction):
        """Cria o ticket quando um tópico é selecionado."""
        topic_id = int(self.select.values[0])
        topic = await self.db.get_ticket_topic(topic_id)
        
        if not topic:
            await interaction.response.send_message("❌ Tópico não encontrado.", ephemeral=True)
            return
        
        guild = interaction.guild
        user = interaction.user
        
        if not guild:
            await interaction.response.send_message("Erro: servidor não encontrado.", ephemeral=True)
            return
        
        # Busca configurações
        settings = await self.db.get_ticket_settings(guild.id)
        category_id = settings.get("category_id")
        
        if not category_id:
            await interaction.response.send_message(
                "❌ Sistema de tickets não configurado. Use `!ticket_setup` primeiro.",
                ephemeral=True
            )
            return
        
        # Converte ID para int com validação
        try:
            cat_id = int(category_id) if category_id and str(category_id).isdigit() else None
        except (ValueError, TypeError):
            cat_id = None
        
        if not cat_id:
            await interaction.response.send_message(
                "❌ Categoria de tickets inválida. Use `!ticket_setup` para reconfigurar.",
                ephemeral=True
            )
            return
        
        # Tenta buscar canal com get_channel, se falhar usa fetch_channel
        category = guild.get_channel(cat_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            try:
                category = await guild.fetch_channel(cat_id)
                if not isinstance(category, discord.CategoryChannel):
                    category = None
            except (discord.NotFound, discord.HTTPException):
                category = None
        
        if not category or not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                "❌ Categoria de tickets não encontrada. Use `!ticket_setup` para reconfigurar.",
                ephemeral=True
            )
            return
        
        # Verifica limite de tickets abertos
        settings = await self.db.get_ticket_settings(guild.id)
        max_tickets = settings.get("max_tickets_per_user", 1) or 1
        
        open_count = await self.db.count_open_tickets_by_user(guild.id, user.id)
        if open_count >= max_tickets:
            await interaction.response.send_message(
                f"❌ Você já tem {open_count} ticket(s) aberto(s). O limite é {max_tickets} ticket(s) por usuário.\n"
                f"Por favor, feche seus tickets existentes antes de abrir um novo.",
                ephemeral=True
            )
            return
        
        # Cria o canal
        emoji_str = topic.get("emoji", "🎫")
        channel_name = f"{emoji_str}-{topic['name'].lower().replace(' ', '-')}-{user.name.lower()}"
        channel_name = channel_name[:100]  # Limite do Discord
        
        # Busca cargos do tópico
        role_ids = await self.db.get_topic_roles(topic_id)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_messages=True,
                read_message_history=True,
            ),
        }
        
        # Adiciona permissões para cargos de staff do tópico
        for role_id_str in role_ids:
            try:
                role_id = int(role_id_str) if role_id_str and str(role_id_str).isdigit() else None
                if role_id:
                    role = guild.get_role(role_id)
                    if role:
                        overwrites[role] = discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=True,
                            read_message_history=True,
                        )
            except (ValueError, TypeError):
                pass
        
        # Adiciona permissões para cargos globais de staff
        settings = await self.db.get_ticket_settings(guild.id)
        global_staff_roles_str = settings.get("global_staff_roles")
        if global_staff_roles_str:
            try:
                global_role_ids = [int(rid.strip()) for rid in global_staff_roles_str.split(",") if rid.strip() and str(rid.strip()).isdigit()]
                for global_role_id in global_role_ids:
                    role = guild.get_role(global_role_id)
                    if role:
                        overwrites[role] = discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=True,
                            read_message_history=True,
                        )
            except (ValueError, TypeError) as e:
                LOGGER.warning("Erro ao processar cargos globais ao criar ticket: %s", e)
        
        # Adiciona permissão para administradores
        overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
        
        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Ticket criado por {user}",
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Não tenho permissão para criar canais. Verifique as permissões do bot.",
                ephemeral=True
            )
            return
        except Exception as e:
            LOGGER.error("Erro ao criar canal de ticket: %s", e, exc_info=e)
            await interaction.response.send_message(
                "❌ Erro ao criar o canal de ticket. Tente novamente.",
                ephemeral=True
            )
            return
        
        # Cria registro no banco
        ticket_id = await self.db.create_ticket(guild.id, channel.id, user.id, topic_id)
        
        # Envia embed de boas-vindas com cores modernas
        colors_map = {
            "success": discord.Color.green(),
            "primary": discord.Color.blue(),
            "danger": discord.Color.red(),
            "secondary": discord.Color.greyple(),
        }
        embed_color = colors_map.get(topic.get("button_color", "primary"), discord.Color.blue())
        
        embed = discord.Embed(
            title=f"{emoji_str} {topic['name']}",
            description=f"✨ {topic.get('description', 'Bem-vindo ao seu ticket!')}\n\n💬 Use os botões abaixo para gerenciar seu ticket.",
            color=embed_color,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="👤 Autor", value=user.mention, inline=True)
        embed.add_field(name="📅 Criado em", value=discord.utils.format_dt(discord.utils.utcnow(), style="R"), inline=True)
        embed.add_field(name="🎯 Tópico", value=topic['name'], inline=True)
        embed.set_footer(text=f"🎫 Ticket #{ticket_id} • Sistema de Tickets")
        
        view = TicketControlView(self.db, ticket_id, user.id)
        await channel.send(embed=embed, view=view)
        
        # Notifica staff sobre novo ticket
        role_ids = await self.db.get_topic_roles(topic_id)
        if role_ids:
            mentions = []
            for role_id_str in role_ids:
                try:
                    role = guild.get_role(int(role_id_str))
                    if role:
                        mentions.append(role.mention)
                except (ValueError, TypeError):
                    pass
            
            if mentions:
                notification_embed = discord.Embed(
                    title="🔔✨ Novo Ticket Criado",
                    description=f"👤 {user.mention} abriu um novo ticket!\n\n🎟️ Acesse: {channel.mention}",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow(),
                )
                notification_embed.add_field(name="🎯 Tópico", value=f"{emoji_str} {topic['name']}", inline=True)
                notification_embed.add_field(name="🆔 Ticket ID", value=f"#{ticket_id}", inline=True)
                notification_embed.add_field(name="⏰ Criado", value=discord.utils.format_dt(discord.utils.utcnow(), style="R"), inline=True)
                notification_embed.set_footer(text="💼 Sistema de Tickets • Notificação de Staff")
                
                await channel.send(
                    f"{' '.join(mentions)} - Novo ticket criado!",
                    embed=notification_embed
                )
        
        await interaction.response.send_message(
            f"✅ Ticket criado! Acesse {channel.mention}",
            ephemeral=True
        )


class TicketControlView(discord.ui.View):
    """View persistente com botões de controle do ticket."""
    
    def __init__(self, db: Database, ticket_id: int = None, author_id: int = None, is_closed: bool = False):
        super().__init__(timeout=None)
        self.db = db
        self.ticket_id = ticket_id
        self.author_id = author_id
        self.is_closed = is_closed
        
        # Se o ticket estiver fechado, adiciona botão de reabertura
        if is_closed:
            self.add_item(ReopenButton(self.db))
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Verifica se o usuário pode interagir com os botões."""
        # Busca ticket pelo canal (para views persistentes)
        ticket = await self.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message("❌ Ticket não encontrado.", ephemeral=True)
            return False
        
        # Atualiza atributos da view se necessário
        if not self.ticket_id:
            self.ticket_id = ticket["id"]
        if not self.author_id:
            self.author_id = int(ticket["user_id"])
        
        # Autor e administradores sempre podem
        if interaction.user.id == self.author_id or interaction.user.guild_permissions.administrator:
            return True
        
        # Verifica se é staff do tópico
        if ticket.get("topic_id"):
            role_ids = await self.db.get_topic_roles(ticket["topic_id"])
            user_roles = [role.id for role in interaction.user.roles]
            for role_id_str in role_ids:
                try:
                    if int(role_id_str) in user_roles:
                        return True
                except (ValueError, TypeError):
                    pass
        
        # Verifica cargos globais de staff
        try:
            guild_id = int(ticket["guild_id"]) if str(ticket["guild_id"]).isdigit() else None
        except (ValueError, TypeError):
            guild_id = None
        
        if not guild_id:
            return False
        
        settings = await self.db.get_ticket_settings(guild_id)
        global_staff_roles_str = settings.get("global_staff_roles")
        if global_staff_roles_str:
            try:
                global_role_ids = [int(rid.strip()) for rid in global_staff_roles_str.split(",") if rid.strip()]
                user_roles = [role.id for role in interaction.user.roles]
                for global_role_id in global_role_ids:
                    if global_role_id in user_roles:
                        return True
            except (ValueError, TypeError) as e:
                LOGGER.warning("Erro ao processar cargos globais: %s", e)
        
        await interaction.response.send_message(
            "❌ Você não tem permissão para interagir com este ticket.",
            ephemeral=True
        )
        return False
    
    async def on_timeout(self):
        """Remove botões quando a view expira (não deve acontecer com timeout=None, mas por segurança)."""
        pass
    
    @discord.ui.button(label="🔒 Fechar", style=discord.ButtonStyle.danger, custom_id="ticket_close_rota40")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Fecha o ticket após confirmação."""
        # Busca ticket se não tiver o ID
        if not self.ticket_id:
            ticket = await self.db.get_ticket_by_channel(interaction.channel.id)
            if not ticket:
                await interaction.response.send_message("❌ Ticket não encontrado.", ephemeral=True)
                return
            self.ticket_id = ticket["id"]
            self.author_id = int(ticket["user_id"])
        
        # Verifica permissão (admin ou autor)
        if not interaction.user.guild_permissions.administrator and interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Apenas administradores ou o autor do ticket podem fechá-lo.",
                ephemeral=True
            )
            return
        
        # Confirmação
        view = ConfirmCloseView(self.db, self.ticket_id, interaction.channel)
        await interaction.response.send_message(
            "⚠️ Tem certeza que deseja fechar este ticket? Uma transcrição será gerada.",
            view=view,
            ephemeral=True
        )
    
    @discord.ui.button(label="🙋‍♂️ Assumir", style=discord.ButtonStyle.primary, custom_id="ticket_claim_rota40")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Marca o ticket como assumido e renomeia o canal."""
        # Busca ticket se não tiver o ID
        if not self.ticket_id:
            ticket = await self.db.get_ticket_by_channel(interaction.channel.id)
            if not ticket:
                await interaction.response.send_message("❌ Ticket não encontrado.", ephemeral=True)
                return
            self.ticket_id = ticket["id"]
        
        ticket = await self.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message("❌ Ticket não encontrado.", ephemeral=True)
            return
        
        if ticket.get("claimed_by"):
            try:
                claimed_id = int(ticket["claimed_by"]) if str(ticket["claimed_by"]).isdigit() else None
                claimed_user = interaction.guild.get_member(claimed_id) if claimed_id else None
            except (ValueError, TypeError):
                claimed_user = None
            
            if claimed_user:
                await interaction.response.send_message(
                    f"ℹ️ Este ticket já está sendo atendido por {claimed_user.mention}.",
                    ephemeral=True
                )
                return
        
        await interaction.response.defer()
        
        # Marca como assumido no banco
        await self.db.claim_ticket(self.ticket_id, interaction.user.id)
        
        # Renomeia o canal
        channel = interaction.channel
        if isinstance(channel, discord.TextChannel):
            try:
                # Formato: 📁-atendimento-nome
                new_name = f"📁-atendimento-{interaction.user.name.lower()}"
                # Limita o tamanho do nome (máximo 100 caracteres no Discord)
                new_name = new_name[:100]
                await channel.edit(name=new_name, reason=f"Ticket assumido por {interaction.user}")
            except discord.Forbidden:
                LOGGER.warning("Sem permissão para renomear canal ao assumir ticket")
            except Exception as e:
                LOGGER.error("Erro ao renomear canal: %s", e, exc_info=e)
        
        # Busca a mensagem original do ticket para atualizar a view
        try:
            async for msg in channel.history(limit=50, oldest_first=True):
                if msg.author == interaction.guild.me and msg.embeds and msg.components:
                    # Encontrou a mensagem do ticket, atualiza a view
                    new_view = TicketControlView(self.db, self.ticket_id, self.user_id)
                    # Desabilita o botão de assumir e atualiza label
                    for item in new_view.children:
                        if isinstance(item, discord.ui.Button) and item.custom_id == "ticket_claim_rota40":
                            item.disabled = True
                            # Limita o nome para não exceder 80 caracteres (limite do Discord)
                            user_name = interaction.user.name[:50]
                            item.label = f"Assumido por {user_name}"
                            break
                    
                    try:
                        await msg.edit(view=new_view)
                    except (discord.NotFound, discord.HTTPException) as e:
                        LOGGER.debug("Não foi possível atualizar mensagem do ticket: %s", e)
                    break
        except Exception as e:
            LOGGER.warning("Erro ao atualizar mensagem original do ticket: %s", e)
        
        # Anuncia no chat
        embed = discord.Embed(
            title="🙋‍♂️✨ Ticket Assumido",
            description=f"👤 **{interaction.user.mention}** assumiu este ticket e é agora o responsável pelo atendimento.",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="💼 Sistema de Tickets • Atendimento Ativo")
        
        await interaction.followup.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=[interaction.user])
        )
    
    @discord.ui.button(label="📝 Transcrição", style=discord.ButtonStyle.secondary, custom_id="ticket_transcript_rota40")
    async def generate_transcript(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Gera transcrição profissional do ticket."""
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("❌ Erro ao gerar transcrição.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Busca informações do ticket
        ticket = await self.db.get_ticket_by_channel(channel.id)
        ticket_id = ticket["id"] if ticket else "N/A"
        topic_name = "N/A"
        if ticket and ticket.get("topic_id"):
            topic = await self.db.get_ticket_topic(ticket["topic_id"])
            if topic:
                topic_name = topic.get("name", "N/A")
        
        # Coleta mensagens com formatação profissional
        messages_data = []
        async for msg in channel.history(limit=None, oldest_first=True):
            # Ignora mensagens do sistema
            if msg.type != discord.MessageType.default:
                continue
            
            author_name = str(msg.author)
            author_id = str(msg.author.id)
            timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')
            
            # Conteúdo da mensagem
            content = msg.content if msg.content else ""
            
            # Adiciona informações sobre embeds
            embed_info = []
            if msg.embeds:
                for embed in msg.embeds:
                    embed_parts = []
                    if embed.title:
                        embed_parts.append(f"Título: {embed.title}")
                    if embed.description:
                        embed_parts.append(f"Descrição: {embed.description[:100]}")
                    if embed_parts:
                        embed_info.append(" | ".join(embed_parts))
            
            # Adiciona informações sobre anexos
            attachments_info = []
            if msg.attachments:
                for att in msg.attachments:
                    attachments_info.append(f"{att.filename} ({att.size} bytes)")
            
            # Formata a linha da mensagem
            message_line = f"[{timestamp}] {author_name} ({author_id})"
            if content:
                message_line += f": {content}"
            if embed_info:
                message_line += f"\n  [Embed: {'; '.join(embed_info)}]"
            if attachments_info:
                message_line += f"\n  [Anexos: {', '.join(attachments_info)}]"
            
            messages_data.append(message_line)
        
        # Cria transcrição estilizada
        transcript_lines = [
            "=" * 80,
            f"TRANSCRIÇÃO DE TICKET - {channel.name.upper()}",
            "=" * 80,
            "",
            f"Ticket ID: #{ticket_id}",
            f"Tópico: {topic_name}",
            f"Canal: {channel.name}",
            f"Servidor: {channel.guild.name}",
            f"Data de Criação: {channel.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Data da Transcrição: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "",
            "-" * 80,
            "HISTÓRICO DE MENSAGENS",
            "-" * 80,
            "",
        ]
        
        transcript_lines.extend(messages_data)
        
        transcript_lines.extend([
            "",
            "-" * 80,
            "FIM DA TRANSCRIÇÃO",
            "-" * 80,
            f"Total de mensagens: {len(messages_data)}",
            f"Gerado em: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "=" * 80,
        ])
        
        transcript = "\n".join(transcript_lines)
        
        # Cria arquivo em memória
        transcript_bytes = transcript.encode("utf-8")
        transcript_file = io.BytesIO(transcript_bytes)
        
        # Envia como arquivo
        file = discord.File(
            fp=transcript_file,
            filename=f"transcript-{channel.name}-{discord.utils.utcnow().strftime('%Y%m%d-%H%M%S')}.txt"
        )
        
        await interaction.followup.send(
            "📝✨ Transcrição profissional gerada:",
            file=file,
            ephemeral=True
        )
    


class ReopenButton(discord.ui.Button):
    """Botão persistente para reabrir ticket fechado."""
    
    def __init__(self, db: Database):
        super().__init__(
            label="🔓 Reabrir",
            style=discord.ButtonStyle.success,
            custom_id="ticket_reopen_rota40"
        )
        self.db = db
    
    async def callback(self, interaction: discord.Interaction):
        """Reabre um ticket fechado."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Apenas administradores podem reabrir tickets.",
                ephemeral=True
            )
            return
        
        ticket = await self.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message("❌ Ticket não encontrado.", ephemeral=True)
            return
        
        ticket_id = ticket["id"]
        
        if ticket.get("status") != "closed":
            await interaction.response.send_message(
                "ℹ️ Este ticket já está aberto.",
                ephemeral=True
            )
            return
        
        await self.db.reopen_ticket(ticket_id)
        
        embed = discord.Embed(
            title="🔓 Ticket Reaberto",
            description=f"Este ticket foi reaberto por {interaction.user.mention}",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        
        await interaction.response.send_message(embed=embed)
        
        # Atualiza a view para remover o botão de reabertura
        author_id = int(ticket["user_id"])
        view = TicketControlView(self.db, ticket_id, author_id, is_closed=False)
        try:
            # Tenta encontrar a mensagem original com os botões
            async for msg in interaction.channel.history(limit=50):
                if msg.embeds and msg.embeds[0].footer and f"Ticket #{ticket_id}" in str(msg.embeds[0].footer.text):
                    await msg.edit(view=view)
                    break
        except Exception as e:
            LOGGER.warning("Erro ao atualizar view após reabertura: %s", e)


class ConfirmCloseView(discord.ui.View):
    """View de confirmação para fechar ticket."""
    
    def __init__(self, db: Database, ticket_id: int, channel: discord.TextChannel):
        super().__init__(timeout=30)
        self.db = db
        self.ticket_id = ticket_id
        self.channel = channel
    
    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.success, custom_id="ticket_confirm_close_rota40")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirma e fecha o ticket."""
        await interaction.response.defer(ephemeral=True)
        
        # Busca informações do ticket ANTES de gerar a transcrição
        ticket = await self.db.get_ticket_by_channel(self.channel.id)
        
        # Gera transcrição profissional antes de fechar
        messages_data_txt = []  # Para formato TXT
        messages_data_html = []  # Para formato HTML (estruturado)
        
        async for msg in self.channel.history(limit=None, oldest_first=True):
            # Ignora mensagens do sistema
            if msg.type != discord.MessageType.default:
                continue
            
            author_name = str(msg.author)
            author_id = str(msg.author.id)
            timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')
            
            content = msg.content if msg.content else ""
            
            # Adiciona informações sobre embeds
            embed_info = []
            if msg.embeds:
                for embed in msg.embeds:
                    embed_parts = []
                    if embed.title:
                        embed_parts.append(f"Título: {embed.title}")
                    if embed.description:
                        embed_parts.append(f"Descrição: {embed.description[:100]}")
                    if embed_parts:
                        embed_info.append(" | ".join(embed_parts))
            
            # Adiciona informações sobre anexos
            attachments_info = []
            if msg.attachments:
                for att in msg.attachments:
                    attachments_info.append(f"{att.filename} ({att.size} bytes)")
            
            # Formata a linha da mensagem para TXT
            message_line = f"[{timestamp}] {author_name} ({author_id})"
            if content:
                message_line += f": {content}"
            if embed_info:
                message_line += f"\n  [Embed: {'; '.join(embed_info)}]"
            if attachments_info:
                message_line += f"\n  [Anexos: {', '.join(attachments_info)}]"
            
            messages_data_txt.append(message_line)
            
            # Dados estruturados para HTML
            messages_data_html.append({
                'author': author_name,
                'author_id': author_id,
                'timestamp': timestamp,
                'content': content,
                'embed_info': embed_info,
                'attachments_info': attachments_info,
            })
        
        # Busca informações do ticket para a transcrição
        topic_name = "N/A"
        claimed_by = None
        if ticket:
            if ticket.get("topic_id"):
                topic = await self.db.get_ticket_topic(ticket["topic_id"])
                if topic:
                    topic_name = topic.get("name", "N/A")
            if ticket.get("claimed_by"):
                claimed_by = ticket["claimed_by"]
        
        # Cria transcrição estilizada
        transcript_lines = [
            "=" * 80,
            f"TRANSCRIÇÃO DE TICKET - {self.channel.name.upper()}",
            "=" * 80,
            "",
            f"Ticket ID: #{self.ticket_id}",
            f"Tópico: {topic_name}",
            f"Canal: {self.channel.name}",
            f"Servidor: {self.channel.guild.name}",
            f"Autor: <@{ticket['user_id']}>" if ticket else "N/A",
            f"Fechado por: {interaction.user} ({interaction.user.id})",
            f"Data de Criação: {self.channel.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Data de Fechamento: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
        ]
        
        if claimed_by:
            claimed_user = interaction.guild.get_member(int(claimed_by))
            if claimed_user:
                transcript_lines.append(f"Atendido por: {claimed_user} ({claimed_by})")
        
        transcript_lines.extend([
            "",
            "-" * 80,
            "HISTÓRICO DE MENSAGENS",
            "-" * 80,
            "",
        ])
        
        transcript_lines.extend(messages_data_txt)
        
        transcript_lines.extend([
            "",
            "-" * 80,
            "FIM DA TRANSCRIÇÃO",
            "-" * 80,
            f"Total de mensagens: {len(messages_data_txt)}",
            f"Gerado em: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "=" * 80,
        ])
        
        transcript = "\n".join(transcript_lines)
        
        # Gera transcrição HTML
        claimed_by_str = None
        if claimed_by:
            try:
                claimed_id = int(claimed_by) if str(claimed_by).isdigit() else None
                claimed_user = interaction.guild.get_member(claimed_id) if claimed_id else None
            except (ValueError, TypeError):
                claimed_user = None
            
            if claimed_user:
                claimed_by_str = str(claimed_user.id)
        
        html_transcript = generate_html_transcript(
            ticket_id=self.ticket_id,
            channel_name=self.channel.name,
            guild_name=self.channel.guild.name,
            user_id=ticket['user_id'] if ticket else "N/A",
            closed_by=str(interaction.user),
            created_at=self.channel.created_at.strftime('%Y-%m-%d %H:%M:%S UTC'),
            closed_at=discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
            topic_name=topic_name,
            claimed_by=claimed_by_str,
            messages_data=messages_data_html,
        )
        
        # Busca canal de logs (ticket já foi buscado acima)
        if ticket:
            try:
                guild_id = int(ticket["guild_id"]) if str(ticket["guild_id"]).isdigit() else None
            except (ValueError, TypeError):
                guild_id = None
            
            if not guild_id:
                LOGGER.warning("Guild ID inválido ao buscar canal de logs")
                settings = {}
            else:
                settings = await self.db.get_ticket_settings(guild_id)
            log_channel_id = settings.get("log_channel_id")
            
            if log_channel_id:
                # Converte ID para int com validação
                try:
                    log_id = int(log_channel_id) if log_channel_id and str(log_channel_id).isdigit() else None
                except (ValueError, TypeError):
                    log_id = None
                
                log_channel = None
                if log_id:
                    log_channel = interaction.guild.get_channel(log_id)
                    if not log_channel:
                        try:
                            log_channel = await interaction.guild.fetch_channel(log_id)
                        except (discord.NotFound, discord.HTTPException):
                            log_channel = None
                
                if log_channel:
                    try:
                        # Cria arquivo TXT em memória
                        transcript_bytes = transcript.encode("utf-8")
                        transcript_file = io.BytesIO(transcript_bytes)
                        file_txt = discord.File(
                            fp=transcript_file,
                            filename=f"transcript-{self.channel.name}-{discord.utils.utcnow().strftime('%Y%m%d-%H%M%S')}.txt"
                        )
                        
                        # Cria arquivo HTML em memória
                        html_bytes = html_transcript.encode("utf-8")
                        html_file = io.BytesIO(html_bytes)
                        file_html = discord.File(
                            fp=html_file,
                            filename=f"transcript-{self.channel.name}-{discord.utils.utcnow().strftime('%Y%m%d-%H%M%S')}.html"
                        )
                        
                        # Prepara informações sobre quem assumiu
                        claimed_info = "Ninguém"
                        if claimed_by:
                            try:
                                claimed_id = int(claimed_by) if str(claimed_by).isdigit() else None
                                claimed_user_obj = interaction.guild.get_member(claimed_id) if claimed_id else None
                                if claimed_user_obj:
                                    claimed_info = f"{claimed_user_obj.mention} ({claimed_user_obj})"
                                else:
                                    claimed_info = f"ID: {claimed_by}"
                            except (ValueError, TypeError):
                                claimed_info = f"ID: {claimed_by}"
                        
                        embed = discord.Embed(
                            title="🔒🎫 Ticket Fechado",
                            description=(
                                f"📝 O ticket `{self.channel.name}` foi fechado por {interaction.user.mention}\n\n"
                                f"📄 As transcrições (TXT e HTML) estão anexadas abaixo."
                            ),
                            color=discord.Color.red(),
                            timestamp=discord.utils.utcnow(),
                        )
                        embed.add_field(name="🆔 Ticket ID", value=f"#{self.ticket_id}", inline=True)
                        embed.add_field(name="🔒 Fechado por", value=f"{interaction.user.mention} ({interaction.user})", inline=True)
                        embed.add_field(name="🙋‍♂️ Assumido por", value=claimed_info, inline=True)
                        if ticket.get("topic_id"):
                            topic = await self.db.get_ticket_topic(ticket["topic_id"])
                            if topic:
                                embed.add_field(name="🎯 Tópico", value=f"{topic.get('emoji', '🎫')} {topic.get('name', 'N/A')}", inline=True)
                        embed.add_field(name="👤 Autor", value=f"<@{ticket['user_id']}>", inline=True)
                        embed.set_footer(text="💼 Sistema de Tickets • Log de Fechamento")
                        await log_channel.send(embed=embed, files=[file_txt, file_html])
                    except Exception as e:
                        LOGGER.error("Erro ao enviar transcrição para canal de logs: %s", e, exc_info=e)
            
            # Envia transcrição ao usuário via DM
            try:
                user_id = int(ticket['user_id']) if str(ticket['user_id']).isdigit() else None
                user = await interaction.guild.fetch_member(user_id) if user_id else None
                if user:
                    try:
                        # Cria arquivos para o usuário
                        transcript_bytes = transcript.encode("utf-8")
                        transcript_file = io.BytesIO(transcript_bytes)
                        file_txt = discord.File(
                            fp=transcript_file,
                            filename=f"transcript-{self.channel.name}-{discord.utils.utcnow().strftime('%Y%m%d-%H%M%S')}.txt"
                        )
                        
                        html_bytes = html_transcript.encode("utf-8")
                        html_file = io.BytesIO(html_bytes)
                        file_html = discord.File(
                            fp=html_file,
                            filename=f"transcript-{self.channel.name}-{discord.utils.utcnow().strftime('%Y%m%d-%H%M%S')}.html"
                        )
                        
                        user_embed = discord.Embed(
                            title="📝✨ Transcrição do Seu Ticket",
                            description=(
                                f"Olá {user.mention}!\n\n"
                                f"Seu ticket **{self.channel.name}** foi fechado.\n\n"
                                f"📄 As transcrições completas estão anexadas abaixo:\n"
                                f"• **TXT**: Formato texto simples\n"
                                f"• **HTML**: Formato visual moderno (abra no navegador)\n\n"
                                f"💡 **Dica:** O arquivo HTML pode ser aberto em qualquer navegador para uma visualização melhor."
                            ),
                            color=discord.Color.blue(),
                            timestamp=discord.utils.utcnow(),
                        )
                        user_embed.add_field(name="🆔 Ticket ID", value=f"#{self.ticket_id}", inline=True)
                        user_embed.add_field(name="🎯 Tópico", value=topic_name, inline=True)
                        user_embed.set_footer(text="💼 Sistema de Tickets • Obrigado por usar nosso serviço!")
                        
                        await user.send(embed=user_embed, files=[file_txt, file_html])
                    except discord.Forbidden:
                        LOGGER.warning("Não foi possível enviar DM ao usuário %s (privacidade)", user.id)
                    except Exception as e:
                        LOGGER.error("Erro ao enviar transcrição ao usuário: %s", e, exc_info=e)
            except (discord.NotFound, discord.HTTPException) as e:
                LOGGER.warning("Usuário não encontrado ou erro ao buscar: %s", e)
        
        # Fecha no banco
        await self.db.close_ticket(self.ticket_id)
        
        # Deleta o canal
        channel_name = self.channel.name
        try:
            await self.channel.delete(reason=f"Ticket fechado por {interaction.user}")
        except Exception as e:
            LOGGER.error("Erro ao deletar canal de ticket: %s", e, exc_info=e)
        
        # Tenta enviar confirmação, mas se o canal já foi deletado, ignora o erro
        try:
            await interaction.followup.send(
                "✅ Ticket fechado e canal deletado.",
                ephemeral=True
            )
        except (discord.HTTPException, discord.NotFound) as e:
            # Canal já foi deletado, não há problema
            pass
        except discord.Forbidden:
            try:
                await interaction.followup.send(
                    "✅ Ticket marcado como fechado, mas não tenho permissão para deletar o canal.",
                    ephemeral=True
                )
            except (discord.HTTPException, discord.NotFound):
                pass
        except discord.NotFound:
            # Canal já foi deletado por outro processo
            LOGGER.warning("Canal de ticket %s já foi deletado", channel_name)
            try:
                await interaction.followup.send(
                    "✅ Ticket fechado.",
                    ephemeral=True
                )
            except (discord.HTTPException, discord.NotFound):
                pass
        except Exception as e:
            LOGGER.error("Erro ao deletar canal de ticket: %s", e, exc_info=e)
            try:
                await interaction.followup.send(
                    "✅ Ticket marcado como fechado, mas ocorreu um erro ao deletar o canal.",
                    ephemeral=True
                )
            except (discord.HTTPException, discord.NotFound):
                pass
    
    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger, custom_id="ticket_cancel_close_rota40")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancela o fechamento."""
        await interaction.response.send_message("❌ Fechamento cancelado.", ephemeral=True)
        self.stop()


class TicketPanelModal(discord.ui.Modal, title="Configurar Painel de Tickets"):
    """Modal para configurar título e descrição do painel."""
    
    panel_title = discord.ui.TextInput(
        label="Título do Painel",
        placeholder="🎫 Sistema de Tickets",
        default="🎫 Sistema de Tickets",
        max_length=256,
        required=True
    )
    
    panel_description = discord.ui.TextInput(
        label="Descrição do Painel",
        placeholder="Clique no botão abaixo para abrir um ticket...",
        default="Clique no botão abaixo para abrir um ticket.\n\nSelecione o tipo de atendimento que você precisa e nossa equipe irá ajudá-lo!",
        style=discord.TextStyle.paragraph,
        max_length=2000,
        required=True
    )
    
    def __init__(self, view: 'TicketSetupView'):
        super().__init__()
        self.setup_view = view
    
    async def on_submit(self, interaction: discord.Interaction):
        self.setup_view.panel_title = self.panel_title.value
        self.setup_view.panel_description = self.panel_description.value
        await interaction.response.defer()
        await self.setup_view.update_embed()


class TicketTopicModal(discord.ui.Modal, title="Criar Tópico de Ticket"):
    """Modal para criar um novo tópico."""
    
    topic_name = discord.ui.TextInput(
        label="Nome do Tópico",
        placeholder="Suporte, Denúncia, etc.",
        max_length=100,
        required=True
    )
    
    topic_description = discord.ui.TextInput(
        label="Descrição",
        placeholder="Descreva o propósito deste tipo de ticket...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True
    )
    
    def __init__(self, view: 'TicketSetupView'):
        super().__init__()
        self.setup_view = view
    
    async def on_submit(self, interaction: discord.Interaction):
        self.setup_view.current_topic_name = self.topic_name.value
        self.setup_view.current_topic_description = self.topic_description.value
        await interaction.response.defer(ephemeral=True)
        await self.setup_view.show_topic_options(interaction)


class TicketSetupView(discord.ui.View):
    """View interativa para configurar o sistema de tickets."""
    
    def __init__(self, bot: commands.Bot, db: Database, guild: discord.Guild, parent_view=None):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = db
        self.guild = guild
        self.parent_view = parent_view
        
        # Adiciona botões "Criar Novo" para cada seletor
        # NOTA: ChannelSelect e RoleSelect ocupam a linha inteira (5 componentes),
        # então os botões "➕ Criar" serão adicionados após todos os selects serem processados
        # Eles serão adicionados dinamicamente na linha 4 junto com os outros botões
        # Para evitar conflitos, vamos adicioná-los depois que os decorators forem processados
        self.create_category_btn = discord.ui.Button(
            label="➕ Criar Categoria",
            style=discord.ButtonStyle.success,
            row=4
        )
        self.create_category_btn.callback = self.create_category
        
        self.create_logs_btn = discord.ui.Button(
            label="➕ Criar Canal Logs",
            style=discord.ButtonStyle.success,
            row=4
        )
        self.create_logs_btn.callback = self.create_log_channel
        
        self.create_ticket_channel_btn = discord.ui.Button(
            label="➕ Criar Canal Tickets",
            style=discord.ButtonStyle.success,
            row=4
        )
        self.create_ticket_channel_btn.callback = self.create_ticket_channel
        
        self.create_staff_role_btn = discord.ui.Button(
            label="➕ Criar Cargo",
            style=discord.ButtonStyle.success,
            row=4
        )
        self.create_staff_role_btn.callback = self.create_staff_role
        
        # NOTA: Os decorators @discord.ui.button são processados quando a classe é definida,
        # então os componentes já estão em self.children quando __init__ é chamado.
        # Vamos adicionar os botões "➕ Criar" apenas se houver espaço na linha 4.
        # Primeiro, vamos contar quantos botões decorados já existem na linha 4
        buttons_row_4 = [child for child in self.children if isinstance(child, discord.ui.Button) and child.row == 4]
        
        # Se houver espaço (menos de 5 botões), adiciona os botões "➕ Criar"
        # Mas vamos ser conservadores e adicionar apenas 1 ou 2 botões para evitar overflow
        remaining_slots = 5 - len(buttons_row_4)
        if remaining_slots >= 1:
            self.add_item(self.create_category_btn)
        if remaining_slots >= 2:
            self.add_item(self.create_logs_btn)
        # Não adicionamos os outros dois botões para evitar overflow
        # Os usuários podem usar os selects para escolher canais/cargos existentes
        
        # Adiciona botão voltar se parent_view existir
        if self.parent_view:
            # Remove o botão "Configurações Avançadas" se existir para dar espaço ao BackButton
            advanced_button = None
            for child in list(self.children):
                if isinstance(child, discord.ui.Button) and child.row == 4:
                    if "Configurações Avançadas" in child.label:
                        advanced_button = child
                        break
            if advanced_button:
                self.remove_item(advanced_button)
            # Verifica se há espaço para o botão voltar
            buttons_row_4_after = [child for child in self.children if isinstance(child, discord.ui.Button) and child.row == 4]
            if len(buttons_row_4_after) < 5:
                self.add_item(BackButton(self.parent_view))
        
        # Estado da configuração
        self.category_id = None
        self.ticket_channel_id = None
        self.log_channel_id = None
        self.max_tickets = 1
        self.global_staff_roles = []  # Lista de IDs de cargos globais
        self.panel_title = "🎫 Sistema de Tickets"
        self.panel_description = "Clique no botão abaixo para abrir um ticket.\n\nSelecione o tipo de atendimento que você precisa e nossa equipe irá ajudá-lo!"
        self.topics = []
        
        # Estado temporário para criação de tópicos
        self.current_topic_name = None
        self.current_topic_description = None
        self.current_topic_emoji = "🎫"
        self.current_topic_color = "primary"
        self.current_topic_id = None
        
        # Mensagem original do embed (para atualização em tempo real)
        self.setup_message: Optional[discord.Message] = None
    
    async def load_existing_settings(self):
        """Carrega todas as configurações existentes do banco de dados."""
        try:
            # Carrega configurações de tickets
            settings = await self.db.get_ticket_settings(self.guild.id)
            if settings:
                if settings.get("category_id"):
                    try:
                        self.category_id = int(settings["category_id"]) if str(settings["category_id"]).isdigit() else None
                    except (ValueError, TypeError):
                        self.category_id = None
                if settings.get("ticket_channel_id"):
                    try:
                        self.ticket_channel_id = int(settings["ticket_channel_id"]) if str(settings["ticket_channel_id"]).isdigit() else None
                    except (ValueError, TypeError):
                        self.ticket_channel_id = None
                if settings.get("log_channel_id"):
                    try:
                        self.log_channel_id = int(settings["log_channel_id"]) if str(settings["log_channel_id"]).isdigit() else None
                    except (ValueError, TypeError):
                        self.log_channel_id = None
                if settings.get("max_tickets_per_user"):
                    self.max_tickets = int(settings["max_tickets_per_user"])
                if settings.get("global_staff_roles"):
                    # Converte string separada por vírgulas para lista de IDs com validação
                    roles_str = settings["global_staff_roles"]
                    if roles_str:
                        self.global_staff_roles = []
                        for role_id_str in roles_str.split(","):
                            role_id_clean = role_id_str.strip()
                            if role_id_clean:
                                try:
                                    role_id = int(role_id_clean) if str(role_id_clean).isdigit() else None
                                    if role_id:
                                        self.global_staff_roles.append(role_id)
                                except (ValueError, TypeError):
                                    continue
            
            # Carrega tópicos existentes
            existing_topics = await self.db.get_ticket_topics(self.guild.id)
            self.topics = [dict(topic) for topic in existing_topics]
        except Exception as e:
            LOGGER.error("Erro ao carregar configurações existentes: %s", e, exc_info=e)
    
    async def update_embed(self):
        """Atualiza o embed com o estado atual."""
        # Cores modernas e vibrantes
        colors = [
            discord.Color.blue(),
            discord.Color.purple(),
            discord.Color.magenta(),
            discord.Color.blue(),
        ]
        color = colors[len(self.topics) % len(colors)]
        
        embed = discord.Embed(
            title="🎫⚙️ Configuração de Tickets",
            description="✨ Configure o sistema de tickets usando os componentes abaixo.\n\n💡 **Dica:** Use os botões ➕ para criar novos canais ou selecione existentes.",
            color=color
        )
        
        # Status da configuração com emojis
        status = []
        
        # Verifica categoria com conversão segura e fallback
        if self.category_id:
            try:
                cat_id = int(self.category_id) if self.category_id and str(self.category_id).isdigit() else None
            except (ValueError, TypeError):
                cat_id = None
            
            category = None
            if cat_id:
                category = self.guild.get_channel(cat_id)
                if not category or not isinstance(category, discord.CategoryChannel):
                    try:
                        fetched = await self.guild.fetch_channel(cat_id)
                        if isinstance(fetched, discord.CategoryChannel):
                            category = fetched
                    except (discord.NotFound, discord.HTTPException):
                        category = None
            
            if category:
                status.append(f"📁 **Categoria:** <#{cat_id}>")
            else:
                status.append(f"📁 **Categoria:** ⚠️ Categoria configurada não encontrada (ID: {self.category_id})")
        else:
            status.append(f"📁 **Categoria:** ❌ Não configurada")
        
        # Verifica canal de logs com conversão segura e fallback
        if self.log_channel_id:
            try:
                log_id = int(self.log_channel_id) if self.log_channel_id and str(self.log_channel_id).isdigit() else None
            except (ValueError, TypeError):
                log_id = None
            
            log_channel = None
            if log_id:
                log_channel = self.guild.get_channel(log_id)
                if not log_channel:
                    try:
                        log_channel = await self.guild.fetch_channel(log_id)
                    except (discord.NotFound, discord.HTTPException):
                        log_channel = None
            
            if log_channel:
                status.append(f"📜 **Canal de Logs:** <#{log_id}>")
            else:
                status.append(f"📜 **Canal de Logs:** ⚠️ Canal configurado não encontrado (ID: {self.log_channel_id})")
        else:
            status.append(f"📜 **Canal de Logs:** ❌ Não configurado")
        
        # Verifica canal de tickets com conversão segura e fallback
        if self.ticket_channel_id:
            try:
                ticket_id = int(self.ticket_channel_id) if self.ticket_channel_id and str(self.ticket_channel_id).isdigit() else None
            except (ValueError, TypeError):
                ticket_id = None
            
            channel = None
            if ticket_id:
                channel = self.guild.get_channel(ticket_id)
                if not channel:
                    try:
                        channel = await self.guild.fetch_channel(ticket_id)
                    except (discord.NotFound, discord.HTTPException):
                        channel = None
            
            if channel:
                status.append(f"🎟️ **Canal de Tickets:** <#{ticket_id}>")
            else:
                status.append(f"🎟️ **Canal de Tickets:** ⚠️ Canal configurado não encontrado (ID: {self.ticket_channel_id})")
        else:
            status.append(f"🎟️ **Canal de Tickets:** ❌ Não configurado")
        
        # Verifica cargos globais com conversão segura e fallback
        if self.global_staff_roles:
            valid_roles = []
            for role_id in self.global_staff_roles[:5]:
                try:
                    r_id = int(role_id) if role_id and str(role_id).isdigit() else None
                    if r_id:
                        role = self.guild.get_role(r_id)
                        if not role:
                            try:
                                role = await self.guild.fetch_role(r_id)
                            except (discord.NotFound, discord.HTTPException):
                                role = None
                        if role:
                            valid_roles.append(f"<@&{r_id}>")
                except (ValueError, TypeError):
                    continue
            
            if valid_roles:
                roles_mentions = ", ".join(valid_roles)
                if len(self.global_staff_roles) > 5:
                    roles_mentions += f" e mais {len(self.global_staff_roles) - 5}"
                status.append(f"👮 **Cargos Globais:** {roles_mentions}")
            else:
                status.append(f"👮 **Cargos Globais:** ⚠️ Cargos configurados não encontrados")
        else:
            status.append(f"👮 **Cargos Globais:** ⚠️ Nenhum configurado")
        
        status.append(f"🔢 **Limite por usuário:** {self.max_tickets} ticket(s)")
        status.append(f"📝 **Tópicos criados:** {len(self.topics)}")
        
        embed.add_field(name="📊 Status da Configuração", value="\n".join(status), inline=False)
        
        if self.topics:
            topics_lines = []
            for t in self.topics[:10]:
                topic_id = t.get('id')
                # Carrega cargos do tópico
                topic_roles = []
                if topic_id:
                    try:
                        role_ids = await self.db.get_topic_roles(topic_id)
                        if role_ids:
                            # Limita a 3 cargos para não ficar muito longo
                            role_mentions = [f"<@&{role_id}>" for role_id in role_ids[:3]]
                            if len(role_ids) > 3:
                                role_mentions.append(f"e mais {len(role_ids) - 3}")
                            topic_roles = ", ".join(role_mentions)
                    except Exception as e:
                        LOGGER.warning("Erro ao carregar cargos do tópico %s: %s", topic_id, e)
                
                topic_line = f"{t.get('emoji', '🎫')} **{t['name']}** - {t.get('description', '')[:50]}..."
                if topic_roles:
                    topic_line += f"\n   └ 👮 Cargos: {topic_roles}"
                else:
                    topic_line += "\n   └ 👮 Cargos: ⚠️ Nenhum configurado"
                topics_lines.append(topic_line)
            
            topics_text = "\n\n".join(topics_lines)
            embed.add_field(name="🎯 Tópicos Configurados", value=topics_text, inline=False)
        
        embed.set_footer(text="💼 Sistema de Tickets • Configure tudo antes de finalizar")
        
        return embed
    
    async def update_embed_message(self, interaction: discord.Interaction):
        """Atualiza o embed da mensagem original em tempo real."""
        try:
            embed = await self.update_embed()
            if self.setup_message:
                await self.setup_message.edit(embed=embed, view=self)
            elif hasattr(interaction, 'message') and interaction.message:
                await interaction.message.edit(embed=embed, view=self)
        except (discord.NotFound, discord.Forbidden, AttributeError) as e:
            LOGGER.warning("Não foi possível atualizar o embed: %s", e)
    
    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Selecione a categoria para tickets...",
        channel_types=[discord.ChannelType.category],
        min_values=0,
        max_values=1,
        row=0
    )
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        """Seleciona a categoria para os tickets."""
        if select.values:
            self.category_id = select.values[0].id
            await interaction.response.send_message(
                f"✅ Categoria selecionada: {select.values[0].mention}",
                ephemeral=True
            )
        else:
            self.category_id = None
            await interaction.response.send_message(
                "❌ Categoria removida.",
                ephemeral=True
            )
        # Atualiza o embed em tempo real
        await self.update_embed_message(interaction)
    
    async def create_category(self, interaction: discord.Interaction):
        """Abre modal para criar categoria."""
        async def on_success(inter: discord.Interaction, category: discord.CategoryChannel):
            self.category_id = category.id
            await self.db.upsert_ticket_settings(self.guild.id, category_id=category.id)
            LOGGER.info(f"Categoria '{category.name}' criada e configurada para tickets no guild {self.guild.id}")
            await self.update_embed_message(inter)
        
        modal = CreateCategoryModal(guild=self.guild, on_success=on_success)
        await interaction.response.send_modal(modal)
    
    async def create_log_channel(self, interaction: discord.Interaction):
        """Abre modal para criar canal de logs."""
        async def on_success(inter: discord.Interaction, channel: discord.TextChannel):
            self.log_channel_id = channel.id
            await self.db.upsert_ticket_settings(self.guild.id, log_channel_id=channel.id)
            LOGGER.info(f"Canal de logs '{channel.name}' criado e configurado para tickets no guild {self.guild.id}")
            await self.update_embed_message(inter)
        
        modal = CreateChannelModal(
            guild=self.guild,
            title="Criar Canal de Logs",
            channel_name_label="Nome do Canal de Logs",
            on_success=on_success
        )
        await interaction.response.send_modal(modal)
    
    async def create_ticket_channel(self, interaction: discord.Interaction):
        """Abre modal para criar canal de tickets."""
        async def on_success(inter: discord.Interaction, channel: discord.TextChannel):
            self.ticket_channel_id = channel.id
            await self.db.upsert_ticket_settings(self.guild.id, ticket_channel_id=channel.id)
            LOGGER.info(f"Canal de tickets '{channel.name}' criado e configurado no guild {self.guild.id}")
            await self.update_embed_message(inter)
        
        modal = CreateChannelModal(
            guild=self.guild,
            title="Criar Canal de Tickets",
            channel_name_label="Nome do Canal de Tickets",
            on_success=on_success
        )
        await interaction.response.send_modal(modal)
    
    async def create_staff_role(self, interaction: discord.Interaction):
        """Abre modal para criar cargo de staff."""
        async def on_success(inter: discord.Interaction, role: discord.Role):
            if role.id not in self.global_staff_roles:
                self.global_staff_roles.append(role.id)
            # Atualiza no banco
            roles_str = ",".join(str(rid) for rid in self.global_staff_roles)
            await self.db.upsert_ticket_settings(self.guild.id, global_staff_roles=roles_str)
            LOGGER.info(f"Cargo de staff '{role.name}' criado e adicionado aos globais no guild {self.guild.id}")
            await self.update_embed_message(inter)
        
        modal = CreateRoleModal(guild=self.guild, on_success=on_success)
        await interaction.response.send_modal(modal)
    
    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Selecione o canal de logs...",
        channel_types=[discord.ChannelType.text],
        min_values=0,
        max_values=1,
        row=1
    )
    async def select_log_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        """Seleciona o canal de logs."""
        if select.values:
            self.log_channel_id = select.values[0].id
            await interaction.response.send_message(
                f"✅ Canal de logs selecionado: {select.values[0].mention}",
                ephemeral=True
            )
        else:
            self.log_channel_id = None
            await interaction.response.send_message(
                "❌ Canal de logs removido.",
                ephemeral=True
            )
        # Atualiza o embed em tempo real
        await self.update_embed_message(interaction)
    
    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Selecione o canal de tickets (painel)...",
        channel_types=[discord.ChannelType.text],
        min_values=0,
        max_values=1,
        row=2
    )
    async def select_ticket_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        """Seleciona o canal onde o painel de tickets será exibido."""
        if select.values:
            self.ticket_channel_id = select.values[0].id
            await interaction.response.send_message(
                f"✅ Canal de tickets selecionado: {select.values[0].mention}",
                ephemeral=True
            )
        else:
            self.ticket_channel_id = None
            await interaction.response.send_message(
                "❌ Canal de tickets removido.",
                ephemeral=True
            )
        # Atualiza o embed em tempo real
        await self.update_embed_message(interaction)
    
    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Selecione os cargos de staff globais...",
        min_values=0,
        max_values=25,
        row=3
    )
    async def select_global_staff_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        """Seleciona cargos globais de staff que terão acesso a todos os tickets."""
        if select.values:
            self.global_staff_roles = [role.id for role in select.values]
            roles_mentions = ", ".join([role.mention for role in select.values[:5]])
            if len(select.values) > 5:
                roles_mentions += f" e mais {len(select.values) - 5} cargo(s)"
            await interaction.response.send_message(
                f"✅ Cargos globais selecionados: {roles_mentions}",
                ephemeral=True
            )
        else:
            self.global_staff_roles = []
            await interaction.response.send_message(
                "❌ Cargos globais removidos.",
                ephemeral=True
            )
        # Atualiza o embed em tempo real
        await self.update_embed_message(interaction)
    
    @discord.ui.button(label="📝 Configurar Painel", style=discord.ButtonStyle.primary, emoji="✨", row=4)
    async def configure_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre modal para configurar título e descrição do painel."""
        modal = TicketPanelModal(self)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="➕ Adicionar Tópico", style=discord.ButtonStyle.success, emoji="🎯", row=4)
    async def add_topic(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre modal para criar um novo tópico."""
        modal = TicketTopicModal(self)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🔢 Limite de Tickets", style=discord.ButtonStyle.secondary, emoji="⚙️", row=4)
    async def set_limit(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Define o limite de tickets por usuário."""
        class LimitModal(discord.ui.Modal, title="Limite de Tickets"):
            limit = discord.ui.TextInput(
                label="Quantos tickets por usuário?",
                placeholder="1",
                default="1",
                max_length=2,
                required=True
            )
            
            def __init__(self, setup_view):
                super().__init__()
                self.setup_view = setup_view
            
            async def on_submit(self, interaction: discord.Interaction):
                try:
                    limit = int(self.limit.value)
                    if limit < 1:
                        limit = 1
                    self.setup_view.max_tickets = limit
                    await interaction.response.send_message(
                        f"✅ Limite definido: {limit} ticket(s) por usuário",
                        ephemeral=True
                    )
                    # Atualiza o embed após definir limite
                    await self.setup_view.update_embed_message(interaction)
                except ValueError:
                    await interaction.response.send_message(
                        "❌ Valor inválido. Use um número.",
                        ephemeral=True
                    )
        
        modal = LimitModal(self)
        await interaction.response.send_modal(modal)
    
    async def show_topic_options(self, interaction: discord.Interaction):
        """Mostra opções de emoji e cor para o tópico atual."""
        embed = discord.Embed(
            title="🎨✨ Configurar Tópico",
            description=f"**{self.current_topic_name}**\n\n📝 {self.current_topic_description}\n\n🎯 Selecione o emoji e a cor do botão abaixo:",
            color=discord.Color.purple()
        )
        embed.add_field(name="😀 Emoji atual", value=self.current_topic_emoji, inline=True)
        embed.add_field(name="🎨 Cor atual", value=self.current_topic_color.title(), inline=True)
        embed.set_footer(text="💡 Selecione o emoji e a cor, depois confirme o tópico")
        
        view = TopicOptionsView(self)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="⚙️ Configurações Avançadas", style=discord.ButtonStyle.secondary, emoji="🔧", row=4)
    async def advanced_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre menu de configurações avançadas."""
        class AdvancedSettingsView(discord.ui.View):
            def __init__(self, setup_view):
                super().__init__(timeout=300)
                self.setup_view = setup_view
            
            @discord.ui.button(label="🗑️ Limpar Configurações", style=discord.ButtonStyle.danger, emoji="⚠️", row=0)
            async def clear_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
                """Limpa todas as configurações de tickets."""
                embed = discord.Embed(
                    title="⚠️ Confirmar Limpeza de Configurações",
                    description=(
                        "Tem certeza que deseja **LIMPAR TODAS** as configurações de tickets?\n\n"
                        "❌ Isso irá deletar:\n"
                        "• Todas as configurações (categoria, canais, limites)\n"
                        "• Todos os tópicos criados\n"
                        "• Cargos globais configurados\n\n"
                        "⚠️ **Esta ação não pode ser desfeita!**"
                    ),
                    color=discord.Color.red()
                )
                
                view = ConfirmClearSettingsView(self.setup_view)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
            @discord.ui.button(label="📊 Gerenciar Históricos", style=discord.ButtonStyle.secondary, emoji="🗂️", row=0)
            async def manage_history(self, interaction: discord.Interaction, button: discord.ui.Button):
                """Abre menu para gerenciar históricos de tickets."""
                embed = discord.Embed(
                    title="🗂️ Gerenciar Históricos de Tickets",
                    description="Escolha qual histórico deseja limpar:",
                    color=discord.Color.orange()
                )
                
                view = HistoryManageView(self.setup_view)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
            @discord.ui.button(label="📝 Gerenciar Tópicos", style=discord.ButtonStyle.secondary, emoji="⚙️", row=0)
            async def manage_topics(self, interaction: discord.Interaction, button: discord.ui.Button):
                """Abre menu para editar ou deletar tópicos existentes."""
                if not self.setup_view.topics:
                    await interaction.response.send_message(
                        "❌ Nenhum tópico configurado ainda. Use '➕ Adicionar Tópico' para criar um.",
                        ephemeral=True
                    )
                    return
                
                # Recarrega tópicos do banco para garantir dados atualizados
                existing_topics = await self.setup_view.db.get_ticket_topics(self.setup_view.guild.id)
                self.setup_view.topics = [dict(topic) for topic in existing_topics]
                
                # Cria Select com os tópicos
                options = []
                for topic in self.setup_view.topics[:25]:  # Limite do Discord
                    emoji_str = topic.get("emoji", "🎫")
                    name = topic.get("name", "Sem nome")
                    description = topic.get("description", "")[:100]
                    
                    options.append(
                        discord.SelectOption(
                            label=name,
                            description=description,
                            emoji=emoji_str,
                            value=str(topic["id"]),
                        )
                    )
                
                view = TopicManageView(self.setup_view, options)
                embed = discord.Embed(
                    title="📝⚙️ Gerenciar Tópicos",
                    description="Selecione um tópico para editar ou deletar:",
                    color=discord.Color.blue()
                )
                embed.set_footer(text="💡 Escolha um tópico no menu abaixo")
                
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        embed = discord.Embed(
            title="⚙️🔧 Configurações Avançadas",
            description="Escolha uma opção:",
            color=discord.Color.blue()
        )
        
        view = AdvancedSettingsView(self)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="✅ Finalizar Configuração", style=discord.ButtonStyle.success, row=4)
    async def finish_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Finaliza a configuração e cria o painel."""
        if not self.category_id:
            await interaction.response.send_message(
                "❌ Você precisa selecionar uma categoria primeiro!",
                ephemeral=True
            )
            return
        
        if not self.topics:
            await interaction.response.send_message(
                "❌ Você precisa criar pelo menos um tópico!",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        
        try:
            # Prepara cargos globais como string separada por vírgulas
            global_staff_roles_str = ",".join([str(role_id) for role_id in self.global_staff_roles]) if self.global_staff_roles else None
            
            # Salva configurações no banco (incluindo ticket_channel_id se já foi selecionado)
            await self.db.upsert_ticket_settings(
                self.guild.id,
                category_id=self.category_id,
                ticket_channel_id=self.ticket_channel_id,
                log_channel_id=self.log_channel_id,
                max_tickets_per_user=self.max_tickets,
                global_staff_roles=global_staff_roles_str
            )
            
            # Cria canal de tickets se não existir
            if not self.ticket_channel_id:
                try:
                    # Busca categoria com fallback
                    category = self.guild.get_channel(self.category_id)
                    if not category or not isinstance(category, discord.CategoryChannel):
                        try:
                            category = await self.guild.fetch_channel(self.category_id)
                            if not isinstance(category, discord.CategoryChannel):
                                category = None
                        except (discord.NotFound, discord.HTTPException):
                            category = None
                    
                    ticket_channel = await self.guild.create_text_channel(
                        "🎫-suporte",
                        category=category if isinstance(category, discord.CategoryChannel) else None,
                        reason="Canal criado para painel de tickets"
                    )
                    self.ticket_channel_id = ticket_channel.id
                    await self.db.upsert_ticket_settings(
                        self.guild.id,
                        ticket_channel_id=ticket_channel.id
                    )
                except discord.Forbidden:
                    await interaction.followup.send(
                        "❌ Não tenho permissão para criar canais. Configure manualmente o canal de tickets.",
                        ephemeral=True
                    )
                    return
            
            # Busca canal de tickets com fallback
            channel = self.guild.get_channel(self.ticket_channel_id)
            if not channel:
                try:
                    channel = await self.guild.fetch_channel(self.ticket_channel_id)
                except (discord.NotFound, discord.HTTPException):
                    channel = None
            
            if not channel:
                await interaction.followup.send(
                    "❌ Canal de tickets não encontrado.",
                    ephemeral=True
                )
                return
            
            # Verifica se já existe um painel e deleta
            settings = await self.db.get_ticket_settings(self.guild.id)
            panel_message_id = settings.get("panel_message_id")
            if panel_message_id:
                try:
                    old_message = await channel.fetch_message(int(panel_message_id))
                    await old_message.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass
            
            # Cria embed do painel com design moderno
            embed = discord.Embed(
                title=self.panel_title,
                description=self.panel_description.replace("{max_tickets}", str(self.max_tickets)) if "{max_tickets}" in self.panel_description else self.panel_description,
                color=discord.Color.purple(),
            )
            
            # Lista tópicos com emojis
            topics_text = "\n".join([
                f"{t.get('emoji', '🎫')} **{t['name']}**\n   └ {t.get('description', 'Sem descrição')[:80]}"
                for t in self.topics[:10]  # Limite visual
            ])
            if topics_text:
                embed.add_field(name="🎯 Tipos de Tickets Disponíveis", value=topics_text, inline=False)
            
            # Adiciona informações sobre limite
            embed.add_field(
                name="ℹ️ Informações Importantes",
                value=f"🔢 **Limite:** {self.max_tickets} ticket(s) por usuário\n⏰ **Resposta:** Nossa equipe responderá o mais rápido possível",
                inline=False
            )
            
            embed.set_footer(text="💼 Sistema de Tickets • Clique no botão para começar")
            
            view = TicketOpenView(self.db)
            message = await channel.send(embed=embed, view=view)
            
            # Salva message_id
            await self.db.upsert_ticket_settings(self.guild.id, panel_message_id=message.id)
            
            await interaction.followup.send(
                f"✅✨ Configuração concluída com sucesso!\n\n🎟️ Painel criado em {channel.mention}\n🎯 {len(self.topics)} tópico(s) configurado(s)\n💼 Sistema pronto para uso!",
                ephemeral=False
            )
            
        except Exception as e:
            LOGGER.error("Erro ao finalizar setup: %s", e, exc_info=e)
            await interaction.followup.send(
                f"❌ Erro ao finalizar configuração: {str(e)}",
                ephemeral=True
            )


class TopicOptionsView(discord.ui.View):
    """View para configurar emoji e cor de um tópico."""
    
    def __init__(self, setup_view: TicketSetupView):
        super().__init__(timeout=300)
        self.setup_view = setup_view
    
    @discord.ui.button(label="🎫", style=discord.ButtonStyle.secondary)
    async def emoji_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.setup_view.current_topic_emoji = "🎫"
        await interaction.response.send_message("✅ Emoji selecionado: 🎫", ephemeral=True)
    
    @discord.ui.button(label="💬", style=discord.ButtonStyle.secondary)
    async def emoji_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.setup_view.current_topic_emoji = "💬"
        await interaction.response.send_message("✅ Emoji selecionado: 💬", ephemeral=True)
    
    @discord.ui.button(label="🛟", style=discord.ButtonStyle.secondary)
    async def emoji_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.setup_view.current_topic_emoji = "🛟"
        await interaction.response.send_message("✅ Emoji selecionado: 🛟", ephemeral=True)
    
    @discord.ui.button(label="🔴", style=discord.ButtonStyle.secondary)
    async def emoji_4(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.setup_view.current_topic_emoji = "🔴"
        await interaction.response.send_message("✅ Emoji selecionado: 🔴", ephemeral=True)
    
    @discord.ui.button(label="Verde", style=discord.ButtonStyle.success)
    async def color_green(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.setup_view.current_topic_color = "success"
        await interaction.response.send_message("✅ Cor selecionada: Verde", ephemeral=True)
    
    @discord.ui.button(label="Azul", style=discord.ButtonStyle.primary)
    async def color_blue(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.setup_view.current_topic_color = "primary"
        await interaction.response.send_message("✅ Cor selecionada: Azul", ephemeral=True)
    
    @discord.ui.button(label="Vermelho", style=discord.ButtonStyle.danger)
    async def color_red(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.setup_view.current_topic_color = "danger"
        await interaction.response.send_message("✅ Cor selecionada: Vermelho", ephemeral=True)
    
    @discord.ui.button(label="Cinza", style=discord.ButtonStyle.secondary)
    async def color_gray(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.setup_view.current_topic_color = "secondary"
        await interaction.response.send_message("✅ Cor selecionada: Cinza", ephemeral=True)
    
    @discord.ui.button(label="✅ Confirmar Tópico", style=discord.ButtonStyle.success, row=2)
    async def confirm_topic(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cria o tópico com as configurações escolhidas."""
        await interaction.response.defer()
        
        # Validação robusta: verifica se o nome do tópico foi definido
        topic_name = self.setup_view.current_topic_name
        if not topic_name or not isinstance(topic_name, str) or not topic_name.strip():
            await interaction.followup.send(
                "❌ Erro: O nome do tópico é obrigatório. Por favor, preencha o nome no modal anterior.",
                ephemeral=True
            )
            return
        
        # Sanitiza valores antes de enviar
        topic_name = topic_name.strip()
        topic_description = (self.setup_view.current_topic_description or "").strip()
        topic_emoji = (self.setup_view.current_topic_emoji or "🎫").strip()
        topic_color = (self.setup_view.current_topic_color or "primary").strip()
        
        try:
            topic_id = await self.setup_view.db.create_ticket_topic(
                self.setup_view.guild.id,
                topic_name,  # Já validado e sanitizado
                topic_description,
                topic_emoji,
                topic_color,
            )
            
            self.setup_view.topics.append({
                "id": topic_id,
                "name": topic_name,
                "description": topic_description,
                "emoji": topic_emoji,
            })
            
            # Atualiza o embed após criar o tópico
            await self.setup_view.update_embed_message(interaction)
            
            # Pergunta sobre cargos
            embed = discord.Embed(
                title="👥✨ Configurar Cargos do Tópico",
                description=f"**{topic_name}**\n\n👮 Deseja adicionar cargos de staff para este tópico?\n\n💡 Selecione os cargos abaixo ou clique em 'Pular' para continuar sem cargos específicos.",
                color=discord.Color.blue()
            )
            
            view = RoleConfigView(self.setup_view, topic_id)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
            # Limpa estado temporário
            self.setup_view.current_topic_name = None
            self.setup_view.current_topic_description = None
            
        except Exception as e:
            LOGGER.error("Erro ao criar tópico: %s", e, exc_info=e)
            await interaction.followup.send(
                f"❌ Erro ao criar tópico: {str(e)}",
                ephemeral=True
            )


class TopicManageView(discord.ui.View):
    """View para gerenciar (editar/deletar) tópicos existentes."""
    
    def __init__(self, setup_view: TicketSetupView, options: list):
        super().__init__(timeout=300)
        self.setup_view = setup_view
        self.selected_topic_id = None
        
        # Cria Select com os tópicos
        self.select = discord.ui.Select(
            placeholder="Selecione um tópico para gerenciar...",
            options=options,
            min_values=1,
            max_values=1,
        )
        self.select.callback = self.on_select
        self.add_item(self.select)
    
    async def on_select(self, interaction: discord.Interaction):
        """Quando um tópico é selecionado, mostra opções de editar/deletar."""
        topic_id = int(self.select.values[0])
        self.selected_topic_id = topic_id
        
        # Busca dados do tópico
        topic = await self.setup_view.db.get_ticket_topic(topic_id)
        if not topic:
            await interaction.response.send_message(
                "❌ Tópico não encontrado.",
                ephemeral=True
            )
            return
        
        # Carrega cargos do tópico
        topic_role_ids = await self.setup_view.db.get_topic_roles(topic_id)
        
        embed = discord.Embed(
            title=f"📝⚙️ Gerenciar: {topic.get('emoji', '🎫')} {topic.get('name', 'N/A')}",
            description=f"**Descrição:** {topic.get('description', 'Sem descrição')}\n\nEscolha uma ação:",
            color=discord.Color.blue()
        )
        embed.add_field(name="🎨 Emoji", value=topic.get('emoji', '🎫'), inline=True)
        embed.add_field(name="🎨 Cor", value=topic.get('button_color', 'primary'), inline=True)
        
        # Adiciona cargos configurados
        if topic_role_ids:
            role_mentions = [f"<@&{role_id}>" for role_id in topic_role_ids[:5]]
            if len(topic_role_ids) > 5:
                role_mentions.append(f"e mais {len(topic_role_ids) - 5}")
            embed.add_field(
                name="👮 Cargos Configurados",
                value=", ".join(role_mentions),
                inline=False
            )
        else:
            embed.add_field(
                name="👮 Cargos Configurados",
                value="⚠️ Nenhum cargo configurado",
                inline=False
            )
        
        view = TopicActionView(self.setup_view, topic_id, topic)
        await interaction.response.edit_message(embed=embed, view=view)


class TopicActionView(discord.ui.View):
    """View com ações para editar ou deletar um tópico."""
    
    def __init__(self, setup_view: TicketSetupView, topic_id: int, topic: dict):
        super().__init__(timeout=300)
        self.setup_view = setup_view
        self.topic_id = topic_id
        self.topic = topic
    
    @discord.ui.button(label="✏️ Editar", style=discord.ButtonStyle.primary, emoji="📝", row=0)
    async def edit_topic(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre modal para editar o tópico."""
        modal = EditTopicModal(self.setup_view, self.topic_id, self.topic)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="👮 Gerenciar Cargos", style=discord.ButtonStyle.secondary, emoji="⚙️", row=0)
    async def manage_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre view para gerenciar cargos do tópico."""
        # Carrega cargos atuais
        current_role_ids = await self.setup_view.db.get_topic_roles(self.topic_id)
        
        embed = discord.Embed(
            title=f"👮⚙️ Gerenciar Cargos: {self.topic.get('emoji', '🎫')} {self.topic.get('name', 'N/A')}",
            description="Use o menu abaixo para adicionar ou remover cargos deste tópico.",
            color=discord.Color.blue()
        )
        
        if current_role_ids:
            role_mentions = [f"<@&{role_id}>" for role_id in current_role_ids[:10]]
            if len(current_role_ids) > 10:
                role_mentions.append(f"e mais {len(current_role_ids) - 10}")
            embed.add_field(
                name="👮 Cargos Atuais",
                value=", ".join(role_mentions) if role_mentions else "Nenhum",
                inline=False
            )
        else:
            embed.add_field(
                name="👮 Cargos Atuais",
                value="⚠️ Nenhum cargo configurado",
                inline=False
            )
        
        view = TopicRoleManageView(self.setup_view, self.topic_id, self.topic)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="🗑️ Deletar", style=discord.ButtonStyle.danger, emoji="❌", row=0)
    async def delete_topic(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Deleta o tópico após confirmação."""
        embed = discord.Embed(
            title="⚠️ Confirmar Exclusão",
            description=f"Tem certeza que deseja deletar o tópico **{self.topic.get('name', 'N/A')}**?\n\n❌ Esta ação não pode ser desfeita!",
            color=discord.Color.red()
        )
        
        view = ConfirmDeleteTopicView(self.setup_view, self.topic_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class ConfirmDeleteTopicView(discord.ui.View):
    """View de confirmação para deletar tópico."""
    
    def __init__(self, setup_view: TicketSetupView, topic_id: int):
        super().__init__(timeout=60)
        self.setup_view = setup_view
        self.topic_id = topic_id
    
    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.danger)
    async def confirm_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirma e deleta o tópico."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Deleta do banco
            await self.setup_view.db.delete_ticket_topic(self.topic_id)
            
            # Remove da lista local
            self.setup_view.topics = [t for t in self.setup_view.topics if t.get('id') != self.topic_id]
            
            # Atualiza embed
            await self.setup_view.update_embed_message(interaction)
            
            await interaction.followup.send(
                f"✅ Tópico deletado com sucesso!",
                ephemeral=True
            )
        except Exception as e:
            LOGGER.error("Erro ao deletar tópico: %s", e, exc_info=e)
            await interaction.followup.send(
                f"❌ Erro ao deletar tópico: {str(e)}",
                ephemeral=True
            )
    
    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancela a exclusão."""
        await interaction.response.send_message("❌ Exclusão cancelada.", ephemeral=True)
        self.stop()


class TopicRoleManageView(discord.ui.View):
    """View para gerenciar cargos de um tópico."""
    
    def __init__(self, setup_view: TicketSetupView, topic_id: int, topic: dict):
        super().__init__(timeout=300)
        self.setup_view = setup_view
        self.topic_id = topic_id
        self.topic = topic
    
    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Selecione cargos para adicionar...",
        min_values=0,
        max_values=25,
        row=0
    )
    async def add_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        """Adiciona cargos ao tópico."""
        if not select.values:
            await interaction.response.send_message(
                "❌ Nenhum cargo selecionado.",
                ephemeral=True
            )
            return
        
        added_roles = []
        already_existing = []
        
        for role in select.values:
            try:
                # Verifica se já existe
                existing_roles = await self.setup_view.db.get_topic_roles(self.topic_id)
                if str(role.id) in existing_roles:
                    already_existing.append(role.mention)
                else:
                    await self.setup_view.db.add_topic_role(self.topic_id, role.id)
                    added_roles.append(role.mention)
            except Exception as e:
                LOGGER.error("Erro ao adicionar cargo ao tópico: %s", e, exc_info=e)
        
        message_parts = []
        if added_roles:
            message_parts.append(f"✅ Cargos adicionados: {', '.join(added_roles)}")
        if already_existing:
            message_parts.append(f"ℹ️ Já existiam: {', '.join(already_existing)}")
        
        await interaction.response.send_message(
            "\n".join(message_parts) if message_parts else "❌ Nenhum cargo foi adicionado.",
            ephemeral=True
        )
        
        # Atualiza embed principal
        await self.setup_view.update_embed_message(interaction)
        
        # Atualiza embed atual
        await self.update_role_embed(interaction)
    
    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Selecione cargos para remover...",
        min_values=0,
        max_values=25,
        row=1
    )
    async def remove_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        """Remove cargos do tópico."""
        if not select.values:
            await interaction.response.send_message(
                "❌ Nenhum cargo selecionado.",
                ephemeral=True
            )
            return
        
        removed_roles = []
        not_found = []
        
        for role in select.values:
            try:
                # Verifica se existe
                existing_roles = await self.setup_view.db.get_topic_roles(self.topic_id)
                if str(role.id) not in existing_roles:
                    not_found.append(role.mention)
                else:
                    await self.setup_view.db.remove_topic_role(self.topic_id, role.id)
                    removed_roles.append(role.mention)
            except Exception as e:
                LOGGER.error("Erro ao remover cargo do tópico: %s", e, exc_info=e)
        
        message_parts = []
        if removed_roles:
            message_parts.append(f"✅ Cargos removidos: {', '.join(removed_roles)}")
        if not_found:
            message_parts.append(f"ℹ️ Não estavam configurados: {', '.join(not_found)}")
        
        await interaction.response.send_message(
            "\n".join(message_parts) if message_parts else "❌ Nenhum cargo foi removido.",
            ephemeral=True
        )
        
        # Atualiza embed principal
        await self.setup_view.update_embed_message(interaction)
        
        # Atualiza embed atual
        await self.update_role_embed(interaction)
    
    async def update_role_embed(self, interaction: discord.Interaction):
        """Atualiza o embed com os cargos atuais."""
        try:
            current_role_ids = await self.setup_view.db.get_topic_roles(self.topic_id)
            
            embed = discord.Embed(
                title=f"👮⚙️ Gerenciar Cargos: {self.topic.get('emoji', '🎫')} {self.topic.get('name', 'N/A')}",
                description="Use os menus abaixo para adicionar ou remover cargos deste tópico.",
                color=discord.Color.blue()
            )
            
            if current_role_ids:
                role_mentions = [f"<@&{role_id}>" for role_id in current_role_ids[:10]]
                if len(current_role_ids) > 10:
                    role_mentions.append(f"e mais {len(current_role_ids) - 10}")
                embed.add_field(
                    name="👮 Cargos Atuais",
                    value=", ".join(role_mentions) if role_mentions else "Nenhum",
                    inline=False
                )
            else:
                embed.add_field(
                    name="👮 Cargos Atuais",
                    value="⚠️ Nenhum cargo configurado",
                    inline=False
                )
            
            if hasattr(interaction, 'message') and interaction.message:
                await interaction.message.edit(embed=embed, view=self)
        except Exception as e:
            LOGGER.warning("Erro ao atualizar embed de cargos: %s", e)


class EditTopicModal(discord.ui.Modal, title="Editar Tópico"):
    """Modal para editar um tópico existente."""
    
    def __init__(self, setup_view: TicketSetupView, topic_id: int, topic: dict):
        super().__init__()
        self.setup_view = setup_view
        self.topic_id = topic_id
        self.topic = topic
        
        # Cria campos com valores atuais
        self.topic_name = discord.ui.TextInput(
            label="Nome do Tópico",
            placeholder="Suporte, Denúncia, etc.",
            default=topic.get('name', ''),
            max_length=100,
            required=True
        )
        
        self.topic_description = discord.ui.TextInput(
            label="Descrição",
            placeholder="Descreva o propósito deste tipo de ticket...",
            default=topic.get('description', ''),
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=False
        )
        
        self.add_item(self.topic_name)
        self.add_item(self.topic_description)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Atualiza o tópico no banco de dados."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Validação
            if not self.topic_name.value or not self.topic_name.value.strip():
                await interaction.followup.send(
                    "❌ O nome do tópico é obrigatório.",
                    ephemeral=True
                )
                return
            
            # Atualiza no banco
            await self.setup_view.db.update_ticket_topic(
                self.topic_id,
                name=self.topic_name.value.strip(),
                description=self.topic_description.value.strip() if self.topic_description.value else "",
            )
            
            # Atualiza na lista local
            for topic in self.setup_view.topics:
                if topic.get('id') == self.topic_id:
                    topic['name'] = self.topic_name.value.strip()
                    topic['description'] = self.topic_description.value.strip() if self.topic_description.value else ""
                    break
            
            # Atualiza embed
            await self.setup_view.update_embed_message(interaction)
            
            await interaction.followup.send(
                f"✅ Tópico **{self.topic_name.value}** atualizado com sucesso!",
                ephemeral=True
            )
        except Exception as e:
            LOGGER.error("Erro ao editar tópico: %s", e, exc_info=e)
            await interaction.followup.send(
                f"❌ Erro ao editar tópico: {str(e)}",
                ephemeral=True
            )


class ConfirmClearSettingsView(discord.ui.View):
    """View de confirmação para limpar todas as configurações."""
    
    def __init__(self, setup_view: TicketSetupView):
        super().__init__(timeout=60)
        self.setup_view = setup_view
    
    @discord.ui.button(label="✅ Confirmar Limpeza", style=discord.ButtonStyle.danger)
    async def confirm_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirma e limpa todas as configurações."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Limpa configurações
            await self.setup_view.db.clear_ticket_settings(self.setup_view.guild.id)
            # Limpa tópicos
            await self.setup_view.db.clear_ticket_topics(self.setup_view.guild.id)
            
            # Reseta estado local
            self.setup_view.category_id = None
            self.setup_view.ticket_channel_id = None
            self.setup_view.log_channel_id = None
            self.setup_view.max_tickets = 1
            self.setup_view.global_staff_roles = []
            self.setup_view.topics = []
            
            # Atualiza embed
            await self.setup_view.update_embed_message(interaction)
            
            await interaction.followup.send(
                "✅ Todas as configurações foram limpas com sucesso!",
                ephemeral=True
            )
        except Exception as e:
            LOGGER.error("Erro ao limpar configurações: %s", e, exc_info=e)
            await interaction.followup.send(
                f"❌ Erro ao limpar configurações: {str(e)}",
                ephemeral=True
            )
    
    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancela a limpeza."""
        await interaction.response.send_message("❌ Limpeza cancelada.", ephemeral=True)
        self.stop()


class HistoryManageView(discord.ui.View):
    """View para gerenciar históricos de tickets."""
    
    def __init__(self, setup_view: TicketSetupView):
        super().__init__(timeout=300)
        self.setup_view = setup_view
    
    @discord.ui.button(label="🗑️ Limpar Todos os Tickets", style=discord.ButtonStyle.danger, row=0)
    async def clear_all_tickets(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Limpa todos os tickets (abertos e fechados)."""
        embed = discord.Embed(
            title="⚠️ Confirmar Limpeza de Todos os Tickets",
            description="Tem certeza que deseja deletar **TODOS** os tickets (abertos e fechados)?\n\n❌ **Esta ação não pode ser desfeita!**",
            color=discord.Color.red()
        )
        view = ConfirmClearAllTicketsView(self.setup_view)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="🔒 Limpar Apenas Fechados", style=discord.ButtonStyle.secondary, row=0)
    async def clear_closed_tickets(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Limpa apenas tickets fechados."""
        embed = discord.Embed(
            title="⚠️ Confirmar Limpeza de Tickets Fechados",
            description="Tem certeza que deseja deletar todos os tickets **FECHADOS**?\n\n❌ **Esta ação não pode ser desfeita!**",
            color=discord.Color.orange()
        )
        view = ConfirmClearClosedTicketsView(self.setup_view)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="🔓 Limpar Apenas Abertos", style=discord.ButtonStyle.secondary, row=0)
    async def clear_open_tickets(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Limpa apenas tickets abertos."""
        embed = discord.Embed(
            title="⚠️ Confirmar Limpeza de Tickets Abertos",
            description="Tem certeza que deseja deletar todos os tickets **ABERTOS**?\n\n⚠️ **Atenção:** Isso pode afetar tickets em andamento!\n\n❌ **Esta ação não pode ser desfeita!**",
            color=discord.Color.orange()
        )
        view = ConfirmClearOpenTicketsView(self.setup_view)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class ConfirmClearAllTicketsView(discord.ui.View):
    """Confirmação para limpar todos os tickets."""
    
    def __init__(self, setup_view: TicketSetupView):
        super().__init__(timeout=60)
        self.setup_view = setup_view
    
    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            count = await self.setup_view.db.clear_all_tickets(self.setup_view.guild.id)
            await interaction.followup.send(
                f"✅ {count} ticket(s) deletado(s) com sucesso!",
                ephemeral=True
            )
        except Exception as e:
            LOGGER.error("Erro ao limpar tickets: %s", e, exc_info=e)
            await interaction.followup.send(
                f"❌ Erro ao limpar tickets: {str(e)}",
                ephemeral=True
            )
    
    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Operação cancelada.", ephemeral=True)
        self.stop()


class ConfirmClearClosedTicketsView(discord.ui.View):
    """Confirmação para limpar tickets fechados."""
    
    def __init__(self, setup_view: TicketSetupView):
        super().__init__(timeout=60)
        self.setup_view = setup_view
    
    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            count = await self.setup_view.db.clear_closed_tickets(self.setup_view.guild.id)
            await interaction.followup.send(
                f"✅ {count} ticket(s) fechado(s) deletado(s) com sucesso!",
                ephemeral=True
            )
        except Exception as e:
            LOGGER.error("Erro ao limpar tickets fechados: %s", e, exc_info=e)
            await interaction.followup.send(
                f"❌ Erro ao limpar tickets: {str(e)}",
                ephemeral=True
            )
    
    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Operação cancelada.", ephemeral=True)
        self.stop()


class ConfirmClearOpenTicketsView(discord.ui.View):
    """Confirmação para limpar tickets abertos."""
    
    def __init__(self, setup_view: TicketSetupView):
        super().__init__(timeout=60)
        self.setup_view = setup_view
    
    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            count = await self.setup_view.db.clear_open_tickets(self.setup_view.guild.id)
            await interaction.followup.send(
                f"✅ {count} ticket(s) aberto(s) deletado(s) com sucesso!",
                ephemeral=True
            )
        except Exception as e:
            LOGGER.error("Erro ao limpar tickets abertos: %s", e, exc_info=e)
            await interaction.followup.send(
                f"❌ Erro ao limpar tickets: {str(e)}",
                ephemeral=True
            )
    
    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Operação cancelada.", ephemeral=True)
        self.stop()


class RoleConfigView(discord.ui.View):
    """View para configurar cargos de um tópico."""
    
    def __init__(self, setup_view: TicketSetupView, topic_id: int):
        super().__init__(timeout=300)
        self.setup_view = setup_view
        self.topic_id = topic_id
    
    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Selecione os cargos de staff...",
        min_values=0,
        max_values=25
    )
    async def select_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        """Adiciona cargos ao tópico."""
        await interaction.response.defer()
        
        try:
            # Remove cargos antigos do tópico
            # (Por simplicidade, vamos adicionar os novos - em produção, você pode querer fazer um replace)
            
            # Adiciona os cargos selecionados
            for role in select.values:
                await self.setup_view.db.add_topic_role(self.topic_id, role.id)
            
            if select.values:
                roles_mention = ", ".join([role.mention for role in select.values])
                await interaction.followup.send(
                    f"✅ Cargos adicionados ao tópico: {roles_mention}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "ℹ️ Nenhum cargo selecionado. O tópico foi criado sem cargos específicos.",
                    ephemeral=True
                )
        except Exception as e:
            LOGGER.error("Erro ao adicionar cargos: %s", e, exc_info=e)
            await interaction.followup.send(
                f"❌ Erro ao adicionar cargos: {str(e)}",
                ephemeral=True
            )
    
    @discord.ui.button(label="⏭️ Pular", style=discord.ButtonStyle.secondary)
    async def skip_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Pula a configuração de cargos."""
        await interaction.response.send_message(
            "ℹ️ Tópico criado sem cargos específicos. Você pode adicionar depois.",
            ephemeral=True
        )


class TicketCog(commands.Cog):
    """Cog para sistema de tickets."""
    
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db
    
    @commands.command(name="ticket_setup")
    @commands.has_permissions(administrator=True)
    async def ticket_setup(self, ctx: commands.Context):
        """Interface interativa para configurar o sistema de tickets."""
        guild = ctx.guild
        if not guild:
            await ctx.reply("Este comando só funciona em servidores.")
            return
        
        # Verifica permissões do bot
        bot_member = guild.me
        if not bot_member.guild_permissions.manage_channels:
            await ctx.reply(
                "❌ Eu preciso da permissão **Gerenciar Canais** para configurar tickets.",
                delete_after=15
            )
            return
        
        if not bot_member.guild_permissions.manage_roles:
            await ctx.reply(
                "❌ Eu preciso da permissão **Gerenciar Cargos** para configurar tickets.",
                delete_after=15
            )
            return
        
        view = TicketSetupView(self.bot, self.db, guild)
        # Carrega TODAS as configurações existentes do banco
        await view.load_existing_settings()
        embed = await view.update_embed()
        
        message = await ctx.reply(embed=embed, view=view)
        view.setup_message = message
    
    @commands.command(name="ticket")
    @commands.has_permissions(administrator=True)
    async def create_ticket_panel(self, ctx: commands.Context):
        """Cria o painel de tickets no canal configurado."""
        guild = ctx.guild
        if not guild:
            await ctx.reply("Este comando só funciona em servidores.")
            return
        
        topics = await self.db.get_ticket_topics(guild.id)
        if not topics:
            await ctx.reply(
                "❌ Nenhum tópico configurado. Use `!ticket_setup` primeiro.",
                delete_after=15
            )
            return
        
        # Busca canal configurado
        settings = await self.db.get_ticket_settings(guild.id)
        ticket_channel_id = settings.get("ticket_channel_id")
        
        if ticket_channel_id:
            try:
                channel_id = int(ticket_channel_id) if str(ticket_channel_id).isdigit() else None
            except (ValueError, TypeError):
                channel_id = None
            
            channel = None
            if channel_id:
                channel = guild.get_channel(channel_id)
                if not channel:
                    try:
                        channel = await guild.fetch_channel(channel_id)
                    except (discord.NotFound, discord.HTTPException):
                        channel = None
            
            if not channel or not isinstance(channel, discord.TextChannel):
                await ctx.reply(
                    "❌ Canal de tickets configurado não encontrado. Use `!ticket_setup` para reconfigurar.",
                    delete_after=15
                )
                return
        else:
            # Se não estiver configurado, usa o canal atual
            channel = ctx.channel
            # Salva o canal
            await self.db.upsert_ticket_settings(guild.id, ticket_channel_id=channel.id)
        
        # Verifica se já existe um painel e deleta a mensagem antiga se necessário
        panel_message_id = settings.get("panel_message_id")
        if panel_message_id:
            try:
                old_message = await channel.fetch_message(int(panel_message_id))
                if old_message:
                    try:
                        await old_message.delete()
                    except discord.NotFound:
                        pass
            except (discord.NotFound, ValueError, discord.Forbidden):
                pass
        
        # Cria embed do painel com design moderno
        embed = discord.Embed(
            title="🎫✨ Sistema de Tickets",
            description=(
                "👋 Bem-vindo ao nosso sistema de tickets!\n\n"
                "🎯 Clique no botão abaixo para abrir um ticket.\n"
                "📝 Selecione o tipo de atendimento que você precisa e nossa equipe irá ajudá-lo!\n\n"
                "💡 **Dica:** Você pode ter até **{max_tickets}** ticket(s) aberto(s) simultaneamente."
            ).format(max_tickets=settings.get("max_tickets_per_user", 1) or 1),
            color=discord.Color.purple(),
        )
        
        # Lista tópicos com emojis
        topics_text = "\n".join([
            f"{topic.get('emoji', '🎫')} **{topic['name']}**\n   └ {topic.get('description', 'Sem descrição')[:80]}"
            for topic in topics[:10]  # Limite visual
        ])
        if topics_text:
            embed.add_field(name="🎯 Tipos de Tickets Disponíveis", value=topics_text, inline=False)
        
        # Adiciona informações sobre limite
        max_tickets = settings.get("max_tickets_per_user", 1) or 1
        embed.add_field(
            name="ℹ️ Informações Importantes",
            value=f"🔢 **Limite:** {max_tickets} ticket(s) por usuário\n⏰ **Resposta:** Nossa equipe responderá o mais rápido possível",
            inline=False
        )
        
        embed.set_footer(text="💼 Sistema de Tickets • Clique no botão para começar")
        
        view = TicketOpenView(self.db)
        message = await channel.send(embed=embed, view=view)
        
        # Salva message_id
        await self.db.upsert_ticket_settings(guild.id, panel_message_id=message.id)
        
        await ctx.reply(f"✅ Painel de tickets criado/atualizado em {channel.mention}!")
    
    @commands.command(name="ticket_stats")
    @commands.has_permissions(administrator=True)
    async def ticket_stats(self, ctx: commands.Context):
        """Exibe estatísticas de tickets do servidor."""
        guild = ctx.guild
        if not guild:
            await ctx.reply("Este comando só funciona em servidores.")
            return
        
        stats = await self.db.get_ticket_stats(guild.id)
        
        embed = discord.Embed(
            title="📊✨ Estatísticas de Tickets",
            description=f"📈 Análise completa do sistema de tickets de **{guild.name}**\n\n💼 Dados atualizados em tempo real",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow(),
        )
        
        embed.add_field(name="📈 Total de Tickets", value=f"**{stats['total']}** tickets", inline=True)
        embed.add_field(name="🟢 Tickets Abertos", value=f"**{stats['open']}** ativos", inline=True)
        embed.add_field(name="🔴 Tickets Fechados", value=f"**{stats['closed']}** resolvidos", inline=True)
        
        if stats["total"] > 0:
            resolution_time = f"⏱️ **{stats['avg_resolution_hours']:.2f} horas**" if stats["avg_resolution_hours"] > 0 else "⏱️ **N/A**"
            embed.add_field(
                name="⏱️ Tempo Médio de Resolução",
                value=resolution_time,
                inline=True
            )
            embed.add_field(
                name="📊 Taxa de Resolução",
                value=f"✅ **{stats['resolution_rate']:.1f}%**",
                inline=True
            )
            embed.add_field(
                name="📉 Taxa de Abertura",
                value=f"🟢 **{100 - stats['resolution_rate']:.1f}%**",
                inline=True
            )
        
        embed.set_footer(text="💼 Sistema de Tickets • Estatísticas em Tempo Real")
        
        await ctx.reply(embed=embed)


async def setup(bot):
    """Função de setup para carregamento da extensão."""
    from db import Database
    
    await bot.add_cog(TicketCog(bot, bot.db))
