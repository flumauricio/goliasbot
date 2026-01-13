import io
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

# Importa REQUIRED_SHIPS para obter tamanhos
from actions.naval_combat import REQUIRED_SHIPS

LOGGER = logging.getLogger(__name__)

# Geometria do grid (coordenadas atualizadas)
# Centro A1: X = 139, Y = 237
# Centro J10: X = 855, Y = 887
GRID_A1_X = 139
GRID_A1_Y = 237
GRID_J10_X = 855
GRID_J10_Y = 887
STEP_X = (GRID_J10_X - GRID_A1_X) / 9  # ~79.56px
STEP_Y = (GRID_J10_Y - GRID_A1_Y) / 9  # ~72.22px

# Tamanho do tabuleiro
BOARD_SIZE = (1024, 1024)


class NavalRenderer:
    """Renderer de imagens para Batalha Naval com cache de assets."""
    
    def __init__(self, assets_path: Path):
        self.assets_path = assets_path
        self._board_image: Optional[Image.Image] = None
        self._hit_icon: Optional[Image.Image] = None
        self._miss_icon: Optional[Image.Image] = None
        self._ship_images: Dict[str, Image.Image] = {}
        self._acerto_image: Optional[Image.Image] = None
        self._erro_image: Optional[Image.Image] = None
        self._loaded = False
    
    def _load_assets(self) -> None:
        """Carrega todos os assets uma única vez na inicialização."""
        if self._loaded:
            return
        
        try:
            # Carrega tabuleiro base
            board_path = self.assets_path / "board.png"
            if not board_path.exists():
                # Tenta .jpg se .png não existir
                board_path = self.assets_path / "board.jpg"
            
            if board_path.exists():
                self._board_image = Image.open(board_path).convert("RGBA")
                if self._board_image.size != BOARD_SIZE:
                    self._board_image = self._board_image.resize(BOARD_SIZE, Image.Resampling.LANCZOS)
            else:
                # Cria tabuleiro branco se não existir
                self._board_image = Image.new("RGBA", BOARD_SIZE, (255, 255, 255, 255))
                LOGGER.warning("board.png/jpg não encontrado, usando tabuleiro branco")
            
            # Carrega ícones (cache em memória)
            hit_path = self.assets_path / "hit.png"
            miss_path = self.assets_path / "miss.png"
            
            if hit_path.exists():
                self._hit_icon = Image.open(hit_path).convert("RGBA")
            else:
                LOGGER.warning("hit.png não encontrado")
            
            if miss_path.exists():
                self._miss_icon = Image.open(miss_path).convert("RGBA")
            else:
                LOGGER.warning("miss.png não encontrado")
            
            # Carrega navios (SEM redimensionamento - tamanhos originais)
            for ship_name in ["ship1", "ship2", "ship3", "ship4"]:
                ship_path = self.assets_path / f"{ship_name}.png"
                if ship_path.exists():
                    self._ship_images[ship_name] = Image.open(ship_path).convert("RGBA")
                else:
                    LOGGER.warning(f"{ship_name}.png não encontrado")
            
            # Carrega imagens de feedback (acerto e erro)
            acerto_path = self.assets_path / "acerto.jpg"
            if acerto_path.exists():
                self._acerto_image = Image.open(acerto_path).convert("RGB")
            else:
                LOGGER.warning("acerto.jpg não encontrado")
            
            erro_path = self.assets_path / "erro.jpg"
            if erro_path.exists():
                self._erro_image = Image.open(erro_path).convert("RGB")
            else:
                LOGGER.warning("erro.jpg não encontrado")
            
            self._loaded = True
        
        except Exception as exc:
            LOGGER.error("Erro ao carregar assets: %s", exc, exc_info=True)
            raise
    
    def calculate_grid_position(self, coord: str) -> Tuple[int, int]:
        """Converte coordenada (A1-J10) para posição em pixels (centro da célula)."""
        if len(coord) < 2:
            raise ValueError(f"Coordenada inválida: {coord}")
        
        letter = coord[0].upper()
        number_str = coord[1:]
        
        if letter < 'A' or letter > 'J':
            raise ValueError(f"Letra inválida: {letter}")
        
        try:
            number = int(number_str)
            if number < 1 or number > 10:
                raise ValueError(f"Número inválido: {number}")
        except ValueError:
            raise ValueError(f"Número inválido: {number_str}")
        
        # Calcula posição do centro da célula
        col = ord(letter) - ord('A')
        row = number - 1
        
        x = int(GRID_A1_X + col * STEP_X)
        y = int(GRID_A1_Y + row * STEP_Y)
        
        return (x, y)
    
    def calculate_midpoint(self, start_coord: str, end_coord: str) -> Tuple[int, int]:
        """Calcula o ponto médio entre duas coordenadas para posicionamento do navio."""
        start_x, start_y = self.calculate_grid_position(start_coord)
        end_x, end_y = self.calculate_grid_position(end_coord)
        
        mid_x = (start_x + end_x) // 2
        mid_y = (start_y + end_y) // 2
        
        return (mid_x, mid_y)
    
    def _get_ship_image(self, ship_type: str, direction: str) -> Optional[Image.Image]:
        """Retorna imagem do navio, rotacionada se necessário (SEM redimensionamento).
        
        Lógica de rotação:
        - Se mesma letra (vertical) → rotaciona 90°
        - Se mesmo número (horizontal) → não rotaciona
        """
        if not self._loaded:
            self._load_assets()
        
        ship_img = self._ship_images.get(ship_type)
        if not ship_img:
            return None
        
        # Cria cópia para não modificar o original
        ship_img = ship_img.copy()
        
        if direction.upper() == 'V':
            # Vertical: mesma letra, números diferentes → rotaciona 90 graus
            ship_img = ship_img.rotate(90, expand=True)
        
        return ship_img
    
    def render_preview(
        self,
        ships: List[Dict[str, any]],
        shots: Optional[List[str]] = None,
    ) -> io.BytesIO:
        """Renderiza preview efêmero durante posicionamento."""
        return self.render_private_board(ships, shots or [])
    
    def render_private_board(
        self,
        ships: List[Dict[str, any]],
        shots: List[str],
    ) -> io.BytesIO:
        """Renderiza visão privada (dono): navios posicionados + tiros recebidos."""
        if not self._loaded:
            self._load_assets()
        
        # Cria cópia do tabuleiro base
        board = self._board_image.copy()
        
        # Desenha navios
        for ship in ships:
            ship_type = ship.get("type", "").lower()
            start_coord = ship.get("start", "").upper()
            end_coord = ship.get("end", "").upper()
            direction = ship.get("direction", "H").upper()
            
            if not ship_type or not start_coord:
                continue
            
            # Se não tiver end_coord, usa apenas start (compatibilidade)
            if not end_coord:
                end_coord = start_coord
            
            ship_img = self._get_ship_image(ship_type, direction)
            if not ship_img:
                continue
            
            # Calcula ponto médio entre início e fim
            mid_x, mid_y = self.calculate_midpoint(start_coord, end_coord)
            
            # Centraliza o navio no ponto médio
            paste_x = mid_x - ship_img.width // 2
            paste_y = mid_y - ship_img.height // 2
            
            # Cola com mask para preservar transparência
            board.paste(ship_img, (paste_x, paste_y), ship_img)
        
        # Desenha tiros recebidos
        for shot_coord in shots:
            try:
                # shot_coord pode ser string ou dict
                if isinstance(shot_coord, dict):
                    coord = shot_coord.get("coord", "")
                    is_hit = shot_coord.get("hit", False)
                else:
                    coord = str(shot_coord)
                    # Determina se é hit ou miss (verifica se há navio na coordenada)
                    is_hit = any(
                        self._is_coord_in_ship(coord, ship)
                        for ship in ships
                    )
                
                if not coord:
                    continue
                
                x, y = self.calculate_grid_position(coord)
                
                icon = self._hit_icon if (is_hit and self._hit_icon) else (self._miss_icon if self._miss_icon else None)
                if icon:
                    icon_x = x - icon.width // 2
                    icon_y = y - icon.height // 2
                    board.paste(icon, (icon_x, icon_y), icon)
            except (ValueError, KeyError):
                continue
        
        # Converte para BytesIO
        output = io.BytesIO()
        board.save(output, format="PNG")
        output.seek(0)
        return output
    
    def render_public_board(
        self,
        shots: List[Dict[str, any]],
        show_transition: bool = False,
        player_name: Optional[str] = None,
    ) -> io.BytesIO:
        """Renderiza visão pública: apenas mar + ícones hit/miss (SEM navios)."""
        if not self._loaded:
            self._load_assets()
        
        # Se deve mostrar transição, renderiza a imagem de transição
        if show_transition and player_name:
            return self.render_turn_transition(player_name)
        
        # Cria cópia do tabuleiro base (sem navios)
        board = self._board_image.copy()
        
        # Desenha apenas os tiros
        for shot in shots:
            coord = shot.get("coord", "")
            is_hit = shot.get("hit", False)
            
            if not coord:
                continue
            
            try:
                x, y = self.calculate_grid_position(coord)
                icon = self._hit_icon if (is_hit and self._hit_icon) else (self._miss_icon if self._miss_icon else None)
                
                if icon:
                    icon_x = x - icon.width // 2
                    icon_y = y - icon.height // 2
                    board.paste(icon, (icon_x, icon_y), icon)
            except ValueError:
                continue
        
        # Converte para BytesIO
        output = io.BytesIO()
        board.save(output, format="PNG")
        output.seek(0)
        return output
    
    def render_feedback_image(self, is_hit: bool) -> Optional[io.BytesIO]:
        """Renderiza imagem de feedback (acerto ou erro)."""
        if not self._loaded:
            self._load_assets()
        
        image = self._acerto_image if is_hit else self._erro_image
        if not image:
            return None
        
        # Retorna cópia da imagem como BytesIO
        output = io.BytesIO()
        image.save(output, format="JPEG")
        output.seek(0)
        return output
    
    def _is_coord_in_ship(self, coord: str, ship: Dict[str, any]) -> bool:
        """Verifica se uma coordenada está dentro de um navio."""
        start_coord = ship.get("start", "").upper()
        direction = ship.get("direction", "H").upper()
        ship_type = ship.get("type", "").lower()
        
        if not start_coord or not ship_type:
            return False
        
        try:
            start_x, start_y = self.calculate_grid_position(start_coord)
            coord_x, coord_y = self.calculate_grid_position(coord)
            
            # Obtém tamanho do navio
            ship_size = 0
            for req_ship in REQUIRED_SHIPS:
                if req_ship["type"].lower() == ship_type:
                    ship_size = req_ship["size"]
                    break
            
            if ship_size == 0:
                return False
            
            if direction == 'V':
                # Vertical: mesma letra (mesma coluna X), números diferentes (linhas Y)
                # Verifica se está na mesma coluna X
                if coord_x != start_x:
                    return False
                # Para vertical, o navio ocupa múltiplas linhas Y
                start_row = int((start_y - GRID_A1_Y) / STEP_Y) if STEP_Y > 0 else 0
                coord_row = int((coord_y - GRID_A1_Y) / STEP_Y) if STEP_Y > 0 else 0
                return start_row <= coord_row < start_row + ship_size
            else:
                # Horizontal: mesmo número (mesma linha Y), letras diferentes (colunas X)
                # Verifica se está na mesma linha Y
                if coord_y != start_y:
                    return False
                # Para horizontal, o navio ocupa múltiplas colunas X
                start_col = int((start_x - GRID_A1_X) / STEP_X) if STEP_X > 0 else 0
                coord_col = int((coord_x - GRID_A1_X) / STEP_X) if STEP_X > 0 else 0
                return start_col <= coord_col < start_col + ship_size
        
        except (ValueError, ZeroDivisionError):
            return False
    
    def render_turn_transition(self, player_name: str) -> io.BytesIO:
        """Renderiza imagem intermediária informando o próximo jogador."""
        if not self._loaded:
            self._load_assets()
        
        # Cria imagem baseada no tabuleiro (fundo)
        board = self._board_image.copy()
        
        # Cria uma camada semi-transparente escura
        overlay = Image.new('RGBA', BOARD_SIZE, (0, 0, 0, 200))
        board = Image.alpha_composite(board.convert('RGBA'), overlay).convert('RGB')
        
        # Cria contexto de desenho
        draw = ImageDraw.Draw(board)
        
        # Tenta carregar fonte, se não conseguir usa padrão
        try:
            # Tenta usar fonte padrão do sistema
            font_large = ImageFont.truetype("arial.ttf", 72)
            font_medium = ImageFont.truetype("arial.ttf", 48)
        except:
            try:
                font_large = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 72)
                font_medium = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 48)
            except:
                # Fallback para fonte padrão
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()
        
        # Texto principal
        main_text = "⚓ É A SUA VEZ!"
        sub_text = f"Jogador: {player_name}"
        
        # Calcula posição central
        bbox_main = draw.textbbox((0, 0), main_text, font=font_large)
        text_width_main = bbox_main[2] - bbox_main[0]
        text_height_main = bbox_main[3] - bbox_main[1]
        
        bbox_sub = draw.textbbox((0, 0), sub_text, font=font_medium)
        text_width_sub = bbox_sub[2] - bbox_sub[0]
        text_height_sub = bbox_sub[3] - bbox_sub[1]
        
        # Posição central
        x_main = (BOARD_SIZE[0] - text_width_main) // 2
        y_main = BOARD_SIZE[1] // 2 - text_height_main - 20
        
        x_sub = (BOARD_SIZE[0] - text_width_sub) // 2
        y_sub = BOARD_SIZE[1] // 2 + 20
        
        # Desenha texto com sombra (para melhor legibilidade)
        shadow_offset = 3
        draw.text((x_main + shadow_offset, y_main + shadow_offset), main_text, font=font_large, fill=(0, 0, 0, 255))
        draw.text((x_main, y_main), main_text, font=font_large, fill=(255, 255, 255, 255))
        
        draw.text((x_sub + shadow_offset, y_sub + shadow_offset), sub_text, font=font_medium, fill=(0, 0, 0, 255))
        draw.text((x_sub, y_sub), sub_text, font=font_medium, fill=(200, 200, 255, 255))
        
        # Converte para BytesIO
        output = io.BytesIO()
        board.save(output, format="PNG")
        output.seek(0)
        return output
