"""Make user_id nullable in cards table

Revision ID: 717fcc15f31a
Revises: 51466b55b8e2
Create Date: 2024-12-18 16:08:42.871413

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '717fcc15f31a'
down_revision: Union[str, None] = '51466b55b8e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if cards_new table exists and drop it if it does
    conn = op.get_bind()
    if sa.inspect(conn).has_table('cards_new'):
        op.drop_table('cards_new')

    # Create new table with desired schema
    op.create_table(
        'cards_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('manaCost', sa.String(length=50), nullable=True),
        sa.Column('type', sa.String(length=100), nullable=True),
        sa.Column('color', sa.String(length=50), nullable=True),
        sa.Column('abilities', sa.Text(), nullable=True),
        sa.Column('flavorText', sa.Text(), nullable=True),
        sa.Column('rarity', sa.Enum('Common', 'Uncommon', 'Rare', 'Mythic Rare', name='rarity'), nullable=False),
        sa.Column('set_name', sa.String(), nullable=True),
        sa.Column('card_number', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('user_id', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cards_id'), 'cards_new', ['id'], unique=False)

    # Copy data from old table to new table
    conn = op.get_bind()
    conn.execute(
        sa.text(
            '''
            INSERT INTO cards_new (id, name, rarity, set_name, card_number, user_id)
            SELECT id, name, rarity, set_name, card_number, user_id
            FROM cards
            '''
        )
    )

    # Drop old table and rename new table
    op.drop_table('cards')
    op.rename_table('cards_new', 'cards')


def downgrade() -> None:
    # Check if cards_new table exists and drop it if it does
    conn = op.get_bind()
    if sa.inspect(conn).has_table('cards_new'):
        op.drop_table('cards_new')

    # Create new table with desired schema
    op.create_table(
        'cards_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('mana_cost', sa.String(length=50), nullable=True),
        sa.Column('card_type', sa.String(length=100), nullable=False),
        sa.Column('rules_text', sa.Text(), nullable=True),
        sa.Column('flavor_text', sa.Text(), nullable=True),
        sa.Column('toughness', sa.String(length=50), nullable=True),
        sa.Column('power', sa.String(length=50), nullable=True),
        sa.Column('artist', sa.String(length=100), nullable=True),
        sa.Column('rarity', sa.Enum('Common', 'Uncommon', 'Rare', 'Mythic Rare', name='rarity'), nullable=False),
        sa.Column('set_name', sa.String(), nullable=False),
        sa.Column('card_number', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cards_id'), 'cards_new', ['id'], unique=False)

    # Copy data from old table to new table
    conn = op.get_bind()
    conn.execute(
        sa.text(
            '''
            INSERT INTO cards_new (id, name, rarity, set_name, card_number, user_id, mana_cost, card_type, rules_text, flavor_text, toughness, power, artist)
            SELECT id, name, rarity, set_name, card_number, user_id, manaCost, type, abilities, flavorText, toughness, power, artist
            FROM cards
            '''
        )
    )

    # Drop old table and rename new table
    op.drop_table('cards')
    op.rename_table('cards_new', 'cards')
