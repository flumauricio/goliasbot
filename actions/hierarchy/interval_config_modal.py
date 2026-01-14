"""Modal para configurar intervalo de verificação de promoções."""

import logging

import discord

LOGGER = logging.getLogger(__name__)


class IntervalConfigModal(discord.ui.Modal, title="Configurar Intervalo de Verificação"):
    """Modal para configurar intervalo de verificação de promoções."""
    
    def __init__(self, current_interval: int, db, guild: discord.Guild, parent_view):
        super().__init__()
        self.db = db
        self.guild = guild
        self.parent_view = parent_view
        
        # Limpa qualquer item existente
        self.clear_items()
        
        # Campo para intervalo
        self.interval_input = discord.ui.TextInput(
            label="Intervalo (horas)",
            placeholder="Ex: 1, 2, 6, 12, 24",
            required=True,
            max_length=3,
            default=str(current_interval)
        )
        self.add_item(self.interval_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Parse valor
            interval_str = self.interval_input.value.strip()
            if not interval_str.isdigit():
                await interaction.followup.send(
                    "❌ Intervalo deve ser um número válido.",
                    ephemeral=True
                )
                return
            
            interval = int(interval_str)
            if interval < 1:
                await interaction.followup.send(
                    "❌ Intervalo deve ser pelo menos 1 hora.",
                    ephemeral=True
                )
                return
            
            if interval > 168:  # 7 dias
                await interaction.followup.send(
                    "❌ Intervalo máximo é 168 horas (7 dias).",
                    ephemeral=True
                )
                return
            
            # Salva no banco
            await self.db.upsert_settings(
                self.guild.id,
                hierarchy_check_interval_hours=interval
            )
            
            await interaction.followup.send(
                f"✅ Intervalo de verificação configurado para **{interval} hora(s)**.\n"
                f"O bot verificará promoções automaticamente a cada {interval} hora(s).",
                ephemeral=True
            )
            
            # Atualiza embed (se a mensagem ainda existir)
            try:
                embed = await self.parent_view.build_embed()
                if interaction.message:
                    await interaction.message.edit(embed=embed, view=self.parent_view)
            except discord.NotFound:
                pass  # Mensagem foi deletada
            except Exception as e:
                LOGGER.warning("Erro ao atualizar mensagem após configurar intervalo: %s", e)
            
        except ValueError:
            await interaction.followup.send(
                "❌ Valor inválido. Use um número entre 1 e 168.",
                ephemeral=True
            )
        except Exception as e:
            LOGGER.error("Erro ao configurar intervalo: %s", e, exc_info=True)
            await interaction.followup.send(
                "❌ Erro ao configurar intervalo. Tente novamente.",
                ephemeral=True
            )
