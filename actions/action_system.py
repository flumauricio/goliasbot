import logging
import io
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands

from db import Database

LOGGER = logging.getLogger(__name__)

# Views para gerenciar participantes removidos
class RemoveParticipantView(discord.ui.View):
    """View para remover participante."""
    
    def __init__(self, db: Database, action_id: int, action_view, removed_by: int):
        super().__init__(timeout=60)
        self.db = db
        self.action_id = action_id
        self.action_view = action_view
        self.removed_by = removed_by
    
    @discord.ui.select(
        placeholder="Selecione o participante para remover...",
        min_values=1,
        max_values=1,
        row=0
    )
    async def select_participant(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Remove o participante selecionado."""
        if not select.values:
            return
        
        try:
            user_id = int(select.values[0])
            
            # Defer para permitir operações longas
            await interaction.response.defer(ephemeral=True)
            
            await self.db.remove_participant_by_mod(self.action_id, user_id, self.removed_by)
            
            # Atualiza embed principal (sem mensagem ephemeral)
            await self.action_view.update_embed()
            
        except Exception as exc:
            LOGGER.error("Erro ao remover participante: %s", exc, exc_info=True)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ Erro ao remover participante.",
                        ephemeral=True
                    )
            except:
                pass


class RestoreParticipantView(discord.ui.View):
    """View para restaurar participante removido."""
    
    def __init__(self, db: Database, action_id: int, action_view):
        super().__init__(timeout=60)
        self.db = db
        self.action_id = action_id
        self.action_view = action_view
    
    @discord.ui.select(
        placeholder="Selecione o participante para restaurar...",
        min_values=1,
        max_values=1,
        row=0
    )
    async def select_participant(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Restaura o participante selecionado."""
        if not select.values:
            return
        
        try:
            user_id = int(select.values[0])
            await self.db.restore_participant(self.action_id, user_id)
            
            await interaction.response.send_message(
                f"✅ Participante restaurado com sucesso!",
                ephemeral=True
            )
            
            # Atualiza embed
            await self.action_view.update_embed(interaction)
            
        except Exception as exc:
            LOGGER.error("Erro ao restaurar participante: %s", exc, exc_info=True)
            await interaction.response.send_message(
                "❌ Erro ao restaurar participante.",
                ephemeral=True
            )


# FinalValueModal removido - agora usa o valor cadastrado diretamente na ação


def generate_action_transcript_html(
    action: dict,
    participants: list,
    removed_participants: list,
    user_id: int,
    user_earned: float,
    user_stats: Optional[dict],
    guild: Optional[discord.Guild] = None
) -> str:
    """Gera HTML do transcript da ação para um usuário específico."""
    
    # Formata datas
    created_at = action.get("created_at")
    closed_at = action.get("closed_at") or datetime.utcnow()
    
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        except:
            created_at = datetime.utcnow()
    if isinstance(closed_at, str):
        try:
            closed_at = datetime.fromisoformat(closed_at.replace('Z', '+00:00'))
        except:
            closed_at = datetime.utcnow()
    
    created_str = created_at.strftime("%d/%m/%Y %H:%M:%S") if isinstance(created_at, datetime) else "N/A"
    closed_str = closed_at.strftime("%d/%m/%Y %H:%M:%S") if isinstance(closed_at, datetime) else "N/A"
    
    # Informações da ação
    action_name = action.get("type_name", "Ação Desconhecida")
    total_value = action.get("total_value", 0.0)
    participant_count = len(participants)
    rateio = total_value / participant_count if participant_count > 0 else 0
    
    # Stats do usuário
    user_participations = user_stats.get("participations", 0) if user_stats else 0
    user_total_earned = user_stats.get("total_earned", 0.0) if user_stats else 0.0
    
    # Lista de participantes
    participants_html = ""
    for idx, participant in enumerate(participants, 1):
        p_user_id = int(participant["user_id"])
        p_joined_at = participant.get("joined_at", "")
        
        # Formata timestamp
        if isinstance(p_joined_at, str):
            try:
                p_joined_dt = datetime.fromisoformat(p_joined_at.replace('Z', '+00:00'))
                p_joined_str = p_joined_dt.strftime("%d/%m/%Y %H:%M:%S")
            except:
                p_joined_str = p_joined_at
        else:
            p_joined_str = str(p_joined_at)
        
        # Busca nome do usuário
        user_name = f"User {p_user_id}"
        if guild:
            member = guild.get_member(p_user_id)
            if member:
                user_name = member.display_name
        
        is_current_user = p_user_id == user_id
        highlight = 'class="current-user"' if is_current_user else ''
        participants_html += f"""
            <tr {highlight}>
                <td>{idx}</td>
                <td>{user_name}</td>
                <td>{p_joined_str}</td>
                <td>R$ {rateio:,.2f}</td>
            </tr>
        """
    
    # Lista de removidos
    removed_html = ""
    if removed_participants:
        for idx, removed in enumerate(removed_participants, 1):
            r_user_id = int(removed["user_id"])
            r_removed_at = removed.get("removed_at", "")
            
            if isinstance(r_removed_at, str):
                try:
                    r_removed_dt = datetime.fromisoformat(r_removed_at.replace('Z', '+00:00'))
                    r_removed_str = r_removed_dt.strftime("%d/%m/%Y %H:%M:%S")
                except:
                    r_removed_str = r_removed_at
            else:
                r_removed_str = str(r_removed_at)
            
            user_name = f"User {r_user_id}"
            if guild:
                member = guild.get_member(r_user_id)
                if member:
                    user_name = member.display_name
            
            removed_html += f"""
                <tr>
                    <td>{idx}</td>
                    <td>{user_name}</td>
                    <td>{r_removed_str}</td>
                </tr>
            """
    
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transcript - {action_name}</title>
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
            min-height: 100vh;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
        }}
        header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        header h1 {{
            font-size: 2em;
            margin-bottom: 10px;
        }}
        header p {{
            opacity: 0.9;
            font-size: 1.1em;
        }}
        .content {{
            padding: 30px;
        }}
        section {{
            margin-bottom: 30px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
            border-left: 4px solid #667eea;
        }}
        section h2 {{
            color: #667eea;
            margin-bottom: 15px;
            font-size: 1.5em;
        }}
        .info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .info-item {{
            background: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        .info-item strong {{
            display: block;
            color: #667eea;
            margin-bottom: 5px;
            font-size: 0.9em;
        }}
        .info-item span {{
            font-size: 1.2em;
            color: #333;
            font-weight: bold;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        thead {{
            background: #667eea;
            color: white;
        }}
        th {{
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}
        td {{
            padding: 12px;
            border-bottom: 1px solid #e0e0e0;
        }}
        tbody tr:hover {{
            background: #f0f0f0;
        }}
        tbody tr.current-user {{
            background: #e3f2fd;
            font-weight: bold;
        }}
        .user-result {{
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            color: white;
            padding: 25px;
            border-radius: 10px;
            text-align: center;
        }}
        .user-result h2 {{
            color: white;
            margin-bottom: 20px;
        }}
        .user-result .value {{
            font-size: 2.5em;
            font-weight: bold;
            margin: 10px 0;
        }}
        .user-result .stats {{
            margin-top: 20px;
            padding-top: 20px;
            border-top: 2px solid rgba(255,255,255,0.3);
        }}
        .no-data {{
            text-align: center;
            color: #999;
            padding: 20px;
            font-style: italic;
        }}
        @media print {{
            body {{
                background: white;
            }}
            .container {{
                box-shadow: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎯 Transcript da Ação</h1>
            <p>{action_name}</p>
            <p>Criada em: {created_str} | Finalizada em: {closed_str}</p>
        </header>
        
        <div class="content">
            <section class="action-info">
                <h2>📊 Informações da Ação</h2>
                <div class="info-grid">
                    <div class="info-item">
                        <strong>Tipo de Ação</strong>
                        <span>{action_name}</span>
                    </div>
                    <div class="info-item">
                        <strong>Valor Total</strong>
                        <span>R$ {total_value:,.2f}</span>
                    </div>
                    <div class="info-item">
                        <strong>Participantes</strong>
                        <span>{participant_count}</span>
                    </div>
                    <div class="info-item">
                        <strong>Rateio por Player</strong>
                        <span>R$ {rateio:,.2f}</span>
                    </div>
                </div>
            </section>
            
            <section class="participants">
                <h2>✅ Participantes</h2>
                {f'''
                <table>
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Nome</th>
                            <th>Data de Entrada</th>
                            <th>Valor Ganho</th>
                        </tr>
                    </thead>
                    <tbody>
                        {participants_html}
                    </tbody>
                </table>
                ''' if participants_html else '<p class="no-data">Nenhum participante</p>'}
            </section>
            
            {f'''
            <section class="removed">
                <h2>🚫 Participantes Removidos</h2>
                <table>
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Nome</th>
                            <th>Data de Remoção</th>
                        </tr>
                    </thead>
                    <tbody>
                        {removed_html}
                    </tbody>
                </table>
            </section>
            ''' if removed_html else ''}
            
            <section class="user-result">
                <h2>🏆 Seu Resultado</h2>
                <div class="value">R$ {user_earned:,.2f}</div>
                <p>Valor ganho nesta ação</p>
                <div class="stats">
                    <p><strong>Participações Totais:</strong> {user_participations} ações</p>
                    <p><strong>Total Ganho (Geral):</strong> R$ {user_total_earned:,.2f}</p>
                </div>
            </section>
        </div>
    </div>
</body>
</html>"""
    
    return html


async def send_transcript_to_participants(
    action: dict,
    participants: list,
    guild: discord.Guild,
    db: Database,
    bot: commands.Bot
) -> None:
    """Envia transcript HTML via DM para cada participante."""
    if not participants:
        return
    
    # Busca participantes removidos
    # O action dict vem do get_active_action que retorna com "id" como chave
    action_id = action.get("id")
    if not action_id:
        LOGGER.error("Ação sem ID válido para buscar removidos")
        return
    removed_participants = await db.get_removed_participants(action_id)
    
    # Calcula rateio
    total_value = action.get("total_value", 0.0)
    participant_count = len(participants)
    rateio = total_value / participant_count if participant_count > 0 else 0
    
    success_count = 0
    fail_count = 0
    
    for participant in participants:
        try:
            user_id = int(participant["user_id"])
            
            # Busca membro no servidor
            member = guild.get_member(user_id)
            if not member:
                # Tenta buscar via bot
                try:
                    member = await bot.fetch_user(user_id)
                except:
                    LOGGER.warning("Não foi possível encontrar usuário %s para enviar transcript", user_id)
                    fail_count += 1
                    continue
            
            # Busca stats do usuário
            guild_id = int(action.get("guild_id", 0))
            user_stats = await db.get_user_stats(guild_id, user_id)
            
            # Gera HTML personalizado
            html_content = generate_action_transcript_html(
                action,
                participants,
                removed_participants,
                user_id,
                rateio,
                user_stats,
                guild
            )
            
            # Cria arquivo em memória
            html_file = discord.File(
                io.BytesIO(html_content.encode('utf-8')),
                filename=f"transcript_acao_{action_id}_{user_id}.html"
            )
            
            # Cria embed informativo
            embed = discord.Embed(
                title="📄 Transcript da Ação Finalizada",
                description=(
                    f"Olá {member.mention if isinstance(member, discord.Member) else 'usuário'}!\n\n"
                    f"A ação **{action.get('type_name', 'Desconhecida')}** foi finalizada com **Vitória**!\n\n"
                    f"📊 **Seu ganho:** R$ {rateio:,.2f}\n"
                    f"👥 **Total de participantes:** {participant_count}\n\n"
                    f"📄 O transcript completo está anexado abaixo. "
                    f"Abra o arquivo HTML no seu navegador para visualizar todas as informações."
                ),
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(
                name="💰 Valor Total da Ação",
                value=f"R$ {total_value:,.2f}",
                inline=True
            )
            embed.add_field(
                name="📊 Rateio por Player",
                value=f"R$ {rateio:,.2f}",
                inline=True
            )
            embed.set_footer(text=f"Ação ID: {action_id} • Sistema de Ações FiveM")
            
            # Envia via DM
            try:
                if isinstance(member, discord.Member):
                    await member.send(embed=embed, file=html_file)
                else:
                    # Se não for Member, tenta enviar para User
                    user = await bot.fetch_user(user_id)
                    await user.send(embed=embed, file=html_file)
                
                success_count += 1
                LOGGER.info("Transcript enviado com sucesso para usuário %s (ação %s)", user_id, action_id)
                
            except discord.Forbidden:
                LOGGER.warning("Não foi possível enviar DM para usuário %s (privacidade desabilitada)", user_id)
                fail_count += 1
            except Exception as e:
                LOGGER.error("Erro ao enviar transcript para usuário %s: %s", user_id, e, exc_info=True)
                fail_count += 1
                
        except Exception as exc:
            LOGGER.error("Erro ao processar participante %s para transcript: %s", participant.get("user_id"), exc, exc_info=True)
            fail_count += 1
    
    LOGGER.info(
        "Transcripts enviados: %d sucessos, %d falhas (ação %s)",
        success_count,
        fail_count,
        action_id
    )


async def generate_ranking_embed(
    guild_id: int,
    guild: discord.Guild,
    db: Database
) -> discord.Embed:
    """Gera embed do ranking de ações."""
    # Busca ranking (sem limite, todos os usuários)
    ranking = await db.get_action_ranking(guild_id, limit=1000)  # Limite alto para pegar todos
    
    embed = discord.Embed(
        title="🏆 Ranking de Ações",
        description="Ranking baseado em participações e total ganho",
        color=discord.Color.gold(),
        timestamp=discord.utils.utcnow()
    )
    
    if not ranking:
        embed.add_field(
            name="📊 Nenhum participante ainda",
            value="Participe de ações para aparecer no ranking!",
            inline=False
        )
    else:
        # Formata ranking: usuários em linhas, informações em colunas
        medals = ["🥇", "🥈", "🥉"]
        
        # Adiciona informações de membro e ordena com desempate por data de entrada no servidor
        ranking_with_members = []
        for user_stat in ranking:
            user_id = int(user_stat["user_id"])
            member = guild.get_member(user_id) if guild else None
            joined_at = member.joined_at if member and member.joined_at else None
            ranking_with_members.append({
                "user_stat": user_stat,
                "member": member,
                "joined_at": joined_at,
                "user_id": user_id
            })
        
        # Ordena por participações (DESC), depois por total ganho (DESC), depois por data de entrada (ASC - mais antigo primeiro)
        # O banco já ordena por participations DESC, total_earned DESC, então só precisamos adicionar o desempate por joined_at
        ranking_with_members.sort(
            key=lambda x: (
                -x["user_stat"].get("participations", 0),  # DESC
                -x["user_stat"].get("total_earned", 0.0),  # DESC
                x["joined_at"] if x["joined_at"] else datetime.max  # ASC (mais antigo primeiro para desempate)
            )
        )
        
        # Prepara dados para colunas
        position_user = []  # Coluna 1: Posição + Usuário
        participations = []  # Coluna 2: Ações
        earnings = []  # Coluna 3: Total Ganho
        
        for idx, data in enumerate(ranking_with_members, 1):
            user_stat = data["user_stat"]
            member = data["member"]
            user_id = data["user_id"]
            participations_count = user_stat.get("participations", 0)
            total_earned = user_stat.get("total_earned", 0.0)
            
            # Escolhe emoji de posição (só para os 3 primeiros)
            if idx <= 3:
                position_emoji = medals[idx - 1]
                position_text = f"{position_emoji} {idx}."
            else:
                position_text = f"{idx}."
            
            # Busca nome do usuário
            if member:
                user_mention = member.mention
            else:
                user_mention = f"<@{user_id}>"
            
            # Concatena posição + usuário
            position_user.append(f"{position_text} {user_mention}")
            participations.append(str(participations_count))
            earnings.append(f"R$ {total_earned:,.2f}")
        
        # Adiciona 3 colunas inline
        embed.add_field(
            name="🏆 Posição & Usuário",
            value="\n".join(position_user),
            inline=True
        )
        
        embed.add_field(
            name="📊 Ações",
            value="\n".join(participations),
            inline=True
        )
        
        embed.add_field(
            name="💰 Total Ganho",
            value="\n".join(earnings),
            inline=True
        )
    
    embed.set_footer(text="Atualizado em")
    
    return embed


async def update_ranking_message(
    guild_id: int,
    guild: discord.Guild,
    db: Database,
    bot: commands.Bot
) -> None:
    """Atualiza ou envia mensagem do ranking no canal configurado."""
    try:
        # Busca configurações
        settings = await db.get_action_settings(guild_id)
        ranking_channel_id = settings.get("ranking_channel_id")
        
        if not ranking_channel_id:
            # Canal não configurado, não faz nada
            return
        
        ranking_channel_id = int(ranking_channel_id)
        
        # Busca canal
        channel = guild.get_channel(ranking_channel_id)
        if not channel:
            # Tenta buscar via fetch
            try:
                channel = await bot.fetch_channel(ranking_channel_id)
            except:
                LOGGER.warning("Canal de ranking não encontrado: %s", ranking_channel_id)
                return
        
        if not isinstance(channel, discord.TextChannel):
            LOGGER.warning("Canal de ranking não é um canal de texto: %s", ranking_channel_id)
            return
        
        # Gera embed do ranking
        embed = await generate_ranking_embed(guild_id, guild, db)
        
        # Busca message_id das configurações
        ranking_message_id = settings.get("ranking_message_id")
        
        if ranking_message_id:
            # Tenta editar mensagem existente
            try:
                ranking_message_id = int(ranking_message_id)
                message = await channel.fetch_message(ranking_message_id)
                await message.edit(embed=embed)
                LOGGER.info("Ranking atualizado (mensagem editada): %s", ranking_message_id)
                return
            except discord.NotFound:
                # Mensagem foi deletada, vai enviar nova
                LOGGER.info("Mensagem de ranking não encontrada, enviando nova")
            except Exception as exc:
                LOGGER.error("Erro ao editar mensagem de ranking: %s", exc, exc_info=True)
        
        # Envia nova mensagem
        try:
            message = await channel.send(embed=embed)
            await db.upsert_ranking_message_id(guild_id, message.id)
            LOGGER.info("Nova mensagem de ranking enviada: %s", message.id)
        except Exception as exc:
            LOGGER.error("Erro ao enviar mensagem de ranking: %s", exc, exc_info=True)
    
    except Exception as exc:
        LOGGER.error("Erro ao atualizar ranking: %s", exc, exc_info=True)


class ActionView(discord.ui.View):
    """View persistente para gerenciar uma ação ativa."""
    
    # Referências às classes de view para garantir acesso
    RemoveParticipantView = RemoveParticipantView
    RestoreParticipantView = RestoreParticipantView
    
    def __init__(self, bot: commands.Bot, db: Database, action_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.db = db
        self.action_id = action_id
        # Define custom_ids dinâmicos para os botões
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if "Entrar na Ação" in child.label or "Entrar" in child.label:
                    child.custom_id = f"action_join_{action_id}"
                elif "Sair da Ação" in child.label or "Sair" in child.label:
                    child.custom_id = f"action_leave_{action_id}"
                elif "Abrir Inscrições" in child.label or "Abrir" in child.label:
                    child.custom_id = f"action_open_{action_id}"
                elif "Fechar Inscrições" in child.label or "Fechar" in child.label:
                    child.custom_id = f"action_close_{action_id}"
                elif "Finalizar Vitória" in child.label or "Vitória" in child.label:
                    child.custom_id = f"action_win_{action_id}"
                elif "Finalizar Derrota" in child.label or "Derrota" in child.label:
                    child.custom_id = f"action_defeat_{action_id}"
                elif "Remover Participante" in child.label or "Remover" in child.label:
                    child.custom_id = f"action_remove_{action_id}"
                elif "Restaurar Participante" in child.label or "Restaurar" in child.label:
                    child.custom_id = f"action_restore_{action_id}"
                elif "Cancelar Ação" in child.label or "Cancelar" in child.label:
                    child.custom_id = f"action_cancel_{action_id}"
    
    async def _check_permissions(self, member: discord.Member, action: dict) -> bool:
        """Verifica se o membro tem permissão (admin, criador ou cargo responsável)."""
        if member.guild_permissions.administrator:
            return True
        
        creator_id = int(action.get("creator_id", 0))
        if member.id == creator_id:
            return True
        
        # Verifica múltiplos cargos responsáveis
        responsible_roles = await self.db.get_responsible_roles(member.guild.id)
        for role_id in responsible_roles:
            role = member.guild.get_role(role_id)
            if role and role in member.roles:
                return True
        
        return False
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Verifica permissões antes de processar interações."""
        if not interaction.guild or not interaction.user:
            return False
        
        action = await self.db.get_active_action(self.action_id)
        if not action:
            await interaction.response.send_message(
                "❌ Ação não encontrada.",
                ephemeral=True
            )
            return False
        
        # Verifica qual botão foi clicado
        if isinstance(interaction.data, dict):
            custom_id = interaction.data.get("custom_id", "")
            
            # Botões que requerem permissão de responsável
            admin_buttons = ["open", "close", "win", "defeat", "remove", "restore", "cancel"]
            if any(btn in custom_id for btn in admin_buttons):
                if not await self._check_permissions(interaction.user, action):
                    await interaction.response.send_message(
                        "❌ Você não tem permissão para usar este botão.",
                        ephemeral=True
                    )
                    return False
        
        return True
    
    async def update_embed(
        self,
        interaction: Optional[discord.Interaction] = None,
        final_value: Optional[float] = None,
        result: Optional[str] = None
    ):
        """Atualiza a embed da ação."""
        action = await self.db.get_active_action(self.action_id)
        if not action:
            if interaction:
                await interaction.response.send_message(
                    "❌ Ação não encontrada.",
                    ephemeral=True
                )
            return
        
        participants = await self.db.get_participants(self.action_id)
        participant_count = len(participants)
        
        # Status visual
        status_emoji = {
            "open": "🟢",
            "closed": "🔒",
            "in_progress": "🟡",
            "finished": "✅"
        }
        status_text = {
            "open": "Aberto",
            "closed": "Inscrições Fechadas",
            "in_progress": "Em Progresso",
            "finished": "Finalizado"
        }
        
        status = action.get("status", "open")
        status_display = f"{status_emoji.get(status, '⚪')} {status_text.get(status, status)}"
        
        # Calcula rateio
        total_value = action.get("total_value", 0.0)
        if final_value is not None:
            rateio_value = final_value / participant_count if participant_count > 0 else 0
        else:
            rateio_value = total_value / participant_count if participant_count > 0 else 0
        
        # Constrói embed
        embed = discord.Embed(
            title=f"🎯 {action.get('type_name', 'Ação')}",
            description=f"**Status:** {status_display}",
            color=discord.Color.green() if status == "open" else discord.Color.orange() if status == "closed" else discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="💰 Valor Total",
            value=f"R$ {total_value:,.2f}",
            inline=True
        )
        
        embed.add_field(
            name="👥 Players",
            value=f"{participant_count}/{action.get('max_players', 0)}",
            inline=True
        )
        
        embed.add_field(
            name="📊 Rateio por Player",
            value=f"R$ {rateio_value:,.2f}" if participant_count > 0 else "Aguardando inscritos...",
            inline=True
        )
        
        # Lista de participantes com menções e stats
        if participants:
            mentions_list = []
            guild = interaction.guild if interaction else None
            if not guild and self.bot:
                action_data = await self.db.get_active_action(self.action_id)
                if action_data:
                    guild = self.bot.get_guild(int(action_data.get("guild_id", 0)))
            
            # Separa em colunas: Número, Nome, Participações, Total Ganho
            names_col = []
            participations_col = []
            earnings_col = []
            
            for idx, participant in enumerate(participants, 1):
                user_id = int(participant["user_id"])
                mention = f"<@{user_id}>"
                
                if guild:
                    member = guild.get_member(user_id)
                    if member:
                        mention = member.mention
                
                # Busca stats do usuário
                stats = await self.db.get_user_stats(int(action.get("guild_id", 0)), user_id)
                participations = stats.get("participations", 0) if stats else 0
                total_earned = stats.get("total_earned", 0.0) if stats else 0.0
                
                names_col.append(f"**{idx}.** {mention}")
                participations_col.append(f"📊 {participations}")
                earnings_col.append(f"💰 R$ {total_earned:,.2f}")
            
            # Limita a 15 participantes para não ficar muito longo
            max_display = min(15, len(names_col))
            names_text = "\n".join(names_col[:max_display])
            participations_text = "\n".join(participations_col[:max_display])
            earnings_text = "\n".join(earnings_col[:max_display])
            
            if len(names_col) > max_display:
                names_text += f"\n*+ {len(names_col) - max_display} mais*"
                participations_text += "\n..."
                earnings_text += "\n..."
            
            # Adiciona campos em colunas
            embed.add_field(
                name=f"✅ Inscritos ({participant_count})",
                value=names_text if names_col else "Nenhum inscrito",
                inline=True
            )
            embed.add_field(
                name="📊 Participações",
                value=participations_text if participations_col else "-",
                inline=True
            )
            embed.add_field(
                name="💰 Total Ganho",
                value=earnings_text if earnings_col else "-",
                inline=True
            )
            
            # Lista de removidos
            removed = await self.db.get_removed_participants(self.action_id)
            if removed:
                removed_list = []
                for idx, removed_user in enumerate(removed, 1):
                    user_id = int(removed_user["user_id"])
                    mention = f"<@{user_id}>"
                    if guild:
                        member = guild.get_member(user_id)
                        if member:
                            mention = member.mention
                    removed_list.append(f"**{idx}.** {mention}")
                
                removed_text = "\n".join(removed_list[:10])
                if len(removed_list) > 10:
                    removed_text += f"\n*+ {len(removed_list) - 10} mais*"
                
                embed.add_field(
                    name=f"🚫 Removidos ({len(removed)})",
                    value=removed_text,
                    inline=False
                )
        else:
            embed.add_field(
                name="✅ Inscritos",
                value="Nenhum inscrito",
                inline=False
            )
        
        # Status de inscrições
        registrations_open = bool(action.get("registrations_open", 0))
        if not registrations_open:
            embed.add_field(
                name="🔒 Status de Inscrições",
                value="**Fechadas** - Aguarde o responsável abrir",
                inline=False
            )
        
        # Resultado final (se finalizado)
        if result == "victory" and final_value is not None:
            embed.add_field(
                name="🏆 Resultado Final",
                value=(
                    f"**Vitória!**\n"
                    f"Valor Final: R$ {final_value:,.2f}\n"
                    f"Rateio: R$ {rateio_value:,.2f} por player"
                ),
                inline=False
            )
        elif result == "defeat":
            embed.add_field(
                name="💀 Resultado Final",
                value="**Derrota**\nNenhum valor ganho.",
                inline=False
            )
        
        embed.set_footer(text=f"Ação ID: {self.action_id}")
        
        # Se a ação foi finalizada, remove todos os botões (view=None)
        is_finished = result in ("victory", "defeat") or action.get("status") == "finished"
        view_to_use = None if is_finished else self
        
        # Atualiza botões baseado no status (só se não estiver finalizada)
        if not is_finished:
            user_id = interaction.user.id if interaction and interaction.user else None
            await self._update_buttons(action, participant_count, user_id)
        
        # Atualiza mensagem
        try:
            if interaction:
                if interaction.response.is_done():
                    # Resposta já foi enviada ou deferida, tenta editar mensagem original
                    try:
                        message = await interaction.original_response()
                        await message.edit(embed=embed, view=view_to_use)
                    except (discord.NotFound, AttributeError):
                        # Tenta buscar mensagem pelo channel e message_id
                        action_data = await self.db.get_active_action(self.action_id)
                        if action_data:
                            message_id = action_data.get("message_id")
                            channel_id = action_data.get("channel_id")
                            if message_id and channel_id and str(message_id).isdigit() and str(channel_id).isdigit():
                                channel = interaction.guild.get_channel(int(channel_id))
                                if channel:
                                    message = await channel.fetch_message(int(message_id))
                                    await message.edit(embed=embed, view=view_to_use)
                else:
                    # Tenta editar a mensagem original da interação
                    try:
                        await interaction.response.edit_message(embed=embed, view=view_to_use)
                    except discord.InteractionResponded:
                        # Se já foi respondida, busca a mensagem pelo message_id
                        action_data = await self.db.get_active_action(self.action_id)
                        if action_data:
                            message_id = action_data.get("message_id")
                            channel_id = action_data.get("channel_id")
                            if message_id and channel_id and str(message_id).isdigit() and str(channel_id).isdigit():
                                channel = interaction.guild.get_channel(int(channel_id))
                                if channel:
                                    message = await channel.fetch_message(int(message_id))
                                    await message.edit(embed=embed, view=view_to_use)
            else:
                # Sem interação, busca mensagem pelo message_id
                action_data = await self.db.get_active_action(self.action_id)
                if action_data:
                    message_id = action_data.get("message_id")
                    channel_id = action_data.get("channel_id")
                    if message_id and channel_id and str(message_id).isdigit() and str(channel_id).isdigit():
                        # Busca o bot para acessar o guild
                        if self.bot:
                            guild = self.bot.get_guild(int(action_data.get("guild_id", 0)))
                            if guild:
                                channel = guild.get_channel(int(channel_id))
                                if channel:
                                    try:
                                        message = await channel.fetch_message(int(message_id))
                                        await message.edit(embed=embed, view=view_to_use)
                                    except discord.NotFound:
                                        LOGGER.warning("Mensagem da ação %s não encontrada", self.action_id)
        except discord.NotFound:
            # Mensagem foi deletada
            LOGGER.warning("Mensagem da ação %s não encontrada", self.action_id)
        except Exception as exc:
            LOGGER.error("Erro ao atualizar embed: %s", exc, exc_info=True)
            if interaction:
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message("⚠️ Erro ao atualizar embed.", ephemeral=True)
                    else:
                        await interaction.followup.send("⚠️ Erro ao atualizar embed.", ephemeral=True)
                except:
                    pass
    
    async def _update_buttons(self, action: dict, participant_count: int, user_id: Optional[int]):
        """Atualiza estado dos botões baseado no status da ação."""
        status = action.get("status", "open")
        max_players = action.get("max_players", 0)
        registrations_open = bool(action.get("registrations_open", 0))
        
        # Verifica se usuário está inscrito
        is_participant = False
        if user_id:
            participants = await self.db.get_participants(self.action_id)
            user_id_str = str(user_id)
            is_participant = any(p["user_id"] == user_id_str for p in participants)
        
        # Encontra botões
        join_btn = None
        leave_btn = None
        open_btn = None
        close_btn = None
        win_btn = None
        defeat_btn = None
        remove_btn = None
        restore_btn = None
        cancel_btn = None
        
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id and "join" in child.custom_id:
                    join_btn = child
                elif child.custom_id and "leave" in child.custom_id:
                    leave_btn = child
                elif child.custom_id and "open" in child.custom_id:
                    open_btn = child
                elif child.custom_id and "close" in child.custom_id:
                    close_btn = child
                elif child.custom_id and "win" in child.custom_id:
                    win_btn = child
                elif child.custom_id and "defeat" in child.custom_id:
                    defeat_btn = child
                elif child.custom_id and "remove" in child.custom_id:
                    remove_btn = child
                elif child.custom_id and "restore" in child.custom_id:
                    restore_btn = child
                elif child.custom_id and "cancel" in child.custom_id:
                    cancel_btn = child
        
        # Desabilita todos se finalizado
        if status == "finished":
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
            return
        
        # Estado inicial: inscrições fechadas
        # - Entrar: desabilitado
        # - Sair: desabilitado
        # - Abrir Inscrições: habilitado (apenas para responsáveis)
        # - Fechar Inscrições: desabilitado
        # - Finalizar Vitória: desabilitado
        # - Finalizar Derrota: desabilitado
        # - Cancelar: habilitado (apenas para responsáveis)
        
        if not registrations_open:
            # Inscrições fechadas
            if join_btn:
                join_btn.disabled = True
            if leave_btn:
                leave_btn.disabled = True
            if open_btn:
                # Habilitado apenas para responsáveis (verificação no handler)
                open_btn.disabled = False
            if close_btn:
                close_btn.disabled = True
            if win_btn:
                # Habilitado apenas para responsáveis quando inscrições fechadas (verificação no handler)
                win_btn.disabled = False
            if defeat_btn:
                # Habilitado apenas para responsáveis quando inscrições fechadas (verificação no handler)
                defeat_btn.disabled = False
            if remove_btn:
                # Habilitado apenas para responsáveis quando inscrições fechadas (verificação no handler)
                remove_btn.disabled = False
            if restore_btn:
                # Habilitado apenas para responsáveis quando inscrições fechadas (verificação no handler)
                restore_btn.disabled = False
            if cancel_btn:
                # Habilitado apenas para responsáveis (verificação no handler)
                cancel_btn.disabled = False
        else:
            # Inscrições abertas
            if join_btn:
                # Habilitado se não está cheio e usuário não está inscrito
                # Não desabilita após clicar, apenas quando ação estiver cheia ou inscrições fecharem
                join_btn.disabled = (
                    status != "open" or 
                    participant_count >= max_players
                )
            if leave_btn:
                # Habilitado apenas se usuário estiver inscrito
                leave_btn.disabled = not (is_participant and status == "open")
            if open_btn:
                open_btn.disabled = True
            if close_btn:
                # Habilitado apenas para responsáveis (verificação no handler)
                close_btn.disabled = False
            if win_btn:
                # Desabilitado quando inscrições estão abertas
                win_btn.disabled = True
            if defeat_btn:
                # Desabilitado quando inscrições estão abertas
                defeat_btn.disabled = True
            if remove_btn:
                # Habilitado apenas para responsáveis quando inscrições abertas (verificação no handler)
                remove_btn.disabled = False
            if restore_btn:
                # Habilitado apenas para responsáveis quando inscrições abertas (verificação no handler)
                restore_btn.disabled = False
            if cancel_btn:
                # Habilitado apenas para responsáveis (verificação no handler)
                cancel_btn.disabled = False
    
    def _get_custom_id(self, prefix: str) -> str:
        """Gera custom_id único para esta ação."""
        return f"{prefix}_{self.action_id}"
    
    @discord.ui.button(
        label="✅ Entrar na Ação",
        style=discord.ButtonStyle.success,
        row=2
    )
    async def join_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Adiciona o usuário à ação."""
        try:
            action = await self.db.get_active_action(self.action_id)
            if not action:
                await interaction.response.send_message(
                    "❌ Ação não encontrada.",
                    ephemeral=True
                )
                return
            
            # Verifica se inscrições estão abertas
            registrations_open = action.get("registrations_open", 0)
            if not registrations_open:
                await interaction.response.send_message(
                    "❌ As inscrições estão fechadas. Aguarde o responsável abrir.",
                    ephemeral=True
                )
                return
            
            # Verifica status
            if action.get("status") != "open":
                await interaction.response.send_message(
                    "❌ As inscrições estão fechadas.",
                    ephemeral=True
                )
                return
            
            # Verifica se já está inscrito
            participants = await self.db.get_participants(self.action_id)
            user_id_str = str(interaction.user.id)
            if any(p["user_id"] == user_id_str for p in participants):
                await interaction.response.send_message(
                    "❌ Você já está inscrito nesta ação.",
                    ephemeral=True
                )
                return
            
            # Verifica limite ANTES de adicionar
            participant_count = await self.db.count_participants(self.action_id)
            max_players = action.get("max_players", 0)
            if participant_count >= max_players:
                await interaction.response.send_message(
                    f"❌ Ação está cheia. Limite: {max_players} players.",
                    ephemeral=True
                )
                return
            
            # Adiciona participante
            await self.db.add_participant(self.action_id, interaction.user.id)
            
            # Atualiza embed (sem enviar ephemeral)
            # Usa defer para evitar erro de "already responded"
            await interaction.response.defer()
            await self.update_embed(interaction)
            
        except Exception as exc:
            LOGGER.error("Erro ao entrar na ação: %s", exc, exc_info=True)
            await interaction.response.send_message(
                "❌ Erro ao entrar na ação. Tente novamente.",
                ephemeral=True
            )
    
    @discord.ui.button(
        label="❌ Sair da Ação",
        style=discord.ButtonStyle.danger,
        row=2
    )
    async def leave_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Remove o usuário da ação."""
        try:
            action = await self.db.get_active_action(self.action_id)
            if not action:
                await interaction.response.send_message(
                    "❌ Ação não encontrada.",
                    ephemeral=True
                )
                return
            
            # Verifica status
            if action.get("status") == "closed" or action.get("status") == "finished":
                await interaction.response.send_message(
                    "❌ Não é possível sair desta ação.",
                    ephemeral=True
                )
                return
            
            # Verifica se está inscrito
            participants = await self.db.get_participants(self.action_id)
            user_id_str = str(interaction.user.id)
            if not any(p["user_id"] == user_id_str for p in participants):
                await interaction.response.send_message(
                    "❌ Você não está inscrito nesta ação.",
                    ephemeral=True
                )
                return
            
            # Remove participante
            await self.db.remove_participant(self.action_id, interaction.user.id)
            
            # Atualiza embed (sem enviar ephemeral)
            # Usa defer para evitar erro de "already responded"
            await interaction.response.defer()
            await self.update_embed(interaction)
            
        except Exception as exc:
            LOGGER.error("Erro ao sair da ação: %s", exc, exc_info=True)
            await interaction.response.send_message(
                "❌ Erro ao sair da ação. Tente novamente.",
                ephemeral=True
            )
    
    @discord.ui.button(
        label="🔓 Abrir Inscrições",
        style=discord.ButtonStyle.success,
        row=0
    )
    async def open_registrations(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre as inscrições da ação."""
        try:
            action = await self.db.get_active_action(self.action_id)
            if not action:
                await interaction.response.send_message(
                    "❌ Ação não encontrada.",
                    ephemeral=True
                )
                return
            
            # Verifica permissões
            if not await self._check_permissions(interaction.user, action):
                await interaction.response.send_message(
                    "❌ Você não tem permissão para gerenciar inscrições.",
                    ephemeral=True
                )
                return
            
            # Verifica se já está aberto
            registrations_open = action.get("registrations_open", 0)
            if registrations_open:
                await interaction.response.send_message(
                    "❌ As inscrições já estão abertas.",
                    ephemeral=True
                )
                return
            
            # Abre inscrições
            await self.db.update_action_status(
                self.action_id, 
                action.get("status", "open"),
                registrations_open=True
            )
            
            # Atualiza embed
            await self.update_embed(interaction)
            
        except Exception as exc:
            LOGGER.error("Erro ao abrir inscrições: %s", exc, exc_info=True)
            await interaction.response.send_message(
                "❌ Erro ao abrir inscrições. Tente novamente.",
                ephemeral=True
            )
    
    @discord.ui.button(
        label="🔒 Fechar Inscrições",
        style=discord.ButtonStyle.primary,
        row=0
    )
    async def close_registrations(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Fecha as inscrições da ação."""
        try:
            action = await self.db.get_active_action(self.action_id)
            if not action:
                await interaction.response.send_message(
                    "❌ Ação não encontrada.",
                    ephemeral=True
                )
                return
            
            # Verifica permissões
            if not await self._check_permissions(interaction.user, action):
                await interaction.response.send_message(
                    "❌ Você não tem permissão para gerenciar inscrições.",
                    ephemeral=True
                )
                return
            
            # Verifica se já está fechado
            registrations_open = action.get("registrations_open", 0)
            if not registrations_open:
                await interaction.response.send_message(
                    "❌ As inscrições já estão fechadas.",
                    ephemeral=True
                )
                return
            
            # Fecha inscrições
            await self.db.update_action_status(
                self.action_id, 
                action.get("status", "open"),
                registrations_open=False
            )
            
            # Atualiza embed (isso também atualiza os botões)
            await self.update_embed(interaction)
            
        except Exception as exc:
            LOGGER.error("Erro ao fechar inscrições: %s", exc, exc_info=True)
            await interaction.response.send_message(
                "❌ Erro ao fechar inscrições. Tente novamente.",
                ephemeral=True
            )
    
    @discord.ui.button(
        label="🏆 Finalizar Vitória",
        style=discord.ButtonStyle.success,
        row=1
    )
    async def finish_victory(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Finaliza a ação com vitória usando o valor cadastrado."""
        try:
            action = await self.db.get_active_action(self.action_id)
            if not action:
                await interaction.response.send_message(
                    "❌ Ação não encontrada.",
                    ephemeral=True
                )
                return
            
            # Verifica permissões
            if not await self._check_permissions(interaction.user, action):
                await interaction.response.send_message(
                    "❌ Você não tem permissão para finalizar ações.",
                    ephemeral=True
                )
                return
            
            # Verifica participantes
            participants = await self.db.get_participants(self.action_id)
            if not participants:
                await interaction.response.send_message(
                    "❌ Não há participantes nesta ação.",
                    ephemeral=True
                )
                return
            
            # Usa o valor cadastrado na ação
            total_value = action.get("total_value", 0.0)
            if total_value <= 0:
                await interaction.response.send_message(
                    "❌ Valor da ação inválido.",
                    ephemeral=True
                )
                return
            
            # Calcula rateio
            participant_count = len(participants)
            rateio = total_value / participant_count
            
            # Responde à interação primeiro (defer para permitir operações longas)
            await interaction.response.defer()
            
            # Incrementa stats de todos os participantes
            guild_id = int(action["guild_id"])
            for participant in participants:
                user_id = int(participant["user_id"])
                await self.db.increment_stats(guild_id, user_id, rateio)
            
            # Atualiza ação no banco
            await self.db.update_action_status(
                self.action_id,
                status="finished",
                final_value=total_value,
                result="victory"
            )
            
            # Envia transcripts via DM para todos os participantes
            guild = interaction.guild
            if guild:
                await send_transcript_to_participants(
                    action,
                    participants,
                    guild,
                    self.db,
                    self.bot
                )
            
            # Atualiza embed
            await self.update_embed(interaction, final_value=total_value, result="victory")
            
            # Atualiza ranking
            if guild:
                await update_ranking_message(
                    guild_id,
                    guild,
                    self.db,
                    self.bot
                )
            
            # Embed já foi atualizada com o resultado, não precisa enviar nova mensagem
            
        except Exception as exc:
            LOGGER.error("Erro ao finalizar vitória: %s", exc, exc_info=True)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ Erro ao finalizar ação. Tente novamente.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ Erro ao finalizar ação. Tente novamente.",
                        ephemeral=True
                    )
            except:
                pass
    
    @discord.ui.button(
        label="💀 Finalizar Derrota",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def finish_defeat(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Finaliza a ação com derrota."""
        try:
            action = await self.db.get_active_action(self.action_id)
            if not action:
                await interaction.response.send_message(
                    "❌ Ação não encontrada.",
                    ephemeral=True
                )
                return
            
            # Verifica permissões
            if not await self._check_permissions(interaction.user, action):
                await interaction.response.send_message(
                    "❌ Você não tem permissão para finalizar ações.",
                    ephemeral=True
                )
                return
            
            # Busca participantes para incrementar apenas participações
            participants = await self.db.get_participants(self.action_id)
            guild_id = int(action["guild_id"])
            
            for participant in participants:
                user_id = int(participant["user_id"])
                await self.db.increment_participation_only(guild_id, user_id)
            
            # Atualiza ação no banco
            await self.db.update_action_status(
                self.action_id,
                status="finished",
                result="defeat"
            )
            
            await interaction.response.send_message(
                "✅ Ação finalizada como derrota.",
                ephemeral=True
            )
            
            # Atualiza embed
            await self.update_embed(interaction, result="defeat")
            
            # Atualiza ranking
            guild = interaction.guild
            if guild:
                await update_ranking_message(
                    guild_id,
                    guild,
                    self.db,
                    self.bot
                )
            
        except Exception as exc:
            LOGGER.error("Erro ao finalizar derrota: %s", exc, exc_info=True)
            await interaction.response.send_message(
                "❌ Erro ao finalizar ação. Tente novamente.",
                ephemeral=True
            )
    
    @discord.ui.button(
        label="🗑️ Remover Participante",
        style=discord.ButtonStyle.danger,
        row=0
    )
    async def remove_participant(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Remove um participante da ação (apenas moderadores)."""
        try:
            action = await self.db.get_active_action(self.action_id)
            if not action:
                await interaction.response.send_message(
                    "❌ Ação não encontrada.",
                    ephemeral=True
                )
                return
            
            # Verifica permissões
            if not await self._check_permissions(interaction.user, action):
                await interaction.response.send_message(
                    "❌ Você não tem permissão para remover participantes.",
                    ephemeral=True
                )
                return
            
            # Busca participantes
            participants = await self.db.get_participants(self.action_id)
            if not participants:
                await interaction.response.send_message(
                    "❌ Não há participantes para remover.",
                    ephemeral=True
                )
                return
            
            # Cria select menu com participantes
            options = []
            for participant in participants:
                user_id = int(participant["user_id"])
                member = interaction.guild.get_member(user_id) if interaction.guild else None
                name = member.display_name if member else f"User {user_id}"
                options.append(
                    discord.SelectOption(
                        label=name[:100],
                        value=str(user_id),
                        description=f"Remover {name}"
                    )
                )
            
            view = self.RemoveParticipantView(self.db, self.action_id, self, interaction.user.id)
            view.select_participant.options = options
            
            await interaction.response.send_message(
                "👤 Selecione o participante para remover:",
                view=view,
                ephemeral=True
            )
            
        except Exception as exc:
            LOGGER.error("Erro ao remover participante: %s", exc, exc_info=True)
            await interaction.response.send_message(
                "❌ Erro ao remover participante. Tente novamente.",
                ephemeral=True
            )
    
    @discord.ui.button(
        label="↩️ Restaurar Participante",
        style=discord.ButtonStyle.secondary,
        row=0
    )
    async def restore_participant(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Restaura um participante removido (apenas moderadores)."""
        try:
            action = await self.db.get_active_action(self.action_id)
            if not action:
                await interaction.response.send_message(
                    "❌ Ação não encontrada.",
                    ephemeral=True
                )
                return
            
            # Verifica permissões
            if not await self._check_permissions(interaction.user, action):
                await interaction.response.send_message(
                    "❌ Você não tem permissão para restaurar participantes.",
                    ephemeral=True
                )
                return
            
            # Busca removidos
            removed = await self.db.get_removed_participants(self.action_id)
            if not removed:
                await interaction.response.send_message(
                    "❌ Não há participantes removidos para restaurar.",
                    ephemeral=True
                )
                return
            
            # Verifica limite antes de restaurar
            participant_count = await self.db.count_participants(self.action_id)
            max_players = action.get("max_players", 0)
            if participant_count >= max_players:
                await interaction.response.send_message(
                    f"❌ Ação está cheia. Limite: {max_players} players.",
                    ephemeral=True
                )
                return
            
            # Cria select menu com removidos
            options = []
            for removed_user in removed:
                user_id = int(removed_user["user_id"])
                member = interaction.guild.get_member(user_id) if interaction.guild else None
                name = member.display_name if member else f"User {user_id}"
                options.append(
                    discord.SelectOption(
                        label=name[:100],
                        value=str(user_id),
                        description=f"Restaurar {name}"
                    )
                )
            
            view = self.RestoreParticipantView(self.db, self.action_id, self)
            view.select_participant.options = options
            
            await interaction.response.send_message(
                "↩️ Selecione o participante para restaurar:",
                view=view,
                ephemeral=True
            )
            
        except Exception as exc:
            LOGGER.error("Erro ao restaurar participante: %s", exc, exc_info=True)
            await interaction.response.send_message(
                "❌ Erro ao restaurar participante. Tente novamente.",
                ephemeral=True
            )
    
    @discord.ui.button(
        label="❌ Cancelar Ação",
        style=discord.ButtonStyle.danger,
        row=0
    )
    async def cancel_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancela e deleta a ação."""
        try:
            action = await self.db.get_active_action(self.action_id)
            if not action:
                await interaction.response.send_message(
                    "❌ Ação não encontrada.",
                    ephemeral=True
                )
                return
            
            # Verifica permissões
            if not await self._check_permissions(interaction.user, action):
                await interaction.response.send_message(
                    "❌ Você não tem permissão para cancelar ações.",
                    ephemeral=True
                )
                return
            
            # Deleta ação
            await self.db.delete_active_action(self.action_id)
            
            # Tenta deletar mensagem
            message_id = action.get("message_id")
            if message_id and str(message_id).isdigit():
                try:
                    channel_id = action.get("channel_id")
                    if channel_id and str(channel_id).isdigit():
                        channel = interaction.guild.get_channel(int(channel_id))
                        if channel:
                            message = await channel.fetch_message(int(message_id))
                            await message.delete()
                except Exception as exc:
                    LOGGER.warning("Erro ao deletar mensagem: %s", exc)
            
            await interaction.response.send_message(
                "✅ Ação cancelada e deletada.",
                ephemeral=True
            )
            
        except Exception as exc:
            LOGGER.error("Erro ao cancelar ação: %s", exc, exc_info=True)
            await interaction.response.send_message(
                "❌ Erro ao cancelar ação. Tente novamente.",
                ephemeral=True
            )


class ActionTypeSelectView(discord.ui.View):
    """View com select menu para escolher tipo de ação."""
    
    def __init__(self, bot: commands.Bot, db: Database, guild: discord.Guild, action_types: list):
        super().__init__(timeout=60)
        self.bot = bot
        self.db = db
        self.guild = guild
        self.action_types = action_types
        self.select_message: Optional[discord.Message] = None
        
        # Cria opções do select
        options = []
        for action_type in action_types:
            options.append(
                discord.SelectOption(
                    label=action_type["name"],
                    value=str(action_type["id"]),
                    description=f"Min: {action_type['min_players']} | Max: {action_type['max_players']} | Valor: R$ {action_type['total_value']:,.2f}",
                    emoji="🎯"
                )
            )
        
        self.select_action_type.options = options
    
    @discord.ui.select(
        placeholder="Selecione o tipo de ação...",
        min_values=1,
        max_values=1,
        row=0
    )
    async def select_action_type(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Cria uma nova ação do tipo selecionado."""
        if not select.values:
            return
        
        try:
            type_id = int(select.values[0])
            action_type = next((at for at in self.action_types if at["id"] == type_id), None)
            
            if not action_type:
                await interaction.response.send_message(
                    "❌ Tipo de ação não encontrado.",
                    ephemeral=True
                )
                return
            
            # Busca canal configurado ou usa o atual
            settings = await self.db.get_action_settings(self.guild.id)
            action_channel_id = settings.get("action_channel_id")
            
            target_channel = None
            if action_channel_id and str(action_channel_id).isdigit():
                target_channel = self.guild.get_channel(int(action_channel_id))
                if not target_channel:
                    try:
                        target_channel = await self.guild.fetch_channel(int(action_channel_id))
                    except (discord.NotFound, discord.HTTPException):
                        target_channel = interaction.channel  # Fallback para canal atual
            else:
                target_channel = interaction.channel
            
            # Cria ação ativa (com inscrições fechadas inicialmente)
            action_id = await self.db.create_active_action(
                self.guild.id,
                type_id,
                interaction.user.id,
                0,  # message_id será atualizado depois
                target_channel.id
            )
            
            # Cria view persistente
            view = ActionView(self.bot, self.db, action_id)
            
            # Busca ação criada
            action = await self.db.get_active_action(action_id)
            
            # Configura estado inicial dos botões (inscrições fechadas)
            await view._update_buttons(action, 0, None)
            
            # Cria embed inicial e envia no canal configurado
            embed = await self._build_initial_embed(action, action_type)
            
            # Envia no canal configurado
            message = await target_channel.send(embed=embed, view=view)
            
            # Atualiza message_id no banco
            await self.db.update_action_status(action_id, action.get("status", "open"), message_id=message.id)
            
            # Registra view para persistência
            self.bot.add_view(view, message_id=message.id)
            
            # Confirma criação e deleta mensagem de seleção
            await interaction.response.send_message(
                f"✅ Ação criada em {target_channel.mention}!",
                ephemeral=True
            )
            
            # Deleta a mensagem de seleção
            try:
                if hasattr(interaction, 'message') and interaction.message:
                    await interaction.message.delete()
            except:
                pass
            
        except Exception as exc:
            LOGGER.error("Erro ao criar ação: %s", exc, exc_info=True)
            await interaction.response.send_message(
                "❌ Erro ao criar ação. Tente novamente.",
                ephemeral=True
            )
    
    async def _build_initial_embed(self, action: dict, action_type: dict) -> discord.Embed:
        """Constrói embed inicial da ação (com inscrições fechadas)."""
        embed = discord.Embed(
            title=f"🎯 {action_type['name']}",
            description="**Status:** 🟢 Aberto\n**Inscrições:** 🔒 Fechadas",
            color=discord.Color.orange(),  # Laranja para indicar que está fechado
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="💰 Valor Total",
            value=f"R$ {action_type['total_value']:,.2f}",
            inline=True
        )
        
        embed.add_field(
            name="👥 Players",
            value=f"0/{action_type['max_players']}",
            inline=True
        )
        
        embed.add_field(
            name="📊 Rateio por Player",
            value="Aguardando inscritos...",
            inline=True
        )
        
        embed.add_field(
            name="✅ Inscritos",
            value="Nenhum inscrito",
            inline=False
        )
        
        embed.add_field(
            name="🔒 Status de Inscrições",
            value="**Fechadas** - Aguarde o responsável abrir",
            inline=False
        )
        
        embed.set_footer(text=f"Ação ID: {action['id']}")
        
        return embed
    


class ActionCog(commands.Cog):
    """Cog para gerenciar ações FiveM."""
    
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db
    
    async def _check_permissions(self, member: discord.Member) -> bool:
        """Verifica se o membro tem permissão (admin ou cargo responsável)."""
        if member.guild_permissions.administrator:
            return True
        
        # Verifica múltiplos cargos responsáveis
        responsible_roles = await self.db.get_responsible_roles(member.guild.id)
        for role_id in responsible_roles:
            role = member.guild.get_role(role_id)
            if role and role in member.roles:
                return True
        
        return False
    
    @commands.command(name="acao")
    async def create_action(self, ctx: commands.Context):
        """Cria uma nova ação."""
        if not ctx.guild:
            await ctx.reply("❌ Use este comando em um servidor.")
            return
        
        if not await self._check_permissions(ctx.author):
            await ctx.reply(
                "❌ Você não tem permissão para usar este comando.\n"
                "É necessário ser administrador ou ter o cargo responsável configurado.",
                delete_after=10
            )
            return
        
        # Busca tipos de ação
        action_types = await self.db.get_action_types(ctx.guild.id)
        
        if not action_types:
            await ctx.reply(
                "❌ Nenhum tipo de ação cadastrado.\n"
                "Use `!acao_setup` para configurar os tipos de ação primeiro.",
                delete_after=15
            )
            return
        
        # Cria view com select menu
        view = ActionTypeSelectView(self.bot, self.db, ctx.guild, list(action_types))
        await ctx.reply(
            "🎯 Selecione o tipo de ação que deseja criar:",
            view=view
        )
        
        
        # Deleta o comando
        try:
            await ctx.message.delete()
        except:
            pass
