"""Add additional fields to User model

Revision ID: dcf21ca21359
Revises: 
Create Date: 2024-07-20 13:23:29.326933

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dcf21ca21359'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('phone_number', sa.String(length=15), nullable=True))
        batch_op.add_column(sa.Column('age', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('gender', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('city', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('state', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('country', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('abha_id', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('abha_address', sa.String(length=100), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('abha_address')
        batch_op.drop_column('abha_id')
        batch_op.drop_column('country')
        batch_op.drop_column('state')
        batch_op.drop_column('city')
        batch_op.drop_column('gender')
        batch_op.drop_column('age')
        batch_op.drop_column('phone_number')

    # ### end Alembic commands ###
