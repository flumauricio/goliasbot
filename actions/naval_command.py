import asyncio
import io
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import discord
from discord.ext import commands

from db import Database
from actions.naval_combat import NavalGame, REQUIRED_SHIPS
from actions.naval_renderer import NavalRenderer

LOGGER = logging.getLogger(__name__)

# Pontuação
POINTS_HIT = 10
POINTS_MISS = -2
POINTS_WIN = 50


class SetupFleetModal(discord.ui.Modal):
    """Modal para posicionar navios usando coordenadas início e fim."""
    
    def __init__(self, naval_cog, game: NavalGame, player_id: int, ship_type: str, ship_name: str, dm_message_id: Optional[int] = None):
        super().__init__(title=f"Posicionar {ship_name}")
        self.naval_cog = naval_cog
        self.game = game
        self.player_id = player_id
        self.ship_type = ship_type
        self.ship_name = ship_name
        self.dm_message_id = dm_message_id
        
        # Obtém tamanho do navio
        ship_size = 0
        for req_ship in REQUIRED_SHIPS:
            if req_ship["type"].lower() == ship_type.lower():
                ship_size = req_ship["size"]
                break
        
        self.ship_size = ship_size
        
        if ship_size == 1:
            # Navio de 1 posição: apenas uma coordenada
            self.coord_input = discord.ui.TextInput(
                label="Coordenada",
                placeholder="Ex: A1",
                required=True,
                max_length=3,
                min_length=2,
            )
            self.add_item(self.coord_input)
            self.start_input = None
            self.end_input = None
        else:
            # Navios de 2+ posições: coordenada inicial
            self.start_input = discord.ui.TextInput(
                label="Coordenada Inicial",
                placeholder="Ex: A1",
                required=True,
                max_length=3,
                min_length=2,
            )
            self.add_item(self.start_input)
            
            # Campo para direção (será preenchido automaticamente ou pelo usuário)
            # O placeholder mostra um exemplo de como calcular
            direction_placeholder = "H (Horizontal) ou V (Vertical)"
            if ship_size == 2:
                direction_placeholder = "H ou V - Ex: A1 H → A2, A1 V → B1"
            elif ship_size == 3:
                direction_placeholder = "H ou V - Ex: A1 H → A3, A1 V → C1"
            elif ship_size == 4:
                direction_placeholder = "H ou V - Ex: A1 H → A4, A1 V → D1"
            
            self.direction_input = discord.ui.TextInput(
                label="Direção",
                placeholder=direction_placeholder,
                required=True,
                max_length=1,
                min_length=1,
            )
            self.add_item(self.direction_input)
            self.coord_input = None
    
    def _calculate_possible_end_coords(self, start_coord: str) -> List[str]:
        """Calcula as coordenadas finais possíveis baseadas na inicial e tamanho do navio."""
        try:
            letter, number = NavalGame.parse_coordinate(start_coord)
            possible_ends = []
            
            # Horizontal: mesmo número, letras diferentes
            # Verifica se cabe à direita
            end_letter_h = chr(ord(letter) + self.ship_size - 1)
            if end_letter_h <= 'J':
                possible_ends.append(f"{end_letter_h}{number}")
            
            # Verifica se cabe à esquerda
            start_letter_h = chr(ord(letter) - self.ship_size + 1)
            if start_letter_h >= 'A':
                possible_ends.append(f"{start_letter_h}{number}")
            
            # Vertical: mesma letra, números diferentes
            # Verifica se cabe para baixo
            end_number_v = number + self.ship_size - 1
            if end_number_v <= 10:
                possible_ends.append(f"{letter}{end_number_v}")
            
            # Verifica se cabe para cima
            start_number_v = number - self.ship_size + 1
            if start_number_v >= 1:
                possible_ends.append(f"{letter}{start_number_v}")
            
            return possible_ends
        except ValueError:
            return []
    
    async def on_submit(self, interaction: discord.Interaction):
        # IMPORTANTE: Sempre defer no início (não ephemeral em DM)
        await interaction.response.defer()
        
        try:
            if self.ship_size == 1:
                # Navio de 1 posição: usa a mesma coordenada para início e fim
                coord = self.coord_input.value.strip().upper()
                start_coord = coord
                end_coord = coord
            else:
                # Navios de 2+ posições
                start_coord = self.start_input.value.strip().upper()
                direction = self.direction_input.value.strip().upper()
                
                if direction not in ['H', 'V']:
                    await interaction.followup.send(
                        "❌ Direção inválida. Use H (Horizontal) ou V (Vertical)."
                    )
                    return
                
                # Calcula coordenada final baseada na inicial e direção
                letter, number = NavalGame.parse_coordinate(start_coord)
                
                if direction == 'V':
                    # Vertical: mesma letra, número aumenta
                    end_number = number + self.ship_size - 1
                    if end_number > 10:
                        # Mostra coordenadas finais possíveis
                        possible_ends = self._calculate_possible_end_coords(start_coord)
                        if possible_ends:
                            ends_str = ", ".join(possible_ends)
                            await interaction.followup.send(
                                f"❌ Navio não cabe nesta posição (vertical).\n"
                                f"💡 **Coordenadas finais possíveis a partir de {start_coord}:** {ends_str}\n"
                                f"Tente uma coordenada inicial mais acima ou use direção Horizontal (H)."
                            )
                        else:
                            await interaction.followup.send(
                                f"❌ Navio não cabe nesta posição. Tente outra coordenada inicial."
                            )
                        return
                    end_coord = f"{letter}{end_number}"
                else:
                    # Horizontal: mesmo número, letra aumenta
                    end_letter = chr(ord(letter) + self.ship_size - 1)
                    if end_letter > 'J':
                        # Mostra coordenadas finais possíveis
                        possible_ends = self._calculate_possible_end_coords(start_coord)
                        if possible_ends:
                            ends_str = ", ".join(possible_ends)
                            await interaction.followup.send(
                                f"❌ Navio não cabe nesta posição (horizontal).\n"
                                f"💡 **Coordenadas finais possíveis a partir de {start_coord}:** {ends_str}\n"
                                f"Tente uma coordenada inicial mais à esquerda ou use direção Vertical (V)."
                            )
                        else:
                            await interaction.followup.send(
                                f"❌ Navio não cabe nesta posição. Tente outra coordenada inicial."
                            )
                        return
                    end_coord = f"{end_letter}{number}"
            
            # Valida posicionamento
            valid, error = self.game.validate_ship_placement(
                self.player_id,
                self.ship_type,
                start_coord,
                end_coord
            )
            
            if not valid:
                await interaction.followup.send(
                    f"❌ {error}"
                )
                return
            
            # Adiciona navio
            success, error, direction = self.game.add_ship(
                self.player_id,
                self.ship_type,
                start_coord,
                end_coord
            )
            
            if not success:
                await interaction.followup.send(
                    f"❌ {error}"
                )
                return
            
            # Salva no banco
            await self.naval_cog.db.update_naval_game(
                self.game.game_id,
                player1_board=json.dumps(self.game.player1_board) if self.player_id == self.game.player1_id else None,
                player2_board=json.dumps(self.game.player2_board) if self.player_id == self.game.player2_id else None,
            )
            
            # Recarrega o jogo do banco para ter dados atualizados
            game_data = await self.naval_cog.db.get_naval_game(self.game.game_id)
            updated_game = NavalGame(game_data)
            
            # Atualiza a mesma mensagem DM
            user = self.naval_cog.bot.get_user(self.player_id)
            if not user:
                return
            
            try:
                if self.dm_message_id:
                    dm_channel = await user.create_dm()
                    try:
                        dm_message = await dm_channel.fetch_message(self.dm_message_id)
                    except discord.NotFound:
                        dm_message = None
                else:
                    # Se não tem mensagem, cria nova
                    dm_channel = await user.create_dm()
                    dm_message = None
            except Exception as exc:
                LOGGER.error("Erro ao acessar DM: %s", exc)
                return
            
            # Renderiza preview com dados atualizados
            board = updated_game.get_player_board(self.player_id)
            ships = board.get("ships", [])
            shots = board.get("shots", [])
            
            renderer = self.naval_cog.get_renderer()
            shot_coords = [s.get("coord", "") if isinstance(s, dict) else str(s) for s in shots]
            preview_buffer = renderer.render_preview(ships, shot_coords)
            preview_file = discord.File(preview_buffer, filename="preview.png")
            
            # Verifica se a frota está completa
            is_complete = updated_game.is_fleet_complete(self.player_id)
            both_complete = (updated_game.is_fleet_complete(updated_game.player1_id) and 
                           updated_game.is_fleet_complete(updated_game.player2_id))
            
            # Se a frota está completa, envia mensagem nova ao invés de atualizar
            if is_complete:
                # Envia mensagem nova com link para o canal
                channel = self.naval_cog.bot.get_channel(updated_game.channel_id)
                if channel:
                    if both_complete:
                        complete_embed = discord.Embed(
                            title="🎉 Frota Completa!",
                            description=(
                                f"**Sua frota foi posicionada com sucesso!**\n\n"
                                f"🔗 **[Clique aqui para ir ao canal da partida](https://discord.com/channels/{updated_game.guild_id}/{updated_game.channel_id})**\n\n"
                                f"⚓ A partida está começando!"
                            ),
                            color=discord.Color.green(),
                        )
                    else:
                        complete_embed = discord.Embed(
                            title="🎉 Frota Completa!",
                            description=(
                                f"**Sua frota foi posicionada com sucesso!**\n\n"
                                f"🔗 **[Clique aqui para ir ao canal da partida](https://discord.com/channels/{updated_game.guild_id}/{updated_game.channel_id})**\n\n"
                                f"A partida começará quando ambos os jogadores completarem o setup."
                            ),
                            color=discord.Color.green(),
                        )
                    await dm_channel.send(embed=complete_embed)
                
                # Se ambos completaram, inicia a partida e agenda limpeza da DM para ambos
                if both_complete:
                    # Agenda limpeza da DM após 5 segundos para ambos os jogadores
                    async def cleanup_dm_for_player(player_id: int):
                        await asyncio.sleep(5)
                        try:
                            player = self.naval_cog.bot.get_user(player_id)
                            if player:
                                player_dm = await player.create_dm()
                                # Limpa todas as mensagens do bot na DM
                                async for msg in player_dm.history(limit=None):
                                    if msg.author == self.naval_cog.bot.user:
                                        try:
                                            await msg.delete()
                                        except:
                                            pass
                        except Exception as exc:
                            LOGGER.error("Erro ao limpar DM do jogador %s: %s", player_id, exc)
                    
                    # Inicia tasks de limpeza para ambos os jogadores
                    asyncio.create_task(cleanup_dm_for_player(updated_game.player1_id))
                    asyncio.create_task(cleanup_dm_for_player(updated_game.player2_id))
                    
                    # Inicia partida
                    await self.naval_cog.start_game(updated_game)
                return
            
            # Se não está completo, atualiza a mensagem normalmente
            placed_count = len(ships)
            total_needed = sum(req["count"] for req in REQUIRED_SHIPS)
            description = f"🚢 **Progresso:** {placed_count}/{total_needed} navios posicionados\n\nClique nos botões abaixo para posicionar seus navios:"
            
            embed = discord.Embed(
                title="⚓ Montagem da Frota",
                description=description,
                color=discord.Color.blue(),
            )
            embed.set_image(url="attachment://preview.png")
            
            # Atualiza view com jogo atualizado
            view = FleetSetupView(self.naval_cog, updated_game, self.player_id, self.dm_message_id)
            
            if dm_message:
                # Para atualizar arquivo, precisamos deletar e recriar a mensagem
                try:
                    await dm_message.delete()
                except:
                    pass
                new_message = await dm_channel.send(embed=embed, file=preview_file, view=view)
                # Atualiza dm_message_id na view também
                view.dm_message_id = new_message.id
                self.dm_message_id = new_message.id
            else:
                new_message = await dm_channel.send(embed=embed, file=preview_file, view=view)
                view.dm_message_id = new_message.id
                self.dm_message_id = new_message.id
        
        except ValueError as e:
            await interaction.followup.send(
                f"❌ {str(e)}"
            )
        except Exception as exc:
            LOGGER.error("Erro ao atualizar setup DM: %s", exc, exc_info=True)
            await interaction.followup.send(
                f"✅ Navio posicionado! (Erro ao atualizar visualização)"
            )


class FleetSetupView(discord.ui.View):
    """View para fase de setup da frota com botões individuais para cada navio."""
    
    def __init__(self, naval_cog, game: NavalGame, player_id: int, dm_message_id: Optional[int] = None):
        super().__init__(timeout=None)  # Sem timeout para views persistentes
        self.naval_cog = naval_cog
        self.game = game
        self.player_id = player_id
        self.dm_message_id = dm_message_id
        
        # Adiciona botão para cada navio necessário
        board = game.get_player_board(player_id)
        placed_ships = {ship.get("type", "").lower() for ship in board.get("ships", [])}
        
        row = 0
        for req_ship in REQUIRED_SHIPS:
            ship_type = req_ship["type"]
            ship_size = req_ship["size"]
            ship_name = f"Navio {ship_size}x1"
            
            # Conta quantos navios deste tipo já foram posicionados
            count_placed = sum(1 for s in board.get("ships", []) if s.get("type", "").lower() == ship_type.lower())
            count_needed = req_ship["count"]
            
            # Cria botão para cada navio necessário
            for i in range(count_needed):
                is_placed = i < count_placed
                button = discord.ui.Button(
                    label=f"🚢 {ship_name} #{i+1}",
                    style=discord.ButtonStyle.primary if not is_placed else discord.ButtonStyle.secondary,
                    row=row,
                    disabled=is_placed,
                    custom_id=f"naval_setup_{game.game_id}_{player_id}_{ship_type}_{i}"
                )
                if not is_placed:
                    button.callback = self._create_ship_callback(ship_type, ship_name, i)
                self.add_item(button)
                
                if len(self.children) % 5 == 0:
                    row += 1
    
    def _create_ship_callback(self, ship_type: str, ship_name: str, index: int):
        """Cria callback dinâmico para cada botão de navio."""
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.player_id:
                await interaction.response.send_message(
                    "❌ Esta não é sua partida!",
                    ephemeral=True
                )
                return
            
            modal = SetupFleetModal(
                self.naval_cog, 
                self.game, 
                self.player_id, 
                ship_type, 
                ship_name,
                self.dm_message_id
            )
            await interaction.response.send_modal(modal)
        
        return callback


class NavalGameView(discord.ui.View):
    """View principal da partida em andamento."""
    
    def __init__(self, naval_cog, game: NavalGame):
        super().__init__(timeout=None)  # Sem timeout para views persistentes
        self.naval_cog = naval_cog
        self.game = game
        
        # Select menus para coordenadas (com custom_id para persistência)
        self.letter_select = discord.ui.Select(
            placeholder="Selecione a letra (A-J)",
            options=[discord.SelectOption(label=chr(65 + i), value=chr(65 + i)) for i in range(10)],
            row=0,
            custom_id=f"naval_letter_{game.game_id}"
        )
        self.letter_select.callback = self.on_letter_select
        self.add_item(self.letter_select)
        
        self.number_select = discord.ui.Select(
            placeholder="Selecione o número (1-10)",
            options=[discord.SelectOption(label=str(i), value=str(i)) for i in range(1, 11)],
            row=1,
            custom_id=f"naval_number_{game.game_id}"
        )
        self.number_select.callback = self.on_number_select
        self.add_item(self.number_select)
        
        self.selected_letter = None
        self.selected_number = None
    
    async def on_letter_select(self, interaction: discord.Interaction):
        # IMPORTANTE: Sempre defer no início
        await interaction.response.defer(ephemeral=True)
        self.selected_letter = interaction.data["values"][0]
    
    async def on_number_select(self, interaction: discord.Interaction):
        # IMPORTANTE: Sempre defer no início
        await interaction.response.defer(ephemeral=True)
        self.selected_number = interaction.data["values"][0]
    
    @discord.ui.button(label="🔥 DISPARAR", style=discord.ButtonStyle.danger, row=2, custom_id=None)
    async def fire_shot(self, interaction: discord.Interaction, button: discord.ui.Button):
        # IMPORTANTE: Sempre defer no início
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        
        if user_id not in [self.game.player1_id, self.game.player2_id]:
            await interaction.followup.send(
                "❌ Você não está nesta partida!",
                ephemeral=True
            )
            return
        
        if user_id != self.game.current_turn:
            await interaction.followup.send(
                "❌ Não é seu turno!",
                ephemeral=True
            )
            return
        
        if not self.selected_letter or not self.selected_number:
            await interaction.followup.send(
                "❌ Selecione uma coordenada primeiro!",
                ephemeral=True
            )
            return
        
        coord = f"{self.selected_letter}{self.selected_number}"
        
        # Guarda turno ANTES de executar o tiro
        old_turn = self.game.current_turn
        
        # Executa tiro
        success, is_hit, error = self.game.fire_shot(user_id, coord)
        
        if not success:
            await interaction.followup.send(
                f"❌ {error}",
                ephemeral=True
            )
            return
        
        # Atualiza timestamp
        await self.naval_cog.db.update_naval_game_last_move(self.game.game_id)
        
        # Salva no banco
        await self.naval_cog.db.update_naval_game(
            self.game.game_id,
            current_turn=str(self.game.current_turn),
            player1_board=json.dumps(self.game.player1_board),
            player2_board=json.dumps(self.game.player2_board),
        )
        
        # Atualiza estatísticas
        if is_hit:
            await self.naval_cog.db.update_naval_stats(
                self.game.guild_id,
                user_id,
                total_hits=1,
                points=POINTS_HIT,
            )
        else:
            await self.naval_cog.db.update_naval_stats(
                self.game.guild_id,
                user_id,
                total_misses=1,
                points=POINTS_MISS,
            )
        
        # Verifica vitória
        if self.game.check_victory(user_id):
            # Vitória!
            await self.naval_cog.end_game(self.game, user_id)
            return
        
        # Verifica se o turno mudou
        show_transition = (old_turn != self.game.current_turn)
        
        # Mostra feedback visual (acerto ou erro) na embed principal
        await self.naval_cog.update_game_display_with_feedback(
            self.game, 
            is_hit=is_hit,
            show_transition=show_transition
        )
        
        # Reseta seleção
        self.selected_letter = None
        self.selected_number = None
    
    @discord.ui.button(label="📋 Ver Meu Tabuleiro", style=discord.ButtonStyle.secondary, row=3, custom_id=None)
    async def view_my_board(self, interaction: discord.Interaction, button: discord.ui.Button):
        # IMPORTANTE: Sempre defer no início
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        
        if user_id not in [self.game.player1_id, self.game.player2_id]:
            await interaction.followup.send(
                "❌ Você não está nesta partida!",
                ephemeral=True
            )
            return
        
        board = self.game.get_player_board(user_id)
        ships = board.get("ships", [])
        shots = board.get("shots", [])
        
        renderer = self.naval_cog.get_renderer()
        shot_coords = [s.get("coord", "") if isinstance(s, dict) else str(s) for s in shots]
        board_buffer = renderer.render_private_board(ships, shot_coords)
        
        board_file = discord.File(board_buffer, filename="my_board.png")
        
        await interaction.followup.send(
            "📋 **Seu Tabuleiro:**",
            file=board_file,
            ephemeral=True
        )


class QueueView(discord.ui.View):
    """View para fila de matchmaking."""
    
    def __init__(self, naval_cog, guild_id: int):
        super().__init__(timeout=300)
        self.naval_cog = naval_cog
        self.guild_id = guild_id
    
    @discord.ui.button(label="❌ Sair da Fila", style=discord.ButtonStyle.danger)
    async def leave_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        # IMPORTANTE: Sempre defer no início
        await interaction.response.defer(ephemeral=True)
        
        await self.naval_cog.db.remove_from_queue(self.guild_id, interaction.user.id)
        await interaction.followup.send(
            "✅ Você saiu da fila de matchmaking.",
            ephemeral=True
        )
        await self.naval_cog.update_queue_display(self.guild_id)


class NavalCog(commands.Cog):
    """Cog para sistema de Batalha Naval."""
    
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db
        self.renderer: Optional[NavalRenderer] = None
        self._timeout_task: Optional[asyncio.Task] = None
    
    async def cog_load(self):
        """Inicializa o renderer ao carregar o cog."""
        # Caminho dos assets: raiz do bot (ao lado do main.py)
        assets_path = Path(__file__).parent.parent / "assets" / "naval"
        
        # Verifica se a pasta existe
        if not assets_path.exists():
            LOGGER.warning("Pasta de assets não encontrada: %s", assets_path)
            # Cria a pasta se não existir
            assets_path.mkdir(parents=True, exist_ok=True)
        
        self.renderer = NavalRenderer(assets_path)
        # Carrega assets na inicialização
        self.renderer._load_assets()
        
        # Inicia task de timeout
        self._timeout_task = asyncio.create_task(self._timeout_monitor())
        
        # Restaura partidas ativas
        await self._restore_active_games()
    
    async def cog_unload(self):
        """Cancela task de timeout ao descarregar."""
        if self._timeout_task:
            self._timeout_task.cancel()
    
    def get_renderer(self) -> NavalRenderer:
        """Retorna o renderer."""
        if not self.renderer:
            assets_path = Path(__file__).parent.parent / "assets" / "naval"
            self.renderer = NavalRenderer(assets_path)
            self.renderer._load_assets()
        return self.renderer
    
    def get_next_ship_needed(self, game: NavalGame, player_id: int) -> Optional[Dict]:
        """Retorna o próximo navio que o jogador precisa posicionar."""
        board = game.get_player_board(player_id)
        ships = board.get("ships", [])
        
        ship_counts = {}
        for ship in ships:
            ship_type = ship.get("type", "").lower()
            ship_counts[ship_type] = ship_counts.get(ship_type, 0) + 1
        
        for req_ship in REQUIRED_SHIPS:
            current_count = ship_counts.get(req_ship["type"].lower(), 0)
            if current_count < req_ship["count"]:
                return {
                    "type": req_ship["type"],
                    "name": req_ship["type"].upper().replace("SHIP", "Navio "),
                    "count": req_ship["count"] - current_count,
                }
        
        return None
    
    async def _restore_active_games(self):
        """Restaura partidas ativas na inicialização."""
        try:
            active_games = await self.db.list_active_naval_games()
            
            for game_data in active_games:
                try:
                    game = NavalGame(game_data)
                    channel = self.bot.get_channel(game.channel_id)
                    if channel and game.message_id:
                        try:
                            message = await channel.fetch_message(game.message_id)
                            view = NavalGameView(self, game) if game.status == "active" else None
                            if view:
                                self.bot.add_view(view, message_id=game.message_id)
                        except discord.NotFound:
                            LOGGER.warning("Mensagem %s não encontrada para partida %s", game.message_id, game.game_id)
                except Exception as exc:
                    LOGGER.error("Erro ao restaurar partida %s: %s", game_data.get("id"), exc)
        except Exception as exc:
            LOGGER.error("Erro ao restaurar partidas: %s", exc, exc_info=True)
    
    async def _timeout_monitor(self):
        """Monitora partidas sem movimento há mais de 5 minutos."""
        while True:
            try:
                await asyncio.sleep(60)  # Verifica a cada 1 minuto
                
                stale_games = await self.db.get_stale_games(timeout_minutes=5)
                
                for game_data in stale_games:
                    try:
                        game = NavalGame(game_data)
                        
                        # Declara vitória por W.O. para o jogador ativo
                        winner_id = game.current_turn
                        loser_id = game.player2_id if winner_id == game.player1_id else game.player1_id
                        
                        # Atualiza estatísticas
                        await self.db.update_naval_stats(
                            game.guild_id,
                            winner_id,
                            wins=1,
                            points=POINTS_WIN,
                        )
                        await self.db.increment_naval_streak(game.guild_id, winner_id)
                        
                        await self.db.update_naval_stats(
                            game.guild_id,
                            loser_id,
                            losses=1,
                        )
                        await self.db.reset_naval_streak(game.guild_id, loser_id)
                        
                        # Finaliza partida
                        from datetime import datetime
                        await self.db.update_naval_game(
                            game.game_id,
                            status="finished",
                            finished_at=datetime.utcnow().isoformat(),
                        )
                        
                        # Notifica jogadores
                        try:
                            channel = self.bot.get_channel(game.channel_id)
                            if channel:
                                winner = self.bot.get_user(winner_id)
                                loser = self.bot.get_user(loser_id)
                                
                                embed = discord.Embed(
                                    title="⏰ Partida Finalizada por Timeout",
                                    description=(
                                        f"**{winner.mention if winner else 'Jogador'}** venceu por W.O.!\n"
                                        f"**{loser.mention if loser else 'Oponente'}** não respondeu há mais de 5 minutos."
                                    ),
                                    color=discord.Color.orange(),
                                )
                                await channel.send(embed=embed)
                        except Exception as exc:
                            LOGGER.error("Erro ao notificar timeout: %s", exc)
                        
                        LOGGER.info("Partida %s finalizada por timeout (vencedor: %s)", game.game_id, winner_id)
                    
                    except Exception as exc:
                        LOGGER.error("Erro ao processar timeout da partida %s: %s", game_data.get("id"), exc)
            
            except asyncio.CancelledError:
                break
            except Exception as exc:
                LOGGER.error("Erro no monitor de timeout: %s", exc)
    
    async def start_game(self, game: NavalGame):
        """Inicia uma partida (ambas as frotas completas)."""
        # Recarrega o jogo do banco para ter dados atualizados
        game_data = await self.db.get_naval_game(game.game_id)
        updated_game = NavalGame(game_data)
        
        await self.db.update_naval_game(
            updated_game.game_id,
            status="active",
        )
        updated_game.status = "active"
        
        # Mostra transição na primeira vez com o nome do jogador
        current_player = self.bot.get_user(updated_game.current_turn)
        await self.update_game_display(
            updated_game, 
            show_transition=True,
            player_name=current_player.display_name if current_player else None
        )
    
    async def end_game(self, game: NavalGame, winner_id: int):
        """Finaliza uma partida."""
        loser_id = game.player2_id if winner_id == game.player1_id else game.player1_id
        
        # Atualiza estatísticas
        await self.db.update_naval_stats(
            game.guild_id,
            winner_id,
            wins=1,
            points=POINTS_WIN,
        )
        await self.db.increment_naval_streak(game.guild_id, winner_id)
        
        await self.db.update_naval_stats(
            game.guild_id,
            loser_id,
            losses=1,
        )
        await self.db.reset_naval_streak(game.guild_id, loser_id)
        
        # Finaliza partida
        from datetime import datetime
        await self.db.update_naval_game(
            game.game_id,
            status="finished",
            finished_at=datetime.utcnow().isoformat(),
        )
        
        # Renderiza tabuleiros finais
        renderer = self.get_renderer()
        
        player1_board = game.get_player_board(game.player1_id)
        player2_board = game.get_player_board(game.player2_id)
        
        # Converte shots para formato esperado pelo renderer público
        p1_shots = [{"coord": s.get("coord", ""), "hit": s.get("hit", False)} for s in player2_board.get("shots", [])]
        p2_shots = [{"coord": s.get("coord", ""), "hit": s.get("hit", False)} for s in player1_board.get("shots", [])]
        
        p1_public = renderer.render_public_board(p1_shots)
        p2_public = renderer.render_public_board(p2_shots)
        
        p1_file = discord.File(p1_public, filename="board.png")
        p2_file = discord.File(p2_public, filename="board.png")
        
        # Limpa canal e mostra resultado
        try:
            channel = self.bot.get_channel(game.channel_id)
            if not channel:
                return
            
            # Limpa todas as mensagens do canal
            try:
                async for message in channel.history(limit=None):
                    try:
                        await message.delete()
                    except:
                        pass
            except Exception as exc:
                LOGGER.warning("Erro ao limpar canal: %s", exc)
            
            winner = self.bot.get_user(winner_id)
            loser = self.bot.get_user(loser_id)
            
            # Embed de resultado
            result_embed = discord.Embed(
                title="🎉 Partida Finalizada!",
                description=(
                    f"**🏆 Vencedor:** {winner.mention if winner else 'Jogador'}\n"
                    f"**💀 Perdedor:** {loser.mention if loser else 'Oponente'}\n\n"
                    f"**Tabuleiros Finais:**"
                ),
                color=discord.Color.green(),
            )
            
            await channel.send(embed=result_embed, files=[p1_file, p2_file])
            
            # Mostra ranking atualizado
            ranking = await self.db.get_naval_ranking(game.guild_id, limit=10)
            if ranking:
                ranking_text = "🏆 **Ranking Atualizado:**\n\n"
                for i, player in enumerate(ranking[:10], 1):
                    user = self.bot.get_user(int(player["user_id"]))
                    name = user.display_name if user else f"Jogador {player['user_id']}"
                    ranking_text += (
                        f"**{i}.** {name} - "
                        f"🎯 {player['points']} pts | "
                        f"✅ {player['wins']}W | "
                        f"❌ {player['losses']}L"
                    )
                    if player.get("current_streak", 0) > 0:
                        ranking_text += f" | 🔥 {player['current_streak']} streak"
                    ranking_text += "\n"
                
                ranking_embed = discord.Embed(
                    title="📊 Ranking de Batalha Naval",
                    description=ranking_text,
                    color=discord.Color.blue(),
                )
                await channel.send(embed=ranking_embed)
        except Exception as exc:
            LOGGER.error("Erro ao finalizar partida: %s", exc)
    
    async def update_game_display_with_feedback(
        self, 
        game: NavalGame, 
        is_hit: bool,
        show_transition: bool = False
    ):
        """Atualiza a exibição com feedback visual (acerto/erro) seguido de transição/tabuleiro."""
        try:
            channel = self.bot.get_channel(game.channel_id)
            if not channel:
                return
            
            renderer = self.get_renderer()
            
            # 1. Mostra imagem de feedback (acerto ou erro)
            feedback_buffer = renderer.render_feedback_image(is_hit)
            if feedback_buffer:
                feedback_file = discord.File(feedback_buffer, filename="feedback.jpg")
                
                current_player = self.bot.get_user(game.current_turn)
                opponent_id = game.player2_id if game.current_turn == game.player1_id else game.player1_id
                opponent = self.bot.get_user(opponent_id)
                
                feedback_embed = discord.Embed(
                    title="⚓ Batalha Naval",
                    description=(
                        f"**Turno de:** {current_player.mention if current_player else 'Jogador'}\n"
                        f"**Oponente:** {opponent.mention if opponent else 'Oponente'}\n\n"
                        f"{'🎯 **ACERTO!** Você mantém o turno!' if is_hit else '💥 **ÁGUA!** Turno do oponente.'}"
                    ),
                    color=discord.Color.green() if is_hit else discord.Color.red(),
                )
                feedback_embed.set_image(url="attachment://feedback.jpg")
                
                view = NavalGameView(self, game)
                
                # Atualiza mensagem com feedback
                if game.message_id:
                    try:
                        message = await channel.fetch_message(game.message_id)
                        await message.delete()
                        new_message = await channel.send(embed=feedback_embed, file=feedback_file, view=view)
                        await self.db.update_naval_game(game.game_id, message_id=new_message.id)
                        game.message_id = new_message.id
                    except discord.NotFound:
                        new_message = await channel.send(embed=feedback_embed, file=feedback_file, view=view)
                        await self.db.update_naval_game(game.game_id, message_id=new_message.id)
                        game.message_id = new_message.id
                else:
                    new_message = await channel.send(embed=feedback_embed, file=feedback_file, view=view)
                    await self.db.update_naval_game(game.game_id, message_id=new_message.id)
                    game.message_id = new_message.id
                
                # Aguarda 2 segundos antes de mostrar próximo estado
                await asyncio.sleep(2)
            
            # 2. Se acertou, apenas atualiza tabuleiro (jogador mantém turno)
            if is_hit:
                await self.update_game_display(game, show_transition=False)
            else:
                # 3. Se errou, mostra transição e depois tabuleiro
                if show_transition:
                    # Mostra transição do próximo jogador
                    await self.update_game_display(game, show_transition=True)
                    # Aguarda 3 segundos
                    await asyncio.sleep(3)
                # Atualiza com tabuleiro normal
                await self.update_game_display(game, show_transition=False)
        
        except Exception as exc:
            LOGGER.error("Erro ao atualizar exibição com feedback: %s", exc, exc_info=True)
    
    async def update_game_display(self, game: NavalGame, show_transition: bool = True, player_name: Optional[str] = None):
        """Atualiza a exibição da partida com feedback visual imediato."""
        try:
            channel = self.bot.get_channel(game.channel_id)
            if not channel:
                return
            
            renderer = self.get_renderer()
            current_player = self.bot.get_user(game.current_turn)
            
            # Usa player_name fornecido ou pega do current_player
            if not player_name and current_player:
                player_name = current_player.display_name
            
            # Renderiza visão pública (tiros do jogador atual)
            # Tabuleiro público mostra apenas mar + hit/miss (SEM navios)
            current_player_board = game.get_player_board(game.current_turn)
            opponent_board = game.get_opponent_board(game.current_turn)
            
            # Converte shots para formato esperado (já está salvo no banco)
            shots = [{"coord": s.get("coord", ""), "hit": s.get("hit", False)} for s in opponent_board.get("shots", [])]
            
            # Renderiza tabuleiro com transição se necessário
            board_buffer = renderer.render_public_board(
                shots, 
                show_transition=show_transition,
                player_name=player_name if show_transition else None
            )
            board_file = discord.File(board_buffer, filename="board.png")
            
            # Cria embed com informações atualizadas
            opponent_id = game.player2_id if game.current_turn == game.player1_id else game.player1_id
            opponent = self.bot.get_user(opponent_id)
            
            # Conta acertos e erros do jogador atual
            hits = sum(1 for s in shots if s.get("hit", False))
            misses = len(shots) - hits
            
            embed = discord.Embed(
                title="⚓ Batalha Naval",
                description=(
                    f"**Turno de:** {current_player.mention if current_player else 'Jogador'}\n"
                    f"**Oponente:** {opponent.mention if opponent else 'Oponente'}\n\n"
                    f"🎯 **Acertos:** {hits} | 💥 **Erros:** {misses}\n\n"
                    f"Use os menus abaixo para selecionar uma coordenada e clicar em **🔥 DISPARAR**"
                ),
                color=discord.Color.blue(),
            )
            embed.set_image(url="attachment://board.png")
            
            view = NavalGameView(self, game)
            
            if game.message_id:
                try:
                    message = await channel.fetch_message(game.message_id)
                    # Deleta e recria para atualizar arquivo
                    await message.delete()
                    new_message = await channel.send(embed=embed, file=board_file, view=view)
                    await self.db.update_naval_game(game.game_id, message_id=new_message.id)
                    game.message_id = new_message.id
                    return
                except discord.NotFound:
                    pass
            
            # Se não encontrou mensagem, cria nova
            message = await channel.send(embed=embed, file=board_file, view=view)
            await self.db.update_naval_game(game.game_id, message_id=message.id)
            game.message_id = message.id
        
        except Exception as exc:
            LOGGER.error("Erro ao atualizar exibição da partida: %s", exc, exc_info=True)
    
    async def update_queue_display(self, guild_id: int):
        """Atualiza exibição da fila."""
        queue = await self.db.get_queue(guild_id)
        
        # Tenta fazer match
        match = await self.db.match_players(guild_id)
        if match:
            player1_id, player2_id = match
            await self.create_game(guild_id, player1_id, player2_id)
    
    async def create_game(self, guild_id: int, player1_id: int, player2_id: int, channel: Optional[discord.TextChannel] = None):
        """Cria uma nova partida. Setup via DM, jogo no canal configurado."""
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                raise ValueError(f"Guild {guild_id} não encontrada")
            
            # Busca canal configurado
            settings = await self.db.get_settings(guild_id)
            naval_channel_id = settings.get("channel_naval")
            
            if naval_channel_id:
                naval_channel = guild.get_channel(int(naval_channel_id))
                if naval_channel:
                    channel = naval_channel
            
            # Se não foi fornecido um canal configurado, usa o fornecido ou tenta encontrar um
            if not channel:
                if not naval_channel_id:
                    channel = guild.system_channel
                    if not channel:
                        # Tenta encontrar qualquer canal de texto
                        for ch in guild.text_channels:
                            bot_member = guild.get_member(self.bot.user.id)
                            if bot_member and ch.permissions_for(bot_member).send_messages:
                                channel = ch
                                break
            
            if not channel:
                raise ValueError("Não foi possível encontrar canal para criar partida. Configure com !naval_setup")
            
            # Cria partida no banco
            game_id = await self.db.create_naval_game(guild_id, player1_id, player2_id, channel.id)
            game_data = await self.db.get_naval_game(game_id)
            game = NavalGame(game_data)
            
            player1 = self.bot.get_user(player1_id)
            player2 = self.bot.get_user(player2_id)
            
            # Envia setup via DM para cada jogador
            view1 = FleetSetupView(self, game, player1_id)
            view2 = FleetSetupView(self, game, player2_id)
            
            # Renderiza preview inicial (vazio) - um para cada jogador
            renderer = self.get_renderer()
            empty_preview1 = renderer.render_preview([], [])
            empty_preview2 = renderer.render_preview([], [])
            preview_file1 = discord.File(empty_preview1, filename="preview.png")
            preview_file2 = discord.File(empty_preview2, filename="preview.png")
            
            # Envia DM para player1
            if player1:
                try:
                    dm_channel1 = await player1.create_dm()
                    dm_embed1 = discord.Embed(
                        title="⚓ Nova Partida de Batalha Naval",
                        description=(
                            f"**Oponente:** {player2.mention if player2 else 'Oponente'}\n\n"
                            f"🚢 **Fase de Setup:** Posicione sua frota!\n"
                            f"**Progresso:** 0/5 navios posicionados\n\n"
                            f"Clique nos botões abaixo para posicionar seus navios:"
                        ),
                        color=discord.Color.blue(),
                    )
                    dm_embed1.set_image(url="attachment://preview.png")
                    dm_msg1 = await dm_channel1.send(embed=dm_embed1, file=preview_file1, view=view1)
                    view1.dm_message_id = dm_msg1.id
                except discord.Forbidden:
                    LOGGER.warning("Não foi possível enviar DM para player1 %s", player1_id)
                except Exception as exc:
                    LOGGER.error("Erro ao enviar DM para player1: %s", exc, exc_info=True)
            
            # Envia DM para player2
            if player2:
                try:
                    dm_channel2 = await player2.create_dm()
                    dm_embed2 = discord.Embed(
                        title="⚓ Nova Partida de Batalha Naval",
                        description=(
                            f"**Oponente:** {player1.mention if player1 else 'Oponente'}\n\n"
                            f"🚢 **Fase de Setup:** Posicione sua frota!\n"
                            f"**Progresso:** 0/5 navios posicionados\n\n"
                            f"Clique nos botões abaixo para posicionar seus navios:"
                        ),
                        color=discord.Color.blue(),
                    )
                    dm_embed2.set_image(url="attachment://preview.png")
                    dm_msg2 = await dm_channel2.send(embed=dm_embed2, file=preview_file2, view=view2)
                    view2.dm_message_id = dm_msg2.id
                except discord.Forbidden:
                    LOGGER.warning("Não foi possível enviar DM para player2 %s", player2_id)
                except Exception as exc:
                    LOGGER.error("Erro ao enviar DM para player2: %s", exc, exc_info=True)
            
            # Envia mensagem no canal informando que a partida começou
            channel_embed = discord.Embed(
                title="⚓ Nova Partida Iniciada",
                description=(
                    f"**{player1.mention if player1 else 'Jogador 1'}** vs **{player2.mention if player2 else 'Jogador 2'}**\n\n"
                    f"🚢 **Fase de Setup:** Ambos os jogadores estão posicionando suas frotas via DM.\n"
                    f"A partida começará quando ambos completarem o setup."
                ),
                color=discord.Color.blue(),
            )
            message = await channel.send(embed=channel_embed)
            await self.db.update_naval_game(game_id, message_id=message.id)
        
        except Exception as exc:
            LOGGER.error("Erro ao criar partida: %s", exc, exc_info=True)
            raise
    
    @commands.command(name="naval_challenge", aliases=["naval"])
    async def naval_challenge(self, ctx: commands.Context, opponent: discord.Member):
        """Desafia um jogador para uma partida de Batalha Naval.

Uso: !naval @usuario ou !naval_challenge @usuario

Exemplos:
- !naval @Jogador
- !naval_challenge @Amigo
"""
        try:
            if opponent.id == ctx.author.id:
                await ctx.reply("❌ Você não pode desafiar a si mesmo!", delete_after=10)
                return
            
            if opponent.bot:
                await ctx.reply("❌ Você não pode desafiar um bot!", delete_after=10)
                return
            
            # Verifica se já tem partida ativa
            existing = await self.db.get_naval_game_by_players(ctx.guild.id, ctx.author.id)
            if existing:
                await ctx.reply("❌ Você já tem uma partida ativa!", delete_after=10)
                return
            
            existing2 = await self.db.get_naval_game_by_players(ctx.guild.id, opponent.id)
            if existing2:
                await ctx.reply(f"❌ {opponent.mention} já tem uma partida ativa!", delete_after=10)
                return
            
            await self.create_game(ctx.guild.id, ctx.author.id, opponent.id, ctx.channel)
            await ctx.reply(f"✅ Desafio enviado para {opponent.mention}!", delete_after=10)
        
        except Exception as exc:
            LOGGER.error("Erro no comando naval_challenge: %s", exc, exc_info=True)
            await ctx.reply(
                "❌ Ocorreu um erro ao criar a partida. Verifique os logs ou tente novamente.",
                delete_after=15
            )
    
    @commands.command(name="naval_queue")
    async def naval_queue(self, ctx: commands.Context):
        """Entra ou sai da fila de matchmaking para Batalha Naval.

Uso: !naval_queue

Exemplos:
- !naval_queue
"""
        # Verifica se já tem partida ativa
        existing = await self.db.get_naval_game_by_players(ctx.guild.id, ctx.author.id)
        if existing:
            await ctx.reply("❌ Você já tem uma partida ativa!", delete_after=10)
            return
        
        queue = await self.db.get_queue(ctx.guild.id)
        in_queue = any(int(q["user_id"]) == ctx.author.id for q in queue)
        
        if in_queue:
            await self.db.remove_from_queue(ctx.guild.id, ctx.author.id)
            await ctx.reply("✅ Você saiu da fila de matchmaking.", delete_after=10)
        else:
            await self.db.add_to_queue(ctx.guild.id, ctx.author.id)
            await ctx.reply("✅ Você entrou na fila de matchmaking!", delete_after=10)
            
            # Tenta fazer match
            await self.update_queue_display(ctx.guild.id)
    
    @commands.command(name="naval_rank")
    async def naval_rank(self, ctx: commands.Context):
        """Exibe o ranking dos top 10 jogadores de Batalha Naval do servidor.

Uso: !naval_rank

Exemplos:
- !naval_rank
"""
        ranking = await self.db.get_naval_ranking(ctx.guild.id, limit=10)
        
        if not ranking:
            await ctx.reply("📊 Nenhum jogador no ranking ainda.", delete_after=15)
            return
        
        embed = discord.Embed(
            title="🏆 Ranking de Batalha Naval",
            description="Top 10 jogadores do servidor",
            color=discord.Color.gold(),
        )
        
        ranking_text = []
        medals = ["🥇", "🥈", "🥉"]
        
        for i, player in enumerate(ranking[:10], 1):
            user_id = int(player["user_id"])
            user = self.bot.get_user(user_id)
            username = user.mention if user else f"ID: {user_id}"
            
            medal = medals[i - 1] if i <= 3 else f"**{i}.**"
            
            ranking_text.append(
                f"{medal} {username}\n"
                f"   🎯 Pontos: {player['points']} | "
                f"Vitórias: {player['wins']} | "
                f"Derrotas: {player['losses']} | "
                f"Sequência: {player['current_streak']}"
            )
        
        embed.add_field(name="Ranking", value="\n".join(ranking_text), inline=False)
        embed.set_footer(text="Use !naval_stats para ver suas estatísticas")
        
        await ctx.reply(embed=embed, delete_after=60)
    
    @commands.command(name="naval_stats")
    async def naval_stats(self, ctx: commands.Context):
        """Exibe suas estatísticas pessoais de Batalha Naval (pontos, vitórias, derrotas, etc).

Uso: !naval_stats

Exemplos:
- !naval_stats
"""
        stats = await self.db.get_naval_stats(ctx.guild.id, ctx.author.id)
        
        if not stats:
            await ctx.reply(
                "📊 Você ainda não tem estatísticas.\n"
                "Jogue uma partida para começar!",
                delete_after=15
            )
            return
        
        embed = discord.Embed(
            title=f"📊 Estatísticas de {ctx.author.display_name}",
            color=discord.Color.blue(),
        )
        
        win_rate = (stats["wins"] / (stats["wins"] + stats["losses"]) * 100) if (stats["wins"] + stats["losses"]) > 0 else 0
        
        embed.add_field(name="🎯 Pontos", value=str(stats["points"]), inline=True)
        embed.add_field(name="✅ Vitórias", value=str(stats["wins"]), inline=True)
        embed.add_field(name="❌ Derrotas", value=str(stats["losses"]), inline=True)
        embed.add_field(name="📈 Taxa de Vitória", value=f"{win_rate:.1f}%", inline=True)
        embed.add_field(name="🎯 Acertos", value=str(stats["total_hits"]), inline=True)
        embed.add_field(name="💥 Erros", value=str(stats["total_misses"]), inline=True)
        embed.add_field(name="🔥 Sequência Atual", value=str(stats["current_streak"]), inline=True)
        
        await ctx.reply(embed=embed, delete_after=60)
    
    @commands.command(name="naval_setup")
    @commands.has_permissions(administrator=True)
    async def naval_setup(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Configura o canal onde as partidas de Batalha Naval serão jogadas.

Uso: !naval_setup [canal]

Exemplos:
- !naval_setup
- !naval_setup #batalha-naval
"""
        if not channel:
            channel = ctx.channel
        
        await self.db.upsert_settings(ctx.guild.id, channel_naval=channel.id)
        
        embed = discord.Embed(
            title="✅ Canal Configurado",
            description=f"Canal de Batalha Naval configurado: {channel.mention}",
            color=discord.Color.green(),
        )
        await ctx.reply(embed=embed, delete_after=15)
    
    @commands.command(name="naval_zerar")
    @commands.has_permissions(administrator=True)
    async def naval_zerar(self, ctx: commands.Context):
        """Zera todas as estatísticas de Batalha Naval do servidor (apenas administradores).

Uso: !naval_zerar

Exemplos:
- !naval_zerar
"""
        await self.db.clear_naval_stats(ctx.guild.id)
        
        embed = discord.Embed(
            title="✅ Ranking Zerado",
            description="Todas as estatísticas de Batalha Naval foram zeradas.",
            color=discord.Color.orange(),
        )
        await ctx.reply(embed=embed, delete_after=15)
    
    @commands.command(name="naval_fim")
    @commands.has_permissions(administrator=True)
    async def naval_fim(self, ctx: commands.Context):
        """Finaliza todas as partidas de Batalha Naval em andamento do servidor (apenas administradores).

Uso: !naval_fim

Exemplos:
- !naval_fim
"""
        try:
            # Busca todas as partidas ativas do servidor
            active_games = await self.db.list_active_naval_games(ctx.guild.id)
            
            if not active_games:
                await ctx.reply("ℹ️ Não há partidas ativas para finalizar.", delete_after=10)
                return
            
            finalized_count = 0
            from datetime import datetime
            
            for game_data in active_games:
                try:
                    game = NavalGame(game_data)
                    
                    # Finaliza a partida sem vencedor (cancelamento)
                    await self.db.update_naval_game(
                        game.game_id,
                        status="finished",
                        finished_at=datetime.utcnow().isoformat(),
                    )
                    
                    # Tenta notificar no canal
                    try:
                        channel = self.bot.get_channel(game.channel_id)
                        if channel:
                            player1 = self.bot.get_user(game.player1_id)
                            player2 = self.bot.get_user(game.player2_id)
                            
                            embed = discord.Embed(
                                title="⛔ Partida Cancelada",
                                description=(
                                    f"**Jogador 1:** {player1.mention if player1 else 'Jogador'}\n"
                                    f"**Jogador 2:** {player2.mention if player2 else 'Oponente'}\n\n"
                                    f"A partida foi finalizada por um administrador."
                                ),
                                color=discord.Color.red(),
                            )
                            await channel.send(embed=embed)
                    except Exception as exc:
                        LOGGER.warning("Erro ao notificar cancelamento: %s", exc)
                    
                    finalized_count += 1
                    LOGGER.info("Partida %s finalizada por comando admin", game.game_id)
                    
                except Exception as exc:
                    LOGGER.error("Erro ao finalizar partida %s: %s", game_data.get("id"), exc, exc_info=True)
            
            embed = discord.Embed(
                title="✅ Partidas Finalizadas",
                description=f"**{finalized_count}** partida(s) foram finalizadas com sucesso.",
                color=discord.Color.green(),
            )
            await ctx.reply(embed=embed, delete_after=15)
            
        except Exception as exc:
            LOGGER.error("Erro no comando naval_fim: %s", exc, exc_info=True)
            await ctx.reply(
                "❌ Ocorreu um erro ao finalizar as partidas. Verifique os logs.",
                delete_after=15
            )


async def setup(bot):
    """Função de setup para carregamento da extensão."""
    from db import Database
    
    await bot.add_cog(NavalCog(bot, bot.db))