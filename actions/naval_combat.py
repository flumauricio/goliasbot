import json
import logging
import re
from typing import Dict, List, Optional, Tuple

LOGGER = logging.getLogger(__name__)

# Regex para validar formato de coordenada
COORD_REGEX = re.compile(r"^[A-J]([1-9]|10)$", re.IGNORECASE)

# Navios necessários
REQUIRED_SHIPS = [
    {"type": "ship4", "count": 1, "size": 4},
    {"type": "ship3", "count": 1, "size": 3},
    {"type": "ship2", "count": 1, "size": 2},
    {"type": "ship1", "count": 2, "size": 1},
]

# Total de pontos de impacto para vitória
TOTAL_HIT_POINTS = 11  # 4 + 3 + 2 + 1 + 1


class NavalGame:
    """Gerencia lógica de uma partida de Batalha Naval."""
    
    def __init__(self, game_data: Dict):
        self.game_id = game_data["id"]
        self.guild_id = int(game_data["guild_id"])
        self.player1_id = int(game_data["player1_id"])
        self.player2_id = int(game_data["player2_id"])
        self.current_turn = int(game_data["current_turn"])
        self.status = game_data["status"]
        self.channel_id = int(game_data["channel_id"])
        self.message_id = int(game_data.get("message_id")) if game_data.get("message_id") else None
        
        # Carrega boards
        self.player1_board = json.loads(game_data["player1_board"])
        self.player2_board = json.loads(game_data["player2_board"])
    
    @staticmethod
    def parse_coordinate(coord_str: str) -> Tuple[str, int]:
        """Parse coordenada no formato 'A1' ou 'J10'. Retorna (letra, número)."""
        coord_str = coord_str.strip().upper()
        
        if not COORD_REGEX.match(coord_str):
            raise ValueError("Formato inválido. Use: A1, J10, etc.")
        
        letter = coord_str[0]
        number = int(coord_str[1:])
        
        if letter < 'A' or letter > 'J':
            raise ValueError(f"Letra inválida: {letter}. Use A-J.")
        
        if number < 1 or number > 10:
            raise ValueError(f"Número inválido: {number}. Use 1-10.")
        
        return (letter, number)
    
    def get_player_board(self, player_id: int) -> Dict:
        """Retorna o board de um jogador."""
        if player_id == self.player1_id:
            return self.player1_board
        elif player_id == self.player2_id:
            return self.player2_board
        else:
            raise ValueError(f"Jogador {player_id} não está nesta partida")
    
    def get_opponent_board(self, player_id: int) -> Dict:
        """Retorna o board do oponente."""
        if player_id == self.player1_id:
            return self.player2_board
        elif player_id == self.player2_id:
            return self.player1_board
        else:
            raise ValueError(f"Jogador {player_id} não está nesta partida")
    
    def validate_ship_placement(
        self,
        player_id: int,
        ship_type: str,
        start_coord: str,
        end_coord: str,
    ) -> Tuple[bool, Optional[str]]:
        """Valida posicionamento de um navio usando coordenadas início e fim."""
        board = self.get_player_board(player_id)
        ships = board.get("ships", [])
        
        # Verifica se o navio já foi posicionado
        ship_counts = {}
        for ship in ships:
            ship_type_existing = ship.get("type", "").lower()
            ship_counts[ship_type_existing] = ship_counts.get(ship_type_existing, 0) + 1
        
        # Verifica limite de navios
        for req_ship in REQUIRED_SHIPS:
            if req_ship["type"].lower() == ship_type.lower():
                current_count = ship_counts.get(ship_type.lower(), 0)
                if current_count >= req_ship["count"]:
                    return (False, f"Você já posicionou todos os navios do tipo {ship_type}")
                break
        
        # Parse coordenadas
        try:
            start_letter, start_number = self.parse_coordinate(start_coord)
            end_letter, end_number = self.parse_coordinate(end_coord)
        except ValueError as e:
            return (False, str(e))
        
        # Encontra tamanho do navio
        ship_size = 0
        for req_ship in REQUIRED_SHIPS:
            if req_ship["type"].lower() == ship_type.lower():
                ship_size = req_ship["size"]
                break
        
        if ship_size == 0:
            return (False, f"Tipo de navio inválido: {ship_type}")
        
        # Validação matemática: calcula distância
        letter_equal = (start_letter == end_letter)
        number_equal = (start_number == end_number)
        
        # Proibição de diagonais
        if not letter_equal and not number_equal:
            return (False, "Navios não podem ser posicionados na diagonal. Use coordenadas na mesma linha ou coluna.")
        
        # Determina direção e valida tamanho
        # IMPORTANTE: Letras = Eixo X, Números = Eixo Y
        if letter_equal:
            # Vertical: mesma letra (mesma coluna X), números diferentes (linhas Y diferentes)
            diff = abs(end_number - start_number)
            if diff != (ship_size - 1):
                return (False, f"Navio {ship_type} deve ocupar {ship_size} células. Diferença entre coordenadas: {diff + 1}")
            direction = 'V'
            # Garante que start é o menor número
            if start_number > end_number:
                start_number, end_number = end_number, start_number
        else:
            # Horizontal: mesmo número (mesma linha Y), letras diferentes (colunas X diferentes)
            diff = abs(ord(end_letter) - ord(start_letter))
            if diff != (ship_size - 1):
                return (False, f"Navio {ship_type} deve ocupar {ship_size} células. Diferença entre coordenadas: {diff + 1}")
            direction = 'H'
            # Garante que start é a letra menor
            if start_letter > end_letter:
                start_letter, end_letter = end_letter, start_letter
        
        # Verifica limites do grid
        if direction == 'V':
            if end_number > 10:
                return (False, "Navio ultrapassa os limites do grid (vertical)")
        else:
            if end_letter > 'J':
                return (False, "Navio ultrapassa os limites do grid (horizontal)")
        
        # Verifica colisões com outros navios
        start_coord_final = f"{start_letter}{start_number}"
        new_ship_cells = self._get_ship_cells(start_coord_final, direction, ship_size)
        
        for existing_ship in ships:
            existing_start = existing_ship.get("start", "").upper()
            existing_dir = existing_ship.get("direction", "H").upper()
            existing_type = existing_ship.get("type", "").lower()
            
            # Encontra tamanho do navio existente
            existing_size = 0
            for req_ship in REQUIRED_SHIPS:
                if req_ship["type"].lower() == existing_type:
                    existing_size = req_ship["size"]
                    break
            
            if existing_size == 0:
                continue
            
            existing_cells = self._get_ship_cells(existing_start, existing_dir, existing_size)
            
            # Verifica sobreposição (normaliza tudo para maiúsculas)
            new_cells_upper = {cell.upper() for cell in new_ship_cells}
            existing_cells_upper = {cell.upper() for cell in existing_cells}
            
            if new_cells_upper & existing_cells_upper:
                return (False, "Navio colide com outro navio já posicionado")
        
        return (True, None)
    
    def _get_ship_cells(self, start_coord: str, direction: str, size: int) -> List[str]:
        """Retorna lista de células ocupadas por um navio (sempre em maiúsculas).
        
        IMPORTANTE: Letras = Eixo X (colunas), Números = Eixo Y (linhas)
        """
        cells = []
        # Garante maiúsculas
        start_coord = start_coord.upper()
        letter = start_coord[0]
        number = int(start_coord[1:])
        
        if direction.upper() == 'V':
            # Vertical: mesma letra (coluna X), números diferentes (linhas Y)
            for i in range(size):
                new_number = number + i
                if new_number <= 10:
                    cells.append(f"{letter}{new_number}".upper())
        else:
            # Horizontal: mesmo número (linha Y), letras diferentes (colunas X)
            for i in range(size):
                new_letter = chr(ord(letter) + i)
                if new_letter <= 'J':
                    cells.append(f"{new_letter}{number}".upper())
        
        return cells
    
    def add_ship(
        self,
        player_id: int,
        ship_type: str,
        start_coord: str,
        end_coord: str,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Adiciona um navio ao board do jogador. Retorna (sucesso, erro, direção)."""
        valid, error = self.validate_ship_placement(player_id, ship_type, start_coord, end_coord)
        if not valid:
            return (False, error, None)
        
        board = self.get_player_board(player_id)
        ships = board.get("ships", [])
        
        # Parse coordenadas
        start_letter, start_number = self.parse_coordinate(start_coord)
        end_letter, end_number = self.parse_coordinate(end_coord)
        
        # Determina direção e normaliza início
        if start_letter == end_letter:
            direction = 'V'
            if start_number > end_number:
                start_number, end_number = end_number, start_number
        else:
            direction = 'H'
            if start_letter > end_letter:
                start_letter, end_letter = end_letter, start_letter
        
        start_coord_final = f"{start_letter}{start_number}".upper()
        
        # Adiciona navio
        ships.append({
            "type": ship_type.lower(),
            "start": start_coord_final,
            "end": f"{end_letter}{end_number}".upper(),
            "direction": direction,
        })
        
        board["ships"] = ships
        
        # Atualiza board no objeto
        if player_id == self.player1_id:
            self.player1_board = board
        else:
            self.player2_board = board
        
        return (True, None, direction)
    
    def is_fleet_complete(self, player_id: int) -> bool:
        """Verifica se a frota do jogador está completa."""
        board = self.get_player_board(player_id)
        ships = board.get("ships", [])
        
        ship_counts = {}
        for ship in ships:
            ship_type = ship.get("type", "").lower()
            ship_counts[ship_type] = ship_counts.get(ship_type, 0) + 1
        
        # Verifica se todos os navios necessários foram posicionados
        for req_ship in REQUIRED_SHIPS:
            current_count = ship_counts.get(req_ship["type"].lower(), 0)
            if current_count < req_ship["count"]:
                return False
        
        return True
    
    def fire_shot(self, attacker_id: int, coord: str) -> Tuple[bool, bool, Optional[str]]:
        """Executa um tiro. Retorna (sucesso, acerto, mensagem)."""
        if self.status != "active":
            return (False, False, "Partida não está em andamento")
        
        if attacker_id != self.current_turn:
            return (False, False, "Não é seu turno")
        
        # Valida coordenada
        try:
            letter, number = self.parse_coordinate(coord)
            coord_parsed = f"{letter}{number}".upper()
        except ValueError as e:
            return (False, False, str(e))
        
        # Verifica se já atirou nesta coordenada (normaliza para maiúsculas)
        opponent_board = self.get_opponent_board(attacker_id)
        shots = opponent_board.get("shots", [])
        
        for shot in shots:
            shot_coord = shot.get("coord", "").upper()
            if shot_coord == coord_parsed:
                return (False, False, "Você já atirou nesta coordenada")
        
        # Verifica se acertou
        opponent_ships = opponent_board.get("ships", [])
        is_hit = False
        
        for ship in opponent_ships:
            ship_cells = self._get_ship_cells(
                ship.get("start", ""),
                ship.get("direction", "H").upper(),
                self._get_ship_size(ship.get("type", ""))
            )
            if coord_parsed in [c.upper() for c in ship_cells]:
                is_hit = True
                break
        
        # Adiciona tiro ao board do oponente (sempre salva em maiúsculas)
        shots.append({
            "coord": coord_parsed,
            "hit": is_hit,
        })
        opponent_board["shots"] = shots
        
        # Atualiza board no objeto
        if attacker_id == self.player1_id:
            self.player2_board = opponent_board
        else:
            self.player1_board = opponent_board
        
        # Se acertou, mantém turno; se errou, passa turno
        if not is_hit:
            self.current_turn = self.player2_id if attacker_id == self.player1_id else self.player1_id
        
        return (True, is_hit, None)
    
    def _get_ship_size(self, ship_type: str) -> int:
        """Retorna o tamanho de um navio."""
        for req_ship in REQUIRED_SHIPS:
            if req_ship["type"].lower() == ship_type.lower():
                return req_ship["size"]
        return 0
    
    def check_victory(self, player_id: int) -> bool:
        """Verifica se um jogador venceu (todos os navios do oponente foram afundados)."""
        opponent_board = self.get_opponent_board(player_id)
        ships = opponent_board.get("ships", [])
        shots = opponent_board.get("shots", [])
        
        # Conta pontos de impacto (cada célula acertada conta como 1 ponto)
        hit_cells = set()
        for shot in shots:
            if shot.get("hit", False):
                hit_cells.add(shot.get("coord", "").upper())
        
        # Verifica quantas células de navios foram acertadas
        total_hit_points = 0
        for ship in ships:
            ship_cells = self._get_ship_cells(
                ship.get("start", ""),
                ship.get("direction", "H").upper(),
                self._get_ship_size(ship.get("type", ""))
            )
            
            for cell in ship_cells:
                if cell.upper() in hit_cells:
                    total_hit_points += 1
        
        return total_hit_points >= TOTAL_HIT_POINTS
    
    def to_dict(self) -> Dict:
        """Converte o jogo para dicionário para salvar no banco."""
        return {
            "id": self.game_id,
            "guild_id": str(self.guild_id),
            "player1_id": str(self.player1_id),
            "player2_id": str(self.player2_id),
            "current_turn": str(self.current_turn),
            "status": self.status,
            "channel_id": str(self.channel_id),
            "message_id": str(self.message_id) if self.message_id else None,
            "player1_board": json.dumps(self.player1_board),
            "player2_board": json.dumps(self.player2_board),
        }
