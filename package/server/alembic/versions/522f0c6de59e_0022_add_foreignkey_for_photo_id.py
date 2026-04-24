"""add ForeignKey for photo_id

Revision ID: 522f0c6de59e
Revises: eb64391bffef
Create Date: 2026-04-24 23:36:21.173049

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '522f0c6de59e'
down_revision: Union[str, None] = 'eb64391bffef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. 修改字段类型，强制 USING 转换 varchar -> uuid
    op.alter_column(
        'flight_tickets', 'photo_id',
        existing_type=sa.VARCHAR(length=36),
        type_=sa.UUID(),
        existing_comment='关联照片ID',
        existing_nullable=True,
        postgresql_using='photo_id::uuid'  # 关键修复
    )
    op.alter_column(
        'train_tickets', 'photo_id',
        existing_type=sa.VARCHAR(length=36),
        type_=sa.UUID(),
        existing_comment='关联照片ID',
        existing_nullable=True,
        postgresql_using='photo_id::uuid'  # 关键修复
    )

    # 2. 清理无效的 photo_id（不存在于 photos 表的）
    op.execute("""
        UPDATE flight_tickets
        SET photo_id = NULL
        WHERE photo_id NOT IN (SELECT id FROM photos);
    """)
    op.execute("""
        UPDATE train_tickets
        SET photo_id = NULL
        WHERE photo_id NOT IN (SELECT id FROM photos);
    """)

    # 3. 创建外键
    op.create_foreign_key(
        'fk_flight_tickets_photo_id',
        'flight_tickets', 'photos',
        ['photo_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_train_tickets_photo_id',
        'train_tickets', 'photos',
        ['photo_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 降级：先删外键
    op.drop_constraint('fk_train_tickets_photo_id', 'train_tickets', type_='foreignkey')
    op.drop_constraint('fk_flight_tickets_photo_id', 'flight_tickets', type_='foreignkey')

    # 字段改回 varchar
    op.alter_column('train_tickets', 'photo_id',
               existing_type=sa.UUID(),
               type_=sa.VARCHAR(length=36),
               existing_comment='关联照片ID',
               existing_nullable=True)
    op.alter_column('flight_tickets', 'photo_id',
               existing_type=sa.UUID(),
               type_=sa.VARCHAR(length=36),
               existing_comment='关联照片ID',
               existing_nullable=True)
