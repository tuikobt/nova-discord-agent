"""Transaction-neutral repository primitives, always constrained to one owner."""

from dataclasses import fields
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import NotFoundError, StaleWriteError, ValidationError


class CoreRepository:
    model = None
    data_type = None
    extra_fields = frozenset()

    def __init__(self, session: AsyncSession, owner_id: str):
        self.session, self.owner_id = session, owner_id

    def query(self):
        return select(self.model).where(self.model.owner_id == self.owner_id)

    async def get(self, record_id: str, *, required: bool = True):
        row = await self.session.scalar(self.query().where(self.model.id == record_id))
        if row is None and required:
            raise NotFoundError()
        return row

    async def add(self, record_id: str, values: dict):
        self.validate_fields(values)
        row = self.model(id=record_id, owner_id=self.owner_id, **values)
        self.session.add(row)
        await self.session.flush()
        return row

    async def page(self, query, page: int, page_size: int):
        query = query.where(self.model.owner_id == self.owner_id)
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self.session.scalars(
            query.order_by(self.model.created_at, self.model.id)
            .offset(page * page_size)
            .limit(page_size)
        )
        return tuple(rows), total

    async def update(self, record_id: str, values: dict, expected: int | datetime):
        self.validate_fields(values, updating=True)
        model = self.model
        versioned = hasattr(model, "version")
        stamp = model.version if versioned else model.updated_at
        changes = {**values, **({"version": model.version + 1} if versioned else {})}
        row = await self.session.scalar(
            update(model)
            .where(model.owner_id == self.owner_id, model.id == record_id, stamp == expected)
            .values(**changes)
            .returning(model)
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise StaleWriteError()
        return row

    def validate_fields(self, values: dict, *, updating=False):
        allowed = {field.name for field in fields(self.data_type)} | self.extra_fields
        if updating:
            allowed.add("updated_at")
        if not values.keys() <= allowed:
            raise ValidationError("Không được đổi ID, owner hoặc trường không hỗ trợ.")
